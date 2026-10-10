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
from pipeline.trends.derive import added_spans, removed_spans
from pipeline.trends.schema import TrendFacts

REPORTS = "reports"
CHANGES = "changes"
HIGHLIGHTS = "highlights"
TOPIC_MENTIONS = "topic_mentions"  # derived trend facts (D-021), one row per sentence + topic
CATEGORY_ACTIVITY = "category_activity"  # derived trend facts, one row per change + category
TABLES = (REPORTS, CHANGES, HIGHLIGHTS, TOPIC_MENTIONS, CATEGORY_ACTIVITY)
TREND_TABLES = (TOPIC_MENTIONS, CATEGORY_ACTIVITY)
MERGE_CHUNK_ROWS = 500  # rows per MERGE statement (keeps each JSON parameter small)

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
    ("old_spans_json", "STRING"),  # [[start, end], ...] of removed words inside old_text
    ("new_spans_json", "STRING"),  # [[start, end], ...] of added words inside new_text
)
TOPIC_MENTION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analysis_id", "STRING"),
    ("ticker", "STRING"),
    ("change_id", "STRING"),
    ("sentence_id", "STRING"),
    ("position", "INT"),
    ("topic", "STRING"),
    ("topic_source", "STRING"),
    ("matched_terms", "ARRAY<STRING>"),
    ("status", "STRING"),
    ("sentence_text", "STRING"),
    ("added_spans_json", "STRING"),
)
CATEGORY_ACTIVITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("analysis_id", "STRING"),
    ("ticker", "STRING"),
    ("change_id", "STRING"),
    ("category", "STRING"),
    ("change_type", "STRING"),
    ("score", "INT"),
    ("added_sentences", "INT"),
    ("removed_sentences", "INT"),
    ("modified_sentences", "INT"),
    ("added_words", "INT"),
    ("removed_words", "INT"),
    ("modified_words", "INT"),
)
COLUMNS = {
    REPORTS: REPORT_COLUMNS,
    CHANGES: CHANGE_COLUMNS,
    HIGHLIGHTS: HIGHLIGHT_COLUMNS,
    TOPIC_MENTIONS: TOPIC_MENTION_COLUMNS,
    CATEGORY_ACTIVITY: CATEGORY_ACTIVITY_COLUMNS,
}
KEYS = {
    REPORTS: ("analysis_id",),
    CHANGES: ("analysis_id", "change_id"),
    HIGHLIGHTS: ("analysis_id", "change_id", "position"),
    TOPIC_MENTIONS: ("analysis_id", "change_id", "sentence_id", "topic"),
    CATEGORY_ACTIVITY: ("analysis_id", "change_id", "category"),
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


# Columns added after a table first shipped: (table, column, type). `databricks_setup.py` adds
# them to an existing table with ALTER TABLE ... ADD COLUMNS when DESCRIBE shows they are missing.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    (HIGHLIGHTS, "old_spans_json", "STRING"),
    (HIGHLIGHTS, "new_spans_json", "STRING"),
)


def describe_sql(s: DatabricksSettings, table: str) -> str:
    return f"DESCRIBE TABLE {s.table(table)}"


def add_columns_sql(s: DatabricksSettings, table: str, cols: list[tuple[str, str]]) -> str:
    col_sql = ", ".join(f"`{name}` {typ}" for name, typ in cols)
    return f"ALTER TABLE {s.table(table)} ADD COLUMNS ({col_sql})"


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
    sentences = {s.id: s for c in comp.changes for s in c.sentences}  # carry the diff marks
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
                "old_spans_json": json.dumps(
                    [list(sp) for sp in removed_spans(sentences[h.old_sentence_id])]
                    if h.old_sentence_id in sentences
                    else []
                ),
                "new_spans_json": json.dumps(
                    [list(sp) for sp in added_spans(sentences[h.new_sentence_id])]
                    if h.new_sentence_id in sentences
                    else []
                ),
            }
        )
    return out


def topic_mention_rows(facts: TrendFacts) -> list[dict]:
    return [
        {
            "analysis_id": facts.analysis_id,
            "ticker": m.ticker,
            "change_id": m.change_id,
            "sentence_id": m.sentence_id,
            "position": m.position,
            "topic": m.topic,
            "topic_source": m.source,
            "matched_terms": list(m.matched_terms),
            "status": m.status,
            "sentence_text": m.text,
            "added_spans_json": json.dumps([list(sp) for sp in m.added_spans]),
        }
        for m in facts.topic_mentions
    ]


