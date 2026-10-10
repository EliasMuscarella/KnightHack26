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
    ctx = run_pipeline("FIXTUR", settings, fixture=True, until_stage=4)
    assert "matches" in ctx.outputs and "diff_records" not in ctx.outputs


def test_rubric_json_matches_module():
    from pipeline.rubric import export

    on_disk = json.loads((ROOT / "contract" / "rubric.json").read_text())
    assert on_disk == export()


def test_cancel_event_stops_between_stages(e2e):
    import threading

    from pipeline.errors import PipelineError

    settings, *_ = e2e
    cancel = threading.Event()
    seen = []

    def progress(ev):
        seen.append((ev.stage, ev.status))
        if ev.stage == 2 and ev.status == "done":
            cancel.set()

    with pytest.raises(PipelineError, match="cancelled"):
        run_pipeline("FIXTUR", settings, fixture=True, progress=progress, cancel=cancel)
    assert (3, "started") not in seen


def test_cli_force_flag_exists():
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "pipeline.run", "--help"], capture_output=True, text=True, cwd=ROOT
    )
    assert "--force" in r.stdout and "--refresh-llm" in r.stdout


def test_non_fixture_run_refuses_lexical_fallback(monkeypatch, tmp_path):
    from pipeline.config import Settings
    from pipeline.embed import load_embedder
    from pipeline.errors import ConfigError

    monkeypatch.delenv("RISKDIFF_EMBED_BACKEND", raising=False)
    monkeypatch.delenv("RISKDIFF_ALLOW_LEXICAL", raising=False)
    s = Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path,
        embed_model="definitely/not-a-model-xyz",
        llm_model="x",
        gemini_model="y",
        api_origin="o",
    )
    with pytest.raises(ConfigError, match="RISKDIFF_ALLOW_LEXICAL"):
        load_embedder(s, allow_lexical=False)
    assert load_embedder(s, allow_lexical=True).backend == "lexical-fallback"


def test_same_text_under_other_accessions_does_not_hit_stale_cache(e2e, tmp_path):
    """Identical sentences under different accession numbers must get their own cache entries."""
    import pipeline.run as run_mod
    from pipeline.types import FetchResult

    settings, *_ = e2e
    orig = run_mod._fixture_fetch_result

    def swapped() -> FetchResult:
        fr = orig()
        return fr.model_copy(
            update={
                "old": fr.old.model_copy(update={"accession_number": "0000000000-22-000009"}),
                "new": fr.new.model_copy(update={"accession_number": "0000000000-23-000009"}),
            }
        )

    run_mod._fixture_fetch_result = swapped
    try:
        ctx = run_pipeline("FIXTUR", settings, fixture=True)
    finally:
        run_mod._fixture_fetch_result = orig
    comp = ctx.outputs["comparison"]
    assert comp.old_filing.accession_number == "0000000000-22-000009"
    assert all(k.startswith("0000000000-2") for k in comp.sentence_index)
