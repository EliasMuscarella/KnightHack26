"""Stage 2 tests: headings, group headers, lead-sentence headings, sentence splitting, ids/offsets."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.errors import SegmentationFailed
from pipeline.extract import extract_item_1a
from pipeline.segment import segment, split_sentences
from pipeline.types import ExtractedSection

FIX = Path(__file__).resolve().parents[1] / "contract" / "fixtures"


def section_from_units(units: list[dict], acc: str = "0000000000-25-000001") -> ExtractedSection:
    text = "\n".join(u["text"] for u in units)
    return ExtractedSection(
        accession_number=acc,
        html="",
        text=text,
        word_count=len(text.split()),
        char_count=len(text),
        start_heading="Item 1A. Risk Factors",
        end_heading="Item 1B.",
        method="test",
        candidates=1,
        units=units,
    )


def U(text: str, emph: bool = False, runs=None, tag="p", in_table=False) -> dict:
    runs = runs or [[text, emph]]
    non_ws = sum(len(t.replace(" ", "")) for t, e in runs if e)
    total = sum(len(t.replace(" ", "")) for t, _ in runs)
    return {
        "text": text,
        "runs": runs,
        "tag": tag,
        "in_table": in_table,
        "emph_ratio": non_ws / total if total else 0.0,
        "html": "",
    }


BODY = "We face a risk. It could hurt us in the U.S. and abroad, e.g. in Europe. Gadgetron Inc. is a supplier."


def test_blocks_groups_ids_and_offsets():
    units = [
        U("Investing involves risk. Read carefully."),
        U("Risks Related to Our Business", emph=True),
        U("We depend on suppliers.", emph=True),
        U(BODY),
        U("RISKS RELATED TO REGULATION"),  # all caps group header
        U("Laws may change.", emph=True),
        U(BODY),
        U("• " + BODY),
    ]
    seg = segment(section_from_units(units))
    assert [b.heading for b in seg.blocks] == [
        "Investing involves risk.",
        "We depend on suppliers.",
        "Laws may change.",
    ]
    assert seg.section_groups == ["Risks Related to Our Business", "RISKS RELATED TO REGULATION"]
    assert seg.blocks[0].section_group is None
    assert seg.blocks[1].section_group == "Risks Related to Our Business"
    assert seg.blocks[2].section_group == "RISKS RELATED TO REGULATION"
    b = seg.blocks[1]
    assert b.id == "0000000000-25-000001:1"
    assert [s.id for s in b.sentences] == [f"{b.id}:{i}" for i in range(4)]
    assert b.sentences[0].is_heading and b.sentences[0].text == "We depend on suppliers."
    for blk in seg.blocks:
        for s in blk.sentences:
            assert seg.text[s.char_start : s.char_end] == s.text
    # bullet glyph stripped, body sentences split on real boundaries only
    assert seg.blocks[2].sentences[-1].text == "Gadgetron Inc. is a supplier."
    assert not any(s.text.startswith("•") for s in seg.blocks[2].sentences)


def test_consecutive_headings_make_group_header():
    units = [
        U("Operational Matters", emph=True),
        U("Our factory may flood.", emph=True),
        U(BODY),
        U("Our staff may leave.", emph=True),
        U(BODY),
        U("Third heading.", emph=True),
        U(BODY),
    ]
    seg = segment(section_from_units(units))
    assert seg.section_groups == ["Operational Matters"]
    assert [b.heading for b in seg.blocks] == [
        "Our factory may flood.",
        "Our staff may leave.",
        "Third heading.",
    ]


def test_lead_sentence_heading_split():
    lead = "The Company's business can be impacted by political events and trade disputes."
    rest = "The Company has international operations with sales outside the U.S. representing a majority of total net sales. Trade policies could hurt."
    units = [
        U(lead + " " + rest, runs=[[lead, True], [" " + rest, False]]),
        U(
            "Another lead sentence that is bold here. Then plain body text follows it with enough words to count as body text.",
            runs=[
                ["Another lead sentence that is bold here.", True],
                [
                    " Then plain body text follows it with enough words to count as body text.",
                    False,
                ],
            ],
        ),
        U("Third heading here.", emph=True),
        U(BODY),
    ]
    seg = segment(section_from_units(units))
    assert seg.blocks[0].heading == lead
    assert seg.blocks[0].sentences[1].text.startswith("The Company has international operations")
    assert seg.blocks[1].heading == "Another lead sentence that is bold here."
    for blk in seg.blocks:
        for s in blk.sentences:
            assert seg.text[s.char_start : s.char_end] == s.text


def test_split_sentences_handles_abbreviations():
    sents = [
        s
        for s, _, _ in split_sentences(
            "We operate in the U.S. and the E.U. markets. Gadgetron Inc. supplies parts, e.g. widgets. Mr. Smith left on Jan. 5, 2025. Revenue fell 10% i.e. by $1.2 billion."
        )
    ]
    assert sents == [
        "We operate in the U.S. and the E.U. markets.",
        "Gadgetron Inc. supplies parts, e.g. widgets.",
        "Mr. Smith left on Jan. 5, 2025.",
        "Revenue fell 10% i.e. by $1.2 billion.",
    ]


def test_too_few_blocks_fails():
    with pytest.raises(SegmentationFailed):
        segment(section_from_units([U("Heading.", emph=True), U(BODY)]))


def test_fixture_pair_segments_plausibly():
    for name, acc in (
        ("FIXTURE_10K_FY2024.htm", "0000000000-24-000001"),
        ("FIXTURE_10K_FY2025.htm", "0000000000-25-000001"),
    ):
        seg = segment(extract_item_1a((FIX / name).read_bytes(), acc))
        assert len(seg.blocks) == 15
        assert len(seg.section_groups) == 3
        assert all(b.heading.startswith("FIXTURE:") for b in seg.blocks[1:])
        assert all(len(b.sentences) >= 3 for b in seg.blocks)


def test_bullet_before_bold_lead_heading_does_not_crash():
    lead = "Our factory may flood during the rainy season."
    rest = "We have one factory in a low-lying area and it has flooded twice before. Repairs take months."
    units = [
        U("• " + lead + " " + rest, runs=[["• ", False], [lead, True], [" " + rest, False]]),
        U("Second heading here.", emph=True),
        U(BODY),
        U("Third heading here.", emph=True),
        U(BODY),
    ]
    seg = segment(section_from_units(units))
    assert seg.blocks[0].heading == lead
    for blk in seg.blocks:
        for s in blk.sentences:
            assert seg.text[s.char_start : s.char_end] == s.text
