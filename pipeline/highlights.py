"""Highlights: the <= 5 cards shown as "Biggest changes" on a company page (Task J4).

Candidates come only from evidence that already exists on a change: deterministic signals
(hedge-to-actual pairs, quantities, named entities), the change type itself (a new or removed
risk cites the heading sentence `{block_id}:0`), and validated AI rubric answers (kind from the
question, sentences from its citations). Nothing is generated here.

Selection (see select_highlights) runs over four tiers in order:
  1. meaningful change (not "largely_unchanged") + rule-based evidence
  2. meaningful change + AI-rubric-only evidence
  3. essentially unchanged risk + rule-based evidence
  4. essentially unchanged risk + AI-rubric-only evidence
so the cards agree with the "N of M risk factors changed meaningfully" line and rule-based
evidence outranks an AI answer. Within a tier, rank_key orders candidates by parent change
score (desc, the same order as the ranked list), then kind priority (new risk > dropped risk >
potential became actual > figure > newly named), then change id, then the candidate's position
(dollar amounts before percentages before counts, larger figures first; for potential-became-actual
pairs, self-contained sentences before ones that open with "Such", "This", "As a result"…). A new or dropped risk cites its first body sentence (the
card already shows the heading as its title), falling back to the heading sentence. Each tier takes one card per change first,
then second cards of a different kind. At most MAX_PER_CHANGE per change and MAX_TOTAL overall.
A potential_became_actual highlight must carry BOTH a last-year and a this-year sentence: the
before/after is the point of that card, so rubric-only candidates with one side are dropped.
"""

from __future__ import annotations

import re

from pipeline.schema import Change, Highlight, SentenceLocation

KIND_PRIORITY: dict[str, int] = {
    "new_risk": 0,
    "removed_risk": 1,
    "potential_became_actual": 2,
    "new_figure": 3,
    "new_named_party": 4,
}
MAX_PER_CHANGE = 2
MAX_TOTAL = 5
RUBRIC_KIND = {"Q1": "potential_became_actual", "Q2": "new_named_party", "Q3": "new_figure"}
MEANINGFUL = ("new", "removed", "expanded", "reduced", "materially_reworded")


def _split_sides(
    ids: list[str], index: dict[str, SentenceLocation]
) -> tuple[str | None, str | None]:
    old = next((i for i in ids if i in index and index[i].side == "old"), None)
    new = next((i for i in ids if i in index and index[i].side == "new"), None)
    return old, new


ANAPHORIC_OPENERS = (
    "such ",
    "this ",
    "these ",
    "that ",
    "those ",
    "it ",
    "they ",
    "there ",
    "as a result",
    "accordingly",
    "for example",
    "in addition",
    "additionally",
    "however",
    "further,",
)


def _quote_order(text: str | None) -> int:
    """A sentence that leans on the previous one ("Such requests…", "This…") makes a poor
    standalone quote; self-contained sentences come first."""
    t = (text or "").lstrip().lower()
    return 1 if t.startswith(ANAPHORIC_OPENERS) else 0


def _first_body_sentence(block_id: str, index: dict[str, SentenceLocation]) -> str:
    """The first body sentence of a block when it exists (the heading is sentence 0 and the card
    already shows it as the title), else the heading sentence."""
    body = f"{block_id}:1"
    return body if body in index else f"{block_id}:0"


