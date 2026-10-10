"""Upload every already-published local report to the shared library.

    uv run python scripts/sync_to_databricks.py [data/published/NVDA_2025_2026.json ...]

Uses exactly the pipeline's remote publish step (pipeline.store.publisher.publish_remote), so
the result is the same as if each report had been published remotely when it was produced:
the JSON lands byte-for-byte in the Volume and its rows are MERGEd into the tables, including the
derived trend facts (topic_mentions, category_activity; written to data/derived/ when missing).
Reports already in the library are no-ops. Exit code: 0 all ok, 1 some failed, 2 not configured.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import get_databricks_settings, get_settings  # noqa: E402
from pipeline.errors import PipelineError  # noqa: E402
from pipeline.store import DatabricksStore, StoreError  # noqa: E402
from pipeline.store.publisher import publish_remote  # noqa: E402
from pipeline.trends.derive import derived_dir_for  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = argv if argv is not None else sys.argv[1:]
    try:
        settings = get_databricks_settings()
    except PipelineError as e:
        print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
        return 2
    if not settings.enabled:
        print("Databricks is not configured (DATABRICKS_HOST/TOKEN/WAREHOUSE_ID); nothing to do.")
        return 2
    paths = [Path(p) for p in args] or sorted(get_settings().published_dir.glob("*_*_*.json"))
    if not paths:
        print("no published reports found")
        return 0
    try:
        store = DatabricksStore(settings)
    except PipelineError as e:
        print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
        return 1
    failed = 0
    for p in paths:
        try:
            r = publish_remote(p, store, derived_dir=derived_dir_for(get_settings().data_dir))
            print(
                f"{'published' if r.inserted else 'already present'}  {p.name}  -> {r.volume_path}"
            )
        except StoreError as e:
            failed += 1
            print(f"FAILED  {p.name}  [{e.code}] {e.message}", file=sys.stderr)
    print(f"{len(paths) - failed} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
