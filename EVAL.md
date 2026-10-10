# EVAL

Numbers in this file are produced by `uv run python -m eval.eval`. Checks that could not run say so; nothing here is estimated.

## 1. Risk matcher: precision / recall vs golden set

**Not run.** No golden set at `eval/golden_pairs.json` (it requires real filings, see PROGRESS.md blockers).

## 2. LLM rubric consistency (stage 7 repeated with the LLM cache bypassed)

**Blocked.** LLM stage unavailable: HF_TOKEN is not set; GEMINI_API_KEY is not set

## 3. Determinism (full pipeline twice from cache)

Ticker FIXTUR (FIXTURE: synthetic filing pair, because real filings are unavailable in this environment): byte-identical = **True**, identical analysis_id = **True** (`2bd78cac721633ab…`), 165,641 bytes, second-run cache misses: none.

## 4. Citation validator audit (published output)

No published files yet.

