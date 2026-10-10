# Evaluation procedure

All of this needs real filings (SEC access + `.env`). In the overnight build environment that was
blocked, so only the determinism check ran (on the synthetic fixture). See `EVAL.md`.

## 1. Golden set (matcher precision / recall)

1. Print block ids and headings for three companies:
   `uv run python -m eval.golden_tool NVDA > /tmp/nvda_blocks.txt` (and two more tickers).
2. Give the three files to a labeler who has NOT seen `pipeline/match.py` (a fresh Opus subagent,
   with the prompt in `eval/golden_prompt.md`), and ask for 40–60 old↔new correspondences including
   genuinely new and removed risks, saved as `eval/golden_pairs.json` in the format documented at the
   top of `eval/eval.py`, with `"labeled_by": "AI subagent — needs human spot check"`.
3. `uv run python -m eval.eval --write` reports precision/recall at the current threshold and a
   threshold sweep; copy the recommended threshold into `pipeline/match.py` (`DEFAULT_PARAMS`), bump
   `match.STAGE_VERSION`, record the change in `DECISIONS.md`, and rerun.

## 2. Consistency (rubric agreement, score stability)

`uv run python -m eval.eval --consistency-ticker NVDA --consistency-runs 5 --write`
runs stage 7 five times on the 10 most-changed risks with the LLM cache bypassed and reports the
per-question agreement rate and score stability.

## 3. Determinism

`uv run python -m eval.eval --determinism-ticker NVDA --write` runs the full pipeline twice and
asserts byte-identical published JSON and identical `analysis_id`.

## 4. Citation audit

`uv run python -m eval.citation_audit --sample 40` writes `eval/citation_audit.json` with the
mechanical checks done (id exists, text verbatim in the extracted Item 1A, belongs to the change).
A reviewer who has not seen the pipeline then fills in `supports_claim` for each item; the pass
rate must be >= 95% or the failures must be fixed/explained in `EVAL.md`.
