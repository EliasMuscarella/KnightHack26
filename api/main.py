"""RiskDiff API (FastAPI).

GET  /health                 liveness + whether the embedding model is warm
GET  /companies              published comparisons as CompanyCard[]
GET  /comparison/{ticker}    the published Comparison JSON
POST /analyze {"ticker"}     runs the pipeline, streaming StageEvents over SSE; serves a cached
                             result (all stages reported as "cached") when one is published

Security posture: strict ticker validation, CORS restricted to the local frontend origin, one
analysis at a time, a per-analysis timeout, and no stack traces in responses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from pipeline.config import PIPELINE_VERSION, Settings, get_settings, normalize_ticker
from pipeline.errors import InvalidTicker, PipelineError
from pipeline.run import FIXTURE_TICKER, STAGE_LABELS, run_pipeline
from pipeline.schema import CompanyCard, Comparison, StageEvent

log = logging.getLogger("api")

ANALYZE_TIMEOUT_SECONDS = int(os.environ.get("RISKDIFF_ANALYZE_TIMEOUT", "1500"))
ALLOW_FIXTURE = os.environ.get("RISKDIFF_ALLOW_FIXTURE", "") == "1"

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
    "internal": "Something went wrong on the server.",
}


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


class AppState:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedder = None
        self.embedder_error: str | None = None
        self.warm = False
        self.lock = asyncio.Lock()
        self._cards_cache: dict[str, tuple[float, CompanyCard]] = {}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    state = AppState(settings)
    app = FastAPI(title="RiskDiff API", version=PIPELINE_VERSION, docs_url="/docs", redoc_url=None)
    app.state.rd = state

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

    @app.on_event("startup")
    async def _warm() -> None:
        def load() -> None:
            try:
                from pipeline.embed import load_embedder

                state.embedder = load_embedder(settings)
            except Exception as e:  # noqa: BLE001
                state.embedder_error = f"{type(e).__name__}"
                log.warning("embedding warm-up failed: %s", e)
            finally:
                state.warm = True

        threading.Thread(target=load, name="embed-warmup", daemon=True).start()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        emb = state.embedder
        return {
            "status": "ok",
            "model_warm": state.warm and emb is not None,
            "embedding_backend": getattr(emb, "backend", None),
            "embedding_model": getattr(emb, "model_id", None),
            "pipeline_version": PIPELINE_VERSION,
            "sec_configured": bool(settings.sec_user_agent),
        }

    @app.get("/companies")
    async def companies() -> dict[str, list[dict]]:
        cards = await asyncio.to_thread(list_cards, state)
        return {"companies": [c.model_dump(mode="json") for c in cards]}

    @app.get("/comparison/{ticker}")
    async def comparison(ticker: str) -> Any:
        t = normalize_ticker(ticker)
        path = await asyncio.to_thread(find_published, settings.published_dir, t)
        if path is None:
            raise HTTPException(
                status_code=404,
                detail=f"No published comparison for {t}. Use POST /analyze to run one.",
            )
        return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))

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
        if cached is not None:
            return EventSourceResponse(_replay_cached(t, cached), ping=15)
        if not settings.sec_user_agent and t != FIXTURE_TICKER:
            raise HTTPException(status_code=503, detail=FRIENDLY["config"])
        if state.lock.locked():
            raise HTTPException(status_code=409, detail=FRIENDLY["busy"])
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
    out: list[CompanyCard] = []
    pdir = state.settings.published_dir
    if not pdir.exists():
        return out
    seen: set[str] = set()
    for p in sorted(pdir.glob("*_*_*.json"), key=lambda p: p.stem.split("_")[-1], reverse=True):
        try:
            mtime = p.stat().st_mtime
            cached = state._cards_cache.get(str(p))
            if cached and cached[0] == mtime:
                card = cached[1]
            else:
                comp = Comparison.model_validate_json(p.read_text(encoding="utf-8"))
                if comp.is_fixture:
                    continue
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
                state._cards_cache[str(p)] = (mtime, card)
            if card.ticker in seen:
                continue
            seen.add(card.ticker)
            out.append(card)
        except Exception as e:  # noqa: BLE001
            log.warning("skipping unreadable published file %s: %s", p.name, type(e).__name__)
    return sorted(out, key=lambda c: c.ticker)


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def _replay_cached(ticker: str, path: Path):
    for i, label in enumerate(STAGE_LABELS):
        yield _sse(
            "stage",
            StageEvent(stage=i, name=label, status="cached", ticker=ticker).model_dump(mode="json"),
        )
        await asyncio.sleep(0.05)
    comp = json.loads(path.read_text(encoding="utf-8"))
    yield _sse(
        "complete",
        {
            "ticker": ticker,
            "analysis_id": comp.get("analysis_id"),
            "file": path.name,
            "cached": True,
        },
    )


async def _run_live(state: AppState, ticker: str, request: Request):
    async with state.lock:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[Any] = asyncio.Queue()
        done = object()

        def progress(ev: StageEvent) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, ev)

        def work() -> dict:
            preloaded = {"embedder": state.embedder} if state.embedder is not None else None
            ctx = run_pipeline(
                ticker,
                state.settings,
                progress=progress,
                fixture=ticker == FIXTURE_TICKER,
                preloaded=preloaded,
            )
            comp = ctx.outputs["comparison"]
            return {
                "ticker": ticker,
                "analysis_id": comp.analysis_id,
                "file": Path(ctx.outputs["published_path"]).name,
                "cached": False,
            }

        task = loop.run_in_executor(None, work)
        started = time.monotonic()

        async def finish() -> None:
            try:
                result = await task
                queue.put_nowait(("complete", result))
            except PipelineError as e:
                queue.put_nowait(
                    (
                        "error",
                        {
                            "code": e.code,
                            "message": FRIENDLY.get(e.code, e.message),
                            "detail": e.message,
                        },
                    )
                )
            except Exception as e:  # noqa: BLE001
                log.exception("analysis failed: %s", type(e).__name__)
                queue.put_nowait(("error", {"code": "internal", "message": FRIENDLY["internal"]}))
            finally:
                queue.put_nowait(done)

        finisher = asyncio.ensure_future(finish())
        try:
            while True:
                remaining = ANALYZE_TIMEOUT_SECONDS - (time.monotonic() - started)
                if remaining <= 0:
                    yield _sse("error", {"code": "timeout", "message": FRIENDLY["timeout"]})
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=min(remaining, 5.0))
                except TimeoutError:
                    if await request.is_disconnected():
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
            if not finisher.done():
                finisher.cancel()


app = create_app()
