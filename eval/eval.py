"""RiskDiff evaluation harness.

    uv run python -m eval.eval [--golden eval/golden_pairs.json] [--consistency-runs 5]
                               [--consistency-ticker NVDA] [--determinism-ticker NVDA] [--write]

Four checks, each reported honestly (numbers only when they are real):
1. Matcher precision/recall against a golden set of labeled old<->new correspondences, plus a
   sweep over match thresholds to recalibrate `match.DEFAULT_PARAMS` (the sweep result is
   recorded in EVAL.md; the code constant is updated by a human or by --apply).
2. Consistency: stage 7 (LLM rubric + interpretation) run N times on the same 10 changes with the
   LLM cache bypassed; per-question agreement rate and final-score stability.
3. Determinism: the full pipeline run twice from cache; published JSON must be byte-identical.
4. Validator audit: how many LLM claims were dropped and why (from the published output).

Golden set format (eval/golden_pairs.json):
{
  "labeled_by": "...",
  "companies": [{"ticker": "NVDA", "old_accession": "...", "new_accession": "...",
                 "pairs": [{"old_block_id": "...:12", "new_block_id": "...:14"},   # correspondence
                           {"old_block_id": "...:3", "new_block_id": null},         # removed
                           {"old_block_id": null, "new_block_id": "...:20"}]}]      # new
}
Block ids must match those produced by stage 2 for the same filings (see eval/golden_tool.py,
which prints block ids + headings for labeling).
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import match as match_mod  # noqa: E402
from pipeline.config import get_settings  # noqa: E402
from pipeline.errors import PipelineError  # noqa: E402
from pipeline.run import run_pipeline  # noqa: E402

log = logging.getLogger("eval")


# ---------- 1. matcher precision / recall ----------


def _predicted_pairs(matches) -> set[tuple[int | None, int | None]]:
    out = {(p.old_index, p.new_index) for p in matches.pairs}
    out |= {(i, None) for i in matches.unmatched_old}
    out |= {(None, j) for j in matches.unmatched_new}
    return out


def _prf(pred: set, gold: set) -> dict:
    tp = len(pred & gold)
    precision = tp / len(pred) if pred else 0.0
    recall = tp / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "tp": tp,
        "pred": len(pred),
        "gold": len(gold),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def eval_matcher(golden: dict, settings) -> dict:
    """Returns per-company and overall P/R at the current threshold, plus a threshold sweep."""
    results = {"companies": [], "labeled_by": golden.get("labeled_by"), "errors": []}
    sweep_points = [round(0.05 * k, 2) for k in range(2, 19)]
    sweep_acc: dict[float, list[tuple[int, int, int]]] = {t: [] for t in sweep_points}
    all_pred: set = set()
    all_gold: set = set()
    backend = None
    for comp in golden.get("companies", []):
        ticker = comp["ticker"]
        try:
            ctx = run_pipeline(ticker, settings, until_stage=4)
        except PipelineError as e:
            results["errors"].append(f"{ticker}: {e.code}: {e.message}")
            continue
        segs = ctx.outputs["segments"]
        fetch = ctx.outputs["fetch"]
        if comp.get("old_accession") and comp["old_accession"] != fetch.old.accession_number:
            results["errors"].append(
                f"{ticker}: golden old accession {comp['old_accession']} != pipeline {fetch.old.accession_number}"
            )
            continue
        if comp.get("new_accession") and comp["new_accession"] != fetch.new.accession_number:
            results["errors"].append(
                f"{ticker}: golden new accession {comp['new_accession']} != pipeline {fetch.new.accession_number}"
            )
            continue
        old_ids = {b.id: b.index for b in segs["old"].blocks}
        new_ids = {b.id: b.index for b in segs["new"].blocks}
        gold: set = set()
        bad = 0
        for p in comp["pairs"]:
            o, n = p.get("old_block_id"), p.get("new_block_id")
            if (o and o not in old_ids) or (n and n not in new_ids):
                bad += 1
                continue
            gold.add((old_ids[o] if o else None, new_ids[n] if n else None))
        emb = ctx.outputs["embeddings"]
        backend = emb.backend
        # restrict predictions to blocks mentioned in the golden set (labels are partial)
        gold_old = {o for o, _ in gold if o is not None}
        gold_new = {n for _, n in gold if n is not None}

        def restrict(pairs: set, gold_old=gold_old, gold_new=gold_new) -> set:
            return {(o, n) for o, n in pairs if (o in gold_old) or (n in gold_new)}

        cur = restrict(_predicted_pairs(ctx.outputs["matches"]))
        pr = _prf(cur, gold)
        pr.update(
            {"ticker": ticker, "unknown_block_ids_in_golden": bad, "labels": len(comp["pairs"])}
        )
        results["companies"].append(pr)
        all_pred |= {(ticker, *x) for x in cur}
        all_gold |= {(ticker, *x) for x in gold}
        base = match_mod.params_for(emb.backend)
        for t in sweep_points:
            m = match_mod.match_blocks(
                emb,
                match_mod.MatchParams(
                    match_threshold=t,
                    heading_weight=base.heading_weight,
                    body_weight=base.body_weight,
                ),
            )
            r = _prf(restrict(_predicted_pairs(m)), gold)
            sweep_acc[t].append((r["tp"], r["pred"], r["gold"]))
    results["overall"] = _prf(all_pred, all_gold)
    sweep = []
    for t, rows in sweep_acc.items():
        if not rows:
            continue
        tp = sum(r[0] for r in rows)
        pred = sum(r[1] for r in rows)
        gold_n = sum(r[2] for r in rows)
        p = tp / pred if pred else 0.0
        rc = tp / gold_n if gold_n else 0.0
        f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
        sweep.append(
            {"threshold": t, "precision": round(p, 4), "recall": round(rc, 4), "f1": round(f1, 4)}
        )
    results["sweep"] = sweep
    results["backend"] = backend
    if sweep:
        best = max(sweep, key=lambda r: (r["f1"], -abs(r["threshold"] - 0.5)))
        results["recommended_threshold"] = best["threshold"]
        results["current_threshold"] = (
            match_mod.params_for(backend).match_threshold if backend else None
        )
    return results


# ---------- 2. consistency ----------


def eval_consistency(ticker: str, runs: int, settings, n_changes: int = 10) -> dict:
    """Run stage 7 `runs` times with the LLM cache bypassed on the top-N non-unchanged changes."""
    from pipeline import llm as llm_mod
    from pipeline.schema import Sentence
    from pipeline.stages_final import _blocks

    ctx = run_pipeline(ticker, settings, until_stage=6)
    client, reason = llm_mod.select_client(settings)
    if client is None:
        return {"status": "blocked", "reason": reason, "ticker": ticker}
    records = [r for r in ctx.outputs["diff_records"] if r["change_type"] != "largely_unchanged"]
    records.sort(key=lambda r: -(r["stats"]["added_word_count"] + r["stats"]["removed_word_count"]))
    records = records[:n_changes]
    segs = ctx.outputs["segments"]
    fetch = ctx.outputs["fetch"]
    per_q_agree: dict[str, list[float]] = {}
    score_ranges: list[int] = []
    claim_counts: list[list[int]] = []
    from pipeline.diff import DEFAULT_DIFF_PARAMS
    from pipeline.schema import Interpretation, Signals
    from pipeline.score import score_change

    sig_rows = ctx.outputs["signal_rows"]
    sig_by_key = {
        (r["old_block_id"], r["new_block_id"]): s
        for r, s in zip(ctx.outputs["diff_records"], sig_rows, strict=True)
    }
    details = []
    for r in records:
        old, new = _blocks(segs, r)
        sentences = [Sentence.model_validate(s) for s in r["sentences"]]
        answers: dict[str, list[bool]] = {}
        scores: list[int] = []
        n_claims: list[int] = []
        for _ in range(runs):
            res = llm_mod.interpret_change(
                client,
                (new or old).heading,
                old,
                new,
                sentences,
                fetch.old.fiscal_year,
                fetch.new.fiscal_year,
            )
            if res.validation is None:
                continue
            for a in res.validation.rubric:
                answers.setdefault(a.question_id, []).append(a.answer)
            interp = Interpretation(
                status="ok",
                model_id=res.model_id,
                rubric=res.validation.rubric,
                claims=res.validation.claims,
            )
            sig = Signals.model_validate(
                sig_by_key[(r["old_block_id"], r["new_block_id"])]["signals"]
            )
            score, _ = score_change(
                r["change_type"],
                sentences,
                sig,
                interp,
                r["similarity"],
                DEFAULT_DIFF_PARAMS.reworded_similarity,
            )
            scores.append(score)
            n_claims.append(len(res.validation.claims))
        for q, vals in answers.items():
            if vals:
                majority = Counter(vals).most_common(1)[0][1] / len(vals)
                per_q_agree.setdefault(q, []).append(majority)
        if scores:
            score_ranges.append(max(scores) - min(scores))
            claim_counts.append(n_claims)
        details.append({"title": (new or old).heading[:80], "scores": scores, "answers": answers})
    return {
        "status": "ok",
        "ticker": ticker,
        "runs": runs,
        "changes": len(records),
        "model_id": client.model_id,
        "per_question_agreement": {
            q: round(statistics.mean(v), 4) for q, v in sorted(per_q_agree.items())
        },
        "score_range_mean": round(statistics.mean(score_ranges), 2) if score_ranges else None,
        "score_range_max": max(score_ranges) if score_ranges else None,
        "score_identical_fraction": round(
            sum(1 for x in score_ranges if x == 0) / len(score_ranges), 4
        )
        if score_ranges
        else None,
        "details": details,
    }


# ---------- 3. determinism ----------


def eval_determinism(ticker: str, settings) -> dict:
    try:
        ctx1 = run_pipeline(ticker, settings)
        text1 = Path(ctx1.outputs["published_path"]).read_text(encoding="utf-8")
        ctx2 = run_pipeline(ticker, settings)
        text2 = Path(ctx2.outputs["published_path"]).read_text(encoding="utf-8")
    except PipelineError as e:
        return {"status": "blocked", "ticker": ticker, "reason": f"{e.code}: {e.message}"}
    comp1 = ctx1.outputs["comparison"]
    comp2 = ctx2.outputs["comparison"]
    return {
        "status": "ok",
        "ticker": ticker,
        "byte_identical": text1 == text2,
        "analysis_id_identical": comp1.analysis_id == comp2.analysis_id,
        "analysis_id": comp1.analysis_id,
        "bytes": len(text1.encode("utf-8")),
        "second_run_cache_misses": ctx2.cache.misses,
        "is_fixture": comp1.is_fixture,
    }


# ---------- 4. validator audit ----------


def eval_validator(published_dir: Path) -> dict:
    total = dropped = 0
    reasons: Counter = Counter()
    files = 0
    for p in sorted(published_dir.glob("*_*_*.json")) if published_dir.exists() else []:
        files += 1
        d = json.loads(p.read_text(encoding="utf-8"))
        for c in d["changes"]:
            it = c["interpretation"]
            total += len(it["claims"]) + it["dropped_claim_count"]
            dropped += it["dropped_claim_count"]
            for r in it["dropped_reasons"]:
                reasons[r.split(":", 1)[-1].strip()[:60]] += 1
    return {
        "files": files,
        "claims_total": total,
        "claims_dropped": dropped,
        "top_reasons": reasons.most_common(8),
    }


# ---------- report ----------


def render_markdown(res: dict) -> str:
    L: list[str] = []
    L.append("# EVAL\n")
    L.append(
        "Numbers in this file are produced by `uv run python -m eval.eval`. Checks that could not run say so; nothing here is estimated.\n"
    )
    m = res.get("matcher")
    L.append("## 1. Risk matcher: precision / recall vs golden set\n")
    if not m:
        L.append(
            "**Not run.** No golden set at `eval/golden_pairs.json` (it requires real filings, see PROGRESS.md blockers).\n"
        )
    elif m.get("errors") and not m["companies"]:
        L.append("**Blocked.** " + "; ".join(m["errors"]) + "\n")
    else:
        L.append(
            f"Labeled by: {m.get('labeled_by')}. Embedding backend during this run: `{m.get('backend')}`.\n"
        )
        L.append(
            "| Company | labels | TP | predicted | precision | recall | F1 |\n|---|---|---|---|---|---|---|"
        )
        for c in m["companies"]:
            L.append(
                f"| {c['ticker']} | {c['labels']} | {c['tp']} | {c['pred']} | {c['precision']:.2f} | {c['recall']:.2f} | {c['f1']:.2f} |"
            )
        o = m["overall"]
        L.append(
            f"| **All** | | {o['tp']} | {o['pred']} | **{o['precision']:.2f}** | **{o['recall']:.2f}** | **{o['f1']:.2f}** |\n"
        )
        if m.get("errors"):
            L.append("Errors: " + "; ".join(m["errors"]) + "\n")
        L.append("### Threshold sweep (recalibration)\n")
        L.append("| threshold | precision | recall | F1 |\n|---|---|---|---|")
        for r in m["sweep"]:
            mark = " ◀ recommended" if r["threshold"] == m.get("recommended_threshold") else ""
            L.append(
                f"| {r['threshold']:.2f} | {r['precision']:.2f} | {r['recall']:.2f} | {r['f1']:.2f}{mark} |"
            )
        L.append(
            f"\nCurrent `match_threshold` for `{m.get('backend')}`: {m.get('current_threshold')}. Recommended by F1: {m.get('recommended_threshold')}.\n"
        )
    c = res.get("consistency")
    L.append("## 2. LLM rubric consistency (stage 7 repeated with the LLM cache bypassed)\n")
    if not c or c.get("status") != "ok":
        L.append(f"**Blocked.** {c.get('reason') if c else 'not run'}\n")
    else:
        L.append(
            f"Ticker {c['ticker']}, {c['changes']} changes × {c['runs']} runs, model `{c['model_id']}`.\n"
        )
        L.append("| Question | agreement rate |\n|---|---|")
        for q, v in c["per_question_agreement"].items():
            L.append(f"| {q} | {v:.1%} |")
        L.append(
            f"\nFinal score stability: identical across runs for {c['score_identical_fraction']:.0%} of changes; mean score range {c['score_range_mean']} points, max {c['score_range_max']}.\n"
        )
    d = res.get("determinism")
    L.append("## 3. Determinism (full pipeline twice from cache)\n")
    if not d or d.get("status") != "ok":
        L.append(f"**Blocked.** {d.get('reason') if d else 'not run'}\n")
    else:
        fx = (
            " (FIXTURE: synthetic filing pair, because real filings are unavailable in this environment)"
            if d.get("is_fixture")
            else ""
        )
        L.append(
            f"Ticker {d['ticker']}{fx}: byte-identical = **{d['byte_identical']}**, identical analysis_id = **{d['analysis_id_identical']}** (`{d['analysis_id'][:16]}…`), {d['bytes']:,} bytes, second-run cache misses: {d['second_run_cache_misses'] or 'none'}.\n"
        )
    v = res.get("validator")
    L.append("## 4. Citation validator audit (published output)\n")
    if not v or v["files"] == 0:
        L.append("No published files yet.\n")
    else:
        L.append(
            f"{v['files']} published files, {v['claims_total']} LLM claims seen, {v['claims_dropped']} dropped by the validator.\n"
        )
        for reason, n in v["top_reasons"]:
            L.append(f"- {n}× {reason}")
        L.append("")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m eval.eval")
    ap.add_argument("--golden", default=str(ROOT / "eval" / "golden_pairs.json"))
    ap.add_argument("--consistency-runs", type=int, default=5)
    ap.add_argument("--consistency-ticker", default="NVDA")
    ap.add_argument("--determinism-ticker", default="NVDA")
    ap.add_argument("--skip-consistency", action="store_true")
    ap.add_argument("--write", action="store_true", help="write EVAL.md and eval/results.json")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    settings = get_settings()
    res: dict = {}
    gp = Path(args.golden)
    if gp.exists():
        res["matcher"] = eval_matcher(json.loads(gp.read_text()), settings)
    else:
        res["matcher"] = None
    if not args.skip_consistency:
        try:
            res["consistency"] = eval_consistency(
                args.consistency_ticker, args.consistency_runs, settings
            )
        except PipelineError as e:
            res["consistency"] = {"status": "blocked", "reason": f"{e.code}: {e.message}"}
    res["determinism"] = eval_determinism(args.determinism_ticker, settings)
    res["validator"] = eval_validator(settings.published_dir)
    md = render_markdown(res)
    print(md)
    if args.write:
        (ROOT / "EVAL.md").write_text(md, encoding="utf-8")
        (ROOT / "eval" / "results.json").write_text(
            json.dumps(res, indent=2, default=str), encoding="utf-8"
        )
        print("wrote EVAL.md and eval/results.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
