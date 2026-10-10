"""Re-run every stale published report from the earliest stage that changed, then republish and
re-derive its trend facts.

    uv run python scripts/refresh_stale.py [--integrity data/integrity/latest.json] [--only NVDA,SF]
                                           [--dry-run] [--redo] [--no-remote]

Which reports are stale comes from the integrity checker's STALE findings (run it first, or pass
`--check` to run it here). Order: NVDA first (its re-run starts at segmentation, the longest), then
the rest from the oldest published file to the newest.

How "from the earliest stage" works: every stage output is cached under data/cache/stages keyed by
hash(inputs + STAGE_VERSION). A plain `pipeline.run TICKER --force` therefore reuses the cached
output of every stage whose inputs and version are unchanged (raw filings forever, embeddings
unless segmentation changed) and recomputes only from the first stage whose version moved. When the
checker could name the earliest stage (the report records `stage_versions`, or a finding points at
a stage), that stage is passed as `--from-stage` to force recomputation from there even if an old
cache entry would match. The slow embedding stage is recomputed only when segmentation (stage 2) or
embedding (stage 3) changed.

Republishing: `pipeline.run --force` replaces the local published file whose analysis_id differs
(the superseded analysis stays in the shared library with `is_current` moved, never deleted) and,
when Databricks is configured, uploads it and MERGEs its rows (`--no-remote` skips that). Trend
facts are re-derived by the publish hook (data/derived/) and backfilled with
`scripts/derive_trends.py` at the end.

Resumable: per-ticker status, timing and the new analysis_id go to data/integrity/refresh_log.jsonl;
a ticker already refreshed on the current code fingerprint is skipped unless `--redo`. Failures are
logged and the script continues; the exit code is 1 when any report failed, 2 when the integrity
JSON is missing. Never prints secrets. No shell command is built from user input: tickers are
validated and passed as arguments to `python -m pipeline.run`.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import normalize_ticker  # noqa: E402
from pipeline.score import code_fingerprint  # noqa: E402

log = logging.getLogger("refresh")
LOG_PATH = ROOT / "data" / "integrity" / "refresh_log.jsonl"
FIRST = ("NVDA",)  # longest re-run first (segmentation changed); then the rest by age


def stale_reports(integrity: dict) -> list[dict]:
    """[{ticker, analysis_id, earliest_stage}] from the checker's STALE findings and report table."""
    stage_by_ticker = {r["ticker"]: r.get("earliest_stage") for r in integrity.get("reports", [])}
    out = []
    for v in integrity.get("violations", []):
        if v.get("check") != "STALE":
            continue
        t = v["ticker"]
        out.append(
            {
                "ticker": t,
                "analysis_id": v.get("analysis_id"),
                "earliest_stage": v.get("stage")
                if v.get("stage") is not None
                else stage_by_ticker.get(t),
            }
        )
    return out


def published_mtime(ticker: str, published_dir: Path) -> float:
    files = sorted(published_dir.glob(f"{ticker}_*_*.json"))
    return max((p.stat().st_mtime for p in files), default=0.0)


def order(reports: list[dict], published_dir: Path) -> list[dict]:
    first = [r for r in reports if r["ticker"] in FIRST]
    rest = sorted(
        (r for r in reports if r["ticker"] not in FIRST),
        key=lambda r: (published_mtime(r["ticker"], published_dir), r["ticker"]),
    )
    return first + rest


