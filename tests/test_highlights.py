"""Highlights ranking/caps and short-title validation (Task 4)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.highlights import (
    MAX_PER_CHANGE,
    MAX_TOTAL,
    MEANINGFUL,
    candidate_highlights,
    select_highlights,
    truncate_heading,
)
from pipeline.schema import Comparison
from pipeline.stages_final import validated_short_title

ROOT = Path(__file__).resolve().parents[1]


def fixture() -> Comparison:
    return Comparison.model_validate_json(
        (ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text()
    )


def test_highlights_ranked_capped_and_cited():
    comp = fixture()
    hl = select_highlights(comp.changes, comp.sentence_index)
    assert 1 <= len(hl) <= MAX_TOTAL
    by_change = {c.id: c for c in comp.changes}
    # tier 1 (meaningful change, rule-based evidence) comes first; within it pass 1 walks the
    # changes in score order, so the first card belongs to the top-scoring change with evidence
    meaningful = [c for c in comp.changes if c.change_type in MEANINGFUL]
    with_rule_evidence = [
        c for c in meaningful if any(r for _, r in candidate_highlights(c, comp.sentence_index))
    ]
    top = max(with_rule_evidence, key=lambda c: (c.score, c.id))
    assert hl[0].change_id == top.id
    # cards from essentially-unchanged risks never precede cards from meaningful changes
    tiers = [0 if by_change[h.change_id].change_type in MEANINGFUL else 1 for h in hl]
    assert tiers == sorted(tiers)
    counts: dict[str, int] = {}
    for h in hl:
        counts[h.change_id] = counts.get(h.change_id, 0) + 1
        for sid in (h.old_sentence_id, h.new_sentence_id):
            assert sid is None or sid in comp.sentence_index
        assert h.short_title == by_change[h.change_id].short_title
    assert max(counts.values()) <= MAX_PER_CHANGE
    assert len({(h.change_id, h.kind) for h in hl}) == len(hl)
    # the fixture has a brand-new risk: its card is the "new risk" kind, not a figure or name
    new_changes = {c.id for c in comp.changes if c.change_type == "new"}
    kinds_for_new = [h.kind for h in hl if h.change_id in new_changes]
    assert kinds_for_new and kinds_for_new[0] == "new_risk"
    assert hl == comp.highlights  # the fixture file carries exactly the ranked selection


def test_candidates_come_only_from_existing_evidence():
    comp = fixture()
    for c in comp.changes:
        cands = candidate_highlights(c, comp.sentence_index)
        sig_ids = {
            sid
            for h in c.signals.hypothetical_to_actual
            + c.signals.new_quantities
            + c.signals.new_entities
            for sid in h.old_sentence_ids + h.new_sentence_ids
        }
        rubric_ids = {
            sid for a in c.interpretation.rubric if a.answer for sid in a.cited_sentence_ids
        }
        # a new/dropped risk cites its heading or first body sentence
        heading_ids = {f"{b}:{n}" for b in (c.old_block_id, c.new_block_id) if b for n in (0, 1)}
        for h, rule_based in cands:
            for sid in (h.old_sentence_id, h.new_sentence_id):
                assert sid is None or sid in sig_ids | rubric_ids | heading_ids
            if not rule_based:
                assert {h.old_sentence_id, h.new_sentence_id} - {None} <= rubric_ids
        if c.change_type == "largely_unchanged" and not (
            c.signals.new_quantities or c.signals.new_entities or c.signals.hypothetical_to_actual
        ):
            assert cands == []


def test_select_is_deterministic():
    comp = fixture()
    a = [h.model_dump() for h in select_highlights(comp.changes, comp.sentence_index)]
    b = [
        h.model_dump() for h in select_highlights(list(reversed(comp.changes)), comp.sentence_index)
    ]
    assert a == b


def test_truncate_heading():
    assert truncate_heading("Short heading.") == "Short heading"
    long = "We depend on a limited number of third-party foundries to manufacture our products and components."
    t = truncate_heading(long)
    # no ellipsis any more; the cut never ends mid-clause (the dangling "to" is dropped)
    assert t == "We depend on a limited number of third-party foundries"
    assert truncate_heading(long, 8) == "We depend on a limited number of third-party"


def test_validated_short_title_accepts_good_and_falls_back_on_bad():
    heading = "Export controls could restrict our sales to China and harm our results."
    assert (
        validated_short_title(heading, "Export controls on China sales")
        == "Export controls on China sales"
    )
    # too long -> fallback
    fb = validated_short_title(heading, "one two three four five six seven eight nine")
    assert fb.startswith("Export controls could") and len(fb.split()) <= 8
    # banned language -> fallback
    assert validated_short_title(heading, "China sales are likely restricted") == fb
    # not anchored to the heading -> fallback
    assert validated_short_title(heading, "Widget pricing pressure") == fb
    # missing -> fallback
    assert validated_short_title(heading, None) == fb


def test_published_fixture_has_short_titles_and_highlights():
    d = json.loads((ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text())
    assert all(1 <= len(c["short_title"].split()) <= 8 for c in d["changes"])
    assert 1 <= len(d["highlights"]) <= 5


def test_short_titles_batch_is_one_call_and_parsed():
    from pipeline.llm import LLMClient, short_titles_raw

    calls = []

    def complete(system: str, user: str) -> str:
        calls.append(user)
        return '{"titles": [{"change_id": "aaaaaaaaaaaaaaaa", "short_title": "Export controls on China sales"}, {"change_id": "bbbbbbbbbbbbbbbb", "short_title": "x"}]}'

    client = LLMClient(provider="huggingface", model_id="hf:test", _complete=complete)
    raw = short_titles_raw(
        client,
        [
            ("aaaaaaaaaaaaaaaa", "Export controls could restrict sales."),
            ("bbbbbbbbbbbbbbbb", "Other heading."),
        ],
    )
    assert len(calls) == 1 and "aaaaaaaaaaaaaaaa\tExport controls could restrict sales." in calls[0]
    assert {t["change_id"]: t["short_title"] for t in raw["titles"]}[
        "aaaaaaaaaaaaaaaa"
    ] == "Export controls on China sales"


def test_short_titles_batch_returns_none_after_bad_json():
    from pipeline.llm import LLMClient, short_titles_raw

    client = LLMClient(
        provider="huggingface", model_id="hf:test", _complete=lambda s, u: "not json"
    )
    assert short_titles_raw(client, [("aaaaaaaaaaaaaaaa", "H.")]) is None


def test_potential_became_actual_needs_both_sides_and_one_card_per_kind_per_change():
    comp = fixture()
    hl = select_highlights(comp.changes, comp.sentence_index)
    for h in hl:
        if h.kind == "potential_became_actual":
            assert h.old_sentence_id and h.new_sentence_id
    assert len({(h.change_id, h.kind) for h in hl}) == len(hl)


def test_figures_prefer_dollar_amounts_then_percentages():
    from pipeline.highlights import _figure_order

    assert _figure_order("$4.5 billion") < _figure_order("15%") < _figure_order("5 countries")
    assert _figure_order("$4.5 billion") < _figure_order("$60 million")  # larger first
    assert _figure_order("12% -> 22%") < _figure_order("12%")  # the new value counts
    from pipeline.highlights import _magnitude

    assert _magnitude("$4.5 billion") == 4.5e9 and _magnitude("$750 million -> $1.0 billion") == 1e9


def test_quote_order_prefers_self_contained_sentences():
    from pipeline.highlights import _quote_order

    assert _quote_order("Such requests have been expensive.") == 1
    assert _quote_order("Export controls increase the cost of compliance.") == 0
    assert _quote_order(None) == 0


def test_new_risk_card_quotes_the_first_body_sentence():
    comp = fixture()
    hl = select_highlights(comp.changes, comp.sentence_index)
    new_ids = {c.new_block_id for c in comp.changes if c.change_type == "new"}
    for h in hl:
        if h.kind == "new_risk":
            block, _, n = h.new_sentence_id.rpartition(":")
            assert block in new_ids
            assert n == "1" or f"{block}:1" not in comp.sentence_index
