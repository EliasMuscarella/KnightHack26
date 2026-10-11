"""Regression tests for the integrity findings (scripts/check_integrity.py) fixed in the pipeline.

Every real case loads its sentences from the committed published files by sentence id, so the
text stays verbatim (nothing is pasted or paraphrased). Clearly synthetic inputs say so.
"""

from __future__ import annotations

import json
from collections import Counter
from functools import cache
from pathlib import Path

import pytest

from pipeline import diff as diff_mod
from pipeline import highlights as hl
from pipeline import segment as seg_mod
from pipeline import signals as sig_mod
from pipeline.schema import Comparison, Sentence
from pipeline.signals import SignalContext
from pipeline.types import RiskBlock, SentenceRec
from tests.test_diff import NEW, OLD, block
from tests.test_segment import U, section_from_units

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
NVDA = "NVDA_2025_2026"
SF = "SF_2024_2025"


@cache
def comparison(name: str) -> Comparison:
    return Comparison.model_validate(json.loads((PUBLISHED / f"{name}.json").read_text()))


def text(name: str, sid: str) -> str:
    return comparison(name).sentence_index[sid].text


def change(name: str, change_id: str):  # noqa: ANN201
    return next(c for c in comparison(name).changes if c.id == change_id)


def block_from_index(name: str, block_id: str | None) -> RiskBlock | None:
    """Rebuild a RiskBlock from the published sentence index (heading = sentence 0)."""
    if block_id is None:
        return None
    comp = comparison(name)
    sents = sorted(
        (s for s in comp.sentence_index.values() if s.block_id == block_id),
        key=lambda s: int(s.id.rsplit(":", 1)[1]),
    )
    recs = [
        SentenceRec(
            id=s.id,
            text=s.text,
            char_start=s.char_start,
            char_end=s.char_end,
            is_heading=s.is_heading,
        )
        for s in sents
    ]
    return RiskBlock(
        id=block_id,
        accession_number=sents[0].accession_number,
        index=int(block_id.rsplit(":", 1)[1]),
        heading=sents[0].text,
        body="\n".join(s.text for s in sents[1:]),
        section_group=None,
        sentences=recs,
        char_start=sents[0].char_start,
        char_end=sents[-1].char_end,
    )


def context(name: str, change_id: str, sentences: list[Sentence] | None = None) -> SignalContext:
    c = change(name, change_id)
    return SignalContext(
        old=block_from_index(name, c.old_block_id),
        new=block_from_index(name, c.new_block_id),
        sentences=list(sentences if sentences is not None else c.sentences),
        similarity=c.similarity,
        added_word_count=c.stats.added_word_count,
        removed_word_count=c.stats.removed_word_count,
        old_word_count=c.stats.old_word_count,
        new_word_count=c.stats.new_word_count,
    )


# Reference for "what should be marked" (scripts/check_integrity.py, expected_insert_words): a word
# diff that ignores case, whitespace and punctuation.
def _norm_words(s: str) -> list[str]:
    return [t.casefold() for t in diff_mod.TOKEN_RE.findall(s) if t.strip() and t[0].isalnum()]


def _expected_insert_words(old: str, new: str) -> Counter:
    import difflib

    a, b = _norm_words(old), _norm_words(new)
    out: Counter = Counter()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            out.update(b[j1:j2])
    return out


def _marked(spans, op: str) -> Counter:  # noqa: ANN001
    out: Counter = Counter()
    for sp in spans:
        if sp.op == op:
            out.update(_norm_words(sp.text))
    return out


# ---------------------------------------------------------------------------------------------
# 1. PAIR: potential -> actual only from aligned pairs
# ---------------------------------------------------------------------------------------------

NVDA_ANTITRUST_CHANGE = "a4156a06454f6dfd"
NVDA_OLD_INVESTIGATING = "0001045810-25-000023:19:41"
NVDA_NEW_PRELIMINARY = "0001045810-26-000021:21:41"


