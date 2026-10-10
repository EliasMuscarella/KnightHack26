"""Stage 1 tests: TOC trap, heading variants, furniture removal, loud failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.errors import ExtractionFailed
from pipeline.extract import extract_item_1a, find_candidates
from pipeline.html_units import linearize

FIX = Path(__file__).resolve().parents[1] / "contract" / "fixtures"
LOREM = " ".join(
    ["The company faces risks that could adversely affect its operations and results."] * 20
)


def doc(
    heading_html: str,
    *,
    end_html: str = "<p><b>Item 1B. Unresolved Staff Comments</b></p>",
    body_paras: int = 12,
    toc: bool = True,
) -> str:
    toc_html = (
        "<table><tr><td>Item&#160;1A.</td><td>Risk Factors</td><td>12</td></tr>"
        "<tr><td>Item&#160;1B.</td><td>Unresolved Staff Comments</td><td>30</td></tr>"
        "<tr><td>Item&#160;2.</td><td>Properties</td><td>31</td></tr></table>"
        if toc
        else ""
    )
    body = "".join(
        f"<p>{LOREM}</p><div style='text-align:center'>{i + 10}</div><p><a href='#'>Table of Contents</a></p>"
        for i in range(body_paras)
    )
    return (
        "<html><body>"
        "<div style='display:none'><ix:header>2025 FY false</ix:header></div>"
        f"{toc_html}"
        "<p><b>Item 1. Business</b></p><p>We make things. For risks, see Item 1A. Risk Factors.</p>"
        f"{heading_html}{body}{end_html}<p>None.</p>"
        "<p><b>Item 2. Properties</b></p><p>Offices.</p>"
        "<p><b>Item 7. MD&amp;A</b></p><p>Refer to Item 1A. Risk Factors for a discussion.</p>"
        "</body></html>"
    )


def test_toc_trap_picks_body_heading_not_toc_row():
    html = doc(
        "<p><span style='font-weight:700'>ITEM&#160;1A.</span><span style='font-weight:700'> RISK FACTORS</span></p>"
    )
    units = linearize(html)
    cands = find_candidates(units)
    assert len(cands) == 2, cands  # TOC row + body heading
    toc_cand, body_cand = sorted(cands, key=lambda c: c[2])
    assert toc_cand[2] < 10 and body_cand[2] > 200
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert sec.start_heading == "ITEM 1A. RISK FACTORS"
    assert sec.end_heading.startswith("Item 1B")
    assert "see Item 1A" not in sec.text
    assert "Refer to Item 1A" not in sec.text
    assert "Offices." not in sec.text
    assert sec.candidates == 2 and sec.method == "item-1a-heading"


@pytest.mark.parametrize(
    "heading",
    [
        "<p><b>Item 1A — Risk Factors</b></p>",
        "<p><b>Item 1A &#8212; Risk Factors</b></p>",
        "<p><b>Item 1A: Risk Factors</b></p>",
        "<p><b>ITEM 1A.</b></p><p><b>RISK FACTORS</b></p>",
        "<div><span>Item</span>&#160;<span>1A.</span></div><div>Risk Factors</div>",
        "<h2>Item 1A. Risk Factors.</h2>",
        "<p><b>Item 1A.&#160;&#160;Risk&#160;Factors</b></p>",
    ],
)
def test_heading_variants(heading):
    sec = extract_item_1a(doc(heading), "0000000000-25-000001")
    assert sec.word_count > 200
    assert "risk factors" in sec.start_heading.lower() and "1a" in sec.start_heading.lower()
    assert sec.units[0]["text"].startswith("The company faces risks")


def test_ends_at_item_1c_or_2_when_1b_missing():
    sec = extract_item_1a(
        doc("<p><b>Item 1A. Risk Factors</b></p>", end_html="<p><b>Item 1C. Cybersecurity</b></p>"),
        "0000000000-25-000001",
    )
    assert sec.end_heading.startswith("Item 1C")
    sec2 = extract_item_1a(
        doc("<p><b>Item 1A. Risk Factors</b></p>", end_html="<p><b>Item 2. Properties</b></p>"),
        "0000000000-25-000001",
    )
    assert sec2.end_heading.startswith("Item 2")


def test_furniture_removed():
    sec = extract_item_1a(doc("<p><b>Item 1A. Risk Factors</b></p>"), "0000000000-25-000001")
    assert sec.dropped_units >= 20
    assert "Table of Contents" not in sec.text
    assert not any(u["text"].strip().isdigit() for u in sec.units)


def test_short_section_fails_loudly():
    with pytest.raises(ExtractionFailed, match="too short"):
        extract_item_1a(
            doc("<p><b>Item 1A. Risk Factors</b></p>", body_paras=1), "0000000000-25-000001"
        )


def test_missing_heading_fails_loudly():
    html = (
        "<html><body><p>Item 1. Business</p><p>"
        + LOREM * 10
        + "</p><p>Item 2. Properties</p></body></html>"
    )
    with pytest.raises(ExtractionFailed, match="Could not locate"):
        extract_item_1a(html, "0000000000-25-000001")


def test_fallback_risk_factors_heading_without_item_number():
    html = doc("<p><b>Risk Factors</b></p>", toc=False)
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert sec.method == "risk-factors-fallback"


def test_fixture_filings_extract():
    for name in ("FIXTURE_10K_FY2024.htm", "FIXTURE_10K_FY2025.htm"):
        sec = extract_item_1a((FIX / name).read_bytes(), "0000000000-25-000001")
        assert sec.word_count >= 850, (name, sec.word_count)
        assert sec.units[0]["text"].startswith("Investing in our securities")
        assert "Our headquarters" not in sec.text
        assert "FIXTURE Example Widgets Corp | " not in sec.text  # running header dropped
        assert sec.start_heading == "Item 1A. Risk Factors"


def test_running_footer_with_page_numbers_removed():
    body = "".join(
        f"<p>{LOREM}</p><div>Acme Corp | 2025 Form 10-K | {i + 10}</div>" for i in range(12)
    )
    html = (
        "<html><body><p><b>Item 1A. Risk Factors</b></p>"
        + body
        + "<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p></body></html>"
    )
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert "Acme Corp | 2025 Form 10-K" not in sec.text
    assert sec.dropped_units >= 12


def test_inline_xbrl_wrappers_and_table_layout():
    """Workiva-style nesting: ix:nonNumeric wrapping whole sections, and an old-style layout table."""
    paras = "".join(f"<div><span>{LOREM}</span></div>" for _ in range(12))
    html = (
        "<html><body><div style='display:none'><ix:header><ix:hidden>2025 FY</ix:hidden></ix:header></div>"
        "<ix:nonNumeric name='x:Foo' contextRef='c'>"
        "<div><span style='font-weight:700'>Item&#160;1A.</span></div><div><span style='font-weight:700'>Risk Factors</span></div>"
        "<div><span style='font-weight:700;font-style:italic'>Risks Related to Our Business</span></div>"
        "<div><span style='font-weight:700'>Our business could be harmed by a shortage of widgets.</span></div>"
        + paras
        + "</ix:nonNumeric>"
        "<table><tr><td><span style='font-weight:700'>Item 1B. Unresolved Staff Comments</span></td></tr><tr><td>None.</td></tr></table>"
        "</body></html>"
    )
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert sec.start_heading == "Item 1A. Risk Factors"
    assert sec.end_heading.startswith("Item 1B")
    assert sec.units[0]["text"] == "Risks Related to Our Business"
    assert "2025 FY" not in sec.text


def test_page_split_paragraph_is_rejoined_and_continued_headers_dropped():
    first = "Our results could vary because of factors tha"
    html = (
        "<html><body><p><b>Item 1A. Risk Factors</b></p>"
        + "".join(f"<p>{LOREM}</p>" for _ in range(6))
        + f"<p>{first}</p>"
        + "<hr style='page-break-after:always'/><div>14</div><div>Acme Corp | 2025 Form 10-K</div>"
        + "<p><b>Risk Factors (continued)</b></p>"
        + "<p>t we do not control, including demand.</p>"
        + "".join(f"<p>{LOREM}</p>" for _ in range(6))
        + "<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p></body></html>"
    )
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert "(continued)" not in sec.text
    assert "Acme Corp" not in sec.text
    joined = next(u for u in sec.units if u["text"].startswith("Our results could vary"))
    assert (
        joined["text"]
        == "Our results could vary because of factors tha t we do not control, including demand."
    )


def test_heading_sharing_paragraph_with_first_sentence():
    html = (
        "<html><body><p><span style='font-weight:700'>Item 1A. Risk Factors.</span> "
        + LOREM
        + "</p>"
        + "".join(f"<p>{LOREM}</p>" for _ in range(12))
        + "<p><span style='font-weight:700'>Item 1B. Unresolved Staff Comments.</span> None.</p></body></html>"
    )
    sec = extract_item_1a(html, "0000000000-25-000001")
    assert sec.start_heading == "Item 1A. Risk Factors."
    assert sec.units[0]["text"].startswith("The company faces risks")
    assert sec.end_heading.startswith("Item 1B. Unresolved Staff Comments.")


def test_oversized_candidate_fails_loudly():
    html = (
        "<html><body><p><b>Item 1A. Risk Factors</b></p>"
        + "".join(f"<p>{LOREM}</p>" for _ in range(500))
        + "<p><b>Item 2. Properties</b></p></body></html>"
    )
    with pytest.raises(ExtractionFailed, match="over"):
        extract_item_1a(html, "0000000000-25-000001")