def read_log(path: Path = LOG_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def append_log(entry: dict, path: Path = LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def already_done(ticker: str, fingerprint: str, entries: list[dict]) -> bool:
    return any(
        e.get("ticker") == ticker
        and e.get("status") == "ok"
        and e.get("code_fingerprint") == fingerprint
        for e in entries
    )


def run_command(ticker: str, from_stage: int | None, no_remote: bool) -> list[str]:
    cmd = [sys.executable, "-m", "pipeline.run", ticker, "--force"]
    if from_stage is not None:
        cmd += ["--from-stage", str(from_stage)]
    if no_remote:
        cmd.append("--no-remote")
    return cmd


def new_analysis_id(ticker: str, published_dir: Path) -> str | None:
    files = sorted(published_dir.glob(f"{ticker}_*_*.json"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8")).get("analysis_id")
    except (OSError, ValueError):
        return None


def refresh_one(
    r: dict,
    *,
    published_dir: Path,
    no_remote: bool,
    dry_run: bool,
    runner=subprocess.run,  # noqa: ANN001
) -> dict:
    ticker = normalize_ticker(r["ticker"])
    stage = r.get("earliest_stage")
    cmd = run_command(ticker, stage, no_remote)
    entry = {
        "ticker": ticker,
        "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "from_stage": stage,
        "previous_analysis_id": r.get("analysis_id"),
        "command": " ".join(cmd[1:]),
        "code_fingerprint": code_fingerprint(),
    }
    if dry_run:
        return {**entry, "status": "dry-run", "seconds": 0.0}
    t0 = time.monotonic()
    try:
        proc = runner(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=3 * 3600)
        rc = proc.returncode
        tail = (proc.stderr or proc.stdout or "")[-2000:]
    except subprocess.TimeoutExpired:
        rc, tail = 124, "timed out after 3 hours"
    except OSError as e:
        rc, tail = 127, type(e).__name__
    seconds = round(time.monotonic() - t0, 1)
    status = "ok" if rc == 0 else ("ok-local-only" if rc == 3 else "failed")
    return {
        **entry,
        "status": status,
        "exit_code": rc,
        "seconds": seconds,
        "new_analysis_id": new_analysis_id(ticker, published_dir) if rc in (0, 3) else None,
        "log_tail": tail if rc not in (0, 3) else "",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Re-run stale RiskDiff reports from their earliest changed stage"
    )
    ap.add_argument("--integrity", default=str(ROOT / "data" / "integrity" / "latest.json"))
    ap.add_argument(
        "--check", action="store_true", help="Run scripts/check_integrity.py first (no API)"
    )
    ap.add_argument("--published", default=str(ROOT / "data" / "published"))
    ap.add_argument("--only", default=None, help="Comma-separated tickers to restrict to")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--redo", action="store_true", help="Re-run tickers already refreshed on this code"
    )
    ap.add_argument("--no-remote", action="store_true", help="Skip the Databricks publish step")
    ap.add_argument("--log", default=str(LOG_PATH))
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    published_dir = Path(args.published)
    log_path = Path(args.log)

    if args.check:
        subprocess.run(  # noqa: S603 (fixed argv, no user input)
            [
                sys.executable,
                str(ROOT / "scripts" / "check_integrity.py"),
                "--no-api",
                "--json",
                args.integrity,
            ],
            cwd=str(ROOT),
            check=False,
        )
    try:
        integrity = json.loads(Path(args.integrity).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print(
            f"ERROR: integrity JSON not found or unreadable: {args.integrity} (run scripts/check_integrity.py or pass --check)",
            file=sys.stderr,
        )
        return 2
    reports = stale_reports(integrity)
    if args.only:
        wanted = {normalize_ticker(t) for t in args.only.split(",") if t.strip()}
        reports = [r for r in reports if r["ticker"] in wanted]
    reports = order(reports, published_dir)
    if not reports:
        print("nothing stale")
        return 0
    entries = read_log(log_path)
    fp = code_fingerprint()
    failed = 0
    for r in reports:
        t = r["ticker"]
        if not args.redo and already_done(t, fp, entries):
            print(f"skip  {t}: already refreshed on code {fp[:12]}")
            continue
        print(
            f"start {t}: from stage {r.get('earliest_stage') if r.get('earliest_stage') is not None else 'auto (cache decides)'}"
        )
        result = refresh_one(
            r, published_dir=published_dir, no_remote=args.no_remote, dry_run=args.dry_run
        )
        if not args.dry_run:
            append_log(result, log_path)
        print(
            f"{result['status']:<14} {t}  {result.get('seconds', 0)}s  analysis_id {str(result.get('new_analysis_id'))[:12]}"
        )
        if result["status"] == "failed":
            failed += 1
            print(result.get("log_tail", "")[-600:], file=sys.stderr)
    if not args.dry_run:
        derive = subprocess.run(  # noqa: S603
            [sys.executable, str(ROOT / "scripts" / "derive_trends.py")]
            + (["--local-only"] if args.no_remote else []),
            cwd=str(ROOT),
            check=False,
        )
        if derive.returncode not in (0,):
            print(f"derive_trends exited {derive.returncode}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
