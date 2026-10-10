"""Publish step for the shared report library: Volume upload + derived-table MERGEs.

Runs after the local publish (the local file is the source of truth and is never touched here).
Idempotent: uploading an identical file is skipped, every MERGE is insert-if-absent, and the
`is_current` flip only happens the first time an analysis is seen, so re-publishing the same
analysis (or syncing an older local file after a teammate published a newer one) changes nothing.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pipeline.config import ROOT, get_databricks_settings
from pipeline.store import tables
from pipeline.store.databricks import DatabricksStore, StoreError, verify_report
from pipeline.trends.derive import derive_trend_facts, ensure_facts
from pipeline.trends.schema import TrendFacts

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RemotePublishResult:
    analysis_id: str
    ticker: str
    volume_path: str
    inserted: bool  # first time this analysis reached the tables
    made_current: bool

    def to_dict(self) -> dict:
        return {
            "status": "ok",
            "analysis_id": self.analysis_id,
            "ticker": self.ticker,
            "volume_path": self.volume_path,
            "inserted": self.inserted,
            "made_current": self.made_current,
        }


def git_user_name() -> str:
    """`git config user.name` of the publishing machine, or "unknown". Fixed arguments only."""
    try:
        out = subprocess.run(
            ["git", "config", "user.name"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        name = out.stdout.strip()
        return name[:120] if name else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def merge_trend_tables(store: DatabricksStore, facts: TrendFacts) -> int:
    """Insert-if-absent MERGEs of the derived trend facts (topic_mentions, category_activity),
    chunked so each JSON parameter stays small. Returns the number of rows sent."""
    s = store.settings
    sent = 0
    for table, rows in (
        (tables.TOPIC_MENTIONS, tables.topic_mention_rows(facts)),
        (tables.CATEGORY_ACTIVITY, tables.category_activity_rows(facts)),
    ):
        for chunk in tables.chunks(rows):
            store.execute(tables.merge_sql(s, table), {"rows": tables.rows_json(chunk)})
            sent += len(chunk)
    return sent


def publish_remote(
    path: Path,
    store: DatabricksStore,
    *,
    published_by: str | None = None,
    now: datetime | None = None,
    derived_dir: Path | None = None,
) -> RemotePublishResult:
    """Upload `path` and MERGE its rows into reports, changes, highlights, topic_mentions and
    category_activity (in that order), then make it the current report for its ticker + filing
    pair if it is new. The trend facts come from `derived_dir` (written there when missing or
    stale) or are derived in memory. Raises StoreError."""
    path = Path(path)
    data = path.read_bytes()
    comp = verify_report(data)  # contract + analysis_id recompute; fixtures refused
    facts = ensure_facts(comp, derived_dir) if derived_dir else derive_trend_facts(comp)
    s = store.settings
    vpath = store.upload_report(path)

    already = store.execute(tables.exists_sql(s), {"analysis_id": comp.analysis_id})
    inserted = not already
    row = tables.report_row(
        comp,
        volume_path=vpath,
        content_sha256=hashlib.sha256(data).hexdigest(),
        published_by=published_by or git_user_name(),
        published_at=now or datetime.now(UTC),
    )
    # insert-if-absent MERGEs: no-ops for rows that already exist
    store.execute(tables.merge_sql(s, tables.REPORTS), {"rows": tables.rows_json([row])})
    store.execute(
        tables.merge_sql(s, tables.CHANGES), {"rows": tables.rows_json(tables.change_rows(comp))}
    )
    hl = tables.highlight_rows(comp)
    if hl:
        store.execute(tables.merge_sql(s, tables.HIGHLIGHTS), {"rows": tables.rows_json(hl)})
    merge_trend_tables(store, facts)
    made_current = False
    if inserted:
        store.execute(
            tables.flip_current_sql(s),
            {
                "analysis_id": comp.analysis_id,
                "ticker": comp.company.ticker,
                "old_accession": comp.old_filing.accession_number,
                "new_accession": comp.new_filing.accession_number,
            },
        )
        made_current = True
    log.info(
        "shared store: %s %s (%s)",
        comp.company.ticker,
        comp.analysis_id[:12],
        "published" if inserted else "already present",
    )
    return RemotePublishResult(
        analysis_id=comp.analysis_id,
        ticker=comp.company.ticker,
        volume_path=vpath,
        inserted=inserted,
        made_current=made_current,
    )


def derived_dir_for_published(path: Path) -> Path | None:
    """data/published/X.json -> data/derived (siblings under the same data directory); None for a
    file outside a `published` directory (its facts are then derived in memory, never written)."""
    parent = Path(path).resolve().parent
    return parent.parent / "derived" if parent.name == "published" else None


def publish_remote_if_enabled(path: Path, *, enabled: bool | None = None) -> dict:
    """The pipeline's post-publish step (run.py calls it after the local publish, never for the
    fixture). Never raises: returns a status dict ({"status": "ok" | "disabled" | "skipped" |
    "failed", ..., "trend_facts": {...}}) so a remote failure can be reported without undoing the
    local publish.

    It first derives the trend facts of the published file (data/derived/, D-021). That happens
    here and not in pipeline/run.py on purpose: every top-level pipeline/*.py file feeds
    code_fingerprint and therefore analysis_id, so the hook lives in this sub-package."""
    from pipeline.trends.derive import derive_after_publish

    derived_dir = derived_dir_for_published(path)
    trend = (
        derive_after_publish(Path(path), derived_dir)
        if derived_dir is not None
        else {"status": "skipped", "reason": "not in a published directory"}
    )
    out = _publish_remote_step(Path(path), enabled=enabled, derived_dir=derived_dir)
    out["trend_facts"] = trend
    return out


def _publish_remote_step(path: Path, *, enabled: bool | None, derived_dir: Path | None) -> dict:
    if enabled is False:
        return {"status": "skipped", "reason": "--no-remote"}
    try:
        settings = get_databricks_settings()
    except Exception as e:  # noqa: BLE001  (ConfigError: bad host/identifiers)
        return {"status": "failed", "code": getattr(e, "code", "config"), "message": str(e)[:300]}
    if not settings.enabled:
        return {"status": "disabled"}
    try:
        return publish_remote(
            Path(path), DatabricksStore(settings), derived_dir=derived_dir
        ).to_dict()
    except StoreError as e:
        log.warning("remote publish failed [%s]: %s", e.code, e.message)
        return {"status": "failed", "code": e.code, "message": e.message[:300]}
    except Exception as e:  # noqa: BLE001  (DisallowedHost and anything unexpected)
        log.warning("remote publish failed: %s", type(e).__name__)
        return {
            "status": "failed",
            "code": getattr(e, "code", "internal"),
            "message": str(e)[:300],
        }
