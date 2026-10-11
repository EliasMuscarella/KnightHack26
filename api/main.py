"""RiskDiff API (FastAPI).

GET  /health                 liveness + whether the embedding model is warm
GET  /companies              report library: local published files merged with the current
                             reports of the shared Databricks store (deduplicated by analysis_id)
GET  /comparison/{ticker}    the published Comparison JSON (read-through cache: local file first,
                             else fetched from the shared store, verified, saved locally, served)
GET  /store/health           {"remote": "disabled" | "connecting" | "ok" | "offline", "warehouse_state"}
GET  /trends                 cross-company trends (stale-while-revalidate: the shared store's
                             aggregates when available, else the local derived facts)
GET  /ticker-tape            home-page market tape: last known Finnhub quotes for a fixed list of
                             large US stocks (polled in the background; requests never call out)
POST /analyze {"ticker"}     runs the pipeline, streaming StageEvents over SSE; serves a cached
                             result (all stages reported as "cached") when one is published

Security posture: strict ticker validation, CORS restricted to the local frontend origin, one
analysis at a time, a per-analysis timeout, and no stack traces in responses. Databricks is
optional: with no DATABRICKS_* variables everything is local; when it is configured but
unreachable, local reports keep being served and /store/health says "offline". The ticker tape is
optional too: without FINNHUB_API_KEY no poller starts and /ticker-tape reports "unavailable".
Credentials never leave the Python process.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from api.ticker_tape import TickerTapeService, unavailable_body
from pipeline.config import (
    PIPELINE_VERSION,
    Settings,
    get_databricks_settings,
    get_settings,
    load_env,
    normalize_ticker,
)
from pipeline.errors import InvalidTicker, PipelineError
from pipeline.publish import load_published
from pipeline.run import FIXTURE_TICKER, STAGE_LABELS, run_pipeline
from pipeline.schema import CHANGE_TYPES, CompanyCard, Comparison, StageEvent
from pipeline.store import DatabricksStore, StoreDisabled, StoreError, StoreUnavailable, tables
from pipeline.trends import aggregate, derive

log = logging.getLogger("api")

# The constants below read os.environ at import time, so .env must be loaded first.
load_env()
ANALYZE_TIMEOUT_SECONDS = int(os.environ.get("RISKDIFF_ANALYZE_TIMEOUT", "1500"))
ALLOW_FIXTURE = os.environ.get("RISKDIFF_ALLOW_FIXTURE", "") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("RISKDIFF_API_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if h.strip()
]
REMOTE_LIST_TTL_SECONDS = 60.0  # how long the shared store's report list is reused
REMOTE_FAIL_TTL_SECONDS = 20.0  # how long an "offline" answer is reused before retrying
REMOTE_WAIT_SECONDS = 1.0  # how long /companies waits for a cold list refresh before serving
REMOTE_MISS_WAIT_SECONDS = 20.0  # on a local miss, how long /comparison may wait for the store
HEALTH_TTL_SECONDS = 15.0  # how long a completed health check answers before a recheck
HEALTH_NOT_READY_TTL_SECONDS = 3.0  # recheck sooner while the warehouse is starting
HEALTH_WAIT_SECONDS = 0.25  # /store/health waits at most this long for an in-flight check
WAREHOUSE_NOT_READY = frozenset({"STARTING", "STOPPED", "STOPPING"})
TRENDS_TTL_SECONDS = 60.0  # a remote trends result older than this is refreshed in the background
TRENDS_FAIL_RETRY_SECONDS = 20.0  # after a failed refresh, wait this long before the next one
TRENDS_COLD_WAIT_SECONDS = 2.0  # store ok + nothing cached: wait this long for the first result
REMOTE_REFRESH_WAIT_SECONDS = 200.0  # background only: a cold warehouse may take minutes
TRENDS_CACHE_VERSION = 3  # bump when the /trends body changes shape (old disk caches are ignored)
TRENDS_AGGREGATE_VERSION = 2  # bump when aggregate.py changes what it computes

FRIENDLY: dict[str, str] = {
    "invalid_ticker": "That does not look like a ticker. Use 1-6 letters, '.', or '-'.",
    "ticker_not_found": "The SEC company list has no entry for that ticker.",
    "no_10k": "Fewer than two 10-K filings with a primary document were found for this company.",
    "sec_unavailable": "EDGAR could not be reached or returned an error. Try again in a minute.",
    "config": "The server is missing configuration (SEC_USER_AGENT). Ask the operator to set it in .env.",
    "extraction_failed": "Item 1A (Risk Factors) could not be located in one of the filings.",
    "segmentation_failed": "The Risk Factors section could not be split into individual risks.",
    "busy": "Another analysis is running. Only one runs at a time; try again shortly.",
    "timeout": "The analysis took too long and was stopped.",
    "cancelled": "The analysis was cancelled.",
    "publish_conflict": "A published comparison for this ticker already exists with a different analysis id.",
    "embedding_unavailable": "The embedding model is not available on the server; live analysis is disabled.",
    "internal": "Something went wrong on the server.",
}


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


def default_store_factory() -> DatabricksStore:
    """Raises StoreDisabled when DATABRICKS_* is not set (the normal, local-only case)."""
    return DatabricksStore(get_databricks_settings())


class RemoteLibrary:
    """The API's view of the shared store: a TTL-cached list of current reports (refreshed in a
    background thread; requests never wait longer than a short bound), a non-blocking health
    state machine, and the read-through pull of a report that is not on disk. Every failure
    degrades to "offline": local reports are always served.

    Health has four states. `disabled`: no DATABRICKS_* variables. `connecting`: the first check
    has not finished (the SDK client is being built, the first round trip is pending) or the
    warehouse is not running yet (STARTING/STOPPED/STOPPING; a statement starts it). `ok`: the
    last check succeeded with a running warehouse. `offline`: a check or a statement failed after
    the store's retries, or the configuration is unusable. A check that has not finished is never
    reported as offline: requests read the last known state and checks run in the background."""

    def __init__(self, store_factory: Callable[[], Any] | None):
        self._factory = store_factory or default_store_factory
        self._store: Any | None = None
        self._store_failed: str | None = None
        self.disabled = False
        self.lock = threading.Lock()
        self.reports: list[dict] = []
        self.reports_at = 0.0
        self.reports_ok: bool | None = None  # None = never refreshed
        self._refresh_thread: threading.Thread | None = None
        self._pulling: set[str] = set()
        # health state machine (see class docstring)
        self._health_state = "connecting"
        self._warehouse_state: str | None = None
        self._health_at: float | None = None  # monotonic time of the last completed check
        self._health_thread: threading.Thread | None = None

    # -- store handle --

    def store(self) -> Any | None:
        with self.lock:
            if self.disabled or self._store_failed or self._store is not None:
                return self._store
            try:
                self._store = self._factory()
            except StoreDisabled:
                self.disabled = True
            except PipelineError as e:  # bad host / identifiers: configured but unusable
                self._store_failed = e.code
                self._health_state = "offline"
                log.warning("shared store not usable: %s", e.code)
            return self._store

    # -- report list --

    def _refresh(self) -> None:
        store = self.store()
        if store is None:
            return
        try:
            rows = store.list_reports()
            with self.lock:
                self.reports, self.reports_ok = rows, True
                self.reports_at = time.monotonic()
            self.note_success()
        except Exception as e:  # noqa: BLE001  (StoreError or anything unexpected)
            log.warning("shared store list failed [%s]", getattr(e, "code", type(e).__name__))
            with self.lock:
                self.reports_ok = False
                self.reports_at = time.monotonic() - (
                    REMOTE_LIST_TTL_SECONDS - REMOTE_FAIL_TTL_SECONDS
                )
            self.note_failure()

    def ensure_fresh(self, wait: float) -> None:
        """Start a background refresh when the list is stale; wait at most `wait` seconds for it."""
        if self.store() is None:
            return
        with self.lock:
            fresh = (
                self.reports_ok is not None
                and time.monotonic() - self.reports_at < REMOTE_LIST_TTL_SECONDS
            )
            if fresh:
                return
            th = self._refresh_thread
            if th is None or not th.is_alive():
                th = threading.Thread(target=self._refresh, name="store-list", daemon=True)
                self._refresh_thread = th
                th.start()
        if wait > 0:
            th.join(timeout=wait)

    def invalidate(self) -> None:
        with self.lock:
            self.reports_at = 0.0

    def recently_offline(self) -> bool:
        """The last list refresh failed and that answer is still within its TTL: do not make a
        request wait on the store again."""
        with self.lock:
            return (
                self.reports_ok is False
                and time.monotonic() - self.reports_at < REMOTE_LIST_TTL_SECONDS
            )

    def current_rows(self) -> list[dict]:
        """One row per ticker: the newest filing pair among the current reports."""
        best: dict[str, dict] = {}
        with self.lock:
            rows = list(self.reports)
        for r in rows:
            t = r.get("ticker")
            if not isinstance(t, str) or not r.get("analysis_id"):
                continue
            key = (int(r.get("new_fiscal_year") or 0), int(r.get("old_fiscal_year") or 0))
            cur = best.get(t)
            if cur is None or key > (int(cur["new_fiscal_year"]), int(cur["old_fiscal_year"])):
                best[t] = r
        return list(best.values())

    # -- health --

    def _check_health(self) -> None:
        store = self.store()
        if store is None:
            return
        warehouse: str | None = None
        try:
            info = store.health() or {}
            warehouse = info.get("warehouse_state")
            state = "connecting" if warehouse in WAREHOUSE_NOT_READY else "ok"
        except Exception as e:  # noqa: BLE001  (StoreError after retries, or unexpected)
            log.warning("store health failed [%s]", getattr(e, "code", type(e).__name__))
            state = "offline"
        with self.lock:
            self._health_state, self._warehouse_state = state, warehouse
            self._health_at = time.monotonic()

    def note_success(self) -> None:
        """A statement just succeeded: the store is reachable and the warehouse is running."""
        with self.lock:
            if self._store_failed:
                return
            self._health_state = "ok"
            self._warehouse_state = "RUNNING"  # a statement just ran on it
            self._health_at = time.monotonic()

    def note_failure(self) -> None:
        """A statement failed after the store's retries: report offline until the next check."""
        with self.lock:
            self._health_state = "offline"
            self._health_at = time.monotonic()

    def health_state(self, wait: float = 0.0) -> tuple[str, str | None]:
        """(state, warehouse_state) right now. Never blocks longer than `wait`: a stale or missing
        answer starts a background check and the last known state is returned ("connecting"
        until the first check completes)."""
        store = self.store()
        with self.lock:
            if self.disabled:
                return "disabled", None
            if store is None:  # configured but unusable (bad host/identifiers)
                return "offline", None
            ttl = (
                HEALTH_NOT_READY_TTL_SECONDS
                if self._health_state == "connecting"
                else HEALTH_TTL_SECONDS
            )
            stale = self._health_at is None or time.monotonic() - self._health_at >= ttl
            th = self._health_thread
            if stale and (th is None or not th.is_alive()):
                th = threading.Thread(target=self._check_health, name="store-health", daemon=True)
                self._health_thread = th
                th.start()
        if wait > 0 and th is not None and th.is_alive():
            th.join(timeout=wait)
        with self.lock:
            return self._health_state, self._warehouse_state

    def settings_key(self) -> str | None:
        """A short, non-secret key of the configured workspace + catalog + schema (cache scope)."""
        store = self.store()
        s = getattr(store, "settings", None)
        if s is None:
            return None
        raw = "|".join(
            str(getattr(s, a, "") or "") for a in ("host", "catalog", "schema", "warehouse_id")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    # -- read-through pull --

    def pull_for_ticker(self, ticker: str, published_dir: Path, *, wait: float) -> Path | None:
        """Local miss: find the ticker's current report in the store, download + verify it, save it
        under published_dir and return the path. Any failure -> None (the caller answers 404)."""
        if self.store() is None or self.recently_offline():
            return None
        self.ensure_fresh(wait)
        row = next((r for r in self.current_rows() if r.get("ticker") == ticker), None)
        if row is None:
            return None
        return self.pull_row(row, published_dir)

    def pull_row(self, row: dict, published_dir: Path) -> Path | None:
        store = self.store()
        if store is None:
            return None
        try:
            comp, data = store.download_report(
                str(row["analysis_id"]),
                volume_path=row.get("volume_path"),
                content_sha256=row.get("content_sha256"),
            )
        except (StoreError, PipelineError) as e:
            log.warning("could not pull %s from the shared store [%s]", row.get("ticker"), e.code)
            return None
        if comp.company.ticker != row.get("ticker"):
            log.warning("pulled report ticker mismatch for %s; discarded", row.get("ticker"))
            return None
        return save_report(published_dir, comp, data)

    def schedule_pull(self, row: dict, published_dir: Path) -> None:
        """Background: a newer current report exists for a ticker that is stale on disk."""
        t = str(row.get("ticker"))
        with self.lock:
            if t in self._pulling:
                return
            self._pulling.add(t)

        def work() -> None:
            try:
                self.pull_row(row, published_dir)
            finally:
                with self.lock:
                    self._pulling.discard(t)

        threading.Thread(target=work, name=f"store-pull-{t}", daemon=True).start()


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class TrendsService:
    """/trends with stale-while-revalidate.

    * Databricks disabled: computed from LOCAL reports (memoized by a fingerprint of the files it
      reads, in memory and on disk), always `source: "local"`.
    * Databricks configured: the last good remote result is returned immediately (memory, else
      the disk cache `data/cache/trends/trends.json`, which survives restarts) and refreshed in a
      background thread when older than TRENDS_TTL_SECONDS. With no remote result yet, the local
      aggregate is returned (`source: "local"`) while the first refresh runs; when there is
      nothing local either, the lists are empty and `source` is null (the page retries).
    A request never waits on a cold warehouse; only a store that is already `ok` gets a short
    TRENDS_COLD_WAIT_SECONDS for the very first remote result."""

    def __init__(
        self,
        settings: Settings,
        remote: RemoteLibrary,
        local_fn: Callable[[], tuple[str, dict]],
        remote_fn: Callable[[Any, list[dict]], dict],
        library_fn: Callable[[], str] | None = None,
    ):
        self.settings = settings
        self.remote = remote
        self._local_fn = local_fn  # () -> (fingerprint, body); body computed only when needed
        self._remote_fn = remote_fn  # (store, current report rows) -> body
        # () -> key of the current merged library (the /companies set); a remote result computed
        # for another set is stale, so /trends and /companies never list different companies
        # for longer than one refresh
        self._library_fn = library_fn
        self.lock = threading.Lock()
        self._local_lock = threading.Lock()
        self._disk_loaded = False
        self._remote_entry: dict | None = None  # {"store_key", "computed_at", "epoch", "body"}
        self._local_entry: dict | None = None  # {"fingerprint", "computed_at", "body"}
        self._thread: threading.Thread | None = None
        self._failed_at: float | None = None

    @property
    def cache_path(self) -> Path:
        return self.settings.cache_dir / "trends" / "trends.json"

    # -- disk cache --

    def _load_disk(self) -> None:
        with self.lock:
            if self._disk_loaded:
                return
            self._disk_loaded = True
            try:
                doc = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return
            if not isinstance(doc, dict) or doc.get("version") != TRENDS_CACHE_VERSION:
                return
            if isinstance(doc.get("databricks"), dict) and self._remote_entry is None:
                self._remote_entry = doc["databricks"]
            if isinstance(doc.get("local"), dict) and self._local_entry is None:
                self._local_entry = doc["local"]

    def _save_disk(self) -> None:
        with self.lock:
            doc = {
                "version": TRENDS_CACHE_VERSION,
                "databricks": self._remote_entry,
                "local": self._local_entry,
            }
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.cache_path)
        except OSError as e:
            log.warning("could not write the trends cache: %s", type(e).__name__)

    # -- local --

    def local(self) -> tuple[str | None, dict]:
        """(computed_at, body) of the local aggregate, recomputed only when its inputs changed."""
        self._load_disk()
        with self._local_lock:
            fingerprint, compute = self._local_fn()
            with self.lock:
                entry = self._local_entry
            if entry is not None and entry.get("fingerprint") == fingerprint:
                return entry.get("computed_at"), entry["body"]
            body = compute()
            entry = {"fingerprint": fingerprint, "computed_at": _utc_now_iso(), "body": body}
            with self.lock:
                self._local_entry = entry
            self._save_disk()
            return entry["computed_at"], body

    # -- remote --

    def _remote_cached(self) -> dict | None:
        key = self.remote.settings_key()
        with self.lock:
            e = self._remote_entry
        if e is None or key is None or e.get("store_key") != key:
            return None
        return e

    def _refresh_remote(self) -> None:
        try:
            store = self.remote.store()
            if store is None:
                return
            self.remote.ensure_fresh(wait=REMOTE_REFRESH_WAIT_SECONDS)
            if self.remote.reports_ok is not True:
                raise StoreUnavailable("report list unavailable")
            body = self._remote_fn(store, self.remote.current_rows())
            self.remote.note_success()
            entry = {
                "store_key": self.remote.settings_key(),
                "computed_at": _utc_now_iso(),
                "epoch": time.time(),
                "library": library_key(body.get("companies") or []),
                "body": body,
            }
            with self.lock:
                self._remote_entry = entry
                self._failed_at = None
            self._save_disk()
        except Exception as e:  # noqa: BLE001
            log.warning("trends refresh failed [%s]", getattr(e, "code", type(e).__name__))
            if isinstance(e, StoreError) or not isinstance(e, PipelineError):
                self.remote.note_failure()
            with self.lock:
                self._failed_at = time.monotonic()

    def kick_remote(self) -> threading.Thread | None:
        """Start a background refresh unless one is running or the last one failed recently."""
        with self.lock:
            th = self._thread
            if th is not None and th.is_alive():
                return th
            if (
                self._failed_at is not None
                and time.monotonic() - self._failed_at < TRENDS_FAIL_RETRY_SECONDS
            ):
                return None
            th = threading.Thread(target=self._refresh_remote, name="trends-refresh", daemon=True)
            self._thread = th
            th.start()
            return th

    def invalidate(self) -> None:
        """A new report was published here: refresh the remote result soon (served until then)."""
        with self.lock:
            if self._remote_entry is not None:
                self._remote_entry = {**self._remote_entry, "epoch": 0.0}

    # -- the endpoint --

    def get(self) -> dict[str, Any]:
        status, _ = self.remote.health_state()
        if status == "disabled":
            computed_at, body = self.local()
            return {"status": status, "source": "local", "computed_at": computed_at, **body}
        self._load_disk()
        entry = self._remote_cached()
        if entry is None or self._remote_is_stale(entry):
            th = self.kick_remote()
            if entry is None and status == "ok" and th is not None:
                th.join(timeout=TRENDS_COLD_WAIT_SECONDS)
                entry = self._remote_cached()
                status, _ = self.remote.health_state()
        if entry is not None:
            return {
                "status": status,
                "source": "databricks",
                "computed_at": entry.get("computed_at"),
                **entry["body"],
            }
        computed_at, body = self.local()
        if not body["companies"] and status in ("connecting", "ok"):
            return {"status": status, "source": None, "computed_at": None, **body}
        return {"status": status, "source": "local", "computed_at": computed_at, **body}

    def _remote_is_stale(self, entry: dict) -> bool:
        if time.time() - float(entry.get("epoch") or 0) >= TRENDS_TTL_SECONDS:
            return True
        if self._library_fn is None:
            return False
        try:
            return entry.get("library") != self._library_fn()
        except Exception as e:  # noqa: BLE001
            log.warning("library key failed: %s", type(e).__name__)
            return False

    def warm(self) -> None:
        """Startup: compute (or load) the local aggregate and start the first remote refresh."""
        status, _ = self.remote.health_state()
        try:
            self.local()
        except Exception as e:  # noqa: BLE001
            log.warning("local trends warm-up failed: %s", type(e).__name__)
        if status != "disabled":
            self._load_disk()
            self.kick_remote()