def test_aligned_antitrust_pair_still_fires_via_status_change():
    c = change(NVDA, NVDA_ANTITRUST_CHANGE)
    new_s = next(s for s in c.sentences if s.id == NVDA_NEW_PRELIMINARY)
    assert new_s.status == "modified" and new_s.counterpart_id == NVDA_OLD_INVESTIGATING
    hits = sig_mod.hypothetical_to_actual(context(NVDA, NVDA_ANTITRUST_CHANGE))
    pair = [h for h in hits if h.new_sentence_ids == [NVDA_NEW_PRELIMINARY]]
    assert len(pair) == 1
    assert pair[0].old_sentence_ids == [NVDA_OLD_INVESTIGATING]
    assert pair[0].value == "investigating -> published their preliminary finding"


def test_every_potential_to_actual_hit_on_published_data_is_an_aligned_pair():
    for name in (NVDA, SF):
        for c in comparison(name).changes:
            by_id = {s.id: s for s in c.sentences}
            for h in sig_mod.hypothetical_to_actual(context(name, c.id)):
                (o,), (n,) = h.old_sentence_ids, h.new_sentence_ids
                assert by_id[n].status == "modified" and by_id[n].counterpart_id == o, (c.id, h)


def test_added_sentence_sharing_boilerplate_with_unrelated_hedged_sentence_is_not_paired():
    """SYNTHETIC: an added sentence about a legal fine shares 10-K boilerplate with an unrelated
    hedged sentence about advertising demand (the live symptom). Both would pass the old
    lexical-overlap pairing (>= 0.25); they are not an aligned pair, so no signal."""
    old_hedged = (
        "Reduced advertising demand could cause our business, financial condition and results "
        "of operations to be materially and adversely affected."
    )
    new_added = (
        "In 2025, regulators imposed a fine on us, and our business, financial condition and "
        "results of operations were materially and adversely affected."
    )
    assert diff_mod.lexical_ratio(old_hedged, new_added) >= 0.25  # the old trap
    old = block(OLD, 1, "SYNTHETIC heading.", [old_hedged])
    new = block(NEW, 1, "SYNTHETIC heading.", [new_added])
    sentences = [
        Sentence(
            id=f"{OLD}:1:0",
            side="old",
            status="unchanged",
            text="SYNTHETIC heading.",
            pair_index=0,
            counterpart_id=f"{NEW}:1:0",
        ),
        Sentence(
            id=f"{NEW}:1:0",
            side="new",
            status="unchanged",
            text="SYNTHETIC heading.",
            pair_index=0,
            counterpart_id=f"{OLD}:1:0",
        ),
        Sentence(id=f"{OLD}:1:1", side="old", status="removed", text=old_hedged, pair_index=1),
        Sentence(id=f"{NEW}:1:1", side="new", status="added", text=new_added, pair_index=2),
    ]
    ctx = SignalContext(
        old=old,
        new=new,
        sentences=sentences,
        similarity=0.9,
        added_word_count=10,
        removed_word_count=10,
        old_word_count=20,
        new_word_count=20,
    )
    assert sig_mod.hypothetical_to_actual(ctx) == []
    # the wording alone would fire: only the missing alignment keeps this pair out
    assert sig_mod.status_change(old_hedged, new_added) is not None


def test_concluded_marker_already_present_last_year_is_not_a_status_change():
    """NVDA a4156a06454f6dfd: "which have been imposed" appears in both years' sentence; only the
    in-progress wording changed, so this is not "potential became actual"."""
    old = text(NVDA, "0001045810-25-000023:19:30")
    new = text(NVDA, "0001045810-26-000021:21:30")
    assert "imposed" in old and "imposed" in new
    assert sig_mod.status_change(old, new) is None
    # "is considering restrictions ... if adopted" -> "the USG adopted ... restrictions" still fires
    old2 = text(NVDA, "0001045810-25-000023:19:102")
    new2 = text(NVDA, "0001045810-26-000021:21:100")
    assert sig_mod.status_change(old2, new2) == ("considering", "adopted")


