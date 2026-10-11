from __future__ import annotations

import os
import warnings

import pytest

warnings.filterwarnings("ignore", category=SyntaxWarning)

# The suite is offline and deterministic: the dense embedder path is exercised with fakes
# (tests/test_embed_match.py); everything that runs the pipeline uses the lexical embedder.
os.environ.setdefault("RISKDIFF_EMBED_BACKEND", "lexical")


@pytest.fixture(autouse=True)
def _no_ticker_tape_network(monkeypatch):
    """A developer's FINNHUB_API_KEY (shell or .env) must never start the real quote poller in tests."""
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    from pipeline.config import Settings

    monkeypatch.setenv("SEC_USER_AGENT", "RiskDiff Test test@example.com")
    return Settings(
        sec_user_agent="RiskDiff Test test@example.com",
        hf_token=None,
        gemini_api_key=None,
        data_dir=tmp_path / "data",
        embed_model="BAAI/bge-m3",
        llm_model="test/llm",
        gemini_model="gemini-test",
        api_origin="http://localhost:3000",
    )
