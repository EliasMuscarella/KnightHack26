"""Stage 8b: validate against the contract and write the published JSON (canonical form)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pipeline.schema import Comparison, canonical_json

log = logging.getLogger(__name__)


def published_filename(comp: Comparison) -> str:
    return f"{comp.company.ticker}_{comp.old_filing.fiscal_year}_{comp.new_filing.fiscal_year}.json"


def publish(comp: Comparison, published_dir: Path, scratch_dir: Path) -> Path:
    """Fixture output goes to scratch_dir, never to published_dir."""
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
    if path.exists() and path.read_text(encoding="utf-8") == text:
        log.info("published JSON unchanged: %s", path)
        return path
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
