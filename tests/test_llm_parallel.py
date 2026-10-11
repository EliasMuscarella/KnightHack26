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
from pipeline.llm import MAX_ATTEMPTS, SHORT_TITLE_SYSTEM, LLMClient
from pipeline.rubric import QUESTIONS
from pipeline.run import format_timings, run_pipeline
from pipeline.stages_final import llm_concurrency, validated_short_title

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


# ---------- short-titles batch overlapped with stage 7 ----------

_TITLE_STOP = frozenset(
    "a an the of to and or in on for with by our we us its their is are may could might be not".split()
)


def _fake_title(heading: str) -> str:
    words = [
        w.strip(".,")
        for w in heading.removeprefix("FIXTURE: ").split()
        if w.strip(".,").lower() not in _TITLE_STOP
    ]
    return " ".join(words[:3]).capitalize() + " topic"


class SleepyClient(FakeClient):
    """Every call (interpretation or short-titles batch) sleeps `delay`; records when each ran."""

    def __init__(
        self,
        delay: float = 0.3,
        titles_fail: bool = False,
        title_delay: float | None = None,
        cancel: threading.Event | None = None,
    ):
        super().__init__(cancel_after=1 if cancel else None, cancel=cancel)
        self.delay = delay
        self.title_delay = delay if title_delay is None else title_delay
        self.titles_fail = titles_fail
        self.title_calls = 0
        self.spans: dict[str, list[tuple[float, float]]] = {"interp": [], "titles": []}

    def complete(self, system: str, user: str) -> str:
        kind = "titles" if system == SHORT_TITLE_SYSTEM else "interp"
        t0 = time.perf_counter()
        try:
            time.sleep(self.delay if kind == "interp" else self.title_delay)
            if kind == "interp":
                return super().complete(system, user)
            with self.lock:
                self.title_calls += 1
            if self.titles_fail:
                raise RuntimeError("provider down")
            rows = [ln.split("\t", 1) for ln in user.split("HEADINGS:\n", 1)[1].splitlines()]
            return json.dumps(
                {"titles": [{"change_id": c, "short_title": _fake_title(h)} for c, h in rows]}
            )
        finally:
            with self.lock:
                self.spans[kind].append((t0, time.perf_counter()))


def _title_cache_files(data_dir: Path) -> list[Path]:
    root = data_dir / "cache" / "stages" / "llm"
    if not root.exists():
        return []
    return [p for p in root.glob("*.json") if "titles" in json.loads(p.read_text())]


def _published(ctx) -> tuple[str, dict]:
    text = Path(ctx.outputs["published_path"]).read_text()
    return text, json.loads(text)


def test_short_titles_overlap_interpretation_calls(tmp_path, monkeypatch):
    delay = 0.3
    # sequential reference: interpretations first (--until-stage 7 sends no title batch), then
    # a full run where everything else is cached, so the batch is made alone in stage 8
    warm = SleepyClient(delay)
    _run(tmp_path / "seq", warm, monkeypatch, 16, until_stage=7)
    assert warm.title_calls == 0 and warm.calls >= 2
    seq = SleepyClient(delay)
    ctx_seq = _run(tmp_path / "seq", seq, monkeypatch, 16)
    assert seq.calls == 0 and seq.title_calls == 1

    par = SleepyClient(delay)
    ctx_par = _run(tmp_path / "par", par, monkeypatch, 16)
    assert par.title_calls == 1 and par.calls == warm.calls
    ((t0, t1),) = par.spans["titles"]
    assert any(a < t1 and t0 < b for a, b in par.spans["interp"])  # ran at the same time
    wall = ctx_par.stage_seconds["llm"] + ctx_par.stage_seconds["publish"]
    assert delay <= wall < 1.75 * delay, wall  # about one sleep, not two

    text_seq, data = _published(ctx_seq)
    text_par, _ = _published(ctx_par)
    assert text_seq == text_par
    fakes = {_fake_title(c["title"]) for c in data["changes"]}
    assert any(c["short_title"] in fakes for c in data["changes"])  # LLM titles were used
    assert len(_title_cache_files(tmp_path / "par")) == 1


def test_short_titles_failure_does_not_change_interpretations(tmp_path, monkeypatch):
    ok, bad = SleepyClient(0.01), SleepyClient(0.01, titles_fail=True)
    _, good = _published(_run(tmp_path / "ok", ok, monkeypatch, 4))
    _, failed = _published(_run(tmp_path / "bad", bad, monkeypatch, 4))
    assert bad.title_calls == MAX_ATTEMPTS  # tried during stage 7 only, not again in stage 8
    assert _title_cache_files(tmp_path / "bad") == []
    assert [c["interpretation"] for c in failed["changes"]] == [
        c["interpretation"] for c in good["changes"]
    ]
    assert any(c["interpretation"]["status"] == "ok" for c in failed["changes"])
    name = failed["company"]["name"]
    for c in failed["changes"]:
        assert c["short_title"] == validated_short_title(c["title"], None, name)


def test_cached_short_titles_are_reused_without_a_call(tmp_path, monkeypatch):
    first = SleepyClient(0.01)
    text1, _ = _published(_run(tmp_path, first, monkeypatch, 4))
    assert first.title_calls == 1
    # drop the interpretation rows only: stage 7 calls again and finds the batch in the cache
    llm_dir = tmp_path / "cache" / "stages" / "llm"
    titles = _title_cache_files(tmp_path)
    for p in llm_dir.glob("*.json"):
        if p not in titles:
            p.unlink()
    second = SleepyClient(0.01)
    text2, _ = _published(_run(tmp_path, second, monkeypatch, 4))
    assert second.calls == first.calls and second.title_calls == 0
    # everything cached: no pool at all, stage 8 reads the batch from the cache
    third = SleepyClient(0.01)
    text3, _ = _published(_run(tmp_path, third, monkeypatch, 4))
    assert third.calls == 0 and third.title_calls == 0
    assert text1 == text2 == text3


def test_cancel_while_short_titles_in_flight(tmp_path, monkeypatch):
    from pipeline.errors import PipelineError

    cancel = threading.Event()
    fake = SleepyClient(0.01, title_delay=3.0, cancel=cancel)
    t0 = time.perf_counter()
    with pytest.raises(PipelineError, match="cancelled"):
        _run(tmp_path, fake, monkeypatch, 4, cancel=cancel)
    assert time.perf_counter() - t0 < 2.5  # did not wait for the in-flight batch
    assert _title_cache_files(tmp_path) == []
