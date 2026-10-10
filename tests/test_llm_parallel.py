"""Stage 7 runs LLM calls concurrently: output must not depend on concurrency or call order.
Also covers cancellation mid-stage and the per-stage timing table."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

import pytest

from pipeline.config import Settings
from pipeline.llm import SHORT_TITLE_SYSTEM, LLMClient
from pipeline.rubric import QUESTIONS
from pipeline.run import format_timings, run_pipeline
from pipeline.stages_final import llm_concurrency

_SID = re.compile(r"^\[([^\]]+)\] ", re.M)


class FakeClient:
    """Deterministic answers; latency varies per prompt so parallel calls finish out of order."""

    def __init__(self, cancel_after: int | None = None, cancel: threading.Event | None = None):
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = 0
        self.cancel_after = cancel_after
        self.cancel = cancel

    def complete(self, system: str, user: str) -> str:
        if system == SHORT_TITLE_SYSTEM:
            return json.dumps({"titles": []})
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls += 1
            if self.cancel_after is not None and self.calls >= self.cancel_after:
                self.cancel.set()
        try:
            time.sleep(hashlib.sha256(user.encode()).digest()[0] / 255 * 0.05)
            sid = _SID.findall(user)[0]
            return json.dumps(
                {
                    "rubric": [
                        {
                            "question_id": q.id,
                            "answer": False,
                            "cited_sentence_ids": [],
                            "rationale": "n/a",
                        }
                        for q in QUESTIONS
                    ],
                    "claims": [
                        {"text": "The section discusses this topic.", "cited_sentence_ids": [sid]}
                    ],
                }
            )
        finally:
            with self.lock:
                self.active -= 1


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path,
        embed_model="BAAI/bge-m3",
        llm_model="x",
        gemini_model="y",
        api_origin="http://localhost:3000",
    )


def _run(tmp_path: Path, fake: FakeClient, monkeypatch, workers: int, **kw):
    monkeypatch.setenv("RISKDIFF_EMBED_BACKEND", "lexical")
    monkeypatch.setenv("RISKDIFF_LLM_CONCURRENCY", str(workers))
    client = LLMClient(provider="huggingface", model_id="hf:fake", _complete=fake.complete)
    return run_pipeline(
        "FIXTUR",
        _settings(tmp_path),
        fixture=True,
        preloaded={"llm_client": client, "llm_reason": "huggingface"},
        **kw,
    )


def test_parallel_output_is_byte_identical_to_sequential(tmp_path, monkeypatch):
    seq, par = FakeClient(), FakeClient()
    ctx1 = _run(tmp_path / "seq", seq, monkeypatch, 1)
    ctx2 = _run(tmp_path / "par", par, monkeypatch, 6)
    assert ctx1.outputs["llm_calls"] == ctx2.outputs["llm_calls"] >= 2
    assert seq.max_active == 1 and par.max_active > 1
    t1 = Path(ctx1.outputs["published_path"]).read_text()
    t2 = Path(ctx2.outputs["published_path"]).read_text()
    assert t1 == t2
    assert '"status":"ok"' in t1.replace(" ", "")  # the fake answers actually got through


def test_cancel_during_llm_stage_stops_the_run(tmp_path, monkeypatch):
    from pipeline.errors import PipelineError

    cancel = threading.Event()
    fake = FakeClient(cancel_after=1, cancel=cancel)
    with pytest.raises(PipelineError, match="cancelled"):
        _run(tmp_path, fake, monkeypatch, 2, cancel=cancel)


def test_llm_concurrency_env(monkeypatch):
    monkeypatch.delenv("RISKDIFF_LLM_CONCURRENCY", raising=False)
    assert llm_concurrency() == 6
    for raw, want in (("1", 1), ("0", 1), ("99", 16), ("abc", 6), ("8", 8)):
        monkeypatch.setenv("RISKDIFF_LLM_CONCURRENCY", raw)
        assert llm_concurrency() == want


def test_stage_timings_cover_every_stage(tmp_path, monkeypatch):
    ctx = _run(tmp_path, FakeClient(), monkeypatch, 4)
    names = ["fetch", "extract", "segment", "embed", "match", "diff", "signals", "llm", "publish"]
    assert list(ctx.stage_seconds) == names
    table = format_timings(ctx)
    assert "llm" in table and "calls)" in table and "total" in table
