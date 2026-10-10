"""Stage 1: extract the real Item 1A (Risk Factors) section from a 10-K primary document.

Strategy
1. Linearize the HTML into paragraph-like units (html_units.linearize).
2. Find every unit whose whole text is an "Item 1A" heading (tolerates "ITEM 1A.", "Item 1A —",
   non-breaking spaces, and headings split across tags because units merge inline runs).
   Cross-references inside sentences ("see Item 1A. Risk Factors") never match: the regex is
   anchored to the whole unit and limited in length.
3. For each candidate, the section ends at the next unit that is an "Item 1B / 1C / 2" heading.
   The table of contents produces a candidate whose content is tiny; the body heading produces
   one with thousands of words. Take the candidate with the most content.
4. Fail loudly (ExtractionFailed) when no candidate has at least MIN_WORDS words.
5. Remove running page furniture (page numbers, "Table of Contents", repeated short headers).
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from pipeline.errors import ExtractionFailed
from pipeline.html_units import Unit, linearize
from pipeline.types import ExtractedSection

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.0"
MIN_WORDS = 800
MAX_HEADING_WORDS = 20

_SEP = r"[\s:.\-–—‒]*"
START_RE = re.compile(rf"^item{_SEP}1a{_SEP}(risk{_SEP}factors{_SEP})?$", re.I)
RISK_FACTORS_ONLY_RE = re.compile(rf"^risk{_SEP}factors{_SEP}$", re.I)
END_RE = re.compile(rf"^item{_SEP}(1b|1c|2){_SEP}(?![0-9a-z])", re.I)
END_FALLBACK_RE = re.compile(r"^(unresolved staff comments|properties)\b", re.I)

PAGE_NUMBER_RE = re.compile(r"^(page\s*)?\d{1,3}(\s*of\s*\d{1,3})?$", re.I)
ROMAN_RE = re.compile(r"^[ivxlc]{1,6}$", re.I)
FURNITURE_RE = re.compile(
    r"^(table of contents|index|back to top|return to table of contents)$", re.I
)
TERMINAL_PUNCT = (".", "!", "?", ":", ";", '"', "”", ")")


def _norm_key(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip().lower()


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
    return False


def clean_units(units: list[Unit]) -> tuple[list[Unit], int]:
    """Drop page furniture: page numbers, 'Table of Contents', and short unpunctuated lines that
    repeat 3+ times (running headers such as 'Acme Corp | 2025 Form 10-K')."""
    counts = Counter(_norm_key(u.text) for u in units if u.word_count <= 12)
    kept: list[Unit] = []
    dropped = 0
    for u in units:
        key = _norm_key(u.text)
        repeated_header = (
            u.word_count <= 12 and counts[key] >= 3 and not u.text.rstrip().endswith(TERMINAL_PUNCT)
        )
        if _is_furniture(u) or repeated_header:
            dropped += 1
            continue
        kept.append(u)
    return kept, dropped


def extract_item_1a(doc_html: str | bytes, accession_number: str) -> ExtractedSection:
    units = linearize(doc_html)
    if not units:
        raise ExtractionFailed("The filing HTML produced no text units.")
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
    start_heading = units[start].text
    body_start = start + 1
    # "Item 1A." and "Risk Factors" as two separate units: fold the second into the heading
    if body_start < end and RISK_FACTORS_ONLY_RE.match(_norm_key(units[body_start].text)):
        start_heading = f"{start_heading} {units[body_start].text}".strip()
        body_start += 1
    section_units = units[body_start:end]
    section_units, dropped = clean_units(section_units)
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
