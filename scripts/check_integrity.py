"""Integrity checker: does every quote on the site visibly contain the evidence it claims?

    uv run python scripts/check_integrity.py [--api URL] [--no-api] [--published DIR]
                                             [--out INTEGRITY_REPORT.md] [--json data/integrity/latest.json]

Reads every published report (local `data/published/`, plus the Databricks `reports` table when
configured), the derived trend facts (`data/derived/`, re-derived in memory with the current code so
the checks see what the API would serve), and the `/companies`, `/trends` and `/store/health`
responses when an API is running. Writes a readable INTEGRITY_REPORT.md and a machine-readable JSON,
and exits 1 while any violation that is not an accepted exception remains.

Every violation records: check id, ticker, analysis_id, change_id, sentence ids, a short evidence
excerpt, and a classification:
  * `stale`: the report predates a fix that is already in the pipeline (re-running the current code on
    the report's own data no longer produces the finding, or the stage that produces it is newer than
    the report);
  * `code`:  the current code still produces it (re-running it on the report's data reproduces the
    finding, or the finding is in display or serving code);
  * `data`:  cannot be decided from the report alone (it needs the filing).

Checks (ids used in the report):
  SNIP-TOPIC        a topic evidence quote, as displayed after trimming, contains the matched term
  SNIP-CHANGE       a displayed this-year snippet contains a changed span; a last-year snippet a removed one
  TOPIC-NEW         a topic's matched term lies inside an inserted span and is absent from last year's text
  TOPIC-MEANINGFUL  no topic occurrence on an essentially-unchanged risk factor or a company with none
  PAIR              every potential -> actual pair is an aligned (modified, counterpart) sentence pair
  CASE              no highlighted span that differs from its counterpart only by case/space/punctuation
  YEARS             fiscal-year labels agree with each filing's period of report and are consecutive
  COUNTS            the set of current reports is the same everywhere it is listed
  TITLES            short titles are not truncated fragments, not a bare company name, <= 10 words
  PREAMBLE          no change is the Item 1A intro, a Risk Factors Summary entry or a bare group header
  ENTITY            no newly-named entity that matches the stoplist or the noise patterns
  STALE             a report's versions and code fingerprint vs the current code, with the earliest stage
  HEATMAP           heatmap column keys are unique; no company row without any activity

Display trimming is checked with a Python port of the frontend rule (`web/src/lib/snippet.ts` when
it exists, else the older prefix rule in `web/src/lib/quote.ts`); `tests/test_integrity_checker.py`
keeps the two in step with shared vectors. Accepted exceptions live in
`data/integrity/exceptions.json` ([{"check", "ticker", "change_id"?, "reason"}]) and are reported but
do not fail the run. No company, filing or sentence is special-cased anywhere here.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import diff as diff_mod  # noqa: E402
from pipeline import embed as embed_mod  # noqa: E402
from pipeline import extract as extract_mod  # noqa: E402
from pipeline import highlights as hl_mod  # noqa: E402
from pipeline import match as match_mod  # noqa: E402
from pipeline import sec_fetch as fetch_mod  # noqa: E402
from pipeline import segment as seg_mod  # noqa: E402
from pipeline import signals as sig_mod  # noqa: E402
from pipeline.config import PIPELINE_VERSION  # noqa: E402
from pipeline.rubric import RUBRIC_VERSION  # noqa: E402
from pipeline.schema import Change, Comparison  # noqa: E402
from pipeline.score import code_fingerprint  # noqa: E402
from pipeline.trends import aggregate, derive  # noqa: E402
from pipeline.types import RiskBlock, SentenceRec  # noqa: E402

log = logging.getLogger("integrity")

CHECKS = [
    "SNIP-TOPIC",
    "SNIP-CHANGE",
    "TOPIC-NEW",
    "TOPIC-MEANINGFUL",
    "PAIR",
    "CASE",
    "YEARS",
    "COUNTS",
    "TITLES",
    "PREAMBLE",
    "ENTITY",
    "STALE",
    "HEATMAP",
]

# Stage a check's finding points at when it is stale (the earliest stage a re-run must start from).
STAGE_OF_CHECK = {
    "PREAMBLE": 2,
    "CASE": 5,
    "PAIR": 6,
    "ENTITY": 6,
    "TITLES": 8,
}
STAGE_NAMES = {
    0: "sec_fetch",
    1: "extract",
    2: "segment",
    3: "embed",
    4: "match",
    5: "diff",
    6: "signals",
    7: "llm",
    8: "score/publish",
}

MAX_TITLE_WORDS = 10
# Words a short title must not end on (it would be cut mid-clause).
DANGLING_LAST_WORDS = frozenset(
    "including include includes and or but of the a an to in on for with by as at from into "
    "which that our its their his her we they it is are was were be been being may might could "
    "would should can will shall if when while because whether than such other certain any all "
    "laws law inc corp co ltd plc llc".split()
)
ADMINISTRATION_RE = re.compile(
    r"^(?:the\s+)?[a-z]+(?:[\s-][a-z]+)?\s+administration$", re.IGNORECASE
)
TRAILING_STOPWORD_RE = re.compile(
    r"\s(?:in|on|at|of|for|to|by|with|from|and|or|the|a|an)$", re.IGNORECASE
)
SHORT_CODE_RE = re.compile(r"^[A-Za-z]{1,3}[:\-]?\d{1,3}$")

INTRO_RE = re.compile(
    r"^(?:the following (?:risk factors?|risks|discussion|is a (?:summary|discussion))"
    r"|you should (?:carefully )?(?:consider|read)"
    r"|investing in (?:our|the company['’]s) (?:securities|common stock|shares|ordinary shares)"
    r"|(?:an investment|investments?) in our"
    r"|the risks? (?:and uncertainties )?(?:described|discussed|set forth|listed|identified) below"
    r"|this (?:section|item|discussion) (?:contains|discusses|describes|includes|sets forth)"
    r"|in addition to the other information"
    r"|before (?:you )?(?:decide|invest|making an investment)"
    r"|our business,? (?:financial condition,? )?(?:and )?(?:results of operations|operating results)"
    r"[^.]{0,80}?\b(?:could|may|can) be (?:materially )?(?:and adversely )?(?:affected|impacted) by"
    r"(?: any of| one or more of)? the following)",
    re.IGNORECASE,
)
GROUP_HEADER_RE = re.compile(r"^risks? (?:related|relating) to\b", re.IGNORECASE)

TOKEN_RE = diff_mod.TOKEN_RE
PERIOD_DAYS_MIN, PERIOD_DAYS_MAX = 330, 400


# ---------------------------------------------------------------------------------------------
# Violations
# ---------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Violation:
    check: str
    ticker: str
    analysis_id: str | None
    change_id: str | None
    sentence_ids: list[str]
    evidence: str
    classification: str  # stale | code | data
    note: str = ""
    stage: int | None = None  # earliest stage a re-run must start from, when stale

    def key(self) -> tuple:
        return (
            self.check,
            self.ticker,
            self.change_id or "",
            tuple(self.sentence_ids),
            self.evidence[:80],
        )

    def to_json(self) -> dict:
        d = dataclasses.asdict(self)
        return d


def excerpt(text: str | None, limit: int = 220) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t if len(t) <= limit else t[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------------------------
# Display rules (ports of the frontend; see tests/test_integrity_checker.py for parity vectors)
# ---------------------------------------------------------------------------------------------

QUOTE_MAX_CHARS = 220
QUOTE_MARKS_VISIBLE_MAX = 600
TOPIC_EXAMPLE_MAX = 320
_MAGNITUDE = re.compile(r"^(?:million|billion|trillion|thousand|percent|per|basis|%|x\b)", re.I)
_CURRENCY_PREFIX = re.compile(r"^(?:\$|US\$|€|£|¥|USD|EUR)$", re.I)


def _inside_quote(text: str, cut: int) -> bool:
    head = text[:cut]
    return head.count("“") > head.count("”") or head.count('"') % 2 == 1


def _splits_number(prev: str, nxt: str) -> bool:
    if re.search(r"\d[\d,.]*%?$", prev) and _MAGNITUDE.match(nxt):
        return True
    if _CURRENCY_PREFIX.match(prev) and re.match(r"^\d", nxt):
        return True
    if re.match(r"^(?:approximately|about|over|under|nearly|up)$", prev, re.I) and re.match(
        r"^[$\d]", nxt
    ):
        return True
    return False


def _good_cut(text: str, i: int) -> bool:
    before, after = text[:i], text[i + 1 :]
    prev = re.split(r"\s+", before)[-1] if before else ""
    nxt = re.split(r"\s+", after)[0] if after else ""
    if not prev or not nxt:
        return False
    if _inside_quote(text, i):
        return False
    return not _splits_number(prev, nxt)


def trim_quote(text: str, mx: int = QUOTE_MAX_CHARS) -> tuple[str, bool]:
    """Port of web/src/lib/quote.ts `trimQuote`: an exact prefix at a good word boundary."""
    if len(text) <= mx:
        return text, False
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    within = [i for i in spaces if i <= mx and _good_cut(text, i)]
    clause = [i for i in within if i >= mx * 0.6 and re.search(r"[,;:—–]$", text[:i])]
    cut = clause[-1] if clause else (within[-1] if within else -1)
    if cut < mx * 0.5:
        later = next((i for i in spaces if mx < i <= mx + 120 and _good_cut(text, i)), None)
        if later is not None:
            cut = later
        elif cut < 0:
            cut = ([i for i in spaces if i <= mx] or [mx])[-1]
    if cut >= len(text) - 1:
        return text, False
    return re.sub(r"[\s,;:—–-]+$", "", text[:cut]), True


def last_marked_offset(spans: list[dict] | None) -> int:
    """Port of `lastMarkedOffset`: end offset of the last non-equal span."""
    pos = last = 0
    for sp in spans or []:
        pos += len(sp["text"])
        if sp["op"] != "equal":
            last = pos
    return last


def legacy_window(
    text: str, evidence: list[tuple[int, int]], mx: int, extend: bool
) -> tuple[int, int]:
    """What the pre-fix frontend shows: a prefix. `extend` mirrors Quote.tsx / ActualItem, which grow the
    budget to the last marked span (up to 600 chars); topic examples do not extend."""
    budget = mx
    if extend and evidence:
        marked = max(b for _, b in evidence)
        if marked > mx:
            budget = min(QUOTE_MARKS_VISIBLE_MAX, marked + 40)
    head, _ = trim_quote(text, budget)
    return 0, len(head)


def snippet_window(
    text: str, evidence: list[tuple[int, int]], mx: int = QUOTE_MAX_CHARS, context: int = 40
) -> tuple[int, int]:
    """The display rule after the fix (reference implementation; `web/src/lib/snippet.ts` mirrors it):
    a window of at most `mx` characters that always contains the earliest evidence span, with the
    span placed about a third of the way in, snapped to word boundaries (the window starts at a
    word start and ends right before a space). A span longer than the window is shown from its
    start. Visible ellipses on each trimmed side are the caller's job. Returns (start, end)."""
    n = len(text)
    if n <= mx:
        return 0, n
    a, b = min(evidence) if evidence else (0, 0)
    a = max(0, min(a, n))
    b = max(a, min(b, n))
    long_span = (b - a) >= mx
    if long_span:
        start = a
    else:
        start = max(0, a - max(context, (mx - (b - a)) // 3))
        start = min(start, max(0, n - mx))  # the window stays inside the text
        if start + mx < b:  # the span's end must fit
            start = b - mx
        start = min(start, a)  # never past the span start
    if start > 0:  # a word start at or before `start` (never loses the span)
        start = text.rfind(" ", 0, start) + 1
    end = min(n, start + mx)
    if not long_span and end < b:  # the backward snap pushed the span out: move the start forward
        end = b
        nxt = text.find(" ", max(0, end - mx))
        start = min(nxt + 1 if nxt != -1 else start, a)
    if end < n:  # snap the end back to a word end
        prev = text.rfind(" ", start, end)
        if prev != -1 and (long_span or prev >= b):
            end = prev
    return start, end


def display_profile() -> str:
    return "window" if (ROOT / "web" / "src" / "lib" / "snippet.ts").exists() else "legacy"


def displayed_window(
    text: str, evidence: list[tuple[int, int]], mx: int, profile: str, extend: bool = True
) -> tuple[int, int]:
    if profile == "window":
        return snippet_window(text, evidence, mx)
    return legacy_window(text, evidence, mx, extend)


def window_contains(window: tuple[int, int], span: tuple[int, int]) -> bool:
    w0, w1 = window
    a, b = span
    if a >= w0 and b <= w1:
        return True
    # a span longer than the window counts when most of the window is the span
    overlap = max(0, min(b, w1) - max(a, w0))
    return (b - a) > (w1 - w0) and overlap >= 0.8 * (w1 - w0)


# ---------------------------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------------------------


def marked_spans(sentence: dict, op: str) -> list[tuple[int, int]]:
    """Character ranges of `op` ("insert" | "delete") spans inside a sentence's own text, whitespace
    trimmed, adjacent runs merged; the whole sentence for added/removed sentences."""
    status = sentence.get("status")
    text = sentence.get("text") or ""
    if (op == "insert" and status == "added") or (op == "delete" and status == "removed"):
        return [(0, len(text))] if text else []
    out: list[tuple[int, int]] = []
    pos = 0
    for sp in sentence.get("diff_spans") or []:
        end = pos + len(sp["text"])
        if sp["op"] == op:
            seg = text[pos:end]
            a = pos + (len(seg) - len(seg.lstrip()))
            b = end - (len(seg) - len(seg.rstrip()))
            if b > a:
                if out and not text[out[-1][1] : a].strip():
                    out[-1] = (out[-1][0], b)
                else:
                    out.append((a, b))
        pos = end
    return out


def term_occurrences(term: str, text: str) -> list[tuple[int, int]]:
    try:
        rx = re.compile(derive.term_regex(term), re.IGNORECASE)
    except re.error:
        return []
    return [(m.start(), m.end()) for m in rx.finditer(text)]


def inside_any(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    return any(a <= span[0] and span[1] <= b for a, b in spans)


def norm_words(text: str) -> list[str]:
    return [t.casefold() for t in TOKEN_RE.findall(text) if t.strip() and t[0].isalnum()]


def expected_insert_words(old: str, new: str) -> Counter:
    """Inserted words of a word diff that ignores case, whitespace and punctuation (reference)."""
    a = norm_words(old)
    b = norm_words(new)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out: Counter = Counter()
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            out.update(b[j1:j2])
    return out


def stored_insert_words(sentence: dict) -> Counter:
    out: Counter = Counter()
    for sp in sentence.get("diff_spans") or []:
        if sp["op"] == "insert":
            out.update(norm_words(sp["text"]))
    return out


# ---------------------------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Report:
    path: Path
    comp: Comparison
    raw: dict

    @property
    def ticker(self) -> str:
        return self.comp.company.ticker

    @property
    def analysis_id(self) -> str:
        return self.comp.analysis_id


def load_reports(published_dir: Path) -> tuple[list[Report], list[str]]:
    reports: list[Report] = []
    problems: list[str] = []
    for p in sorted(published_dir.glob("*_*_*.json")):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            comp = Comparison.model_validate(raw)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{p.name}: {type(e).__name__}: {str(e)[:120]}")
            continue
        if comp.is_fixture:
            continue
        reports.append(Report(path=p, comp=comp, raw=raw))
    return reports, problems


def current_local(reports: list[Report]) -> dict[str, Report]:
    """One report per ticker: the newest fiscal-year pair by file name, the API's rule."""
    out: dict[str, Report] = {}
    for r in sorted(reports, key=lambda r: r.path.stem.split("_")[-1], reverse=True):
        out.setdefault(r.ticker, r)
    return out


def http_json(url: str, timeout: float = 5.0) -> Any:
    import urllib.request

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (local API)
        return json.loads(resp.read().decode("utf-8"))


def find_api(candidates: list[str]) -> tuple[str | None, dict | None]:
    for base in candidates:
        base = base.rstrip("/")
        try:
            health = http_json(f"{base}/store/health", timeout=3.0)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(health, dict):
            return base, health
    return None, None


def databricks_current() -> tuple[dict[str, str] | None, str]:
    """{ticker: analysis_id} of the store's current reports, or (None, reason)."""
    try:
        from pipeline.config import get_databricks_settings
        from pipeline.store import DatabricksStore, tables
    except Exception as e:  # noqa: BLE001
        return None, f"store modules unavailable: {type(e).__name__}"
    try:
        settings = get_databricks_settings()
    except Exception as e:  # noqa: BLE001
        return None, f"not configured: {type(e).__name__}"
    if not getattr(settings, "enabled", False):
        return None, "not configured (DATABRICKS_HOST / TOKEN / WAREHOUSE_ID unset)"
    try:
        store = DatabricksStore(settings)
        rows = store.execute(tables.list_current_sql(settings), {"current": True})
    except Exception as e:  # noqa: BLE001
        return None, f"unreachable: {type(e).__name__}"
    out: dict[str, str] = {}
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if t and t not in out:
            out[t] = str(r.get("analysis_id") or "")
    return out, f"{len(out)} current rows"


# ---------------------------------------------------------------------------------------------
# Re-running current code on a report's own data (for stale vs code classification)
# ---------------------------------------------------------------------------------------------


def block_from_index(comp: Comparison, block_id: str | None) -> RiskBlock | None:
    if not block_id:
        return None
    locs = [loc for loc in comp.sentence_index.values() if loc.block_id == block_id]
    if not locs:
        return None
    locs.sort(key=lambda loc: int(loc.id.rsplit(":", 1)[1]))
    heading = locs[0].text if locs[0].is_heading else ""
    body = " ".join(loc.text for loc in locs if not loc.is_heading)
    return RiskBlock(
        id=block_id,
        accession_number=locs[0].accession_number,
        index=0,
        heading=heading,
        body=body,
        section_group=None,
        sentences=[
            SentenceRec(
                id=loc.id,
                text=loc.text,
                char_start=loc.char_start,
                char_end=loc.char_end,
                is_heading=loc.is_heading,
            )
            for loc in locs
        ],
        char_start=min(loc.char_start for loc in locs),
        char_end=max(loc.char_end for loc in locs),
    )


def signal_context(comp: Comparison, c: Change) -> sig_mod.SignalContext:
    return sig_mod.SignalContext(
        old=block_from_index(comp, c.old_block_id),
        new=block_from_index(comp, c.new_block_id),
        sentences=list(c.sentences),
        similarity=c.similarity,
        added_word_count=c.stats.added_word_count,
        removed_word_count=c.stats.removed_word_count,
        old_word_count=c.stats.old_word_count,
        new_word_count=c.stats.new_word_count,
    )


class CurrentCode:
    """Lazily re-runs the current signal / trend code on a report's data, memoized per change."""

    def __init__(self) -> None:
        self._nlp = None
        self._p2a: dict[tuple[str, str], set[tuple[str, str]]] = {}
        self._ents: dict[tuple[str, str], set[str]] = {}
        self.facts: dict[str, Any] = {}
        self.errors: list[str] = []

    def nlp(self):  # noqa: ANN201
        if self._nlp is None:
            self._nlp = sig_mod.get_nlp()
        return self._nlp

    def p2a_pairs(self, r: Report, c: Change) -> set[tuple[str, str]] | None:
        key = (r.analysis_id, c.id)
        if key not in self._p2a:
            try:
                hits = sig_mod.hypothetical_to_actual(signal_context(r.comp, c))
                self._p2a[key] = {
                    (o, n) for h in hits for o in h.old_sentence_ids for n in h.new_sentence_ids
                }
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"hypothetical_to_actual {r.ticker}/{c.id}: {type(e).__name__}")
                return None
        return self._p2a[key]

    def entity_values(self, r: Report, c: Change) -> set[str] | None:
        key = (r.analysis_id, c.id)
        if key not in self._ents:
            try:
                hits = sig_mod.new_entities(signal_context(r.comp, c), self.nlp())
                self._ents[key] = {h.value for h in hits}
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"new_entities {r.ticker}/{c.id}: {type(e).__name__}")
                return None
        return self._ents[key]

    def derive(self, r: Report):  # noqa: ANN201
        if r.analysis_id not in self.facts:
            try:
                self.facts[r.analysis_id] = derive.derive_trend_facts(r.comp)
            except Exception as e:  # noqa: BLE001
                self.errors.append(f"derive {r.ticker}: {type(e).__name__}: {str(e)[:100]}")
                self.facts[r.analysis_id] = None
        return self.facts[r.analysis_id]


# ---------------------------------------------------------------------------------------------
# Checks over reports
# ---------------------------------------------------------------------------------------------


def report_is_current_code(r: Report) -> bool:
    return r.comp.code_fingerprint == code_fingerprint()


def check_pair(r: Report, cur: CurrentCode) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    for c in comp.changes:
        by_id = {s.id: s for s in c.sentences}

        def aligned(old_id: str, new_id: str, by_id: dict = by_id) -> bool:
            n, o = by_id.get(new_id), by_id.get(old_id)
            return bool(n and o and n.status == "modified" and n.counterpart_id == old_id)

        pairs: list[tuple[str, str, str, str]] = []  # (old, new, source, detail)
        for h in c.signals.hypothetical_to_actual:
            for o in h.old_sentence_ids:
                for n in h.new_sentence_ids:
                    pairs.append((o, n, "signal", h.value))
        for h in comp.highlights:
            if (
                h.change_id == c.id
                and h.kind == "potential_became_actual"
                and h.old_sentence_id
                and h.new_sentence_id
            ):
                pairs.append((h.old_sentence_id, h.new_sentence_id, "highlight", h.detail or ""))
        for o, n, source, detail in pairs:
            if aligned(o, n):
                continue
            current = cur.p2a_pairs(r, c)
            still = current is not None and (o, n) in current
            o_txt = comp.sentence_index[o].text if o in comp.sentence_index else "?"
            n_txt = comp.sentence_index[n].text if n in comp.sentence_index else "?"
            out.append(
                Violation(
                    check="PAIR",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=c.id,
                    sentence_ids=[o, n],
                    evidence=f"{source} {detail!r}: last year {excerpt(o_txt, 90)!r} / this year {excerpt(n_txt, 90)!r} are not an aligned pair",
                    classification="code" if still else "stale",
                    note=(
                        "the current signal code still pairs these two sentences"
                        if still
                        else "the current signal code does not produce this pair"
                    ),
                    stage=None if still else STAGE_OF_CHECK["PAIR"],
                )
            )
    return out


def check_case(r: Report) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    for c in comp.changes:
        by_id = {s.id: s for s in c.sentences}
        for s in c.sentences:
            if (
                s.side != "new"
                or s.status != "modified"
                or not s.counterpart_id
                or not s.diff_spans
            ):
                continue
            o = by_id.get(s.counterpart_id)
            if o is None:
                continue
            sd = s.model_dump()
            stored = stored_insert_words(sd)
            expected = expected_insert_words(o.text, s.text)
            extra = stored - expected
            if not extra:
                continue
            # does the current diff code still mark these words?
            try:
                _, cur_new = diff_mod.word_spans(o.text, s.text)
                cur_words = Counter()
                for sp in cur_new:
                    if sp.op == "insert":
                        cur_words.update(norm_words(sp.text))
                still = bool(cur_words - expected)
            except Exception:  # noqa: BLE001
                still = True
            words = ", ".join(sorted(extra.elements()))[:120]
            out.append(
                Violation(
                    check="CASE",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=c.id,
                    sentence_ids=[o.id, s.id],
                    evidence=f"highlighted though only case/space/punctuation differ: {words}",
                    classification="code" if still else "stale",
                    note="current diff reproduces it"
                    if still
                    else "current diff no longer marks these words",
                    stage=None if still else STAGE_OF_CHECK["CASE"],
                )
            )
    return out


def check_titles(r: Report) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    name = comp.company.name
    name_keys = {_name_key(name), _name_key(_strip_suffix(name))}
    fallback = getattr(hl_mod, "short_title_from_heading", None) or hl_mod.truncate_heading
    for c in comp.changes:
        problems = title_problems(c.short_title, name_keys)
        if not problems:
            continue
        try:
            current = fallback(c.title)
        except Exception:  # noqa: BLE001
            current = c.short_title
        is_fallback = c.short_title == hl_mod.truncate_heading(c.title)
        current_ok = not title_problems(current, name_keys)
        stale = is_fallback and current != c.short_title and current_ok
        out.append(
            Violation(
                check="TITLES",
                ticker=r.ticker,
                analysis_id=r.analysis_id,
                change_id=c.id,
                sentence_ids=[],
                evidence=f"{c.short_title!r}: {'; '.join(problems)} (heading: {excerpt(c.title, 100)!r})",
                classification="stale" if stale else "code",
                note=(
                    f"the current fallback gives {current!r}"
                    if stale
                    else (
                        "the stored title is not the deterministic fallback, so the validator accepted it"
                        if not is_fallback
                        else f"the current fallback still gives {current!r}"
                    )
                ),
                stage=STAGE_OF_CHECK["TITLES"] if stale else None,
            )
        )
    return out


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _strip_suffix(name: str) -> str:
    return re.sub(
        r"[\s,.]*\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|holdings?|group|com|sa|nv|ag|se)\b[.,\s]*$",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()


def title_problems(title: str, name_keys: set[str]) -> list[str]:
    t = " ".join((title or "").split())
    problems: list[str] = []
    if not t:
        return ["empty"]
    if t.endswith("…") or t.endswith("..."):
        problems.append("ends with an ellipsis (truncated heading)")
    words = re.findall(r"[^\s]+", t.rstrip("…."))
    if len(words) > MAX_TITLE_WORDS:
        problems.append(f"{len(words)} words (max {MAX_TITLE_WORDS})")
    last = re.sub(r"[^\w'’]+$", "", words[-1]).casefold() if words else ""
    if last in DANGLING_LAST_WORDS:
        problems.append(f"ends mid-clause on {last!r}")
    if t.rstrip("…").endswith((",", ";", ":", "(", "-", "–", "—")):
        problems.append("ends on punctuation")
    if _name_key(t) in name_keys or _name_key(_strip_suffix(t)) in name_keys:
        problems.append("is just the company name")
    return problems


def check_preamble(r: Report) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    stale_capable = report_is_current_code(r) is False and _version_tuple(
        seg_mod.STAGE_VERSION
    ) >= (0, 2, 0)
    # duplicate headings per filing side: a summary bullet repeats a real heading
    titles_by_side: dict[str, Counter] = {"old": Counter(), "new": Counter()}
    for c in comp.changes:
        if c.old_title:
            titles_by_side["old"][_title_key(c.old_title)] += 1
        if c.new_title:
            titles_by_side["new"][_title_key(c.new_title)] += 1
    for c in comp.changes:
        text = c.new_text or c.old_text or ""
        first = text.split("\n", 1)[-1].strip()[:200] if "\n" in text else ""
        reasons: list[str] = []
        if INTRO_RE.search(c.title.strip()):
            reasons.append("heading is the Item 1A introduction")
        elif first and INTRO_RE.search(first) and len(c.sentences) <= 6:
            reasons.append("first sentence is the Item 1A introduction")
        if seg_mod.SUMMARY_RE.match(c.title.strip().casefold()):
            reasons.append("heading is a Risk Factors Summary heading")
        n_body = sum(1 for s in c.sentences if not s.id.endswith(":0"))
        if GROUP_HEADER_RE.match(c.title.strip()) and n_body <= 2:
            reasons.append("bare group header with no body")
        for side, title in (("old", c.old_title), ("new", c.new_title)):
            if title and titles_by_side[side][_title_key(title)] > 1 and n_body <= 2:
                reasons.append(f"duplicate heading on the {side} side with no body (summary entry)")
        if not reasons:
            continue
        out.append(
            Violation(
                check="PREAMBLE",
                ticker=r.ticker,
                analysis_id=r.analysis_id,
                change_id=c.id,
                sentence_ids=[f"{c.new_block_id or c.old_block_id}:0"],
                evidence=f"{excerpt(c.title, 120)!r}: {'; '.join(sorted(set(reasons)))}",
                classification="stale" if stale_capable else "code",
                note=(
                    f"segment {seg_mod.STAGE_VERSION} skips intro and summary units; confirmed only by a re-run from stage 2"
                    if stale_capable
                    else "the report was produced by the current code"
                ),
                stage=STAGE_OF_CHECK["PREAMBLE"] if stale_capable else None,
            )
        )
    return out


def _title_key(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.casefold()).strip()


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def entity_problems(value: str, comp: Comparison) -> list[str]:
    problems: list[str] = []
    cleaned = sig_mod.clean_entity(value)
    if cleaned is None:
        problems.append("dropped by the entity post-filter (code or too short)")
    elif cleaned != value.strip():
        problems.append(f"post-filter changes it to {cleaned!r} (trailing/leading stopword)")
    if TRAILING_STOPWORD_RE.search(value.strip()):
        problems.append("trailing preposition")
    if SHORT_CODE_RE.match(value.strip()):
        problems.append("short code")
    if ADMINISTRATION_RE.match(value.strip()):
        problems.append("bare government administration")
    try:
        key, _display = derive.normalize_entity(value)
        ident, toks = derive.own_name_tokens(comp.company.name, comp.company.ticker)
        if not key or derive.is_stop_entity(key, ident, toks):
            problems.append("on the trends entity stoplist")
    except Exception:  # noqa: BLE001
        pass
    return problems


def check_entity(r: Report, cur: CurrentCode) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    for c in comp.changes:
        for h in c.signals.new_entities:
            problems = entity_problems(h.value, comp)
            if not problems:
                continue
            current = cur.entity_values(r, c)
            still = current is not None and h.value in current
            out.append(
                Violation(
                    check="ENTITY",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=c.id,
                    sentence_ids=list(h.new_sentence_ids),
                    evidence=f"{h.value!r}: {'; '.join(problems)}",
                    classification="code" if still else "stale",
                    note="current entity code still emits it"
                    if still
                    else "current entity code no longer emits it",
                    stage=None if still else STAGE_OF_CHECK["ENTITY"],
                )
            )
    return out


def check_years(r: Report) -> list[Violation]:
    comp = r.comp
    old, new = comp.old_filing, comp.new_filing
    out: list[Violation] = []

    def period(f) -> date | None:  # noqa: ANN001
        for attr in ("period_of_report", "report_date"):
            v = getattr(f, attr, None)
            if v:
                try:
                    return date.fromisoformat(str(v)[:10])
                except ValueError:
                    return None
        return None

    po, pn = period(old), period(new)
    reasons: list[str] = []
    classification = "data"
    if new.fiscal_year - old.fiscal_year != 1:
        reasons.append(f"labels FY{old.fiscal_year} and FY{new.fiscal_year} are not consecutive")
    if po and pn:
        days = (pn - po).days
        if not (PERIOD_DAYS_MIN <= days <= PERIOD_DAYS_MAX):
            reasons.append(
                f"periods of report {po} and {pn} are {days} days apart (a filing was skipped or mis-selected)"
            )
            classification = "data"
        off_old, off_new = old.fiscal_year - po.year, new.fiscal_year - pn.year
        if off_old != off_new:
            reasons.append(
                f"label offsets differ: FY{old.fiscal_year} for period {po} vs FY{new.fiscal_year} for period {pn} (label derivation)"
            )
            classification = "code"
        for f, p in ((old, po), (new, pn)):
            if f.fiscal_year - p.year not in (0, -1):
                reasons.append(
                    f"FY{f.fiscal_year} is not the year of its period {p} or the year before"
                )
                classification = "code"
    else:
        reasons.append("no period of report on the filing records") if reasons else None
    if not reasons:
        return out
    out.append(
        Violation(
            check="YEARS",
            ticker=r.ticker,
            analysis_id=r.analysis_id,
            change_id=None,
            sentence_ids=[],
            evidence="; ".join(reasons),
            classification=classification,
            note=f"fiscal_year_source old={getattr(old, 'fiscal_year_source', '?')} new={getattr(new, 'fiscal_year_source', '?')}",
        )
    )
    return out


def check_stale(r: Report) -> tuple[list[Violation], dict]:
    comp = r.comp
    current_fp = code_fingerprint()
    stage_versions = {
        0: fetch_mod.STAGE_VERSION,
        1: extract_mod.STAGE_VERSION,
        2: seg_mod.STAGE_VERSION,
        3: embed_mod.STAGE_VERSION,
        4: match_mod.STAGE_VERSION,
        5: diff_mod.STAGE_VERSION,
        6: sig_mod.STAGE_VERSION,
    }
    recorded = (r.raw.get("stage_versions") or None) if isinstance(r.raw, dict) else None
    reasons: list[str] = []
    earliest: int | None = None
    if comp.pipeline_version != PIPELINE_VERSION:
        reasons.append(f"pipeline {comp.pipeline_version} != {PIPELINE_VERSION}")
        earliest = 0
    if comp.rubric_version != RUBRIC_VERSION:
        reasons.append(f"rubric {comp.rubric_version} != {RUBRIC_VERSION}")
        earliest = 7 if earliest is None else min(earliest, 7)
    if recorded:
        for idx, cur_v in stage_versions.items():
            name = STAGE_NAMES[idx]
            rv = recorded.get(name) or recorded.get(str(idx))
            if rv is not None and rv != cur_v:
                reasons.append(f"stage {idx} {name} {rv} != {cur_v}")
                earliest = idx if earliest is None else min(earliest, idx)
    if comp.code_fingerprint != current_fp:
        reasons.append(
            f"code fingerprint {comp.code_fingerprint[:12]} != current {current_fp[:12]}"
        )
    info = {
        "ticker": r.ticker,
        "analysis_id": r.analysis_id,
        "pipeline_version": comp.pipeline_version,
        "rubric_version": comp.rubric_version,
        "code_fingerprint": comp.code_fingerprint,
        "current_code": comp.code_fingerprint == current_fp,
        "stage_versions_recorded": bool(recorded),
    }
    if not reasons:
        return [], info
    return (
        [
            Violation(
                check="STALE",
                ticker=r.ticker,
                analysis_id=r.analysis_id,
                change_id=None,
                sentence_ids=[],
                evidence="; ".join(reasons),
                classification="stale",
                note=(
                    "stage versions are not recorded in this report; the earliest stage is inferred from the other findings"
                    if not recorded
                    else "stage versions recorded in the report"
                ),
                stage=earliest,
            )
        ],
        info,
    )


# ---------------------------------------------------------------------------------------------
# Checks over trend facts and the served /trends body
# ---------------------------------------------------------------------------------------------


def old_side_text(c: Change) -> str:
    return " ".join(s.text for s in c.sentences if s.side == "old") or (c.old_text or "")


def check_topics(r: Report, facts, served_examples: list[dict], profile: str) -> list[Violation]:  # noqa: ANN001
    """TOPIC-NEW and TOPIC-MEANINGFUL over every mention of the current derivation; SNIP-TOPIC over the
    examples the page shows (served body when available, else the local aggregate)."""
    out: list[Violation] = []
    if facts is None:
        return out
    comp = r.comp
    changes = {c.id: c for c in comp.changes}
    meaningful = sum(v for k, v in facts.by_change_type.items() if k != "largely_unchanged")
    for m in facts.topic_mentions:
        c = changes.get(m.change_id)
        if c is None:
            continue
        spans = [tuple(x) for x in m.added_spans]
        old_text = old_side_text(c)
        for term in m.matched_terms:
            occ = term_occurrences(term, m.text)
            inside = [o for o in occ if inside_any(o, spans)]
            in_old = bool(term_occurrences(term, old_text))
            if occ and inside and not in_old:
                continue
            why = []
            if not occ:
                why.append("term not found in the sentence")
            elif not inside:
                why.append(
                    "term is outside the inserted spans (it was already in the sentence last year)"
                )
            if in_old:
                why.append("term appears in last year's text of this risk factor")
            out.append(
                Violation(
                    check="TOPIC-NEW",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=m.change_id,
                    sentence_ids=[m.sentence_id],
                    evidence=f"{m.topic!r} via {term!r} ({m.source}): {'; '.join(why)}. {excerpt(m.text, 140)!r}",
                    classification="code",
                    note="derived with the current code",
                )
            )
        if c.change_type == "largely_unchanged" or meaningful == 0:
            out.append(
                Violation(
                    check="TOPIC-MEANINGFUL",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=m.change_id,
                    sentence_ids=[m.sentence_id],
                    evidence=(
                        f"{m.topic!r} counted on an essentially unchanged risk factor"
                        + (" of a company with no meaningful changes" if meaningful == 0 else "")
                        + f": {excerpt(m.text, 120)!r}"
                    ),
                    classification="code",
                    note="derived with the current code",
                )
            )
    # SNIP-TOPIC on the displayed examples
    for ex in served_examples:
        if ex.get("ticker") != r.ticker:
            continue
        text = ex.get("text") or ""
        terms = ex.get("matched_terms") or []
        spans = [tuple(x) for x in (ex.get("added_spans") or [])]
        anchors: list[tuple[int, int]] = []
        for term in terms:
            for o in term_occurrences(term, text):
                if inside_any(o, spans) or not spans:
                    anchors.append(o)
        anchors.sort()
        window = displayed_window(text, anchors or spans, TOPIC_EXAMPLE_MAX, profile, extend=False)
        shown = text[window[0] : window[1]]
        missing = [t for t in terms if not term_occurrences(t, shown)]
        if missing:
            out.append(
                Violation(
                    check="SNIP-TOPIC",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=ex.get("change_id"),
                    sentence_ids=[ex.get("sentence_id") or ""],
                    evidence=f"topic {ex.get('topic')!r}: displayed {excerpt(shown, 100)!r} lacks {missing}",
                    classification="code",
                    note=f"display rule: {profile}",
                )
            )
    return out


def check_snip_change(r: Report, served_p2a: list[dict], profile: str) -> list[Violation]:
    out: list[Violation] = []
    comp = r.comp
    sentences: dict[str, dict] = {}
    for c in comp.changes:
        for s in c.sentences:
            sentences[s.id] = s.model_dump()

    def check_side(side: str, sid: str | None, change_id: str, label: str) -> None:
        if not sid or sid not in sentences:
            return
        s = sentences[sid]
        op = "insert" if side == "new" else "delete"
        spans = marked_spans(s, op)
        if not spans:
            return  # nothing marked on this side (unchanged or no removed words): nothing to show
        window = displayed_window(s["text"], spans, QUOTE_MAX_CHARS, profile, extend=True)
        if any(window_contains(window, sp) for sp in spans):
            return
        shown = s["text"][window[0] : window[1]]
        first = s["text"][spans[0][0] : spans[0][1]]
        out.append(
            Violation(
                check="SNIP-CHANGE",
                ticker=r.ticker,
                analysis_id=r.analysis_id,
                change_id=change_id,
                sentence_ids=[sid],
                evidence=f"{label} {side} side shows {excerpt(shown, 90)!r} but the changed words are {excerpt(first, 60)!r}",
                classification="code",
                note=f"display rule: {profile}",
            )
        )

    for h in comp.highlights:
        check_side("old", h.old_sentence_id, h.change_id, f"highlight {h.kind}")
        check_side("new", h.new_sentence_id, h.change_id, f"highlight {h.kind}")
    for row in served_p2a:
        if row.get("ticker") != r.ticker:
            continue
        for side, key_txt, key_sp in (
            ("old", "old_text", "old_spans"),
            ("new", "new_text", "new_spans"),
        ):
            text = row.get(key_txt) or ""
            spans = [tuple(x) for x in (row.get(key_sp) or [])]
            if not text or not spans:
                continue
            window = displayed_window(text, spans, QUOTE_MAX_CHARS, profile, extend=True)
            if any(window_contains(window, sp) for sp in spans):
                continue
            out.append(
                Violation(
                    check="SNIP-CHANGE",
                    ticker=r.ticker,
                    analysis_id=r.analysis_id,
                    change_id=row.get("change_id"),
                    sentence_ids=[row.get(f"{side}_sentence_id") or ""],
                    evidence=f"Trends potential->actual {side} side shows {excerpt(text[window[0] : window[1]], 90)!r} but the changed words are {excerpt(text[spans[0][0] : spans[0][1]], 60)!r}",
                    classification="code",
                    note=f"display rule: {profile}",
                )
            )
    return out


def heatmap_columns(activity: list[dict], max_columns: int = 10) -> list[str]:
    """Port of web/src/lib/trends.ts buildHeatmap column selection."""
    by_cat: dict[str, int] = defaultdict(int)
    for a in activity:
        by_cat[a["category"]] += (
            int(a.get("added_sentences", 0))
            + int(a.get("removed_sentences", 0))
            + int(a.get("modified_sentences", 0))
        )
    ranked = [c for c, _ in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))]
    keep = ranked[:max_columns]
    other_key = "other"
    try:
        src = (ROOT / "web" / "src" / "lib" / "trends.ts").read_text(encoding="utf-8")
        m = re.search(r'OTHER_CATEGORY\s*=\s*"([^"]+)"', src)
        if m:
            other_key = m.group(1)
        m = re.search(r"MAX_HEATMAP_COLUMNS\s*=\s*(\d+)", src)
        if m:
            keep = ranked[: int(m.group(1))]
            return keep + ([other_key] if len(ranked) > int(m.group(1)) else [])
    except OSError:
        pass
    return keep + ([other_key] if len(ranked) > max_columns else [])


