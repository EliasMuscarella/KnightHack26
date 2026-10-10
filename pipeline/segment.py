"""Stage 2: split Item 1A into risk blocks (heading + body) and sentences with stable ids.

Heuristics (all deterministic, documented here):
- A unit is *heading-like* when (almost) all of its text is emphasized (bold/italic/underline/
  h1-h6) or it is ALL CAPS, and it is at most MAX_HEADING_WORDS long.
- A heading-like unit immediately followed by another heading-like unit is a *group header*
  ("Risks Related to Our Industry"); so is a short heading-like unit matching GROUP_RE.
  Group headers are stored as `section_group` on the blocks that follow them.
- A paragraph that starts with an emphasized lead sentence followed by plain text (Apple style)
  is split: the lead becomes the heading, the remainder starts the body.
- The "Risk Factors Summary" bullet list that opens many Item 1A sections (a summary heading
  followed by short bullets, often repeating the group headers) is skipped entirely: it ends at
  the first *real* risk block (a heading followed by a plain paragraph of >= MIN_REAL_BODY_WORDS).
- Intro and boilerplate paragraphs that appear before any risk heading (or between a group
  header and its first risk heading) are skipped, never turned into blocks.
- Sentences are split with pysbd (legal-text aware: "U.S.", "Inc.", "e.g."). Sentence 0 of every
  block is the heading. Ids are "{accession}:{block_index}:{sentence_index}" and char offsets
  index into `SegmentedFiling.text` (= extracted unit texts joined with "\\n").
"""

from __future__ import annotations

import logging
import re

import pysbd

from pipeline.config import SENTENCE_SPLITTER_ID
from pipeline.errors import SegmentationFailed
from pipeline.html_units import Unit
from pipeline.types import ExtractedSection, RiskBlock, SegmentedFiling, SentenceRec

log = logging.getLogger(__name__)

STAGE_VERSION = "0.2.0"
MAX_HEADING_WORDS = 60
MAX_GROUP_WORDS = 15
MIN_BLOCKS = 3

GROUP_RE = re.compile(
    r"^(risks?\s+(related|relating|pertaining)\s+to\b|"
    r"risks?\s+(associated|connected)\s+with\b|"
    r"risks?\s+(of|from|arising from)\b|"
    r"(general|other|additional|legal|regulatory|financial|operational|strategic|economic|industry|"
    r"business|market|tax|macroeconomic|cybersecurity|technology|international|human capital|"
    r"intellectual property|liquidity|governance|compliance)[\w\s,&/-]*\brisks?( factors?)?$)",
    re.I,
)
# "Summary of Risk Factors" / "Risk Factors Summary" is a real block (its bullets are its body), not a
# group header, so it is matched as one block across years instead of leaking bullets into a preamble.
BULLET_RE = re.compile(r"^[•●▪■◦‣⁃·\-–—*]\s*")
SUMMARY_RE = re.compile(
    r"^(summary of (the |our )?(principal |material |key |significant )?risk factors?|"
    r"risk factors? summary|summary risk factors?|summary of risks?)\s*[:.]?$",
    re.I,
)
MIN_REAL_BODY_WORDS = 40
TERMINAL = (".", "!", "?", ":", ";")

_segmenter = pysbd.Segmenter(language="en", clean=False, char_span=True)


def split_sentences(text: str) -> list[tuple[str, int, int]]:
    """Return (sentence, start, end) with offsets into `text`, whitespace trimmed."""
    out: list[tuple[str, int, int]] = []
    for span in _segmenter.segment(text):
        s, start, end = span.sent, span.start, span.end
        lead = len(s) - len(s.lstrip())
        trail = len(s) - len(s.rstrip())
        s2 = s.strip()
        if not s2:
            continue
        out.append((s2, start + lead, end - trail))
    # merge fragments that are too short to be sentences (e.g. "No." split artifacts)
    merged: list[tuple[str, int, int]] = []
    for s, a, b in out:
        if merged and len(s.split()) <= 1 and not merged[-1][0].endswith(TERMINAL):
            ps, pa, _ = merged[-1]
            merged[-1] = (text[pa:b].strip(), pa, b)
            continue
        merged.append((s, a, b))
    return merged


def is_heading_like(u: Unit) -> bool:
    if u.word_count == 0 or u.word_count > MAX_HEADING_WORDS:
        return False
    if u.emph_ratio >= 0.9:
        return True
    letters = [c for c in u.text if c.isalpha()]
    return len(letters) >= 4 and all(c.isupper() for c in letters)


def is_group_header(u: Unit) -> bool:
    t = u.text.strip()
    return u.word_count <= MAX_GROUP_WORDS and not t.endswith(".") and bool(GROUP_RE.match(t))


def split_lead_heading(u: Unit) -> tuple[str, str] | None:
    """Emphasized lead sentence followed by plain text -> (heading, remainder)."""
    if not u.runs or u.emph_ratio >= 0.9 or u.emph_ratio <= 0.0:
        return None
    prefix = ""
    i = 0
    # a plain bullet glyph before the emphasized lead ("• **Heading.** body") is skipped
    if i < len(u.runs) and not u.runs[i].emph and BULLET_RE.fullmatch(u.runs[i].text or ""):
        i += 1
    while i < len(u.runs) and (u.runs[i].emph or not u.runs[i].text.strip()):
        prefix += u.runs[i].text
        i += 1
    if i == 0 or i >= len(u.runs):
        return None
    remainder = "".join(r.text for r in u.runs[i:])
    p, r = prefix.strip(), remainder.strip()
    if len(p.split()) < 4 or len(p.split()) > MAX_HEADING_WORDS or len(r.split()) < 8:
        return None
    if not (p.endswith(TERMINAL) or (r[:1].isupper())):
        return None
    return p, r


