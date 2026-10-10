"""Delta tables derived from published JSON: DDL, MERGE statements and row builders.

The JSON in the Volume is the source of truth; these tables are a rebuildable projection of it
(`scripts/sync_to_databricks.py` re-derives them from the local published files). Table and column
names are constants here; every statement takes its values through parameter markers (`:name`).
Rows are shipped as ONE JSON-text parameter and decoded in SQL with `from_json`, so a whole table
write is a single parameterized MERGE.
"""

from __future__ import annotations

import json
from datetime import datetime

from pipeline.config import DatabricksSettings
from pipeline.schema import CHANGE_TYPES, Comparison

REPORTS = "reports"
CHANGES = "changes"
HIGHLIGHTS = "highlights"
TABLES = (REPORTS, CHANGES, HIGHLIGHTS)

# (column, SQL type) in table order; the struct schema for from_json is derived from this.
REPORT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analysis_id", "STRING"),
    ("ticker", "STRING"),
    ("company_name", "STRING"),
    ("cik", "STRING"),
    ("old_fiscal_year", "INT"),
    ("new_fiscal_year", "INT"),
    ("old_accession", "STRING"),
    ("new_accession", "STRING"),
    ("old_filing_date", "DATE"),
    ("new_filing_date", "DATE"),
    ("pipeline_version", "STRING"),
    ("rubric_version", "STRING"),
    ("published_at", "TIMESTAMP"),
    ("published_by", "STRING"),
    ("volume_path", "STRING"),
    ("content_sha256", "STRING"),
    ("is_current", "BOOLEAN"),
    ("total_changes", "INT"),
    ("max_score", "INT"),
    *((f"n_{ct}", "INT") for ct in CHANGE_TYPES),
)
CHANGE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analysis_id", "STRING"),
    ("change_id", "STRING"),
    ("ticker", "STRING"),
    ("rank", "INT"),
    ("short_title", "STRING"),
    ("title", "STRING"),
    ("change_type", "STRING"),
    ("score", "INT"),
    ("categories", "ARRAY<STRING>"),
    ("added", "INT"),
    ("removed", "INT"),
    ("modified", "INT"),
)
HIGHLIGHT_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analysis_id", "STRING"),
    ("change_id", "STRING"),
    ("ticker", "STRING"),
    ("position", "INT"),
    ("kind", "STRING"),
    ("short_title", "STRING"),
    ("old_sentence_id", "STRING"),
    ("new_sentence_id", "STRING"),
    ("old_text", "STRING"),
    ("new_text", "STRING"),
)
COLUMNS = {REPORTS: REPORT_COLUMNS, CHANGES: CHANGE_COLUMNS, HIGHLIGHTS: HIGHLIGHT_COLUMNS}
KEYS = {
    REPORTS: ("analysis_id",),
    CHANGES: ("analysis_id", "change_id"),
    HIGHLIGHTS: ("analysis_id", "change_id", "position"),
}


# ---------- DDL (all IF NOT EXISTS; running it twice changes nothing) ----------


def ddl(s: DatabricksSettings) -> list[tuple[str, str]]:
    """(label, statement) pairs in execution order."""
    out = [
        ("schema", f"CREATE SCHEMA IF NOT EXISTS `{s.catalog}`.`{s.schema}`"),
        ("volume", f"CREATE VOLUME IF NOT EXISTS `{s.catalog}`.`{s.schema}`.`{s.volume}`"),
    ]
    for table, cols in COLUMNS.items():
        col_sql = ",\n  ".join(
            f"`{name}` {typ}" + (" NOT NULL" if name in KEYS[table] else "") for name, typ in cols
        )
        out.append(
            (table, f"CREATE TABLE IF NOT EXISTS {s.table(table)} (\n  {col_sql}\n) USING DELTA")
        )
    return out


# ---------- rows ----------


def report_row(
    comp: Comparison,
    *,
    volume_path: str,
    content_sha256: str,
    published_by: str,
    published_at: datetime,
) -> dict:
    by = comp.summary.by_change_type
    return {
        "analysis_id": comp.analysis_id,
        "ticker": comp.company.ticker,
        "company_name": comp.company.name,
        "cik": comp.company.cik,
        "old_fiscal_year": comp.old_filing.fiscal_year,
        "new_fiscal_year": comp.new_filing.fiscal_year,
        "old_accession": comp.old_filing.accession_number,
        "new_accession": comp.new_filing.accession_number,
        "old_filing_date": comp.old_filing.filing_date,
        "new_filing_date": comp.new_filing.filing_date,
        "pipeline_version": comp.pipeline_version,
        "rubric_version": comp.rubric_version,
        "published_at": published_at.isoformat(timespec="seconds"),
        "published_by": published_by,
        "volume_path": volume_path,
        "content_sha256": content_sha256,
        "is_current": True,
        "total_changes": comp.summary.total_changes,
        "max_score": comp.summary.max_score,
        **{f"n_{ct}": int(by.get(ct, 0)) for ct in CHANGE_TYPES},
    }