_MAGNITUDE_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand)?", re.I)
_MULT = {"trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3}


def _magnitude(value: str | None) -> float:
    """Numeric size of a figure ("$4.5 billion" -> 4.5e9; "12% -> 22%" uses the new value)."""
    v = (value or "").split("->")[-1]
    m = _MAGNITUDE_RE.search(v)
    if not m:
        return 0.0
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0
    return n * _MULT.get((m.group(2) or "").lower(), 1.0)


def _figure_order(value: str | None) -> tuple[int, float]:
    """Dollar amounts before percentages before other quantities, larger figures first
    (a finance reader's order)."""
    v = value or ""
    if "$" in v:
        kind = 0
    elif "%" in v or "percent" in v.lower():
        kind = 1
    else:
        kind = 2
    return (kind, -_magnitude(v))


def candidate_highlights(
    change: Change, index: dict[str, SentenceLocation]
) -> list[tuple[Highlight, bool]]:
    """All highlight candidates of one change, in a deterministic order.

    Each item is (highlight, rule_based): rule_based is True when the card rests on a
    deterministic signal or on the change type itself, False when its only evidence is a
    validated AI rubric answer.
    """
    out: list[tuple[Highlight, bool]] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    def add(
        kind: str, old: str | None, new: str | None, detail: str | None, rule_based: bool
    ) -> None:
        if old is not None and old not in index:
            old = None
        if new is not None and new not in index:
            new = None
        if old is None and new is None:
            return
        if kind == "potential_became_actual" and (old is None or new is None):
            return  # a before/after card needs both sides
        key = (kind, old, new)
        if key in seen:
            return
        seen.add(key)
        out.append(
            (
                Highlight(
                    change_id=change.id,
                    kind=kind,
                    old_sentence_id=old,
                    new_sentence_id=new,
                    short_title=change.short_title,
                    detail=detail,
                ),
                rule_based,
            )
        )

    sig = change.signals

    def new_text(h) -> str | None:  # noqa: ANN001
        sid = (h.new_sentence_ids or [None])[0]
        return index[sid].text if sid in index else None

    if change.change_type == "new" and change.new_block_id:
        add("new_risk", None, _first_body_sentence(change.new_block_id, index), None, True)
    if change.change_type == "removed" and change.old_block_id:
        add("removed_risk", _first_body_sentence(change.old_block_id, index), None, None, True)
    for h in sorted(sig.hypothetical_to_actual, key=lambda h: _quote_order(new_text(h))):
        add(
            "potential_became_actual",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
            True,
        )
    for h in sorted(sig.new_quantities, key=lambda h: _figure_order(h.value)):
        add(
            "new_figure",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
            True,
        )
    for h in sig.new_entities:
        add("new_named_party", None, (h.new_sentence_ids or [None])[0], h.value, True)
    for ans in change.interpretation.rubric:
        kind = RUBRIC_KIND.get(ans.question_id)
        if kind and ans.answer and ans.cited_sentence_ids:
            old, new = _split_sides(list(ans.cited_sentence_ids), index)
            add(kind, old, new, None, False)
    return out


def rank_key(h: Highlight, change: Change, position: int) -> tuple:
    """Order within a tier: biggest change first (same order as the ranked list), then kind."""
    return (-change.score, KIND_PRIORITY[h.kind], change.id, position)


def select_highlights(changes: list[Change], index: dict[str, SentenceLocation]) -> list[Highlight]:
    by_id = {c.id: c for c in changes}
    # tiers: (meaningful change?, rule-based evidence?) -> candidates ranked within the tier
    tiers: dict[tuple[bool, bool], list[tuple[tuple, Highlight]]] = {
        (m, r): [] for m in (True, False) for r in (True, False)
    }
    for c in changes:
        meaningful = c.change_type in MEANINGFUL
        for pos, (h, rule_based) in enumerate(candidate_highlights(c, index)):
            tiers[(meaningful, rule_based)].append((rank_key(h, c, pos), h))

    chosen: list[Highlight] = []
    per_change: dict[str, int] = {}
    seen_kind: set[tuple[str, str]] = set()

    def take(h: Highlight) -> None:
        chosen.append(h)
        seen_kind.add((h.change_id, h.kind))
        per_change[h.change_id] = per_change.get(h.change_id, 0) + 1

    for key in ((True, True), (True, False), (False, True), (False, False)):
        ranked = sorted(tiers[key], key=lambda x: x[0])
        for _, h in ranked:  # pass 1: the best candidate of each change in this tier
            if len(chosen) >= MAX_TOTAL:
                break
            if h.change_id not in per_change:
                take(h)
        for _, h in ranked:  # pass 2: a second card for a change, of a different kind
            if len(chosen) >= MAX_TOTAL:
                break
            if (
                h in chosen
                or per_change.get(h.change_id, 0) >= MAX_PER_CHANGE
                or (h.change_id, h.kind) in seen_kind
            ):
                continue
            take(h)
    assert all(h.change_id in by_id for h in chosen)
    return chosen


# ---------- deterministic short titles ----------

# Words a short title must not end on (it would be cut mid-clause).
DANGLING_WORDS = frozenset(
    "including include includes and or but of the a an to in on for with by as at from into "
    "which that our its their his her we they it is are was were be been being may might could "
    "would should can will shall if when while because whether than such other certain any all "
    "laws law inc corp co ltd plc llc".split()
)
# A clause starts BEFORE a token whose casefolded form is one of these.
CLAUSE_START_WORDS = frozenset(
    "which that including because as if when where while whether due resulting and or but may "
    "might could would should will can".split()
)
# A clause ends AFTER a token ending with one of these (or a standalone " - ").
CLAUSE_END_CHARS = (",", ";", ":", "\u2014", "\u2013")
_TRAILING_PUNCT = ",;:\u2014\u2013-"
_QUOTES = "\"'\u201c\u201d\u2018\u2019"
_COMPANY_SUFFIX_RE = re.compile(
    r"[\s,.]*\b(?:inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|holdings|"
    r"group|com)\b[.,\s]*$",
    re.IGNORECASE,
)
MAX_TITLE_WORDS = 10
MIN_TITLE_WORDS = 4


def _bare(word: str) -> str:
    """A word with surrounding punctuation stripped, casefolded (for the DANGLING test)."""
    return re.sub(r"^[^\w]+|[^\w'\u2019]+$", "", word).casefold()


CONJUNCTIONS = frozenset({"and", "or", "but"})


def _strip_trailing(tokens: list[str]) -> list[str]:
    """Strip trailing punctuation from the last token, dropping tokens that were only punctuation."""
    words = list(tokens)
    while words:
        last = words[-1].rstrip(_TRAILING_PUNCT)
        if last:
            words[-1] = last
            break
        words.pop()  # a standalone "-" or dash
    return words


def _trim_candidate(tokens: list[str], cut_before_conjunction: bool = False) -> list[str]:
    """Strip trailing punctuation from the last token, then drop trailing DANGLING words while at
    least MIN_TITLE_WORDS words would remain. When the candidate was cut right before a
    conjunction and itself ends in "<conjunction> <word>", the coordination continues past the cut
    ("…regulations, and political | and other actions"), so that trailing pair goes too."""
    words = _strip_trailing(tokens)
    while True:
        if len(words) > MIN_TITLE_WORDS and _bare(words[-1]) in DANGLING_WORDS:
            words = _strip_trailing(words[:-1])
            continue
        if (
            cut_before_conjunction
            and len(words) >= MIN_TITLE_WORDS + 2
            and _bare(words[-2]) in CONJUNCTIONS
        ):
            words = _strip_trailing(words[:-2])
            cut_before_conjunction = False
            continue
        break
    return words


def _name_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _company_keys(company_name: str | None) -> set[str]:
    if not company_name:
        return set()
    keys = {_name_key(company_name)}
    stripped = company_name
    prev = None
    while prev != stripped:
        prev = stripped
        stripped = _COMPANY_SUFFIX_RE.sub("", stripped).strip()
    keys.add(_name_key(stripped))
    return {k for k in keys if k}


def _is_company_name(title: str, company_name: str | None) -> bool:
    keys = _company_keys(company_name)
    if not keys:
        return False
    t = title
    prev = None
    variants = {_name_key(t)}
    while prev != t:
        prev = t
        t = _COMPANY_SUFFIX_RE.sub("", t).strip()
        variants.add(_name_key(t))
    return bool(variants & keys)


def short_title_from_heading(
    heading: str, max_words: int = MAX_TITLE_WORDS, company_name: str | None = None
) -> str:
    """Deterministic short title from an official risk heading (the frontend ports this spec).

    1. Collapse whitespace; strip surrounding quotes; strip trailing ".", ";", ":".
    2. A heading of at most `max_words` words is returned as is.
    3. Clause boundaries lie AFTER a token ending with , ; : \u2014 \u2013 (or a standalone "-"),
       and BEFORE a token whose casefolded form is in CLAUSE_START_WORDS. Each boundary gives a
       candidate: the tokens before it, trailing punctuation stripped from its last token, then
       trailing DANGLING_WORDS removed while at least 4 words remain; a candidate cut right before
       a conjunction that itself ends in "<conjunction> <word>" also loses that pair
       ("…regulations, and political | and other actions" -> "…regulations"). A candidate qualifies with
       4..max_words words and a last word that is not DANGLING. The LONGEST qualifying one wins.
    4. Otherwise: the first `max_words` tokens, trimmed the same way.
    5. Never an ellipsis. A result equal to the company name (with or without a corporate
       suffix) is replaced by step 4.
    """
    t = " ".join((heading or "").split())
    t = t.strip(_QUOTES).strip()
    t = t.rstrip(".;:").strip()
    tokens = t.split(" ") if t else []
    if len(tokens) <= max_words:
        return t

    def step4() -> str:
        return " ".join(_trim_candidate(tokens[:max_words]))

    best: list[str] | None = None
    for k, tok in enumerate(tokens):
        cuts = []
        if tok.casefold() in CLAUSE_START_WORDS:
            cuts.append(k)  # boundary before token k
        if tok.endswith(CLAUSE_END_CHARS) or tok == "-":
            cuts.append(k + 1)  # boundary after token k
        for cut in cuts:
            cand = _trim_candidate(
                tokens[:cut],
                cut_before_conjunction=_bare(tokens[cut]) in CONJUNCTIONS
                if cut < len(tokens)
                else False,
            )
            if not (MIN_TITLE_WORDS <= len(cand) <= max_words):
                continue
            if _bare(cand[-1]) in DANGLING_WORDS:
                continue
            if best is None or len(cand) > len(best):
                best = cand
    result = " ".join(best) if best is not None else step4()
    if _is_company_name(result, company_name):
        result = step4()
    return result


def title_problems(title: str, company_name: str | None = None) -> list[str]:
    """Why a short title is not acceptable (empty list = acceptable): an ellipsis, more than
    MAX_TITLE_WORDS words, a DANGLING last word, a trailing , ; : ( - \u2013 \u2014, or the bare company
    name. Same rules as scripts/check_integrity.py's TITLES check."""
    t = " ".join((title or "").split())
    if not t:
        return ["empty"]
    problems: list[str] = []
    if t.endswith("\u2026") or t.endswith("..."):
        problems.append("ends with an ellipsis")
    words = t.rstrip("\u2026.").split()
    if len(words) > MAX_TITLE_WORDS:
        problems.append(f"{len(words)} words (max {MAX_TITLE_WORDS})")
    if words and _bare(words[-1]) in DANGLING_WORDS:
        problems.append(f"ends mid-clause on {_bare(words[-1])!r}")
    if t.rstrip("\u2026").endswith((",", ";", ":", "(", "-", "\u2013", "\u2014")):
        problems.append("ends on punctuation")
    if _is_company_name(t, company_name):
        problems.append("is just the company name")
    return problems


def truncate_heading(
    heading: str, max_words: int = MAX_TITLE_WORDS, company_name: str | None = None
) -> str:
    """Deterministic fallback short title (kept for callers): short_title_from_heading."""
    return short_title_from_heading(heading, max_words=max_words, company_name=company_name)
