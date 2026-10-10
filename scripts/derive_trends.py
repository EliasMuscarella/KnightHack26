"""Backfill derived trend facts (D-021). Idempotent: re-running changes nothing.

    uv run python scripts/derive_trends.py [--local-only]

1. Every published report on disk (`data/published/*.json`) -> `data/derived/{analysis_id}.trends.json`
   (written only when missing, stale or different).
2. When Databricks is configured (and not --local-only): every current report in the shared
   library. Its facts come from the local derived file, else the report is downloaded through the
   verified path (contract + analysis_id + content hash) and derived. Then the insert-if-absent
   MERGEs into `topic_mentions` and `category_activity`.

Exit code: 0 all ok, 1 some failed, 2 Databricks misconfigured (a bad DATABRICKS_HOST etc.).
Databricks not configured at all is not an error: the local part runs and the script says so.
Never prints secrets.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import get_databricks_settings, get_settings  # noqa: E402
from pipeline.errors import PipelineError  # noqa: E402
from pipeline.publish import load_published  # noqa: E402
from pipeline.store import DatabricksStore, StoreError  # noqa: E402
from pipeline.store.publisher import merge_trend_tables  # noqa: E402
from pipeline.trends.derive import (  # noqa: E402
    derive_trend_facts,
    derived_dir_for,
    load_facts,
    write_facts,
)


def derive_local(published_dir: Path, derived_dir: Path) -> tuple[int, int]:
    """(ok, failed) over the published reports on disk."""
    ok = failed = 0
    for p in sorted(published_dir.glob("*_*_*.json")):
        try:
            comp = load_published(p)
            facts = load_facts(derived_dir, comp.analysis_id)
            if facts is None:
                facts = derive_trend_facts(comp)
            path, changed = write_facts(derived_dir, facts)
            print(f"{'derived  ' if changed else 'unchanged'}  {p.name}  -> {path.name}")
            ok += 1
        except Exception as e:  # noqa: BLE001  (fixture, invalid file, ...)
            failed += 1
            print(f"FAILED  {p.name}  [{type(e).__name__}]", file=sys.stderr)
    return ok, failed


def derive_remote(store: DatabricksStore, derived_dir: Path) -> tuple[int, int]:
    """(ok, failed) over the shared library's current reports."""
    ok = failed = 0
    seen: set[str] = set()
    for row in store.list_reports():
        aid = str(row.get("analysis_id") or "")
        if not aid or aid in seen:
            continue
        seen.add(aid)
        try:
            facts = load_facts(derived_dir, aid)
            if facts is None:
                comp, _ = store.download_report(
                    aid,
                    volume_path=row.get("volume_path"),
                    content_sha256=row.get("content_sha256"),
                )
                facts = derive_trend_facts(comp)
                write_facts(derived_dir, facts)
            n = merge_trend_tables(store, facts)
            print(f"merged  {row.get('ticker')}  {aid[:12]}…  ({n} rows, insert-if-absent)")
            ok += 1
        except (StoreError, PipelineError) as e:
            failed += 1
            print(f"FAILED  {row.get('ticker')}  {aid[:12]}…  [{e.code}]", file=sys.stderr)
    return ok, failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Derive trend facts for every published report")
    ap.add_argument("--local-only", action="store_true", help="Skip the shared Databricks library")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    derived_dir = derived_dir_for(settings.data_dir)
    ok, failed = derive_local(settings.published_dir, derived_dir)
    if not args.local_only:
        try:
            dbs = get_databricks_settings()
        except PipelineError as e:
            print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
            return 2
        if not dbs.enabled:
            print("Databricks is not configured (DATABRICKS_HOST/TOKEN/WAREHOUSE_ID): local only.")
        else:
            try:
                r_ok, r_failed = derive_remote(DatabricksStore(dbs), derived_dir)
            except (StoreError, PipelineError) as e:
                print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
                r_ok, r_failed = 0, 1
            ok, failed = ok + r_ok, failed + r_failed
    print(f"{ok} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