def _is_real_risk_start(units: list[Unit], j: int) -> bool:
    """A heading-like unit followed by a plain, non-bullet paragraph of real length, or an
    Apple-style unit whose emphasized lead is followed by such a body."""
    u = units[j]
    if is_heading_like(u):
        if is_group_header(u):
            return False
        k = j + 1
        if k < len(units):
            nxt = units[k]
            return (
                not is_heading_like(nxt)
                and not BULLET_RE.match(nxt.text)
                and nxt.word_count >= MIN_REAL_BODY_WORDS
            )
        return False
    lead = split_lead_heading(u)
    return lead is not None and len(lead[1].split()) >= MIN_REAL_BODY_WORDS


def summary_skip_range(units: list[Unit]) -> tuple[int, int] | None:
    """Return [start, end) of the Risk Factors Summary section to skip, or None.

    The summary starts at a unit whose whole text matches SUMMARY_RE and ends right before the
    first real risk block that follows (see _is_real_risk_start); a group header immediately
    before that block is kept so the block gets its section_group."""
    for i, u in enumerate(units):
        if u.word_count <= 8 and SUMMARY_RE.match(BULLET_RE.sub("", u.text).strip()):
            for j in range(i + 1, len(units)):
                if _is_real_risk_start(units, j):
                    end = j
                    if (
                        end - 1 > i
                        and is_heading_like(units[end - 1])
                        and is_group_header(units[end - 1])
                    ):
                        end -= 1
                    return (i, end)
            log.warning(
                "summary heading found at unit %d but no real risk block after it; nothing skipped",
                i,
            )
            return None
    return None


def segment(section: ExtractedSection) -> SegmentedFiling:
    acc = section.accession_number
    units = [Unit.from_dict(d, i) for i, d in enumerate(section.units)]
    # offsets of each unit in the joined text
    offsets: list[int] = []
    pos = 0
    for u in units:
        offsets.append(pos)
        pos += len(u.text) + 1
    text = "\n".join(u.text for u in units)

    blocks: list[RiskBlock] = []
    groups: list[str] = []
    current_group: str | None = None
    pending: tuple[str, int] | None = None  # (heading, char_start)
    body: list[tuple[str, int]] = []  # (text, char_start)

    def flush() -> None:
        nonlocal pending, body
        if pending is None:
            # body text with no heading (intro/boilerplate): never a block
            body = []
            return
        heading, h_start = pending
        if not body:
            log.debug("dropping heading without body: %r", heading[:80])
            pending, body = None, []
            return
        bi = len(blocks)
        bid = f"{acc}:{bi}"
        sentences = [
            SentenceRec(
                id=f"{bid}:0",
                text=heading,
                char_start=h_start,
                char_end=h_start + len(heading),
                is_heading=True,
            )
        ]
        for para, p_start in body:
            for s, a, b in split_sentences(para):
                si = len(sentences)
                sentences.append(
                    SentenceRec(
                        id=f"{bid}:{si}",
                        text=s,
                        char_start=p_start + a,
                        char_end=p_start + b,
                        is_heading=False,
                    )
                )
        if len(sentences) < 2:
            pending, body = None, []
            return
        blocks.append(
            RiskBlock(
                id=bid,
                accession_number=acc,
                index=bi,
                heading=heading,
                body="\n".join(p for p, _ in body),
                section_group=current_group,
                sentences=sentences,
                char_start=h_start,
                char_end=sentences[-1].char_end,
            )
        )
        pending, body = None, []

    def set_group(name: str) -> None:
        nonlocal current_group
        current_group = name
        if name not in groups:
            groups.append(name)

    skip = summary_skip_range(units)
    skipped_units = 0
    for u in units:
        if skip is not None and skip[0] <= u.index < skip[1]:
            skipped_units += 1
            continue
        raw = u.text
        stripped = BULLET_RE.sub("", raw)
        u_start = offsets[u.index] + (len(raw) - len(stripped))
        if is_heading_like(u):
            if pending is not None and not body:
                # two headings in a row: the first was a group header
                set_group(pending[0])
                pending = (stripped, u_start)
            elif is_group_header(u):
                flush()
                set_group(stripped)
            else:
                flush()
                pending = (stripped, u_start)
            continue
        lead = split_lead_heading(u)
        if lead is not None:
            heading, remainder = lead
            if pending is not None and not body:
                set_group(pending[0])
            else:
                flush()
            h_off = stripped.index(heading)
            pending = (heading, u_start + h_off)
            body = [(remainder, u_start + stripped.index(remainder, h_off + len(heading)))]
            continue
        if pending is None:
            skipped_units += 1  # intro / boilerplate paragraph before any risk heading
            continue
        body.append((stripped, u_start))
    flush()

    if len(blocks) < MIN_BLOCKS:
        raise SegmentationFailed(
            f"Only {len(blocks)} risk blocks were found in {acc} (minimum {MIN_BLOCKS}). "
            "The filing may use an unusual heading style."
        )
    for b in blocks:
        for s in b.sentences:
            assert text[s.char_start : s.char_end] == s.text, (
                s.id,
                text[s.char_start : s.char_end][:60],
                s.text[:60],
            )
    log.info(
        "stage2 %s: blocks=%d groups=%d sentences=%d skipped_units=%d (summary/intro)",
        acc,
        len(blocks),
        len(groups),
        sum(len(b.sentences) for b in blocks),
        skipped_units,
    )
    return SegmentedFiling(
        accession_number=acc,
        blocks=blocks,
        section_groups=groups,
        text=text,
        word_count=section.word_count,
        char_count=len(text),
        splitter=SENTENCE_SPLITTER_ID,
        skipped_units=skipped_units,
    )
