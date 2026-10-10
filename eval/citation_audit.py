"""Citation audit (deterministic part).

    uv run python -m eval.citation_audit [--sample 40] [--seed 0] [--out eval/citation_audit.json]

Samples AI claims and validated rubric "yes" answers across every published comparison and checks,
for each cited sentence id:
  1. the id exists in `sentence_index`;
  2. the indexed text is found VERBATIM in the extracted Item 1A text of the right filing
     (re-read from the stage-1 cache, so this is an independent check of the published file);
  3. the id belongs to one of the two blocks of the change that cites it.
It writes a JSON file listing each sampled claim with its cited sentences so that a reviewer
(human or a fresh subagent that has not seen the pipeline) can judge the remaining question,
"does the cited sentence actually support the claim?", and record pass/fail per claim.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import get_settings  # noqa: E402
from pipeline.schema import Comparison  # noqa: E402


def load_item1a_texts(cache_dir: Path) -> dict[str, str]:
    """accession -> extracted Item 1A text, from the stage-1 cache files."""
    out: dict[str, str] = {}
    d = cache_dir / "stages" / "extract"
    if not d.exists():
        return out
    for p in d.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out[data["accession_number"]] = data["text"]
        except Exception:  # noqa: BLE001
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=str(ROOT / "eval" / "citation_audit.json"))
    args = ap.parse_args()
    settings = get_settings()
    texts = load_item1a_texts(settings.cache_dir)
    items: list[dict] = []
    for p in (
        sorted(settings.published_dir.glob("*_*_*.json")) if settings.published_dir.exists() else []
    ):
        comp = Comparison.model_validate_json(p.read_text(encoding="utf-8"))
        if comp.is_fixture:
            continue
        for c in comp.changes:
            blocks = {c.old_block_id, c.new_block_id}
            for kind, text, cited in [
                ("claim", cl.text, cl.cited_sentence_ids) for cl in c.interpretation.claims
            ] + [
                ("rubric_yes", f"{a.question_id}: {a.question}", a.cited_sentence_ids)
                for a in c.interpretation.rubric
                if a.answer
            ]:
                checks = []
                for sid in cited:
                    loc = comp.sentence_index.get(sid)
                    exists = loc is not None
                    verbatim = bool(
                        loc
                        and texts.get(loc.accession_number)
                        and loc.text in texts[loc.accession_number]
                    )
                    in_change = bool(loc and loc.block_id in blocks)
                    checks.append(
                        {
                            "sentence_id": sid,
                            "exists": exists,
                            "verbatim_in_item_1a": verbatim,
                            "belongs_to_change": in_change,
                            "text": loc.text if loc else None,
                            "side": loc.side if loc else None,
                        }
                    )
                items.append(
                    {
                        "file": p.name,
                        "ticker": comp.company.ticker,
                        "change_id": c.id,
                        "change_title": c.title,
                        "change_type": c.change_type,
                        "kind": kind,
                        "text": text,
                        "citations": checks,
                        "mechanical_pass": bool(checks)
                        and all(
                            x["exists"] and x["verbatim_in_item_1a"] and x["belongs_to_change"]
                            for x in checks
                        ),
                        "supports_claim": None,
                        "reviewer_note": None,
                    }
                )
    rng = random.Random(args.seed)
    sample = items if len(items) <= args.sample else rng.sample(items, args.sample)
    sample.sort(key=lambda x: (x["ticker"], x["change_id"], x["kind"]))
    report = {
        "total_claims_available": len(items),
        "sampled": len(sample),
        "mechanical_pass": sum(1 for x in sample if x["mechanical_pass"]),
        "item_1a_texts_available_for": sorted(texts),
        "instructions": "For each item set supports_claim to true/false after reading the cited text; a claim passes only if every citation is mechanically valid AND supports it.",
        "items": sample,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"{len(items)} claims available, sampled {len(sample)}, mechanical pass {report['mechanical_pass']}/{len(sample)} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