# ---------------------------------------------------------------------------------------------
# 2. CASE: case / whitespace / punctuation are not changes
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "old_id,new_id",
    [
        ("0001045810-25-000023:19:95", "0001045810-26-000021:21:91"),
        ("0001045810-25-000023:19:96", "0001045810-26-000021:21:92"),
        ("0001045810-25-000023:19:98", "0001045810-26-000021:21:94"),
    ],
)
def test_export_vs_Export_is_not_a_change(old_id, new_id):
    old, new = text(NVDA, old_id), text(NVDA, new_id)
    os_, ns_ = diff_mod.word_spans(old, new)
    assert "".join(s.text for s in os_) == old and "".join(s.text for s in ns_) == new
    assert [s.text for s in os_ if s.op == "delete"][0] == "Excessive or shifting "
    assert not any("export" in s.text.casefold() for s in os_ if s.op == "delete")
    assert not any("export" in s.text.casefold() for s in ns_ if s.op == "insert")


def test_case_only_findings_from_the_baseline_are_gone():
    """The baseline's CASE findings (docs/INTEGRITY_REPORT.before.md) that were pure case /
    punctuation differences: the current diff marks no word the reference diff leaves equal."""
    pairs = [
        (NVDA, "0001045810-25-000023:19:55", "0001045810-26-000021:21:65"),
        (NVDA, "0001045810-25-000023:19:107", "0001045810-26-000021:21:106"),
        (NVDA, "0001045810-25-000023:12:14", "0001045810-26-000021:13:14"),
        (NVDA, "0001045810-25-000023:6:14", "0001045810-26-000021:7:14"),
        (NVDA, "0001045810-25-000023:6:36", "0001045810-26-000021:7:40"),
        (NVDA, "0001045810-25-000023:8:9", "0001045810-26-000021:9:9"),
        (NVDA, "0001045810-25-000023:15:2", "0001045810-26-000021:16:2"),
        (NVDA, "0001045810-25-000023:14:7", "0001045810-26-000021:15:7"),
        (NVDA, "0001045810-25-000023:3:1", "0001045810-26-000021:4:1"),
        (NVDA, "0001045810-25-000023:20:0", "0001045810-26-000021:22:0"),
        (SF, "0000950170-25-027702:14:17", "0001193125-26-067130:14:19"),
        (SF, "0000950170-25-027702:14:37", "0001193125-26-067130:14:37"),
        (SF, "0000950170-25-027702:14:40", "0001193125-26-067130:14:39"),
        (SF, "0000950170-25-027702:20:9", "0001193125-26-067130:20:4"),
        (SF, "0000950170-25-027702:5:7", "0001193125-26-067130:5:6"),
        (SF, "0000950170-25-027702:18:9", "0001193125-26-067130:18:5"),
    ]
    for name, o_id, n_id in pairs:
        old, new = text(name, o_id), text(name, n_id)
        _, ns_ = diff_mod.word_spans(old, new)
        assert "".join(s.text for s in ns_) == new
        extra = _marked(ns_, "insert") - _expected_insert_words(old, new)
        assert not extra, (o_id, n_id, extra)


def test_word_spans_reproduce_text_and_never_mark_punctuation_only_on_published_pairs():
    for name in (NVDA, SF):
        for c in comparison(name).changes:
            by_id = {s.id: s for s in c.sentences}
            for s in c.sentences:
                if s.side != "new" or s.status != "modified":
                    continue
                old = by_id[s.counterpart_id].text
                os_, ns_ = diff_mod.word_spans(old, s.text)
                assert "".join(x.text for x in os_) == old
                assert "".join(x.text for x in ns_) == s.text
                for sp in os_ + ns_:
                    if sp.op != "equal":
                        assert any(ch.isalnum() for ch in sp.text), (s.id, sp)


