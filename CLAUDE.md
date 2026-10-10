# RiskDiff — agent guide

Read this file first on every task, and again after any context reset. Then read
`PROGRESS.md` (where things stand) and `DECISIONS.md` (choices made without a human).
Before touching anything under `web/`, read `DESIGN.md` and follow it: its tokens, type scale, color meaning and don'ts are binding.

## What RiskDiff is

**GitHub Diff for SEC filings.** RiskDiff compares Item 1A (Risk Factors) between a
company's two most recent 10-K filings and shows exactly what management added,
removed, expanded, or reworded, with every claim cited to the original filing text.

Product philosophy (non-negotiable):

- **Source-first.** SEC filing text is the only evidence. Every AI-generated claim must
  cite the exact sentence(s) from the 10-K that support it.
- **Diff-first.** What changed is computed by deterministic code, never by an LLM.
- **AI assists, never decides facts.** Embeddings align equivalent risks across years;
  an LLM answers narrow rubric questions and writes short interpretations, always with
  citations.
- **No fake certainty.** A disclosure change is NOT a risk probability. Never say a
  company "became riskier", never give buy/sell advice, never give percentages of risk.
- **Consistency.** A filing never changes after it's filed, so its analysis must never
  change either. Same inputs + same code version = byte-identical output.

Target platform: desktop/laptop browsers (>= 1280px wide). Dense text must be readable.

## Architecture

```
ticker ──> stage 0 sec_fetch ──> stage 1 extract ──> stage 2 segment ──> stage 3 embed
            (EDGAR JSON+HTML)      (Item 1A HTML)      (risk blocks +      (block vectors)
                                                        sentences + ids)        │
                                                                                 ▼
publish <── stage 8 score ◄── stage 7 llm ◄── stage 6 signals ◄── stage 5 diff ◄── stage 4 match
(JSON)      (rubric.py        (rubric Q&A +     (hedge→actual,     (sentence align,   (Hungarian on
             weights)          interpretation,   entities, qty,     word spans,        1 − similarity,
                               citation-         category)          change_type)       thresholds)
                               validated)
```

Repository layout:

| Path | Purpose |
|------|---------|
| `pipeline/schema.py` | **Single source of truth for data shape** (Pydantic). Everything else conforms to it. |
| `pipeline/rubric.py` | Rubric questions, score weights, `RUBRIC_VERSION`, banned phrases. One place, no hidden math. |
| `pipeline/config.py` | Env vars, versions, paths, model IDs. Secrets come from env only. |
| `pipeline/cache.py` | Per-stage disk cache under `data/cache/` keyed by hash(inputs + stage version). |
| `pipeline/sec_fetch.py` | Stage 0: ticker → CIK → submissions → two latest original 10-Ks → primary HTML. |
| `pipeline/extract.py` | Stage 1: Item 1A HTML extraction (TOC trap, heading variants, stop at 1B/1C/2). |
| `pipeline/segment.py` | Stage 2: risk blocks (heading+body, section groups), sentence split, stable ids, offsets. |
| `pipeline/embed.py` | Stage 3: local sentence-transformers embeddings; chunk+mean-pool over max length. |
| `pipeline/match.py` | Stage 4: heading/body weighted similarity, `linear_sum_assignment`, thresholds. |
| `pipeline/diff.py` | Stage 5: sentence alignment, word-level spans, `change_type` rules in one function. |
| `pipeline/signals.py` | Stage 6: deterministic signals with citations (hedge→actual, entities, quantities, ratios, category). |
| `pipeline/llm.py` | Stage 7: rubric + interpretation via HF Inference Providers (Gemini fallback), temp 0, JSON. |
| `pipeline/validate.py` | Citation validator: drops uncited/invalid/banned-language claims. Runs on every LLM output. |
| `pipeline/score.py` | Stage 8: deterministic score + `score_breakdown`, `analysis_id`. |
| `pipeline/publish.py` | Writes `data/published/{TICKER}_{oldFY}_{newFY}.json`, validated against the contract. |
| `pipeline/run.py` | CLI orchestrator: `python -m pipeline.run NVDA [--from-stage N] [--until-stage N] [--no-cache]`. |
| `contract/` | Exported JSON Schema + `fixtures/FIXTURE_comparison.json` (dev only, every string prefixed `FIXTURE:`). |
| `web/` | Next.js + TypeScript + Tailwind frontend. `web/src/types/comparison.ts` is generated, never hand-edited. |
| `api/` | FastAPI: `GET /companies`, `GET /comparison/{ticker}`, `POST /analyze` (SSE progress). |
| `eval/` | Golden pairs, matcher precision/recall, threshold calibration, consistency + determinism checks. |
| `tests/` | pytest unit tests. |
| `data/cache/` | Gitignored stage cache + raw filings. `data/published/` is committed demo output. |
| `scripts/` | `regen_contract.py` (schema + TS types), `dev.sh` (run everything). |

