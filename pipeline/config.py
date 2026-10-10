"""Configuration: versions, paths, model IDs, and secrets (environment variables only).

Secrets are read from the environment (optionally populated from a repo-root `.env` by
python-dotenv). They are never logged or written anywhere.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PIPELINE_VERSION = "0.1.0"

ROOT = Path(__file__).resolve().parents[1]
TICKER_RE = re.compile(r"^[A-Z.\-]{1,6}$")

DEFAULT_EMBED_MODEL = "BAAI/bge-m3"
DEFAULT_LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
NER_MODEL_ID = "spacy/en_core_web_sm@3.8.0"
SENTENCE_SPLITTER_ID = "pysbd@0.3.4"

_loaded = False


def _load_env() -> None:
    global _loaded
    if not _loaded:
        load_dotenv(ROOT / ".env", override=False)
        _loaded = True


@dataclass(frozen=True)
class Settings:
    sec_user_agent: str | None
    hf_token: str | None
    gemini_api_key: str | None
    data_dir: Path
    embed_model: str
    llm_model: str
    gemini_model: str
    api_origin: str
    hf_offline: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def published_dir(self) -> Path:
        return self.data_dir / "published"

    def redacted(self) -> dict:
        """Safe-to-log view: presence of secrets only, never their values."""
        return {
            "sec_user_agent": "set" if self.sec_user_agent else "MISSING",
            "hf_token": "set" if self.hf_token else "MISSING",
            "gemini_api_key": "set" if self.gemini_api_key else "MISSING",
            "data_dir": str(self.data_dir),
            "embed_model": self.embed_model,
            "llm_model": self.llm_model,
        }


def get_settings() -> Settings:
    _load_env()
    data_dir = Path(os.environ.get("RISKDIFF_DATA_DIR", str(ROOT / "data")))
    ua = (os.environ.get("SEC_USER_AGENT") or "").strip() or None
    return Settings(
        sec_user_agent=ua,
        hf_token=(os.environ.get("HF_TOKEN") or "").strip() or None,
        gemini_api_key=(os.environ.get("GEMINI_API_KEY") or "").strip() or None,
        data_dir=data_dir,
        embed_model=os.environ.get("RISKDIFF_EMBED_MODEL", DEFAULT_EMBED_MODEL),
        llm_model=os.environ.get("RISKDIFF_LLM_MODEL", DEFAULT_LLM_MODEL),
        gemini_model=os.environ.get("RISKDIFF_GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        api_origin=os.environ.get("RISKDIFF_API_ORIGIN", "http://localhost:3000"),
        hf_offline=os.environ.get("HF_HUB_OFFLINE", "") == "1",
    )


def normalize_ticker(raw: str) -> str:
    """Uppercase and validate. Raises InvalidTicker on anything outside ^[A-Z.\\-]{1,6}$."""
    from pipeline.errors import InvalidTicker

    t = (raw or "").strip().upper()
    if not TICKER_RE.match(t):
        raise InvalidTicker("Ticker must be 1-6 characters: letters, '.', or '-'.")
    return t
