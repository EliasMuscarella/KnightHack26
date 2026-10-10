"""API tests: validation, CORS, cached serving, SSE live run on the fixture, no stack traces."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pipeline.config import Settings
from pipeline.schema import Comparison, canonical_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import api.main as api_main

    monkeypatch.setenv("RISKDIFF_EMBED_BACKEND", "lexical")
    monkeypatch.setattr(api_main, "ALLOW_FIXTURE", True)
    settings = Settings(
        sec_user_agent=None,
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path / "data",
        embed_model="x",
        llm_model="x",
        gemini_model="y",
        api_origin="http://localhost:3000",
    )
    # a published-looking document derived from the fixture, written ONLY into this temp dir
    comp = Comparison.model_validate_json(
        (ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text()
    )
    real = comp.model_copy(
        update={"is_fixture": False, "company": comp.company.model_copy(update={"ticker": "TEST"})}
    )
    (settings.published_dir).mkdir(parents=True)
    (settings.published_dir / "TEST_2024_2025.json").write_text(canonical_json(real))
    (settings.published_dir / "FIXTUR_2024_2025.json").write_text(
        canonical_json(comp)
    )  # fixture must be ignored
    app = api_main.create_app(settings)
    with TestClient(app) as c:
        yield c


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for chunk in re.split(r"\r\n\r\n|\n\n", text):
        ev, data = None, None
        for line in chunk.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if ev and data:
            events.append((ev, json.loads(data)))
    return events


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert r.json()["sec_configured"] is False


def test_companies_skip_fixture(client):
    r = client.get("/companies")
    assert r.status_code == 200
    cards = r.json()["companies"]
    assert [c["ticker"] for c in cards] == ["TEST"]
    assert cards[0]["total_changes"] == 7 and cards[0]["is_fixture"] is False
    assert cards[0]["old_filing_date"] == "2024-02-21"


def test_comparison_get_and_404(client):
    r = client.get("/comparison/test")
    assert r.status_code == 200 and r.json()["company"]["ticker"] == "TEST"
    assert client.get("/comparison/NOPE").status_code == 404
    r = client.get("/comparison/bad;ticker")
    assert r.status_code == 400
    assert "Traceback" not in r.text and "detail" in r.json()


def test_cors_restricted_to_frontend_origin(client):
    r = client.options(
        "/companies",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    r = client.options(
        "/companies",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") is None


def test_analyze_rejects_invalid_ticker_server_side(client):
    for bad in ["", "x" * 10, "NV DA", "../etc", "nvda;ls"]:
        r = client.post("/analyze", json={"ticker": bad})
        assert r.status_code in (400, 422), bad
        assert "Traceback" not in r.text


def test_analyze_without_sec_user_agent_is_503(client):
    r = client.post("/analyze", json={"ticker": "NVDA"})
    assert r.status_code == 503
    assert "SEC_USER_AGENT" in r.json()["detail"]


def test_analyze_replays_cached(client):
    with client.stream("POST", "/analyze", json={"ticker": "TEST"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse("".join(r.iter_text()))
    stages = [e for e in events if e[0] == "stage"]
    assert [e[1]["stage"] for e in stages] == list(range(9))
    assert all(e[1]["status"] == "cached" for e in stages)
    assert events[-1][0] == "complete" and events[-1][1]["ticker"] == "TEST"


def test_analyze_live_fixture_streams_stages(client):
    os.environ["RISKDIFF_EMBED_BACKEND"] = "lexical"
    # remove the pre-written fixture file so a real run happens (output goes to scratch, not published)
    (Path(client.app.state.rd.settings.published_dir) / "FIXTUR_2024_2025.json").unlink()
    with client.stream("POST", "/analyze", json={"ticker": "FIXTUR"}) as r:
        assert r.status_code == 200
        events = parse_sse("".join(r.iter_text()))
    kinds = [e[0] for e in events]
    assert kinds[-1] == "complete", events[-3:]
    started = [e[1]["stage"] for e in events if e[0] == "stage" and e[1]["status"] == "started"]
    done = [e[1]["stage"] for e in events if e[0] == "stage" and e[1]["status"] == "done"]
    assert started == list(range(9)) and done == list(range(9))
    assert events[-1][1]["file"] == "FIXTUR_2024_2025.json"
    assert (
        Path(client.app.state.rd.settings.data_dir) / "scratch" / "FIXTUR_2024_2025.json"
    ).exists()
    assert not (Path(client.app.state.rd.settings.published_dir) / "FIXTUR_2024_2025.json").exists()
