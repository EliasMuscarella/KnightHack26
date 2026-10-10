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

PIPELINE_VERSION = "0.2.0"

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
    hf_token: str | None = field(repr=False)
    gemini_api_key: str | None = field(repr=False)
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


# ---- Databricks shared report store (optional; see pipeline/store/databricks.py) ----

DATABRICKS_HOST_SUFFIXES = (
    ".cloud.databricks.com",
    ".gcp.databricks.com",
    ".azuredatabricks.net",
    ".databricks.azure.us",
    ".databricks.azure.cn",
)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


@dataclass(frozen=True)
class DatabricksSettings:
    """All six variables come from the environment. `enabled` is True only when host, token and
    warehouse id are all present; nothing in the app requires them."""

    host: str | None
    token: str | None = field(repr=False)
    warehouse_id: str | None
    catalog: str = "riskdiff"
    schema: str = "main"
    volume: str = "reports"

    @property
    def enabled(self) -> bool:
        return bool(self.host and self.token and self.warehouse_id)

    @property
    def volume_root(self) -> str:
        return f"/Volumes/{self.catalog}/{self.schema}/{self.volume}"

    def table(self, name: str) -> str:
        return f"`{self.catalog}`.`{self.schema}`.`{name}`"

    def redacted(self) -> dict:
        return {
            "host": self.host or "MISSING",
            "token": "set" if self.token else "MISSING",
            "warehouse_id": "set" if self.warehouse_id else "MISSING",
            "catalog": self.catalog,
            "schema": self.schema,
            "volume": self.volume,
            "enabled": self.enabled,
        }


def validate_databricks_host(raw: str) -> str:
    """`https://<workspace>` on a known Databricks domain. Returns the normalized origin."""
    from urllib.parse import urlsplit

    from pipeline.errors import ConfigError

    parts = urlsplit((raw or "").strip())
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.path not in ("", "/") or parts.query:
        raise ConfigError("DATABRICKS_HOST must be an https:// workspace URL with no path")
    if not host.endswith(DATABRICKS_HOST_SUFFIXES):
        raise ConfigError("DATABRICKS_HOST is not on a known Databricks domain")
    return f"https://{host}"


def _ident(name: str, default: str, var: str) -> str:
    from pipeline.errors import ConfigError

    v = (os.environ.get(var) or "").strip() or default
    if not IDENT_RE.match(v):
        raise ConfigError(f"{var} must be a plain SQL identifier (letters, digits, underscore)")
    return v


def get_databricks_settings() -> DatabricksSettings:
    _load_env()
    host = (os.environ.get("DATABRICKS_HOST") or "").strip() or None
    if host:
        host = validate_databricks_host(host)
    return DatabricksSettings(
        host=host,
        token=(os.environ.get("DATABRICKS_TOKEN") or "").strip() or None,
        warehouse_id=(os.environ.get("DATABRICKS_WAREHOUSE_ID") or "").strip() or None,
        catalog=_ident("", "riskdiff", "DATABRICKS_CATALOG"),
        schema=_ident("", "main", "DATABRICKS_SCHEMA"),
        volume=_ident("", "reports", "DATABRICKS_VOLUME"),
    )


def normalize_ticker(raw: str) -> str:
    """Uppercase and validate. Raises InvalidTicker on anything outside ^[A-Z.\\-]{1,6}$."""
    from pipeline.errors import InvalidTicker

    t = (raw or "").strip().upper()
    if not TICKER_RE.match(t):
        raise InvalidTicker("Ticker must be 1-6 characters: letters, '.', or '-'.")
    return t
