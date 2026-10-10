"""One-time (and safely repeatable) Databricks bootstrap for the shared report library.

    uv run python scripts/databricks_setup.py [--dry-run]

Creates, if missing, the schema, the Volume and the Delta tables (`reports`, `changes`,
`highlights`, and the derived trend facts `topic_mentions`, `category_activity`) under
DATABRICKS_CATALOG.DATABRICKS_SCHEMA. Existing workspaces just re-run it to get the two new tables,
then `scripts/derive_trends.py` backfills them. Every statement is CREATE ... IF NOT
EXISTS, so a second run changes nothing. It needs no permission beyond creating objects in the
configured catalog and schema (the catalog itself must already exist). Never prints secrets.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import get_databricks_settings  # noqa: E402
from pipeline.errors import ConfigError  # noqa: E402
from pipeline.store import (  # noqa: E402
    DatabricksStore,
    StoreError,
    tables,  # noqa: E402
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Create the RiskDiff schema, Volume and tables")
    ap.add_argument("--dry-run", action="store_true", help="Print the statements and exit")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = get_databricks_settings()
    except ConfigError as e:
        print(f"ERROR [config]: {e.message}", file=sys.stderr)
        return 2
    print("Databricks settings:", settings.redacted())
    statements = tables.ddl(settings)
    if args.dry_run:
        for label, sql in statements:
            print(f"-- {label}\n{sql};\n")
        return 0
    if not settings.enabled:
        print(
            "ERROR [config]: set DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID "
            "(see .env.example)",
            file=sys.stderr,
        )
        return 2
    try:
        store = DatabricksStore(settings)
        for label, sql in statements:
            store.execute(sql)
            print(f"ok  {label}")
        store.health()
    except StoreError as e:
        print(f"ERROR [{e.code}]: {e.message}", file=sys.stderr)
        return 1
    print(
        f"ready: {settings.volume_root} and {', '.join(settings.table(t) for t in tables.TABLES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