def test_whitespace_and_case_alone_are_not_changes():
    """SYNTHETIC: case, a line break vs a space, and curly vs straight quotes."""
    os_, ns_ = diff_mod.word_spans(
        "Export controls’ scope  may change.", "export controls' scope may change"
    )
    assert all(s.op == "equal" for s in os_ + ns_)


# ---------------------------------------------------------------------------------------------
# 3. TITLES: deterministic short titles
# ---------------------------------------------------------------------------------------------


def test_every_published_heading_gets_an_acceptable_short_title():
    for name in (NVDA, SF):
        comp = comparison(name)
        for c in comp.changes:
            t = hl.short_title_from_heading(c.title, company_name=comp.company.name)
            assert not hl.title_problems(t, comp.company.name), (c.id, t)
            assert not t.endswith(("…", "...")) and len(t.split()) <= 10


def test_live_title_fragments_are_not_produced():
    complex_laws = (
        "We are subject to complex laws, rules, regulations and other actions, "
        "including restrictions on the export of our products, which may adversely impact our "
        "business."
    )
    tech = (
        "The technology industry, including the Internet, is characterized by rapid change and "
        "we face intense competition."
    )
    t1 = hl.short_title_from_heading(complex_laws)
    t2 = hl.short_title_from_heading(tech)
    assert t1 != "We are subject to complex laws" and not hl.title_problems(t1)
    assert t1 == "We are subject to complex laws, rules, regulations"
    assert t2 != "The technology industry, including" and not hl.title_problems(t2)
    assert t2 == "The technology industry, including the Internet"
    assert hl.title_problems("We are subject to complex laws")
    assert hl.title_problems("The technology industry, including")


def test_bare_company_name_is_never_the_title():
    """SYNTHETIC heading built around the real SF company name: the longest clause candidate
    would be the company name itself, so step 4 (first words) is used instead."""
    name = comparison(SF).company.name  # "STIFEL FINANCIAL CORP"
    heading = (
        "Stifel Financial Corp., as a holding company, depends on dividends, distributions and "
        "other payments from its subsidiaries to fund its obligations."
    )
    t = hl.short_title_from_heading(heading, company_name=name)
    assert hl.title_problems("Stifel Financial Corp", name)
    assert hl.title_problems("STIFEL FINANCIAL", name)
    assert not hl.title_problems(t, name), t
    assert t.casefold().replace(".", "").replace(",", "") not in (
        "stifel financial corp",
        "stifel financial",
    )


def test_title_spec_steps():
    f = hl.short_title_from_heading
    assert f("  “Short heading.”  ") == "Short heading"  # step 1 + 2
    # step 4 fallback when no clause boundary qualifies; trailing DANGLING words dropped
    assert (
        f("We depend on a limited number of third-party foundries to manufacture our products.")
        == "We depend on a limited number of third-party foundries"
    )
    assert hl.title_problems("We are subject to complex laws, rules…") == ["ends with an ellipsis"]
    assert "ends on punctuation" in hl.title_problems("Export controls restrict sales,")
    assert hl.truncate_heading("Short heading.") == "Short heading"


# ---------------------------------------------------------------------------------------------
# 4. ENTITY: generic bodies, administrations and codes are not newly named parties
# ---------------------------------------------------------------------------------------------


def test_new_entities_drop_bare_administrations():
    sid = "0001045810-26-000021:21:71"
    s = text(NVDA, sid)
    assert "Biden Administration" in s and "Trump Administration" in s
    values = [h.value for h in sig_mod.new_entities(context(NVDA, NVDA_ANTITRUST_CHANGE))]
    assert "Biden Administration" not in values and "Trump Administration" not in values
    assert "GAIN AI Act" in values  # a real new law named in the same sentence survives
    assert not any(v.endswith(" in") for v in values) and "D:4" not in values


