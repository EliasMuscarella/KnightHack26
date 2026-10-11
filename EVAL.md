# EVAL

Numbers in this file are produced by `uv run python -m eval.eval`. Checks that could not run say so; nothing here is estimated.

## 1. Risk matcher: precision / recall vs golden set

**Not run.** No golden set at `eval/golden_pairs.json` yet (labeling procedure: `eval/README.md`).

## 2. LLM rubric consistency (stage 7 repeated with the LLM cache bypassed)

**Not run.** Repeats stage 7 with live LLM calls; run `uv run python -m eval.eval --consistency-ticker NVDA --write`.

## 3. Determinism (full pipeline twice from cache)

Ticker FIXTUR (FIXTURE: synthetic filing pair, so the check runs offline): byte-identical = **True**, identical analysis_id = **True** (`29e66a6b5bda6e2d…`), 160,234 bytes, second-run cache misses: none.

## 4. Citation validator audit (published output)

2 published files, 33 LLM claims seen, 1 dropped by the validator.

- 1× banned language (advice wording)