def category_activity_rows(facts: TrendFacts) -> list[dict]:
    return [
        {
            "analysis_id": facts.analysis_id,
            "ticker": facts.ticker,
            "change_id": a.change_id,
            "category": cat,
            "change_type": a.change_type,
            "score": a.score,
            "added_sentences": a.added_sentences,
            "removed_sentences": a.removed_sentences,
            "modified_sentences": a.modified_sentences,
            "added_words": a.added_words,
            "removed_words": a.removed_words,
            "modified_words": a.modified_words,
        }
        for a in facts.category_activity
        for cat in a.categories
    ]


def chunks(rows: list[dict], size: int = MERGE_CHUNK_ROWS) -> list[list[dict]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


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


# ---------- /trends: three row-fetching queries over the current reports ----------
# Each takes :current (TRUE) and :ids, a JSON array of the analysis_ids the API treats as current
# (newest filing pair per ticker, the same rule as /companies). Ranking, grouping and sums happen
# in pipeline.trends.aggregate, shared with the local path; SQL only narrows the rows.


def _current_ids(alias: str) -> str:
    return (
        f"{alias}.analysis_id IN (SELECT analysis_id FROM {{reports}} WHERE is_current = :current)\n"
        f"  AND array_contains(from_json(:ids, 'array<string>'), {alias}.analysis_id)"
    )


def trends_topics_sql(s: DatabricksSettings) -> str:
    """One example row per (topic, source, ticker) plus that company's sentence count. Phrases
    only when at least :min_companies companies share them. The example order is
    pipeline.trends.aggregate.EXAMPLE_ORDER_SQL (most matched terms, then shortest sentence)."""
    from pipeline.trends.aggregate import EXAMPLE_ORDER_SQL

    cur = _current_ids("tm").format(reports=s.table(REPORTS))
    return (
        f"WITH m AS (\n"
        f"  SELECT tm.*, c.short_title FROM {s.table(TOPIC_MENTIONS)} tm\n"
        f"  LEFT JOIN {s.table(CHANGES)} c\n"
        f"    ON c.analysis_id = tm.analysis_id AND c.change_id = tm.change_id\n"
        f"  WHERE {cur}\n"
        f"), shared AS (\n"
        f"  SELECT topic FROM m WHERE topic_source = :phrase\n"
        f"  GROUP BY topic HAVING COUNT(DISTINCT ticker) >= :min_companies\n"
        f"), ranked AS (\n"
        f"  SELECT m.*,\n"
        f"    COUNT(*) OVER (PARTITION BY m.topic, m.topic_source, m.ticker) AS ticker_sentence_count,\n"
        f"    ROW_NUMBER() OVER (PARTITION BY m.topic, m.topic_source, m.ticker\n"
        f"      ORDER BY {EXAMPLE_ORDER_SQL}) AS rn\n"
        f"  FROM m WHERE m.topic_source <> :phrase OR m.topic IN (SELECT topic FROM shared)\n"
        f")\n"
        f"SELECT ticker, change_id, sentence_id, topic, topic_source, matched_terms, status,\n"
        f"  sentence_text, added_spans_json, short_title, ticker_sentence_count\n"
        f"FROM ranked WHERE rn = 1 ORDER BY topic, topic_source, ticker"
    )


def trends_activity_sql(s: DatabricksSettings) -> str:
    """Per-change category rows of the current reports (the heatmap sums are done in Python)."""
    cur = _current_ids("ca").format(reports=s.table(REPORTS))
    return (
        f"SELECT ca.ticker, ca.change_id, ca.category, ca.change_type, ca.score,\n"
        f"  ca.added_sentences, ca.removed_sentences, ca.modified_sentences,\n"
        f"  ca.added_words, ca.removed_words, ca.modified_words\n"
        f"FROM {s.table(CATEGORY_ACTIVITY)} ca\n"
        f"WHERE {cur} AND ca.change_type <> :unchanged\n"
        f"ORDER BY ca.ticker, ca.category, ca.change_id"
    )


def trends_potential_to_actual_sql(s: DatabricksSettings) -> str:
    """'Potential became actual' highlights of the current reports, with company and score."""
    cur = _current_ids("h").format(reports=s.table(REPORTS))
    return (
        f"SELECT h.ticker, r.company_name, h.change_id, h.short_title, h.old_sentence_id,\n"
        f"  h.new_sentence_id, h.old_text, h.new_text, h.old_spans_json, h.new_spans_json, c.score\n"
        f"FROM {s.table(HIGHLIGHTS)} h\n"
        f"JOIN {s.table(REPORTS)} r ON r.analysis_id = h.analysis_id\n"
        f"LEFT JOIN {s.table(CHANGES)} c ON c.analysis_id = h.analysis_id AND c.change_id = h.change_id\n"
        f"WHERE {cur} AND h.kind = :kind\n"
        f"ORDER BY c.score DESC, h.ticker"
    )