Stage contract: each stage is a pure function of its inputs + a `STAGE_VERSION` constant.
Cache key = sha256(canonical JSON of inputs + stage version). Change the behavior → bump
the version. Published `analysis_id` = sha256(old accession, new accession,
`PIPELINE_VERSION`, `RUBRIC_VERSION`, all model IDs, prompt text).

## Constraints (RiskDiff invariants — apply everywhere)

* SEC text is the only source of truth; every AI claim and every score point cites valid sentence ids from `sentence_index`
* the LLM never determines what changed and never outputs the score; diffs and scores are deterministic code
* the citation validator runs on every LLM output; uncited or invalid claims are dropped, never displayed
* no probability language, no "riskier", no buy/sell/investment advice, anywhere in UI or outputs
* never fabricate filings, sentences, examples, or numbers; the FIXTURE never ships in published data
* same inputs + same versions → byte-identical published JSON and identical `analysis_id`
* the contract (`pipeline/schema.py`) is the single source of truth for data shape; regenerate TS types after any change
* SEC fair access: send `SEC_USER_AGENT` on every request, stay under 5 requests/second, cache everything, never re-download a cached filing
* outbound HTTP only to an allowlist: `www.sec.gov`, `data.sec.gov`, Hugging Face endpoints, and (if used) the Gemini API — no user-controlled URLs (no SSRF)
* validate ticker input with a strict pattern (`^[A-Z.\-]{1,6}$` after uppercasing) on both client and server
* render filing text as text, never via `dangerouslySetInnerHTML` or raw HTML injection
* secrets only via environment variables, never in code, logs, frontend bundles, or git
* API: CORS restricted to the local frontend origin, one concurrent analysis, request timeouts, no stack traces in error responses
* pin dependency versions; no shell commands built from user input

## Working rules

- Work in task order (see the original brief, summarized in `PROGRESS.md`). Each task has a
  gate; do not start the next pipeline task until the current one meets its criteria.
- Commit after every task (`T3: embedding + matching`). Never push, never deploy.
- Update `PROGRESS.md` after every task. Record every human-free decision in `DECISIONS.md`.
- Blocked? Do everything else, document the blocker in `PROGRESS.md`, never fake the missing piece.
- An approach that fails 3 times → try a meaningfully different approach; if that fails, document and move on.
- Subagents: Opus, high effort, explicit file boundaries. Frontend subagent touches `web/` only.
  Verify subagent output by running tests and inspecting files.
- Never print secret values. Read `.env` only to confirm which variables exist.

## Run commands

```bash
# Python (uv manages a 3.12 venv in .venv)
uv sync                                   # install pinned deps (uv.lock)
uv run python -m pipeline.run NVDA        # full pipeline → data/published/NVDA_<oldFY>_<newFY>.json
uv run python -m pipeline.run NVDA --until-stage 0     # fetch + cache the two 10-Ks only
uv run python -m pipeline.run NVDA --from-stage 5      # recompute from the diff stage on
uv run python -m pipeline.run NVDA --no-cache          # ignore stage caches (raw filings still cached)
uv run python -m pipeline.run NVDA --force             # replace a published file whose analysis_id differs
uv run python -m pipeline.run FIXTUR                   # synthetic fixture pair → data/scratch/ (never published)
uv run python scripts/regen_contract.py   # schema.py → contract/comparison.schema.json → web/src/types/comparison.ts
uv run pytest                             # unit tests
uv run ruff check .                       # lint
uv run python -m eval.eval                # matcher precision/recall + threshold calibration → EVAL.md inputs

# API
uv run uvicorn api.main:app --port 8000 --reload

# Frontend (Node 20+)
cd web && npm install && npm run dev      # http://localhost:3000
cd web && npm run build && npm run lint && npm run typecheck

# Everything for the demo
./scripts/dev.sh
```

Environment: `.env` in the repo root (see `.env.example`). `SEC_USER_AGENT` is required for
stage 0; `HF_TOKEN` for the embedding model download and the LLM stage; `GEMINI_API_KEY` is
an optional LLM fallback. Missing `SEC_USER_AGENT` → stage 0 refuses to run (no invented email).
If the embedding model cannot load, a non-fixture run FAILS unless `RISKDIFF_ALLOW_LEXICAL=1`
(or `RISKDIFF_EMBED_BACKEND=lexical`) explicitly accepts the deterministic lexical fallback,
which is recorded in `model_ids` and changes `analysis_id`. The LLM stage is skipped (marked
`unavailable`) when no provider responds; it is never faked.
