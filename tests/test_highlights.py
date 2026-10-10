"""Highlights ranking/caps and short-title validation (Task 4)."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.highlights import (
    KIND_PRIORITY,
    MAX_PER_CHANGE,
    MAX_TOTAL,
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
    keys = [(KIND_PRIORITY[h.kind], -by_change[h.change_id].score) for h in hl]
    assert keys == sorted(keys)
    counts: dict[str, int] = {}
    for h in hl:
        counts[h.change_id] = counts.get(h.change_id, 0) + 1
        for sid in (h.old_sentence_id, h.new_sentence_id):
            assert sid is None or sid in comp.sentence_index
        assert h.short_title == by_change[h.change_id].short_title
    assert max(counts.values()) <= MAX_PER_CHANGE
    assert hl[0].kind == "potential_became_actual"
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
        heading_ids = {f"{b}:0" for b in (c.old_block_id, c.new_block_id) if b}
        for h in cands:
            for sid in (h.old_sentence_id, h.new_sentence_id):
                assert sid is None or sid in sig_ids | rubric_ids | heading_ids
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
    assert len(t.split()) <= 8 and t.endswith("…")
    assert t.startswith("We depend on a limited number")


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