def check_heatmap(body: dict) -> list[Violation]:
    out: list[Violation] = []
    activity = body.get("category_activity") or []
    columns = heatmap_columns(activity)
    dupes = [c for c, n in Counter(columns).items() if n > 1]
    if dupes:
        out.append(
            Violation(
                check="HEATMAP",
                ticker="*",
                analysis_id=None,
                change_id=None,
                sentence_ids=[],
                evidence=f"duplicate heatmap column keys {dupes}: the catch-all column reuses a real category key (columns {columns})",
                classification="code",
                note="web/src/lib/trends.ts buildHeatmap",
            )
        )
    active = {
        a["ticker"]
        for a in activity
        if (
            a.get("added_sentences", 0)
            + a.get("removed_sentences", 0)
            + a.get("modified_sentences", 0)
        )
        > 0
    }
    for c in body.get("companies") or []:
        if c.get("ticker") not in active:
            out.append(
                Violation(
                    check="HEATMAP",
                    ticker=c.get("ticker") or "?",
                    analysis_id=c.get("analysis_id"),
                    change_id=None,
                    sentence_ids=[],
                    evidence="company row without any category activity would render as an all-empty heatmap row",
                    classification="code",
                    note="emit the row with an explicit 'no changed sentences' cell or leave it out",
                )
            )
    return out


