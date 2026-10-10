"""Build the demo dataset from real pipeline output.

    uv run python scripts/build_demo.py [--candidates NVDA,AAPL,...] [--keep 6] [--dry-run]

1. Runs the full pipeline for each candidate ticker (needs .env with SEC_USER_AGENT; HF_TOKEN
   for the LLM stage). Failures are recorded, never faked.
2. Ranks companies by how substantive their real changes are (judged ONLY by pipeline output):
   substance = number of changes with score >= 30, then the sum of the top-5 scores.
3. Keeps the top `--keep` companies (5-8) in data/published/ (moves the rest to data/scratch/)
   and writes DEMO.md listing, for each kept company, its single highest-scoring change with the
   first cited sentence quoted verbatim from the filing as the candidate demo moment.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import get_settings  # noqa: E402
from pipeline.errors import PipelineError  # noqa: E402
from pipeline.run import run_pipeline  # noqa: E402
from pipeline.schema import Comparison  # noqa: E402

DEFAULT_CANDIDATES = ["NVDA", "AAPL", "MSFT", "META", "AMZN", "TSLA", "AMD", "INTC", "JPM", "GS"]


def substance(comp: Comparison) -> tuple[int, int]:
    scores = sorted((c.score for c in comp.changes), reverse=True)
    return (sum(1 for s in scores if s >= 30), sum(scores[:5]))


def best_moment(comp: Comparison) -> dict | None:
    for c in comp.changes:  # ranked by score already
        for line in c.score_breakdown:
            for sid in line.cited_sentence_ids:
                loc = comp.sentence_index.get(sid)
                if loc and not loc.is_heading:
                    return {
                        "change": c,
                        "line": line,
                        "sid": sid,
                        "text": loc.text,
                        "side": loc.side,
                    }
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=",".join(DEFAULT_CANDIDATES))
    ap.add_argument("--keep", type=int, default=6)
    ap.add_argument(
        "--dry-run", action="store_true", help="rank only; do not move files or write DEMO.md"
    )
    ap.add_argument(
        "--force", action="store_true", help="replace published files whose analysis_id differs"
    )
    args = ap.parse_args()
    settings = get_settings()
    results: list[tuple[str, Comparison, Path]] = []
    failures: list[tuple[str, str]] = []
    for t in [x.strip().upper() for x in args.candidates.split(",") if x.strip()]:
        try:
            ctx = run_pipeline(t, settings, force_publish=args.force)
            path = Path(ctx.outputs["published_path"])
            comp = ctx.outputs["comparison"]
            if comp.is_fixture:
                raise PipelineError("fixture output cannot be part of the demo set")
            results.append((t, comp, path))
            print(
                f"{t}: {comp.summary.total_changes} changes, max score {comp.summary.max_score}, substance={substance(comp)}",
                file=sys.stderr,
            )
        except PipelineError as e:
            failures.append((t, f"{e.code}: {e.message}"))
            print(f"{t}: FAILED {e.code}: {e.message}", file=sys.stderr)
    ranked = sorted(results, key=lambda r: substance(r[1]), reverse=True)
    keep = ranked[: max(5, min(8, args.keep))] if len(ranked) >= 5 else ranked
    dropped = ranked[len(keep) :]
    if args.dry_run:
        for t, comp, _ in ranked:
            print(t, substance(comp))
        return 0
    scratch = settings.data_dir / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    for t, _, path in dropped:
        shutil.move(str(path), str(scratch / path.name))
    lines = [
        "# DEMO",
        "",
        "Demo companies selected from REAL pipeline output (see `scripts/build_demo.py`). Selection rule: most",
        "changes with score >= 30, then highest sum of the top-5 scores. Nothing below is hand-written: every quote",
        "is the cited filing sentence copied from `sentence_index`.",
        "",
    ]
    lines.append(
        "| Ticker | Company | Filings | Changes (new/removed/expanded/reduced/reworded) | Top score |"
    )
    lines.append("|---|---|---|---|---|")
    for t, comp, _ in keep:
        b = comp.summary.by_change_type
        lines.append(
            f"| {t} | {comp.company.name} | FY{comp.old_filing.fiscal_year} → FY{comp.new_filing.fiscal_year} | {comp.summary.total_changes} ({b['new']}/{b['removed']}/{b['expanded']}/{b['reduced']}/{b['materially_reworded']}) | {comp.summary.max_score} |"
        )
    lines.append("")
    lines.append("## Candidate demo moments (one per company)")
    for t, comp, _ in keep:
        m = best_moment(comp)
        lines.append(f"\n### {t}: {comp.company.name}")
        if not m:
            lines.append("No scored change with a cited body sentence.")
            continue
        c = m["change"]
        lines.append(
            f"- Change #{c.rank}: **{c.title}** ({c.change_type}, score {c.score}, categories: {', '.join(c.categories)})"
        )
        lines.append(
            f"- Why it scored: {m['line'].label} (+{m['line'].points}){' — ' + m['line'].detail if m['line'].detail else ''}"
        )
        fy = comp.new_filing.fiscal_year if m["side"] == "new" else comp.old_filing.fiscal_year
        lines.append(f"- Cited sentence (FY{fy} 10-K, id `{m['sid']}`): “{m['text']}”")
        lines.append(f"- Open: `/c/{t}/{c.id}`")
    if failures:
        lines.append("\n## Candidates that failed (not faked, not published)")
        for t, why in failures:
            lines.append(f"- {t}: {why}")
    if dropped:
        lines.append("\n## Ran but not selected (moved to data/scratch/)")
        for t, comp, _ in dropped:
            lines.append(f"- {t}: substance {substance(comp)}")
    (ROOT / "DEMO.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"kept {len(keep)} companies; wrote DEMO.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
