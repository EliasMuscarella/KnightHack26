"""Pipeline orchestrator and CLI.

    uv run python -m pipeline.run NVDA [--from-stage N] [--until-stage N] [--no-cache] [--fixture]

Stages: 0 fetch, 1 extract, 2 segment, 3 embed, 4 match, 5 diff, 6 signals, 7 llm, 8 publish.
Every stage output is cached under data/cache/stages keyed by hash(inputs + stage version).
`--from-stage N` recomputes stages >= N even when cached; `--no-cache` recomputes everything
(raw SEC downloads are still reused: a filed document never changes).
`--fixture` runs the synthetic FIXTURE filing pair (ticker FIXTUR) and writes to data/scratch/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pipeline import extract as extract_mod
from pipeline import segment as segment_mod
from pipeline.cache import StageCache
from pipeline.config import ROOT, Settings, get_settings, normalize_ticker
from pipeline.errors import PipelineError
from pipeline.schema import Company, StageEvent
from pipeline.types import ExtractedSection, FetchResult, FilingRecord, SegmentedFiling

log = logging.getLogger("pipeline")

STAGE_NAMES = ["fetch", "extract", "segment", "embed", "match", "diff", "signals", "llm", "publish"]
STAGE_LABELS = [
    "Fetch filings from EDGAR",
    "Extract Item 1A",
    "Segment risk factors",
    "Embed risk blocks",
    "Match risks across years",
    "Sentence-level diff",
    "Deterministic signals",
    "AI rubric + interpretation",
    "Score + publish",
]
FIXTURE_TICKER = "FIXTUR"
FIXTURE_DIR = ROOT / "contract" / "fixtures"

ProgressFn = Callable[[StageEvent], None]


@dataclass
class RunContext:
    settings: Settings
    cache: StageCache
    from_stage: int | None = None
    until_stage: int = 8
    fixture: bool = False
    progress: ProgressFn | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)  # compute time inside cached()
    stage_seconds: dict[str, float] = field(default_factory=dict)  # wall time, started -> done
    _stage_t0: dict[int, float] = field(default_factory=dict, repr=False)
    cancel: threading.Event | None = None
    force_publish: bool = False
    refresh_llm: bool = False
    remote: bool | None = None  # None = publish to the shared store when DATABRICKS_* is set

    def check_cancelled(self) -> None:
        if self.cancel is not None and self.cancel.is_set():
            raise PipelineError("The analysis was cancelled.", code="cancelled")

    def force(self, idx: int) -> bool:
        return (not self.cache.enabled) or (self.from_stage is not None and idx >= self.from_stage)

    def emit(
        self, idx: int, status: str, message: str | None = None, ticker: str | None = None
    ) -> None:
        if status == "started":
            self.check_cancelled()
            self._stage_t0[idx] = time.perf_counter()
        elapsed = ""
        if status != "started" and idx in self._stage_t0:
            secs = time.perf_counter() - self._stage_t0.pop(idx)
            self.stage_seconds[STAGE_NAMES[idx]] = secs
            elapsed = f" in {secs:.1f}s"
        ev = StageEvent(
            stage=idx, name=STAGE_LABELS[idx], status=status, message=message, ticker=ticker
        )
        log.info(
            "[%d %s] %s%s%s",
            idx,
            STAGE_NAMES[idx],
            status,
            elapsed,
            f": {message}" if message else "",
        )
        if self.progress:
            self.progress(ev)

    def cached(
        self,
        idx: int,
        version: str,
        inputs: Any,
        compute: Callable[[], Any],
        load: Callable[[Any], Any] | None = None,
        dump: Callable[[Any], Any] | None = None,
    ) -> Any:
        """Run a stage through the cache. `inputs` must fully determine the output."""
        name = STAGE_NAMES[idx]
        key = self.cache.key(name, version, inputs)
        if not self.force(idx):
            hit = self.cache.get(name, key)
            if hit is not None:
                return load(hit) if load else hit
        t0 = time.perf_counter()
        value = compute()
        self.timings[name] = self.timings.get(name, 0.0) + (time.perf_counter() - t0)
        self.cache.put(name, key, dump(value) if dump else value)
        return value


def _fixture_fetch_result() -> FetchResult:
    def rec(fname: str, acc: str, fy: int, period: str, filed: str) -> FilingRecord:
        p = FIXTURE_DIR / fname
        data = p.read_bytes()
        return FilingRecord(
            cik="0000000000",
            accession_number=acc,
            form="10-K",
            filing_date=filed,
            report_date=period,
            primary_document=fname,
            edgar_url=f"https://www.sec.gov/FIXTURE/not-a-real-filing-{fy}",
            edgar_index_url=f"https://www.sec.gov/FIXTURE/not-a-real-index-{fy}",
            is_amendment=False,
            html_path=str(p),
            html_sha256=hashlib.sha256(data).hexdigest(),
            fiscal_year=fy,
            fiscal_year_source="dei:DocumentFiscalYearFocus",
        )

    return FetchResult(
        company=Company(
            ticker=FIXTURE_TICKER,
            name="FIXTURE Example Widgets Corp (synthetic, not a real company)",
            cik="0000000000",
        ),
        old=rec("FIXTURE_10K_FY2024.htm", "0000000000-24-000001", 2024, "2024-01-28", "2024-02-21"),
        new=rec("FIXTURE_10K_FY2025.htm", "0000000000-25-000001", 2025, "2025-01-26", "2025-02-26"),
        selection_note="FIXTURE: synthetic filing pair; nothing here comes from EDGAR",
    )


def run_pipeline(
    ticker: str,
    settings: Settings | None = None,
    *,
    from_stage: int | None = None,
    until_stage: int = 8,
    use_cache: bool = True,
    progress: ProgressFn | None = None,
    fixture: bool = False,
    preloaded: dict[str, Any] | None = None,
    cancel: threading.Event | None = None,
    force_publish: bool = False,
    refresh_llm: bool = False,
    remote: bool | None = None,
) -> RunContext:
    """`preloaded` may carry a warm `embedder` (and `llm_client`/`llm_reason`) from a long-lived process.
    `cancel` is checked between stages. `force_publish` allows replacing a published file whose analysis_id differs.
    `remote=False` skips the shared-store publish; None publishes when Databricks is configured (its
    outcome lands in ctx.outputs["remote_publish"] and never undoes the local publish)."""
    settings = settings or get_settings()
    ticker = normalize_ticker(ticker)
    fixture = fixture or ticker == FIXTURE_TICKER
    if fixture:
        ticker = FIXTURE_TICKER
    ctx = RunContext(
        settings=settings,
        cache=StageCache(settings.cache_dir, enabled=use_cache),
        from_stage=from_stage,
        until_stage=until_stage,
        fixture=fixture,
        progress=progress,
        cancel=cancel,
        force_publish=force_publish,
        refresh_llm=refresh_llm,
        remote=remote,
    )
    if preloaded:
        ctx.outputs.update(preloaded)

    # ---- stage 0: fetch ----
    ctx.emit(0, "started", ticker=ticker)
    if fixture:
        fetch = _fixture_fetch_result()
    else:
        from pipeline.sec_fetch import run_stage0

        fetch = run_stage0(ticker, settings)
    ctx.outputs["fetch"] = fetch
    ctx.emit(
        0,
        "done",
        f"{fetch.old.form} FY{fetch.old.fiscal_year} ({fetch.old.filing_date}) vs {fetch.new.form} FY{fetch.new.fiscal_year} ({fetch.new.filing_date})",
        ticker=ticker,
    )
    if until_stage <= 0:
        return ctx

    # ---- stage 1: extract ----
    ctx.emit(1, "started", ticker=ticker)
    sections: dict[str, ExtractedSection] = {}
    for side, rec in (("old", fetch.old), ("new", fetch.new)):
        sections[side] = ctx.cached(
            1,
            extract_mod.STAGE_VERSION,
            {"accession": rec.accession_number, "html_sha256": rec.html_sha256},
            lambda rec=rec: extract_mod.run_stage1(rec.html_path, rec.accession_number),
            load=ExtractedSection.model_validate,
            dump=lambda v: v.model_dump(mode="json"),
        )
    ctx.outputs["sections"] = sections
    ctx.emit(
        1,
        "done",
        f"old: {sections['old'].word_count:,} words, new: {sections['new'].word_count:,} words",
        ticker=ticker,
    )
    if until_stage <= 1:
        return ctx

    # ---- stage 2: segment ----
    ctx.emit(2, "started", ticker=ticker)
    segs: dict[str, SegmentedFiling] = {}
    for side in ("old", "new"):
        sec = sections[side]
        segs[side] = ctx.cached(
            2,
            segment_mod.STAGE_VERSION,
            {
                "accession": sec.accession_number,
                "units_hash": hashlib.sha256(
                    json.dumps(sec.units, sort_keys=True).encode()
                ).hexdigest(),
            },
            lambda sec=sec: segment_mod.segment(sec),
            load=SegmentedFiling.model_validate,
            dump=lambda v: v.model_dump(mode="json"),
        )
    ctx.outputs["segments"] = segs
    ctx.emit(
        2,
        "done",
        f"old: {len(segs['old'].blocks)} risk blocks, new: {len(segs['new'].blocks)} risk blocks",
        ticker=ticker,
    )
    if until_stage <= 2:
        return ctx

    from pipeline.stages_late import run_late_stages

    ctx = run_late_stages(ctx, ticker)
    if "published_path" in ctx.outputs and not fixture:
        from pipeline.store.publisher import publish_remote_if_enabled

        t0 = time.perf_counter()
        ctx.outputs["remote_publish"] = publish_remote_if_enabled(
            Path(ctx.outputs["published_path"]), enabled=ctx.remote
        )
        ctx.timings["remote_publish"] = time.perf_counter() - t0
    return ctx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.run", description="RiskDiff pipeline")
    ap.add_argument("ticker", help="Ticker symbol, e.g. NVDA (or FIXTUR for the synthetic fixture)")
    ap.add_argument(
        "--from-stage", type=int, default=None, help="Recompute from this stage even if cached"
    )
    ap.add_argument("--until-stage", type=int, default=8, help="Stop after this stage (0-8)")
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore all stage caches (raw SEC downloads and raw LLM outputs are still reused; see --refresh-llm)",
    )
    ap.add_argument(
        "--refresh-llm",
        action="store_true",
        help="Re-query the LLM provider for every change instead of reusing cached raw model output "
        "(changes the published file under the same analysis_id; use deliberately)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing published file even if its analysis_id or bytes differ",
    )
    ap.add_argument(
        "--fixture", action="store_true", help="Run on the synthetic FIXTURE filing pair"
    )
    ap.add_argument(
        "--no-remote",
        action="store_true",
        help="Do not publish to the shared Databricks library even if DATABRICKS_* is set",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        ctx = run_pipeline(
            args.ticker,
            from_stage=args.from_stage,
            until_stage=args.until_stage,
            use_cache=not args.no_cache,
            fixture=args.fixture,
            force_publish=args.force,
            refresh_llm=args.refresh_llm,
            remote=False if args.no_remote else None,
        )
    except PipelineError as e:
        print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
        return 2
    if "published_path" in ctx.outputs:
        print(ctx.outputs["published_path"])
        remote = ctx.outputs.get("remote_publish") or {}
        if remote.get("status") == "ok":
            print(f"shared library: {remote['volume_path']}", file=sys.stderr)
        elif remote.get("status") == "failed":
            print(
                f"REMOTE PUBLISH FAILED [{remote.get('code')}]: {remote.get('message')} "
                "(the local published file above is intact)",
                file=sys.stderr,
            )
            return 3
    elif "comparison" in ctx.outputs:
        print(ctx.outputs["comparison"].analysis_id)
    print(format_timings(ctx), file=sys.stderr)
    return 0


def format_timings(ctx: RunContext) -> str:
    """Per-stage wall-clock table for the CLI (stderr only; never part of published output)."""
    rows = [(name, secs) for name, secs in ctx.stage_seconds.items()]
    if "remote_publish" in ctx.timings:
        rows.append(("remote_publish", ctx.timings["remote_publish"]))
    total = sum(secs for _n, secs in rows)
    width = max([len(n) for n, _s in rows] + [5])
    lines = ["stage timings (wall clock):"]
    for name, secs in rows:
        share = f"{100 * secs / total:5.1f}%" if total else "    -"
        note = (
            f"  ({ctx.outputs['llm_calls']} calls)"
            if name == "llm" and "llm_calls" in ctx.outputs
            else ""
        )
        lines.append(f"  {name:<{width}}  {secs:8.1f}s  {share}{note}")
    lines.append(f"  {'total':<{width}}  {total:8.1f}s")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