def test_new_entities_drop_generic_regulators():
    for sid in ("0001193125-26-067130:20:2", "0001193125-26-067130:20:11"):
        assert "SEC" in text(SF, sid)
    values = [h.value for h in sig_mod.new_entities(context(SF, "61ffb76925cf3bc2"))]
    assert "SEC" not in values


def test_generic_entity_rules():
    g = sig_mod.is_generic_entity
    for v in (
        "SEC",
        "the Trump Administration’s",
        "Biden Administration",
        "U.S.",
        "United States",
        "Congress",
        "Federal Reserve",
        "European Union",
        "FTC",
        "Nasdaq, Inc.",
        "first quarter of fiscal 2026",
    ):
        assert g(v), v
    for v in ("GAIN AI Act", "OpenAI", "China", "U.S. Department of Commerce", "EU AI Act"):
        assert not g(v), v


def test_clean_entity_keeps_dropping_codes_and_trailing_prepositions():
    # "AI Diffusion IFR in" (sentence 0001045810-26-000021:21:64) and "D:4" (21:47, 21:63)
    assert "AI Diffusion IFR" in text(NVDA, "0001045810-26-000021:21:64")
    assert "D:4" in text(NVDA, "0001045810-26-000021:21:47")
    assert sig_mod.clean_entity("AI Diffusion IFR in") == "AI Diffusion IFR"
    assert sig_mod.clean_entity("D:4") is None


# ---------------------------------------------------------------------------------------------
# 5. PREAMBLE: the Item 1A introduction is never a risk block
# ---------------------------------------------------------------------------------------------

NVDA_INTRO_BLOCK = "0001045810-26-000021:0"


def _block_units(block_id: str, n_body: int = 3) -> list[dict]:
    """A real risk heading (bold) followed by one plain body paragraph of real sentences."""
    blk = block_from_index(NVDA, block_id)
    assert blk is not None
    body = " ".join(s.text for s in blk.sentences[1 : 1 + n_body])
    return [U(blk.heading, emph=True), U(body)]


def _intro_units(as_lead: bool = False) -> list[dict]:
    heading = text(NVDA, f"{NVDA_INTRO_BLOCK}:0")
    body = " ".join(text(NVDA, f"{NVDA_INTRO_BLOCK}:{i}") for i in (1, 2))
    if as_lead:  # one paragraph: bold lead sentence, then plain text
        return [U(f"{heading} {body}", runs=[[heading, True], [f" {body}", False]])]
    return [U(heading, emph=True), U(body)]


REAL_BLOCKS = ("0001045810-26-000021:5", "0001045810-26-000021:6", "0001045810-26-000021:7")


@pytest.mark.parametrize("as_lead", [False, True])
def test_nvda_intro_is_not_a_block(as_lead):
    group = text(NVDA, "0001045810-26-000021:1:0")  # "Risks Related to Our Industry and Markets"
    units = _intro_units(as_lead) + [U(group, emph=True)]
    for b in REAL_BLOCKS:
        units += _block_units(b)
    seg = seg_mod.segment(section_from_units(units, acc="0001045810-26-000021"))
    intro = text(NVDA, f"{NVDA_INTRO_BLOCK}:0")
    assert all(b.heading != intro and not b.heading.startswith("The following") for b in seg.blocks)
    assert [b.heading for b in seg.blocks] == [
        block_from_index(NVDA, b).heading for b in REAL_BLOCKS
    ]
    assert seg.blocks[0].section_group == group