def check_counts(
    local: dict[str, Report],
    derived_available: dict[str, bool],
    api_companies: list[dict] | None,
    served_body: dict | None,
    store: dict[str, str] | None,
    api_base: str | None,
) -> list[Violation]:
    out: list[Violation] = []
    sets: dict[str, dict[str, str]] = {
        "local published files": {t: r.analysis_id for t, r in local.items()}
    }
    sets["derived trend facts"] = {
        t: local[t].analysis_id for t, ok in derived_available.items() if ok
    }
    if api_companies is not None:
        sets["/companies"] = {
            str(c.get("ticker")): str(c.get("analysis_id") or "") for c in api_companies
        }
    if served_body is not None and api_base:
        sets["/trends companies"] = {
            str(c.get("ticker")): str(c.get("analysis_id") or "")
            for c in served_body.get("companies") or []
        }
    if store is not None:
        sets["Databricks reports (current)"] = store
    universe: set[str] = set()
    for s in sets.values():
        universe |= set(s)
    for t in sorted(universe):
        present = {name: s.get(t) for name, s in sets.items() if t in s}
        missing = [name for name in sets if t not in sets[name]]
        ids = {v for v in present.values() if v}
        if missing or len(ids) > 1:
            out.append(
                Violation(
                    check="COUNTS",
                    ticker=t,
                    analysis_id=next(iter(ids), None),
                    change_id=None,
                    sentence_ids=[],
                    evidence=(
                        (f"missing from {missing}" if missing else "")
                        + ("; " if missing and len(ids) > 1 else "")
                        + (
                            f"different analysis ids across sources: { {k: (v or '')[:12] for k, v in present.items()} }"
                            if len(ids) > 1
                            else ""
                        )
                    ),
                    classification="code",
                    note="the Trends company set must come from the same source as /companies; a report without derived facts is dropped from Trends",
                )
            )
    return out


