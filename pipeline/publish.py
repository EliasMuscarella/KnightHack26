"""Stage 8b: validate against the contract and write the published JSON (canonical form)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline.errors import PipelineError
from pipeline.schema import Comparison, canonical_json

log = logging.getLogger(__name__)


def published_filename(comp: Comparison) -> str:
    return f"{comp.company.ticker}_{comp.old_filing.fiscal_year}_{comp.new_filing.fiscal_year}.json"


def publish(
    comp: Comparison, published_dir: Path, scratch_dir: Path, *, force: bool = False
) -> Path:
    """Fixture output goes to scratch_dir, never to published_dir. An existing published file with
    a different analysis_id is never overwritten unless `force` (a different model/backend/version
    produced it; overwriting silently would change a committed analysis)."""
    # round-trip through JSON to make sure the file validates exactly as written
    text = canonical_json(comp)
    Comparison.model_validate(json.loads(text))
    if comp.is_fixture or comp.company.ticker == "FIXTUR":
        target_dir = scratch_dir
        log.warning(
            "FIXTURE comparison: writing to %s (never to the published directory)", scratch_dir
        )
    else:
        target_dir = published_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / published_filename(comp)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == text:
            log.info("published JSON unchanged: %s", path)
            return path
        try:
            old_id = json.loads(existing).get("analysis_id")
        except ValueError:
            old_id = None
        if target_dir == published_dir and old_id != comp.analysis_id and not force:
            raise PipelineError(
                f"{path.name} already exists with analysis_id {str(old_id)[:12]}… (this run: {comp.analysis_id[:12]}…). "
                "The inputs or versions differ; rerun with --force to replace it.",
                code="publish_conflict",
            )
        if target_dir == published_dir and old_id == comp.analysis_id and not force:
            raise PipelineError(
                f"{path.name} already exists for the same analysis_id but with different bytes. The LLM output "
                "probably changed (e.g. --refresh-llm); rerun with --force to replace it deliberately.",
                code="publish_conflict",
            )
        if target_dir == published_dir and old_id == comp.analysis_id:
            log.warning(
                "published JSON for the same analysis_id differs from the existing file (nondeterminism?): %s",
                path,
            )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    log.info("wrote %s (%d changes, %d bytes)", path, len(comp.changes), len(text.encode("utf-8")))
    return path


def load_published(path: Path) -> Comparison:
    comp = Comparison.model_validate_json(path.read_text(encoding="utf-8"))
    if comp.is_fixture:
        raise ValueError(f"{path} is FIXTURE data and must not be served as a published comparison")
    return comp
