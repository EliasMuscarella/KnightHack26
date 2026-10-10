"""Upgrade published comparison files produced by an older pipeline to the current contract.

    uv run python scripts/migrate_published.py [data/published/NVDA_2025_2026.json ...]

Only presentation fields that can be DERIVED deterministically from the file's own content are
added: `short_title` (deterministic truncation of the real heading; no LLM) and `highlights[]`
(pipeline.highlights.select_highlights over the file's own signals, change types and validated
rubric answers; re-derived on every run so the ranking rule stays current). Nothing else changes: analysis_id, scores, sentences and citations are kept, and a
note records the migration. A full re-run (`pipeline.run TICKER --from-stage 2 --force`) is still
the way to get the newer segmentation/signal improvements into the file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import PIPELINE_VERSION  # noqa: E402
from pipeline.highlights import select_highlights, truncate_heading  # noqa: E402
from pipeline.schema import Comparison, canonical_json  # noqa: E402

NOTE = (
    "Short titles and highlights were derived from this analysis's own content by a migration to "
    f"pipeline {PIPELINE_VERSION} (titles are truncated headings, no language model). Re-run the "
    "pipeline for this ticker to regenerate everything with the current stages."
)


def migrate(path: Path) -> bool:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("is_fixture"):
        print(f"{path.name}: fixture, skipped")
        return False
    changed = False
    for c in d["changes"]:
        if "short_title" not in c:
            c["short_title"] = truncate_heading(c["title"])
            changed = True
    if "highlights" not in d:
        d["highlights"] = []
        changed = True
    comp = Comparison.model_validate(d)
    # highlights are a pure function of the file's own content: always re-derive them so a
    # ranking change in pipeline.highlights reaches already-published files too
    hl = [h.model_dump(mode="json") for h in select_highlights(comp.changes, comp.sentence_index)]
    if hl != d["highlights"]:
        d["highlights"] = hl
        changed = True
    if changed and NOTE not in d["notes"]:
        d["notes"].insert(0, NOTE)
    comp = Comparison.model_validate(d)
    text = canonical_json(comp)
    if text != path.read_text(encoding="utf-8"):
        path.write_text(text, encoding="utf-8")
        print(
            f"{path.name}: migrated ({len(comp.changes)} changes, {len(comp.highlights)} highlights)"
        )
        return True
    print(f"{path.name}: already current")
    return False


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]] or sorted(
        (ROOT / "data" / "published").glob("*_*_*.json")
    )
    for p in paths:
        migrate(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