def change_rows(comp: Comparison) -> list[dict]:
    return [
        {
            "analysis_id": comp.analysis_id,
            "change_id": c.id,
            "ticker": comp.company.ticker,
            "rank": c.rank,
            "short_title": c.short_title,
            "title": c.title,
            "change_type": c.change_type,
            "score": c.score,
            "categories": list(c.categories),
            "added": c.stats.added,
            "removed": c.stats.removed,
            "modified": c.stats.modified,
        }
        for c in comp.changes
    ]


def highlight_rows(comp: Comparison) -> list[dict]:
    idx = comp.sentence_index
    out = []
    for i, h in enumerate(comp.highlights):
        out.append(
            {
                "analysis_id": comp.analysis_id,
                "change_id": h.change_id,
                "ticker": comp.company.ticker,
                "position": i,
                "kind": h.kind,
                "short_title": h.short_title,
                "old_sentence_id": h.old_sentence_id,
                "new_sentence_id": h.new_sentence_id,
                "old_text": idx[h.old_sentence_id].text if h.old_sentence_id in idx else None,
                "new_text": idx[h.new_sentence_id].text if h.new_sentence_id in idx else None,
            }
        )
    return out


def rows_json(rows: list[dict]) -> str:
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":"))


# ---------- statements (parameter markers only; identifiers are constants) ----------


def struct_schema(columns: tuple[tuple[str, str], ...]) -> str:
    return "array<struct<" + ",".join(f"{n}:{t}" for n, t in columns) + ">>"


def merge_sql(s: DatabricksSettings, table: str) -> str:
    """Insert-if-absent MERGE. Rows of an analysis never change (same analysis_id == same
    content), so a matched row is left untouched: re-publishing is a no-op."""
    cols = COLUMNS[table]
    on = " AND ".join(f"t.`{k}` = src.`{k}`" for k in KEYS[table])
    return (
        f"MERGE INTO {s.table(table)} AS t\n"
        f"USING (SELECT inline(from_json(:rows, '{struct_schema(cols)}'))) AS src\n"
        f"ON {on}\n"
        f"WHEN NOT MATCHED THEN INSERT *"
    )


def exists_sql(s: DatabricksSettings) -> str:
    return f"SELECT analysis_id FROM {s.table(REPORTS)} WHERE analysis_id = :analysis_id"


def path_for_sql(s: DatabricksSettings) -> str:
    return (
        f"SELECT volume_path, ticker, content_sha256 FROM {s.table(REPORTS)} "
        f"WHERE analysis_id = :analysis_id"
    )


def flip_current_sql(s: DatabricksSettings) -> str:
    """Make :analysis_id the current report for its ticker + filing pair; only rows whose flag
    actually changes are written (so a repeat is a no-op)."""
    return (
        f"UPDATE {s.table(REPORTS)} SET is_current = (analysis_id = :analysis_id)\n"
        f"WHERE ticker = :ticker AND old_accession = :old_accession AND new_accession = :new_accession\n"
        f"  AND is_current <> (analysis_id = :analysis_id)"
    )


def list_current_sql(s: DatabricksSettings) -> str:
    cols = ", ".join(f"`{n}`" for n, _ in REPORT_COLUMNS)
    return (
        f"SELECT {cols} FROM {s.table(REPORTS)} WHERE is_current = :current\n"
        f"ORDER BY ticker, new_fiscal_year DESC, old_fiscal_year DESC"
    )


def trends_by_category_sql(s: DatabricksSettings) -> str:
    """Per category and change type: how many companies (current reports) have such a change."""
    return (
        f"SELECT cat AS category, c.change_type, COUNT(DISTINCT c.ticker) AS companies\n"
        f"FROM {s.table(CHANGES)} c\n"
        f"JOIN {s.table(REPORTS)} r ON r.analysis_id = c.analysis_id AND r.is_current = :current\n"
        f"LATERAL VIEW explode(c.categories) AS cat\n"
        f"WHERE c.change_type <> :unchanged\n"
        f"GROUP BY cat, c.change_type ORDER BY cat, c.change_type"
    )


def trends_by_kind_sql(s: DatabricksSettings) -> str:
    """Per company: how many highlights of each kind (current reports)."""
    return (
        f"SELECT h.ticker, r.company_name, h.kind, COUNT(*) AS highlights\n"
        f"FROM {s.table(HIGHLIGHTS)} h\n"
        f"JOIN {s.table(REPORTS)} r ON r.analysis_id = h.analysis_id AND r.is_current = :current\n"
        f"GROUP BY h.ticker, r.company_name, h.kind ORDER BY h.ticker, h.kind"
    )


def company_count_sql(s: DatabricksSettings) -> str:
    return f"SELECT COUNT(DISTINCT ticker) AS companies FROM {s.table(REPORTS)} WHERE is_current = :current"