class AppState:
    def __init__(self, settings: Settings, store_factory: Callable[[], Any] | None = None):
        self.settings = settings
        self.embedder = None
        self.embedder_error: str | None = None
        self.warm = False
        # Held by the worker THREAD for the whole pipeline run, so "one analysis at a time" is
        # enforced even if the SSE client disconnects or the request times out.
        self.busy = threading.Lock()
        self._cards_cache: dict[str, tuple[float, CompanyCard, str, str, str]] = {}
        self.remote = RemoteLibrary(store_factory)
        self.trends = TrendsService(
            settings,
            self.remote,
            lambda: local_trends_inputs(self),
            lambda store, rows: remote_trends_body(
                store,
                rows,
                local_cards=list_local(self),
                derived_dir=derive.derived_dir_for(settings.data_dir),
                published_dir=settings.published_dir,
            ),
            lambda: library_key(current_library(self)),
        )
        # market quotes for the home-page tape; the key stays in this object, never in a response
        self.ticker_tape = TickerTapeService(
            settings.data_dir / "cache" / "ticker_tape.json",
            os.environ.get("FINNHUB_API_KEY") or None,
        )


def create_app(
    settings: Settings | None = None, *, store_factory: Callable[[], Any] | None = None
) -> FastAPI:
    settings = settings or get_settings()
    state = AppState(settings, store_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        def load() -> None:
            try:
                from pipeline.embed import load_embedder

                state.embedder = load_embedder(settings)
            except Exception as e:  # noqa: BLE001
                state.embedder_error = f"{type(e).__name__}: {str(e)[:200]}"
                log.warning("embedding warm-up failed: %s", e)
            finally:
                state.warm = True

        threading.Thread(target=load, name="embed-warmup", daemon=True).start()
        # warm the shared-store list, the health state and the trends in the background so the
        # first page load already has them (requests never wait on these threads)
        threading.Thread(
            target=lambda: state.remote.ensure_fresh(0), name="store-warmup", daemon=True
        ).start()
        threading.Thread(target=state.trends.warm, name="trends-warmup", daemon=True).start()
        state.ticker_tape.start()  # no-op without FINNHUB_API_KEY
        yield
        state.ticker_tape.stop()  # flush the last quotes to disk

    app = FastAPI(
        title="RiskDiff API",
        version=PIPELINE_VERSION,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.rd = state

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.api_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(PipelineError)
    async def _pipeline_error(_: Request, exc: PipelineError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"detail": FRIENDLY.get(exc.code, exc.message), "code": exc.code},
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500, content={"detail": FRIENDLY["internal"], "code": "internal"}
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        emb = state.embedder
        return {
            "status": "ok",
            "model_warm": state.warm and emb is not None,
            "embedding_backend": getattr(emb, "backend", None),
            "embedding_model": getattr(emb, "model_id", None),
            "embedding_error": (state.embedder_error or "").split(":")[0] or None,
            "busy": state.busy.locked(),
            "pipeline_version": PIPELINE_VERSION,
            "sec_configured": bool(settings.sec_user_agent),
        }

    @app.get("/companies")
    async def companies() -> dict[str, list[dict]]:
        local = await asyncio.to_thread(list_local, state)
        await asyncio.to_thread(state.remote.ensure_fresh, REMOTE_WAIT_SECONDS)
        cards, stale = merge_library(local, state.remote.current_rows())
        for row in stale:
            state.remote.schedule_pull(row, settings.published_dir)
        return {"companies": cards}

    @app.get("/comparison/{ticker}")
    async def comparison(ticker: str) -> Any:
        t = normalize_ticker(ticker)
        path = await asyncio.to_thread(find_published, settings.published_dir, t)
        comp = await asyncio.to_thread(_safe_load, path) if path else None
        if comp is None:  # read-through: the shared store, verified, saved locally, then served
            pulled = await asyncio.to_thread(
                state.remote.pull_for_ticker,
                t,
                settings.published_dir,
                wait=REMOTE_MISS_WAIT_SECONDS,
            )
            comp = await asyncio.to_thread(_safe_load, pulled) if pulled else None
        if comp is None:
            raise HTTPException(
                status_code=404,
                detail=f"No published comparison for {t}. Use POST /analyze to run one.",
            )
        return JSONResponse(content=comp)

    @app.get("/store/health")
    async def store_health() -> dict[str, str | None]:
        status, warehouse = await asyncio.to_thread(state.remote.health_state, HEALTH_WAIT_SECONDS)
        return {"remote": status, "warehouse_state": warehouse}

    @app.get("/trends")
    async def trends() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(state.trends.get)
        except Exception as e:  # noqa: BLE001  (never a 5xx: an empty, retryable answer)
            log.warning("trends failed: %s", type(e).__name__)
            try:
                status, _ = state.remote.health_state()
            except Exception:  # noqa: BLE001
                status = "offline"
            return {"status": status, "source": None, "computed_at": None, **aggregate.empty_body()}

    @app.get("/ticker-tape")
    async def ticker_tape() -> dict[str, Any]:
        try:
            return await asyncio.to_thread(state.ticker_tape.snapshot)
        except Exception as e:  # noqa: BLE001  (never a 5xx: the tape is decoration)
            log.warning("ticker tape failed: %s", type(e).__name__)
            return unavailable_body()

    @app.post("/analyze")
    async def analyze(req: AnalyzeRequest, request: Request):
        try:
            t = normalize_ticker(req.ticker)
        except InvalidTicker as e:
            raise HTTPException(status_code=400, detail=FRIENDLY["invalid_ticker"]) from e
        if t == FIXTURE_TICKER and not ALLOW_FIXTURE:
            raise HTTPException(
                status_code=400,
                detail="FIXTUR is development data; set RISKDIFF_ALLOW_FIXTURE=1 to analyze it.",
            )
        cached = await asyncio.to_thread(find_published, settings.published_dir, t)
        cached_doc = await asyncio.to_thread(_safe_load, cached) if cached else None
        if cached_doc is not None:
            return EventSourceResponse(_replay_cached(t, cached.name, cached_doc), ping=15)
        if not settings.sec_user_agent and t != FIXTURE_TICKER:
            raise HTTPException(status_code=503, detail=FRIENDLY["config"])
        if t != FIXTURE_TICKER and state.warm and state.embedder is None:
            raise HTTPException(status_code=503, detail=FRIENDLY["embedding_unavailable"])
        if not state.busy.acquire(blocking=False):
            raise HTTPException(status_code=409, detail=FRIENDLY["busy"])
        # the lock is now owned by this request and released by the worker thread when it finishes
        return EventSourceResponse(_run_live(state, t, request), ping=15)

    return app


# ---------- helpers ----------


def find_published(published_dir: Path, ticker: str) -> Path | None:
    if not published_dir.exists():
        return None
    candidates = sorted(published_dir.glob(f"{ticker}_*_*.json"))
    if not candidates:
        return None

    def years(p: Path) -> tuple[int, int]:
        try:
            _, a, b = p.stem.split("_")
            return int(b), int(a)
        except ValueError:
            return (0, 0)

    return max(candidates, key=years)


def list_cards(state: AppState) -> list[CompanyCard]:
    return [
        CompanyCard.model_validate({k: v for k, v in d.items() if k in CompanyCard.model_fields})
        for d in list_local(state)
    ]


def list_local(state: AppState) -> list[dict]:
    """Local published files as card dicts (+ analysis_id and the accession pair), one per
    ticker (newest fiscal-year pair). Fixture data is never listed."""
    out: list[dict] = []
    pdir = state.settings.published_dir
    if not pdir.exists():
        return out
    seen: set[str] = set()
    for p in sorted(pdir.glob("*_*_*.json"), key=lambda p: p.stem.split("_")[-1], reverse=True):
        try:
            mtime = p.stat().st_mtime
            cached = state._cards_cache.get(str(p))
            if cached and cached[0] == mtime:
                _, card, analysis_id, old_acc, new_acc = cached
            else:
                comp = Comparison.model_validate_json(p.read_text(encoding="utf-8"))
                if comp.is_fixture:
                    continue
                analysis_id = comp.analysis_id
                old_acc, new_acc = (
                    comp.old_filing.accession_number,
                    comp.new_filing.accession_number,
                )
                card = CompanyCard(
                    ticker=comp.company.ticker,
                    name=comp.company.name,
                    cik=comp.company.cik,
                    old_fiscal_year=comp.old_filing.fiscal_year,
                    new_fiscal_year=comp.new_filing.fiscal_year,
                    old_filing_date=comp.old_filing.filing_date,
                    new_filing_date=comp.new_filing.filing_date,
                    total_changes=comp.summary.total_changes,
                    by_change_type=comp.summary.by_change_type,
                    max_score=comp.summary.max_score,
                    is_fixture=False,
                    file=p.name,
                )
                state._cards_cache[str(p)] = (mtime, card, analysis_id, old_acc, new_acc)
            if card.ticker in seen:
                continue
            seen.add(card.ticker)
            out.append(
                {
                    **card.model_dump(mode="json"),
                    "analysis_id": analysis_id,
                    "old_accession": old_acc,
                    "new_accession": new_acc,
                    "published_by": None,
                    "published_at": None,
                    "source": "local",
                }
            )
        except Exception as e:  # noqa: BLE001
            log.warning("skipping unreadable published file %s: %s", p.name, type(e).__name__)
    return sorted(out, key=lambda c: c["ticker"])


def current_library(state: AppState, local: list[dict] | None = None) -> list[dict]:
    """The current report library: local files merged with the shared store's current reports,
    one per ticker (newest filing pair). The ONE company set /companies and /trends both list
    (cards keep their accession pair here)."""
    if local is None:
        local = list_local(state)
    cards, _ = merge_library(local, state.remote.current_rows(), keep_accessions=True)
    return cards


def library_key(cards: list[dict]) -> str:
    return "\n".join(sorted(f"{c['ticker']}|{c['analysis_id']}" for c in cards))


def _facts_for_card(
    card: dict, derived_dir: Path, published_dir: Path, *, missing: str
) -> tuple[derive.TrendFacts | None, str | None]:
    """(facts, warning) for one library card: the current derived file, else derived (and written)
    from the local published file when the card is local. `missing` says why a report that is not
    on this machine has no facts. Never raises."""
    ticker, aid = card["ticker"], str(card["analysis_id"])
    try:
        facts = derive.load_facts(derived_dir, aid)
    except ValueError:
        facts = None
    if facts is not None and facts.ticker == ticker:
        return facts, None
    if card.get("source") != "local" or not card.get("file"):
        return None, (
            f"{ticker}: no trend facts of derivation {derive.derivation_id()} for this report "
            f"({missing}); it is listed without topics or activity."
        )
    try:
        comp = load_published(published_dir / str(card["file"]))
        if comp.analysis_id != aid or comp.company.ticker != ticker:
            raise ValueError("the published file is not this card's report")
        return derive.ensure_facts(comp, derived_dir), None
    except Exception as e:  # noqa: BLE001
        log.warning("no trend facts for %s: %s", ticker, type(e).__name__)
        return None, (
            f"{ticker}: trend facts could not be derived for this report ({type(e).__name__}); "
            f"it is listed without topics or activity."
        )


def local_trends_inputs(state: AppState) -> tuple[str, Callable[[], dict]]:
    """(fingerprint, compute) for the local trends aggregate over the current library: exactly
    the /companies set (`current_library`: local files merged with the store's current reports,
    newest filing pair per ticker). A derived file is a pure function of (analysis_id,
    derivation), so the fingerprint needs no file reads; compute loads
    data/derived/{analysis_id}.trends.json and derives (and writes) any local one that is missing
    or stale. A company whose facts are unavailable or cannot be derived is still listed (no
    topics or activity) and named in `warnings`; it never disappears from the page."""
    cards = current_library(state)
    derivation = (
        f"{derive.derivation_id()}|{derive.phrase_model_id()}|agg{TRENDS_AGGREGATE_VERSION}"
    )
    parts = [derivation] + sorted(
        f"{c['ticker']}|{c['analysis_id']}|{c.get('source')}" for c in cards
    )
    fingerprint = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

    def compute() -> dict:
        ddir = derive.derived_dir_for(state.settings.data_dir)
        facts, companies, warnings = [], [], []
        for c in cards:
            f, warning = _facts_for_card(
                c,
                ddir,
                state.settings.published_dir,
                missing="the report is in the shared store but not on this machine yet",
            )
            if f is not None:
                facts.append(f)
                companies.append(aggregate.company_from_facts(f))
            else:
                companies.append(aggregate.company_from_card(c))
                warnings.append(warning)
        return aggregate.body_from_facts(facts, companies=companies, warnings=warnings)

    return fingerprint, compute


def remote_trends_body(
    store: Any,
    rows: list[dict],
    *,
    local_cards: list[dict] | None = None,
    derived_dir: Path | None = None,
    published_dir: Path | None = None,
) -> dict:
    """The trends body when the shared store is configured. The company set is the same merged
    library as /companies (`merge_library` over the local cards and the store's current rows).
    Facts of an analysis come from the store's rows of the CURRENT derivation (`:derivation`);
    an analysis with none there (not synced yet, or written by older code) uses its local derived
    facts when this machine has them, else it is listed with no facts and a warning. At most three
    parameterized queries: activity (which also tells which analyses have facts), then topics and
    potential->actual over exactly those analyses."""
    cards, _ = merge_library(local_cards or [], rows, keep_accessions=True)
    if not cards:
        return aggregate.build_body([])
    s = store.settings
    derivation = derive.derivation_id()
    row_ids = {str(r.get("analysis_id")) for r in rows}
    store_ids = sorted(c["analysis_id"] for c in cards if c["analysis_id"] in row_ids)
    activity_rows: list[dict] = []
    if store_ids:
        activity_rows = store.execute(
            tables.trends_activity_sql(s),
            {"current": True, "ids": json.dumps(store_ids), "derivation": derivation},
        )
    # every change has >= 1 category, so an analysis with changes and no activity row has no
    # facts of this derivation in the store
    present = {str(r.get("analysis_id")) for r in activity_rows}
    present |= {
        c["analysis_id"]
        for c in cards
        if c["analysis_id"] in store_ids and not int(c.get("total_changes") or 0)
    }
    local_facts, companies, warnings = [], [], []
    for c in cards:
        if c["analysis_id"] in present:
            companies.append(aggregate.company_from_card(c))
            continue
        missing = "the shared store has none and the report is not on this machine"
        f, warning = (
            _facts_for_card(c, derived_dir, published_dir or Path("."), missing=missing)
            if derived_dir is not None
            else (None, f"{c['ticker']}: no trend facts for this report ({missing}).")
        )
        if f is not None:
            local_facts.append(f)
            companies.append(aggregate.company_from_facts(f))
        else:
            companies.append(aggregate.company_from_card(c))
            warnings.append(warning)
    ids = json.dumps(sorted(present))
    topic_rows: list[dict] = []
    p2a_rows: list[dict] = []
    if present:
        topic_rows = store.execute(
            tables.trends_topics_sql(s),
            {
                "current": True,
                "ids": ids,
                "derivation": derivation,
                "phrase": "phrase",
                # companies served from local facts can complete a phrase's company count
                "min_companies": max(1, aggregate.PHRASE_MIN_COMPANIES - len(local_facts)),
            },
        )
        p2a_rows = store.execute(
            tables.trends_potential_to_actual_sql(s),
            {"current": True, "ids": ids, "kind": "potential_became_actual"},
        )
    return aggregate.body_from_rows(
        companies,
        topic_rows,
        [r for r in activity_rows if str(r.get("analysis_id")) in present],
        p2a_rows,
        local_facts=local_facts,
        warnings=warnings,
    )


def card_from_row(row: dict) -> dict | None:
    """A `reports` row -> card dict (validated through CompanyCard). Bad rows are skipped."""
    try:
        by = {ct: int(row.get(f"n_{ct}") or 0) for ct in CHANGE_TYPES}
        card = CompanyCard(
            ticker=normalize_ticker(str(row.get("ticker"))),
            name=str(row.get("company_name") or ""),
            cik=str(row.get("cik") or "").zfill(10),
            old_fiscal_year=int(row.get("old_fiscal_year") or 0),
            new_fiscal_year=int(row.get("new_fiscal_year") or 0),
            old_filing_date=str(row.get("old_filing_date") or ""),
            new_filing_date=str(row.get("new_filing_date") or ""),
            total_changes=int(row.get("total_changes") or 0),
            by_change_type=by,
            max_score=min(100, max(0, int(row.get("max_score") or 0))),
            is_fixture=False,
            file=str(row.get("volume_path") or "").rsplit("/", 1)[-1],
        )
    except Exception as e:  # noqa: BLE001
        log.warning("skipping unusable reports row: %s", type(e).__name__)
        return None
    return {
        **card.model_dump(mode="json"),
        "analysis_id": str(row.get("analysis_id")),
        "old_accession": row.get("old_accession"),
        "new_accession": row.get("new_accession"),
        "published_by": row.get("published_by"),
        "published_at": row.get("published_at"),
        "source": "remote",
    }


def merge_library(
    local: list[dict], remote_rows: list[dict], *, keep_accessions: bool = False
) -> tuple[list[dict], list[dict]]:
    """Local cards + the store's current reports, one per ticker, deduplicated by analysis_id.
    The same analysis on both sides is one local card carrying the store's publisher/date. When
    the store's current report for a ticker is a different analysis of the same (or a newer)
    filing pair, the current one wins and the row is returned in `stale` so the caller can pull
    it to disk in the background. Returns (cards sorted by ticker, stale rows)."""
    out: dict[str, dict] = {c["ticker"]: dict(c) for c in local}
    stale: list[dict] = []
    for row in remote_rows:
        rc = card_from_row(row)
        if rc is None:
            continue
        cur = out.get(rc["ticker"])
        if cur is None:
            out[rc["ticker"]] = rc
            continue
        if cur["analysis_id"] == rc["analysis_id"]:
            cur["published_by"] = rc["published_by"]
            cur["published_at"] = rc["published_at"]
            continue
        remote_pair = (rc["new_fiscal_year"], rc["old_fiscal_year"])
        local_pair = (cur["new_fiscal_year"], cur["old_fiscal_year"])
        if remote_pair >= local_pair:
            out[rc["ticker"]] = rc
            stale.append(row)
    cards = sorted(out.values(), key=lambda c: c["ticker"])
    if not keep_accessions:
        for c in cards:
            c.pop("old_accession", None)
            c.pop("new_accession", None)
    return cards, stale


def save_report(published_dir: Path, comp: Comparison, data: bytes) -> Path:
    """Write a verified report byte-for-byte as {TICKER}_{oldFY}_{newFY}.json (atomic replace)."""
    published_dir.mkdir(parents=True, exist_ok=True)
    name = f"{comp.company.ticker}_{comp.old_filing.fiscal_year}_{comp.new_filing.fiscal_year}.json"
    path = published_dir / name
    tmp = path.with_suffix(".json.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    log.info("saved %s from the shared store (%d bytes)", name, len(data))
    return path


def _safe_load(path: Path) -> dict | None:
    """Load a published file through the contract; fixture data or invalid files are treated as absent."""
    try:
        return json.loads(load_published(path).model_dump_json())
    except Exception as e:  # noqa: BLE001
        log.warning("refusing to serve %s: %s", path.name, type(e).__name__)
        return None


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _replay_cached(ticker: str, filename: str, comp: dict):
    for i, label in enumerate(STAGE_LABELS):
        yield _sse(
            "stage",
            StageEvent(stage=i, name=label, status="cached", ticker=ticker).model_dump(mode="json"),
        )
        await asyncio.sleep(0.05)
    yield _sse(
        "complete",
        {
            "ticker": ticker,
            "analysis_id": comp.get("analysis_id"),
            "file": filename,
            "cached": True,
        },
    )


async def _run_live(state: AppState, ticker: str, request: Request):
    """Caller already holds state.busy; the worker thread releases it when the pipeline ends."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    done = object()
    cancel = threading.Event()

    def progress(ev: StageEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    def work() -> None:
        try:
            emb = state.embedder
            preloaded = (
                {"embedder": emb}
                if emb is not None and getattr(emb, "backend", "") == "sentence-transformers"
                else None
            )
            ctx = run_pipeline(
                ticker,
                state.settings,
                progress=progress,
                fixture=ticker == FIXTURE_TICKER,
                preloaded=preloaded,
                cancel=cancel,
            )
            comp = ctx.outputs["comparison"]
            result = {
                "ticker": ticker,
                "analysis_id": comp.analysis_id,
                "file": Path(ctx.outputs["published_path"]).name,
                "cached": False,
                "remote": ctx.outputs.get("remote_publish"),
            }
            state.remote.invalidate()
            state.trends.invalidate()
            loop.call_soon_threadsafe(queue.put_nowait, ("complete", result))
        except PipelineError as e:
            if e.code != "cancelled":
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    (
                        "error",
                        {
                            "code": e.code,
                            "message": FRIENDLY.get(e.code, e.message),
                            "detail": e.message,
                        },
                    ),
                )
        except Exception as e:  # noqa: BLE001
            log.exception("analysis failed: %s", type(e).__name__)
            loop.call_soon_threadsafe(
                queue.put_nowait, ("error", {"code": "internal", "message": FRIENDLY["internal"]})
            )
        finally:
            state.busy.release()
            loop.call_soon_threadsafe(queue.put_nowait, done)

    threading.Thread(target=work, name=f"analyze-{ticker}", daemon=True).start()
    started = time.monotonic()
    try:
        while True:
            remaining = ANALYZE_TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                cancel.set()
                yield _sse("error", {"code": "timeout", "message": FRIENDLY["timeout"]})
                break
            try:
                item = await asyncio.wait_for(queue.get(), timeout=min(remaining, 5.0))
            except TimeoutError:
                if await request.is_disconnected():
                    cancel.set()
                    break
                continue
            if item is done:
                break
            if isinstance(item, StageEvent):
                yield _sse("stage", item.model_dump(mode="json"))
            else:
                kind, payload = item
                yield _sse(kind, payload)
    finally:
        cancel.set()  # a client that went away must not keep a pipeline running past the next stage


app = create_app()
