"""End-to-end on the FIXTURE filing pair: determinism, caching, validity, --until-stage."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pipeline.run import run_pipeline
from pipeline.schema import Comparison

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    from pipeline.config import Settings

    data_dir = tmp_path_factory.mktemp("data")
    os.environ["RISKDIFF_EMBED_BACKEND"] = "lexical"  # no network; deterministic
    settings = Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=data_dir,
        embed_model="BAAI/bge-m3",
        llm_model="x",
        gemini_model="y",
        api_origin="http://localhost:3000",
    )
    ctx1 = run_pipeline("FIXTUR", settings, fixture=True)
    text1 = Path(ctx1.outputs["published_path"]).read_text()
    ctx2 = run_pipeline("FIXTUR", settings, fixture=True, use_cache=False)
    text2 = Path(ctx2.outputs["published_path"]).read_text()
    ctx3 = run_pipeline("FIXTUR", settings, fixture=True)
    text3 = Path(ctx3.outputs["published_path"]).read_text()
    os.environ.pop("RISKDIFF_EMBED_BACKEND", None)
    return settings, ctx1, ctx3, text1, text2, text3


def test_output_is_byte_identical_across_runs(e2e):
    _, _, _, t1, t2, t3 = e2e
    assert t1 == t2 == t3


def test_output_validates_and_is_fixture_scratch_only(e2e):
    settings, ctx1, _, t1, _, _ = e2e
    comp = Comparison.model_validate_json(t1)
    assert comp.is_fixture is True
    assert Path(ctx1.outputs["published_path"]).parent == settings.data_dir / "scratch"
    assert not (settings.data_dir / "published").exists() or not list(
        (settings.data_dir / "published").iterdir()
    )
    assert comp.summary.total_changes == len(comp.changes) >= 10
    assert comp.summary.by_change_type["new"] >= 1 and comp.summary.by_change_type["removed"] >= 1
    assert comp.model_ids.embedding_backend == "lexical-fallback"
    assert comp.summary.interpretation_status == "unavailable"
    for c in comp.changes:
        assert c.interpretation.status in ("unavailable", "skipped")
        for line in c.score_breakdown:
            assert line.cited_sentence_ids and all(
                s in comp.sentence_index for s in line.cited_sentence_ids
            )
        for s in c.sentences:
            loc = comp.sentence_index[s.id]
            assert loc.text == s.text


def test_sentence_offsets_match_section_text(e2e):
    _, ctx1, _, t1, _, _ = e2e
    comp = Comparison.model_validate_json(t1)
    segs = ctx1.outputs["segments"]
    for sid, loc in comp.sentence_index.items():
        text = segs[loc.side].text
        assert text[loc.char_start : loc.char_end] == loc.text, sid


def test_third_run_is_all_cache_hits(e2e):
    _, _, ctx3, _, _, _ = e2e
    assert ctx3.cache.misses == []
    assert "diff" in ctx3.cache.hits and "signals" in ctx3.cache.hits


def test_until_stage_stops_early(e2e):
    settings, *_ = e2e
    os.environ["RISKDIFF_EMBED_BACKEND"] = "lexical"
    try:
        ctx = run_pipeline("FIXTUR", settings, fixture=True, until_stage=4)
    finally:
        os.environ.pop("RISKDIFF_EMBED_BACKEND", None)
    assert "matches" in ctx.outputs and "diff_records" not in ctx.outputs


def test_rubric_json_matches_module():
    from pipeline.rubric import export

    on_disk = json.loads((ROOT / "contract" / "rubric.json").read_text())
    assert on_disk == export()
