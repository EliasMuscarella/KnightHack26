"""RiskDiff API (FastAPI).

GET  /health                 liveness + whether the embedding model is warm
GET  /companies              report library: local published files merged with the current
                             reports of the shared Databricks store (deduplicated by analysis_id)
GET  /comparison/{ticker}    the published Comparison JSON (read-through cache: local file first,
                             else fetched from the shared store, verified, saved locally, served)
GET  /store/health           {"remote": "ok" | "offline" | "disabled"}
GET  /trends                 cross-company aggregates from the shared store's tables
POST /analyze {"ticker"}     runs the pipeline, streaming StageEvents over SSE; serves a cached
                             result (all stages reported as "cached") when one is published

Security posture: strict ticker validation, CORS restricted to the local frontend origin, one
analysis at a time, a per-analysis timeout, and no stack traces in responses. Databricks is
optional: with no DATABRICKS_* variables everything is local; when it is configured but
unreachable, local reports keep being served and /store/health says "offline". Credentials
never leave the Python process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from pipeline.config import (
    PIPELINE_VERSION,
    Settings,
    get_databricks_settings,
    get_settings,
    normalize_ticker,
)
from pipeline.errors import InvalidTicker, PipelineError
from pipeline.publish import load_published
from pipeline.run import FIXTURE_TICKER, STAGE_LABELS, run_pipeline
from pipeline.schema import CHANGE_TYPES, CompanyCard, Comparison, StageEvent
from pipeline.store import DatabricksStore, StoreDisabled, StoreError, tables

log = logging.getLogger("api")

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
REMOTE_MISS_WAIT_SECONDS = 60.0  # on a local miss, how long /comparison may wait for the store
HEALTH_TTL_SECONDS = 15.0
HEALTH_TIMEOUT_SECONDS = 5.0
TRENDS_TTL_SECONDS = 60.0

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
    background thread; requests never wait longer than a short bound), a health probe with its
    own TTL, the read-through pull of a report that is not on disk, and the trends aggregates.
    Every failure degrades to "offline": local reports are always served."""

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
        self._health: tuple[float, str] | None = None
        self._trends: tuple[float, dict] | None = None
        self._pulling: set[str] = set()

    # -- store handle --

    def store(self) -> Any | None:
        with self.lock:
            if self.disabled or self._store is not None:
                return self._store
            try:
                self._store = self._factory()
            except StoreDisabled:
                self.disabled = True
            except PipelineError as e:  # bad host / identifiers: configured but unusable
                self._store_failed = e.code
                log.warning("shared store not usable: %s", e.code)
                self.disabled = True
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
        except StoreError as e:
            log.warning("shared store list failed [%s]", e.code)
            with self.lock:
                self.reports_ok = False
                self.reports_at = time.monotonic() - (
                    REMOTE_LIST_TTL_SECONDS - REMOTE_FAIL_TTL_SECONDS
                )
        except Exception as e:  # noqa: BLE001
            log.warning("shared store list failed: %s", type(e).__name__)
            with self.lock:
                self.reports_ok = False
                self.reports_at = time.monotonic() - (
                    REMOTE_LIST_TTL_SECONDS - REMOTE_FAIL_TTL_SECONDS
                )

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
            self._trends = None

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

    def health(self) -> str:
        store = self.store()
        if store is None:
            return "disabled"
        with self.lock:
            if self._health and time.monotonic() - self._health[0] < HEALTH_TTL_SECONDS:
                return self._health[1]
        try:
            store.health()
            status = "ok"
        except (StoreError, PipelineError):
            status = "offline"
        except Exception as e:  # noqa: BLE001
            log.warning("store health failed: %s", type(e).__name__)
            status = "offline"
        with self.lock:
            self._health = (time.monotonic(), status)
        return status

    # -- read-through pull --

    def pull_for_ticker(self, ticker: str, published_dir: Path, *, wait: float) -> Path | None:
        """Local miss: find the ticker's current report in the store, download + verify it, save it
        under published_dir and return the path. Any failure -> None (the caller answers 404)."""
        if self.store() is None:
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

    # -- trends --

    def trends(self) -> dict:
        store = self.store()
        if store is None:
            return {
                "available": False,
                "remote": "disabled",
                "companies": 0,
                "by_category": [],
                "by_kind": [],
            }
        with self.lock:
            if self._trends and time.monotonic() - self._trends[0] < TRENDS_TTL_SECONDS:
                return self._trends[1]
        s = store.settings
        try:
            count = store.execute(tables.company_count_sql(s), {"current": True})
            by_cat = store.execute(
                tables.trends_by_category_sql(s),
                {"current": True, "unchanged": "largely_unchanged"},
            )
            by_kind = store.execute(tables.trends_by_kind_sql(s), {"current": True})
        except (StoreError, PipelineError) as e:
            log.warning("trends unavailable [%s]", e.code)
            return {
                "available": False,
                "remote": "offline",
                "companies": 0,
                "by_category": [],
                "by_kind": [],
            }
        companies = int((count[0].get("companies") if count else 0) or 0)
        out = {
            "available": True,
            "remote": "ok",
            "companies": companies,
            "by_category": [
                {
                    "category": str(r.get("category")),
                    "change_type": str(r.get("change_type")),
                    "companies": int(r.get("companies") or 0),
                }
                for r in by_cat
                if r.get("change_type") in CHANGE_TYPES
            ],
            "by_kind": [
                {
                    "ticker": str(r.get("ticker")),
                    "company_name": str(r.get("company_name") or ""),
                    "kind": str(r.get("kind")),
                    "highlights": int(r.get("highlights") or 0),
                }
                for r in by_kind
            ],
        }
        with self.lock:
            self._trends = (time.monotonic(), out)
        return out


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
        # warm the shared-store list in the background so the first page load already has it
        threading.Thread(
            target=lambda: state.remote.ensure_fresh(0), name="store-warmup", daemon=True
        ).start()
        yield

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
    async def store_health() -> dict[str, str]:
        try:
            status = await asyncio.wait_for(
                asyncio.to_thread(state.remote.health), timeout=HEALTH_TIMEOUT_SECONDS
            )
        except TimeoutError:
            status = "offline"
        return {"remote": status}

    @app.get("/trends")
    async def trends() -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(state.remote.trends), timeout=REMOTE_MISS_WAIT_SECONDS
            )
        except TimeoutError:
            return {
                "available": False,
                "remote": "offline",
                "companies": 0,
                "by_category": [],
                "by_kind": [],
            }

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


def merge_library(local: list[dict], remote_rows: list[dict]) -> tuple[list[dict], list[dict]]:
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