def test_nvda_intro_then_risk_factors_summary_is_skipped():
    group = text(NVDA, "0001045810-26-000021:1:0")
    bullets = [text(NVDA, "0001045810-26-000021:1:1"), text(NVDA, "0001045810-26-000021:1:2")]
    units = _intro_units() + [U("Risk Factors Summary", emph=True), U(group, emph=True)]
    units += [U(f"• {b}") for b in bullets]
    units += [U(group, emph=True)]
    for b in REAL_BLOCKS:
        units += _block_units(b)
    seg = seg_mod.segment(section_from_units(units, acc="0001045810-26-000021"))
    headings = [b.heading for b in seg.blocks]
    assert headings == [block_from_index(NVDA, b).heading for b in REAL_BLOCKS]
    assert len(headings) == len(set(headings))
    assert seg.section_groups == [group]


# ---------------------------------------------------------------------------------------------
# 6. YEARS: stage 0 selection and fiscal-year labels for a January fiscal year end
#    (all submissions rows and accession numbers below are SYNTHETIC: 0009999999-YY-9xxxxx)
# ---------------------------------------------------------------------------------------------


def _row(acc: str, form: str, filed: str, period: str, doc: str | None = None) -> dict:
    return {
        "accessionNumber": acc,
        "filingDate": filed,
        "reportDate": period,
        "form": form,
        "primaryDocument": doc if doc is not None else f"synthetic-{acc[-6:]}.htm",
    }


def _block(rows: list[dict]) -> dict:
    keys = ["accessionNumber", "filingDate", "reportDate", "form", "primaryDocument"]
    return {k: [r[k] for r in rows] for k in keys}


JAN_2026 = _row("0009999999-26-900002", "10-K", "2026-03-04", "2026-01-31")
JAN_2025 = _row("0009999999-25-900001", "10-K", "2025-03-10", "2025-01-31")
JAN_2024 = _row("0009999999-24-900000", "10-K", "2024-03-07", "2024-01-31")


def _collect(tmp_path, recent: list[dict], pages: dict[str, list[dict]] | None = None):  # noqa: ANN001, ANN202
    from pipeline.sec_fetch import _collect_filings

    pages = pages or {}
    subs = {
        "filings": {
            "recent": _block(recent),
            "files": [{"name": name} for name in pages],
        }
    }
    for name, rows in pages.items():
        p = tmp_path / "sec" / "submissions" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(_block(rows)))
    # the paginated pages are cached on disk, so no client (and no network) is needed
    return _collect_filings(None, "0009999999", tmp_path, subs)  # type: ignore[arg-type]


def _fy_html(fy: int) -> str:
    return (
        '<html><body><div style="display:none"><ix:header><ix:hidden>'
        f'<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="c-1">{fy}</ix:nonNumeric>'
        "</ix:hidden></ix:header></div></body></html>"
    )


def test_two_consecutive_january_periods_pick_the_two_newest_originals(tmp_path):
    from pipeline.sec_fetch import fiscal_year_from_html, select_two_latest

    eightk = _row("0009999999-26-900003", "8-K", "2026-06-03", "")
    filings = _collect(tmp_path, [eightk, JAN_2026, JAN_2025, JAN_2024])
    old, new, note, considered = select_two_latest(filings)
    assert (old["accessionNumber"], new["accessionNumber"]) == (
        JAN_2025["accessionNumber"],
        JAN_2026["accessionNumber"],
    )
    assert "amendments excluded" in note
    # labels: from the dei fact, and from the period of report when there is none
    fy_old = fiscal_year_from_html(_fy_html(2025), old["reportDate"])
    fy_new = fiscal_year_from_html(_fy_html(2026), new["reportDate"])
    assert (fy_old[0], fy_new[0]) == (2025, 2026)
    assert fiscal_year_from_html("<html></html>", old["reportDate"]) == (2025, "period_of_report")
    assert fiscal_year_from_html("<html></html>", new["reportDate"]) == (2026, "period_of_report")


def test_empty_report_date_row_does_not_skip_a_year(tmp_path):
    from pipeline.sec_fetch import select_two_latest

    no_period = dict(JAN_2025, reportDate="")
    filings = _collect(tmp_path, [JAN_2026, no_period, JAN_2024])
    old, new, _, _ = select_two_latest(filings)
    assert new["accessionNumber"] == JAN_2026["accessionNumber"]
    assert old["accessionNumber"] == JAN_2025["accessionNumber"]