# ---------------------------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------------------------


def load_exceptions(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict) and x.get("check") and x.get("reason")]
    except (OSError, ValueError):
        return []


def is_accepted(v: Violation, exceptions: list[dict]) -> str | None:
    for ex in exceptions:
        if ex.get("check") != v.check:
            continue
        if ex.get("ticker") not in (None, "*", v.ticker):
            continue
        if ex.get("change_id") and ex.get("change_id") != v.change_id:
            continue
        if ex.get("evidence_contains") and ex["evidence_contains"] not in v.evidence:
            continue
        return str(ex["reason"])
    return None


def write_markdown(path: Path, result: dict) -> None:
    lines: list[str] = []
    lines.append("# Integrity report")
    lines.append("")
    lines.append(
        f"Generated {result['generated_at']} by `scripts/check_integrity.py`. Exit code {result['exit_code']}."
    )
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for k, v in result["sources"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Current code")
    lines.append("")
    cv = result["current_versions"]
    lines.append(
        f"- pipeline {cv['pipeline_version']}, rubric {cv['rubric_version']}, code fingerprint `{cv['code_fingerprint'][:12]}`, "
        + ", ".join(f"stage {k} {STAGE_NAMES[int(k)]} {v}" for k, v in cv["stage_versions"].items())
    )
    lines.append(f"- display rule checked: `{result['display_profile']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Check | Violations | stale data | code | data | accepted |")
    lines.append("|-------|-----------:|-----------:|-----:|-----:|---------:|")
    for check in CHECKS:
        c = result["counts"][check]
        lines.append(
            f"| {check} | {c['total']} | {c['stale']} | {c['code']} | {c['data']} | {c['accepted']} |"
        )
    tot = result["counts"]["TOTAL"]
    lines.append(
        f"| **Total** | **{tot['total']}** | {tot['stale']} | {tot['code']} | {tot['data']} | {tot['accepted']} |"
    )
    lines.append("")
    lines.append("## Reports")
    lines.append("")
    lines.append(
        "| Ticker | analysis_id | pipeline | rubric | current code | earliest stage to re-run |"
    )
    lines.append(
        "|--------|-------------|----------|--------|--------------|--------------------------|"
    )
    for rep in result["reports"]:
        st = rep.get("earliest_stage")
        st_s = (
            f"{st} ({STAGE_NAMES.get(st, '?')})"
            if st is not None
            else ("—" if rep["current_code"] else "unknown (re-run from stage 2 to be safe)")
        )
        lines.append(
            f"| {rep['ticker']} | `{rep['analysis_id'][:12]}` | {rep['pipeline_version']} | {rep['rubric_version']} | {'yes' if rep['current_code'] else 'no'} | {st_s} |"
        )
    lines.append("")
    lines.append("## Violations")
    lines.append("")
    by_check: dict[str, list[dict]] = defaultdict(list)
    for v in result["violations"]:
        by_check[v["check"]].append(v)
    for check in CHECKS:
        items = by_check.get(check) or []
        if not items:
            continue
        lines.append(f"### {check} ({len(items)})")
        lines.append("")
        for v in items:
            sids = ", ".join(f"`{s}`" for s in v["sentence_ids"] if s) or "—"
            cid = f"`{v['change_id']}`" if v["change_id"] else "—"
            stage = f", re-run from stage {v['stage']}" if v.get("stage") is not None else ""
            lines.append(f"- **{v['ticker']}** change {cid}, sentences {sids}: {v['evidence']}")
            lines.append(f"  - *{v['classification']}*{stage}: {v['note']}")
        lines.append("")
    if result["accepted"]:
        lines.append("## Accepted exceptions")
        lines.append("")
        for v in result["accepted"]:
            lines.append(f"- **{v['check']} {v['ticker']}** {v['evidence']}")
            lines.append(f"  - accepted because: {v['accepted_reason']}")
        lines.append("")
    if result["errors"]:
        lines.append("## Checker notes")
        lines.append("")
        for e in result["errors"]:
            lines.append(f"- {e}")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------


def run(args: argparse.Namespace) -> dict:
    t0 = time.monotonic()
    published_dir = Path(args.published)
    derived_dir = derive.derived_dir_for(Path(args.data_dir))
    profile = display_profile()
    sources: dict[str, str] = {}
    errors: list[str] = []

    reports, problems = load_reports(published_dir)
    errors.extend(problems)
    local = current_local(reports)
    sources["local published"] = (
        f"{len(reports)} files, {len(local)} current ({', '.join(sorted(local))}) in {published_dir}"
    )

    api_base, health = (None, None)
    if not args.no_api:
        candidates = [
            a
            for a in [
                args.api,
                os.environ.get("RISKDIFF_API_URL"),
                "http://127.0.0.1:8000",
                "http://127.0.0.1:8001",
            ]
            if a
        ]
        api_base, health = find_api(candidates)
    api_companies = served_body = None
    if api_base:
        sources["API"] = f"{api_base} (store health {health})"
        try:
            api_companies = (http_json(f"{api_base}/companies", timeout=15.0) or {}).get(
                "companies"
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"/companies failed: {type(e).__name__}")
        try:
            body = http_json(f"{api_base}/trends", timeout=30.0)
            if isinstance(body, dict) and body.get("companies") is not None:
                served_body = body
                sources["/trends"] = (
                    f"status {body.get('status')}, source {body.get('source')}, {len(body.get('companies') or [])} companies"
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"/trends failed: {type(e).__name__}")
    else:
        sources["API"] = "not running (checked --api, RISKDIFF_API_URL, :8000, :8001)"

    store, store_note = databricks_current()
    sources["Databricks"] = store_note

    cur = CurrentCode()
    facts_by_ticker: dict[str, Any] = {}
    derived_available: dict[str, bool] = {}
    for t, r in local.items():
        on_disk = derive.load_facts(derived_dir, r.analysis_id)
        derived_available[t] = on_disk is not None
        facts_by_ticker[t] = cur.derive(r)
    sources["derived trend facts"] = (
        f"{sum(derived_available.values())} of {len(local)} current reports have a current file in {derived_dir}; all re-derived in memory with the current code"
    )
    if served_body is None:
        try:
            served_body = aggregate.body_from_facts(
                [f for f in facts_by_ticker.values() if f is not None]
            )
            sources["/trends"] = "API not running: local aggregate of the current derivation"
        except Exception as e:  # noqa: BLE001
            errors.append(f"local aggregate failed: {type(e).__name__}")
    served_examples = [
        dict(ex, topic=t.get("topic"))
        for t in (served_body or {}).get("topics") or []
        for ex in t.get("examples") or []
    ]
    served_p2a = list((served_body or {}).get("potential_to_actual") or [])

    violations: list[Violation] = []
    report_infos: list[dict] = []
    for t, r in sorted(local.items()):
        stale_v, info = check_stale(r)
        per_report: list[Violation] = []
        per_report += check_pair(r, cur)
        per_report += check_case(r)
        per_report += check_titles(r)
        per_report += check_preamble(r)
        per_report += check_entity(r, cur)
        per_report += check_years(r)
        per_report += check_topics(r, facts_by_ticker.get(t), served_examples, profile)
        per_report += check_snip_change(r, served_p2a, profile)
        stages = [v.stage for v in per_report if v.stage is not None]
        if stale_v:
            inferred = min(stages) if stages else None
            if stale_v[0].stage is None or (inferred is not None and inferred < stale_v[0].stage):
                stale_v[0].stage = inferred if inferred is not None else stale_v[0].stage
            info["earliest_stage"] = stale_v[0].stage
        else:
            info["earliest_stage"] = None
        report_infos.append(info)
        violations += stale_v + per_report
    if served_body is not None:
        violations += check_heatmap(served_body)
    violations += check_counts(
        local, derived_available, api_companies, served_body, store, api_base
    )
    errors.extend(sorted(set(cur.errors)))

    # dedupe, accept exceptions
    seen: set[tuple] = set()
    unique: list[Violation] = []
    for v in violations:
        if v.key() in seen:
            continue
        seen.add(v.key())
        unique.append(v)
    exceptions = load_exceptions(Path(args.exceptions))
    accepted: list[dict] = []
    remaining: list[dict] = []
    for v in unique:
        reason = is_accepted(v, exceptions)
        d = v.to_json()
        if reason:
            d["accepted_reason"] = reason
            accepted.append(d)
        else:
            remaining.append(d)
    counts: dict[str, dict[str, int]] = {}
    for check in CHECKS + ["TOTAL"]:
        rem = [v for v in remaining if check == "TOTAL" or v["check"] == check]
        acc = [v for v in accepted if check == "TOTAL" or v["check"] == check]
        counts[check] = {
            "total": len(rem),
            "stale": sum(1 for v in rem if v["classification"] == "stale"),
            "code": sum(1 for v in rem if v["classification"] == "code"),
            "data": sum(1 for v in rem if v["classification"] == "data"),
            "accepted": len(acc),
        }
    result = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(time.monotonic() - t0, 1),
        "sources": sources,
        "display_profile": profile,
        "current_versions": {
            "pipeline_version": PIPELINE_VERSION,
            "rubric_version": RUBRIC_VERSION,
            "code_fingerprint": code_fingerprint(),
            "stage_versions": {
                "0": fetch_mod.STAGE_VERSION,
                "1": extract_mod.STAGE_VERSION,
                "2": seg_mod.STAGE_VERSION,
                "3": embed_mod.STAGE_VERSION,
                "4": match_mod.STAGE_VERSION,
                "5": diff_mod.STAGE_VERSION,
                "6": sig_mod.STAGE_VERSION,
            },
        },
        "reports": report_infos,
        "counts": counts,
        "violations": remaining,
        "accepted": accepted,
        "errors": errors,
        "exit_code": 1 if remaining else 0,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="RiskDiff integrity checker")
    ap.add_argument("--published", default=str(ROOT / "data" / "published"))
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument(
        "--api", default=None, help="API base URL (default: RISKDIFF_API_URL, :8000, :8001)"
    )
    ap.add_argument("--no-api", action="store_true", help="Do not query a running API")
    ap.add_argument("--out", default=str(ROOT / "INTEGRITY_REPORT.md"))
    ap.add_argument("--json", default=str(ROOT / "data" / "integrity" / "latest.json"))
    ap.add_argument("--exceptions", default=str(ROOT / "data" / "integrity" / "exceptions.json"))
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    result = run(args)
    out_md, out_json = Path(args.out), Path(args.json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    write_markdown(out_md, result)
    tot = result["counts"]["TOTAL"]
    print(
        f"integrity: {tot['total']} violations ({tot['stale']} stale data, {tot['code']} code, {tot['data']} data), "
        f"{tot['accepted']} accepted; wrote {out_md} and {out_json} in {result['duration_seconds']}s"
    )
    for check in CHECKS:
        c = result["counts"][check]
        if c["total"] or c["accepted"]:
            print(
                f"  {check:<17} {c['total']:>4}  (stale {c['stale']}, code {c['code']}, data {c['data']}, accepted {c['accepted']})"
            )
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
