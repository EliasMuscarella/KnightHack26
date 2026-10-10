"""Stage 1: extract the real Item 1A (Risk Factors) section from a 10-K primary document.

Strategy
1. Linearize the HTML into paragraph-like units (html_units.linearize).
2. Find every unit whose whole text is an "Item 1A" heading (tolerates "ITEM 1A.", "Item 1A —",
   non-breaking spaces, and headings split across tags because units merge inline runs). A heading
   that shares a paragraph with its first sentence is split off when its emphasized leading run
   matches. Cross-references inside sentences ("see Item 1A. Risk Factors") never match: the regex
   is anchored to the whole unit (or emphasized lead) and limited in length.
3. For each candidate, the section ends at the next unit that is an "Item 1B / 1C / 2" heading.
   The table of contents produces a candidate whose content is tiny; the body heading produces
   one with thousands of words. Take the candidate with the most content.
4. Fail loudly (ExtractionFailed) when no candidate has at least MIN_WORDS words, or when the best
   candidate is implausibly large (MAX_WORDS: a wrong boundary that swallowed the MD&A).
5. Remove page furniture (page numbers, "Table of Contents", running headers/footers even when
   they carry a page number, "(continued)" headers) and re-join paragraphs that a page break split
   in two.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from pipeline.errors import ExtractionFailed
from pipeline.html_units import Run, Unit, linearize
from pipeline.types import ExtractedSection

log = logging.getLogger(__name__)

STAGE_VERSION = "0.2.1"
MIN_WORDS = 800
MAX_WORDS = 60_000
MAX_HEADING_WORDS = 20

_SEP = r"[\s:.\-–—‒]*"
START_RE = re.compile(rf"^item{_SEP}1a{_SEP}(risk{_SEP}factors{_SEP})?$", re.I)
RISK_FACTORS_ONLY_RE = re.compile(rf"^risk{_SEP}factors{_SEP}$", re.I)
END_RE = re.compile(rf"^item{_SEP}(1b|1c|2){_SEP}(?![0-9a-z])", re.I)
END_FALLBACK_RE = re.compile(
    r"^(unresolved (sec )?staff comments|properties|management[’']?s discussion and analysis|"
    r"quantitative and qualitative disclosures about market risk|legal proceedings)\b",
    re.I,
)

PAGE_NUMBER_RE = re.compile(r"^(page\s*)?\d{1,3}(\s*of\s*\d{1,3})?$", re.I)
ROMAN_RE = re.compile(r"^[ivxlc]{1,6}$", re.I)
FURNITURE_RE = re.compile(
    r"^(table of contents|index|back to top|return to table of contents)$", re.I
)
FORM_FOOTER_RE = re.compile(r"^.{0,80}\b(19|20)\d{2}\s+(annual report|form\s*10-k)\b.{0,40}$", re.I)
CONTINUED_RE = re.compile(r"\(continued\)\s*$", re.I)
TERMINAL_PUNCT = (".", "!", "?", ":", ";", '"', "”")
_TRAILING_PAGE_RE = re.compile(r"[\s|•\-–—]*\b\d{1,3}\s*$")
BULLET_START_RE = re.compile(
    r"^[\u2022\u25cf\u25aa\u25a0\u25e6\u2023\u2043\u00b7\-\u2013\u2014*]\s"
)


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip().lower()


def _header_key(text: str) -> str:
    """Normalized text with digits collapsed and a trailing page number removed, so that
    'Acme | 2025 Form 10-K | 17' and 'Acme | 2025 Form 10-K | 18' count as the same header."""
    return re.sub(r"\d+", "#", _norm_key(_TRAILING_PAGE_RE.sub("", text)))


def _leading_emph(u: Unit) -> str:
    """Text of the emphasized runs at the start of a unit (empty if the unit starts plain)."""
    out = ""
    for r in u.runs:
        if r.emph or (not r.text.strip() and out):
            out += r.text
        else:
            break
    return out.strip()


def split_lead_headings(units: list[Unit]) -> list[Unit]:
    """If a long unit begins with an emphasized 'Item 1A...' / 'Item 1B...' run, split that run
    into its own unit so it can be a boundary candidate (older filers put the heading and the
    first sentence in one paragraph)."""
    out: list[Unit] = []
    for u in units:
        if u.word_count > MAX_HEADING_WORDS and 0.0 < u.emph_ratio < 0.9:
            lead = _leading_emph(u)
            key = _norm_key(lead)
            if (
                lead
                and len(lead.split()) <= MAX_HEADING_WORDS
                and (START_RE.match(key) or END_RE.match(key))
            ):
                rest = u.text[len(lead) :].strip() if u.text.startswith(lead) else None
                if rest:
                    out.append(
                        Unit(
                            text=lead,
                            runs=[Run(lead, True)],
                            tag=u.tag,
                            in_table=u.in_table,
                            html="",
                            emph_ratio=1.0,
                        )
                    )
                    rest_runs: list[Run] = []
                    consumed = len(lead)
                    for r in u.runs:
                        if consumed >= len(r.text):
                            consumed -= len(r.text)
                            continue
                        rest_runs.append(
                            Run(r.text[consumed:], r.emph) if consumed else Run(r.text, r.emph)
                        )
                        consumed = 0
                    out.append(
                        Unit(
                            text=rest,
                            runs=rest_runs or [Run(rest, False)],
                            tag=u.tag,
                            in_table=u.in_table,
                            html=u.html,
                            emph_ratio=0.0,
                        )
                    )
                    continue
        out.append(u)
    for i, u in enumerate(out):
        u.index = i
    return out


def find_candidates(units: list[Unit], *, fallback: bool = False) -> list[tuple[int, int, int]]:
    """Return (start_index, end_index, content_words) for every plausible Item 1A span."""
    starts: list[int] = []
    ends: list[int] = []
    for u in units:
        if u.word_count > MAX_HEADING_WORDS:
            continue
        key = _norm_key(u.text)
        if START_RE.match(key) or (fallback and RISK_FACTORS_ONLY_RE.match(key)):
            starts.append(u.index)
        elif END_RE.match(key) or (fallback and END_FALLBACK_RE.match(key)):
            ends.append(u.index)
    out: list[tuple[int, int, int]] = []
    for s in starts:
        e = next((x for x in ends if x > s), None)
        if e is None:
            continue
        words = sum(units[i].word_count for i in range(s + 1, e))
        out.append((s, e, words))
    return out


def _is_furniture(u: Unit) -> bool:
    t = u.text.strip()
    if not t:
        return True
    if PAGE_NUMBER_RE.match(t) or ROMAN_RE.match(t) or FURNITURE_RE.match(t):
        return True
    if u.word_count <= 12 and (FORM_FOOTER_RE.match(t) or CONTINUED_RE.search(t)):
        return True
    return False


def _merge_units(a: Unit, b: Unit) -> Unit:
    runs = list(a.runs) + [Run(" ", False)] + list(b.runs)
    text = a.text + " " + b.text
    non_ws = [(len(r.text.replace(" ", "")), r.emph) for r in runs]
    total = sum(n for n, _ in non_ws) or 1
    ratio = sum(n for n, e in non_ws if e) / total
    return Unit(
        text=text,
        runs=runs,
        tag=a.tag,
        in_table=a.in_table,
        html=(a.html + "\n" + b.html).strip(),
        emph_ratio=ratio,
    )


def clean_units(units: list[Unit], header_counts: Counter | None = None) -> tuple[list[Unit], int]:
    """Drop page furniture and re-join paragraphs split by a page break.

    Furniture: page numbers, 'Table of Contents', '... 2025 Form 10-K ...' footers, '(continued)'
    headers, and short unpunctuated lines whose digit-normalized text repeats 3+ times
    (`header_counts` may be computed over the whole document).
    Re-join: a unit that does not end with terminal punctuation and is not heading-like, followed
    by a unit starting with a lowercase letter, is one paragraph split across pages."""
    counts = header_counts or Counter(_header_key(u.text) for u in units if u.word_count <= 12)
    kept: list[Unit] = []
    dropped = 0
    for u in units:
        key = _header_key(u.text)
        repeated_header = (
            u.word_count <= 12 and counts[key] >= 3 and not u.text.rstrip().endswith(TERMINAL_PUNCT)
        )
        if _is_furniture(u) or repeated_header:
            dropped += 1
            continue
        if kept:
            prev = kept[-1]
            prev_open = (
                not prev.text.rstrip().endswith(TERMINAL_PUNCT + (")",))
                and prev.emph_ratio < 0.9
                and prev.word_count >= 8
            )
            # the continuation may start with a capitalized word ("... customers in" + "China and ...")
            continues = (
                u.emph_ratio < 0.9 and not BULLET_START_RE.match(u.text) and u.word_count >= 3
            )
            if prev_open and continues:
                kept[-1] = _merge_units(prev, u)
                continue
        kept.append(u)
    return kept, dropped


def extract_item_1a(doc_html: str | bytes, accession_number: str) -> ExtractedSection:
    units = split_lead_headings(linearize(doc_html))
    if not units:
        raise ExtractionFailed("The filing HTML produced no text units.")
    header_counts = Counter(_header_key(u.text) for u in units if u.word_count <= 12)
    method = "item-1a-heading"
    cands = find_candidates(units)
    best = max(cands, key=lambda c: c[2], default=None)
    if best is None or best[2] < MIN_WORDS:
        fb = find_candidates(units, fallback=True)
        fb_best = max(fb, key=lambda c: c[2], default=None)
        if (
            fb_best is not None
            and fb_best[2] >= MIN_WORDS
            and (best is None or fb_best[2] > best[2])
        ):
            best, cands, method = fb_best, fb, "risk-factors-fallback"
    if best is None:
        raise ExtractionFailed(
            "Could not locate an 'Item 1A. Risk Factors' heading followed by an 'Item 1B/1C/2' heading "
            f"in filing {accession_number}."
        )
    start, end, words = best
    if words < MIN_WORDS:
        sizes = ", ".join(f"{w} words" for _, _, w in sorted(cands, key=lambda c: -c[2])[:5])
        raise ExtractionFailed(
            f"Item 1A in filing {accession_number} is too short to analyze: best candidate has {words} words "
            f"(minimum {MIN_WORDS}). Candidates: {sizes or 'none'}. The filer may have omitted risk factors."
        )
    if words > MAX_WORDS:
        raise ExtractionFailed(
            f"The Item 1A candidate in filing {accession_number} spans {words:,} words (over {MAX_WORDS:,}); "
            "the section boundary was probably not found correctly."
        )
    start_heading = units[start].text
    body_start = start + 1
    if body_start < end and RISK_FACTORS_ONLY_RE.match(_norm_key(units[body_start].text)):
        start_heading = f"{start_heading} {units[body_start].text}".strip()
        body_start += 1
    section_units = units[body_start:end]
    section_units, dropped = clean_units(section_units, header_counts)
    for i, u in enumerate(section_units):
        u.index = i
    text = "\n".join(u.text for u in section_units)
    word_count = sum(u.word_count for u in section_units)
    log.info(
        "stage1 %s: method=%s candidates=%d chosen=[%d,%d) words=%d dropped_units=%d",
        accession_number,
        method,
        len(cands),
        start,
        end,
        word_count,
        dropped,
    )
    return ExtractedSection(
        accession_number=accession_number,
        html="\n".join(u.html for u in section_units if u.html),
        text=text,
        word_count=word_count,
        char_count=len(text),
        start_heading=start_heading,
        end_heading=units[end].text,
        method=method,
        candidates=len(cands),
        units=[u.to_dict() for u in section_units],
        dropped_units=dropped,
    )


def run_stage1(html_path: str, accession_number: str) -> ExtractedSection:
    with open(html_path, "rb") as f:
        data = f.read()
    return extract_item_1a(data, accession_number)
