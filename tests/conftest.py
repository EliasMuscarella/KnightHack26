from __future__ import annotations

import warnings

import pytest

warnings.filterwarnings("ignore", category=SyntaxWarning)


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