def test_amendment_between_two_originals_is_ignored(tmp_path):
    from pipeline.sec_fetch import select_two_latest

    amend = _row("0009999999-25-900009", "10-K/A", "2025-05-01", "2025-01-31")
    filings = _collect(tmp_path, [JAN_2026, amend, JAN_2025, JAN_2024])
    old, new, note, considered = select_two_latest(filings)
    assert (old["accessionNumber"], new["accessionNumber"]) == (
        JAN_2025["accessionNumber"],
        JAN_2026["accessionNumber"],
    )
    assert "amendments excluded" in note
    assert any(c.startswith("10-K/A 0009999999-25-900009") for c in considered)


def test_older_original_in_a_paginated_history_file(tmp_path):
    from pipeline.sec_fetch import select_two_latest

    recent = [_row(f"0009999999-26-90010{i}", "10-Q", "2026-0{i}-01", "") for i in range(1, 4)]
    recent = [JAN_2026] + recent
    page = "CIK0009999999-submissions-001.json"
    filings = _collect(tmp_path, recent, {page: [JAN_2025, JAN_2024]})
    old, new, _, _ = select_two_latest(filings)
    assert (old["accessionNumber"], new["accessionNumber"]) == (
        JAN_2025["accessionNumber"],
        JAN_2026["accessionNumber"],
    )


def test_fiscal_year_focus_inside_hidden_header_after_other_dei_facts():
    from pipeline.sec_fetch import fiscal_year_from_html

    html = (
        '<html><head><style>.x{color:red}</style></head><body><div style="display:none">'
        "<ix:header><ix:hidden>"
        '<ix:nonNumeric name="dei:AmendmentFlag" contextRef="c-1">false</ix:nonNumeric>'
        '<ix:nonNumeric name="dei:CurrentFiscalYearEndDate" contextRef="c-1">--01-31</ix:nonNumeric>'
        '<ix:nonNumeric name="dei:DocumentFiscalPeriodFocus" contextRef="c-1">FY</ix:nonNumeric>'
        '<ix:nonNumeric contextRef="c-1" name="dei:DocumentFiscalYearFocus" id="f-4">'
        "<span>2026</span></ix:nonNumeric>"
        '</ix:hidden><ix:resources><xbrli:context id="c-1"><xbrli:period>'
        "<xbrli:startDate>2025-02-01</xbrli:startDate><xbrli:endDate>2026-01-31</xbrli:endDate>"
        "</xbrli:period></xbrli:context></ix:resources></ix:header></div>"
        '<p>Fiscal year ended <ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="c-1">'
        "January 31, 2026</ix:nonNumeric></p></body></html>"
    )
    assert fiscal_year_from_html(html, "2026-01-31") == (2026, "dei:DocumentFiscalYearFocus")


def test_fiscal_year_focus_of_another_context_listed_first_is_not_used():
    """A DocumentFiscalYearFocus fact for a prior-year comparative context appears before the
    document's own fact; the label must come from the document's context (the context of
    dei:DocumentPeriodEndDate)."""
    from pipeline.sec_fetch import fiscal_year_from_html

    html = (
        '<html><body><div style="display:none"><ix:header><ix:hidden>'
        '<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="c-prior">2025</ix:nonNumeric>'
        '<ix:nonNumeric name="dei:DocumentType" contextRef="c-cur">10-K</ix:nonNumeric>'
        '<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="c-cur">2026</ix:nonNumeric>'
        "</ix:hidden></ix:header></div>"
        '<p><ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="c-cur">'
        "January 31, 2026</ix:nonNumeric></p></body></html>"
    )
    assert fiscal_year_from_html(html, "2026-01-31") == (2026, "dei:DocumentFiscalYearFocus")
