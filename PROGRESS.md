# PROGRESS

Hackathon: Knight Hacks 9. Submission due Sunday Oct 11, 2026, 10:30 AM ET.
Build started: Sat Oct 10, 2026 (overnight, no human available).

## Environment blockers found at start (Task 0)

| Blocker | Impact | What the team must do |
|---------|--------|-----------------------|
| No `.env` in the repo → `SEC_USER_AGENT`, `HF_TOKEN`, `GEMINI_API_KEY` all unset | Stage 0 (SEC fetch) refuses to run; LLM stage is skipped and marked unavailable | Create `.env` from `.env.example` with a real contact email in `SEC_USER_AGENT` and a Hugging Face token |
| Network policy of this cloud environment denies `www.sec.gov`, `data.sec.gov`, `efts.sec.gov` (HTTP 403 from the egress proxy) | No real filings can be downloaded tonight → no real demo dataset, no golden set, no real eval numbers | Run the pipeline on a machine with normal internet, or add those hosts under the environment's Allowed domains |
| Network policy denies `huggingface.co` and its CDN | `BAAI/bge-m3` cannot be downloaded; HF Inference Providers unreachable | Same as above. The embedder falls back to a deterministic local lexical model and records that in `model_ids`; the LLM stage is marked unavailable |
| Reachable: PyPI, npm, GitHub release assets, `generativelanguage.googleapis.com` (no key though) | Dependencies install; spaCy model installs; Gemini client can be exercised only with a key | — |

Consequence: everything is built and tested end-to-end against a clearly labeled synthetic
FIXTURE filing pair (`contract/fixtures/`). `data/published/` stays empty until the team runs
the pipeline with network access and `.env`. Nothing fake is ever published.

## Task status

| # | Task | Status | Notes |
|---|------|--------|-------|
| 0 | Scaffold + CLAUDE.md | done | commit ae1c431 |
| 1 | Data contract + fixture + TS types | done | `pipeline/schema.py` → `contract/comparison.schema.json` → `web/src/types/comparison.ts`; `scripts/regen_contract.py --check` is a test |
| 2 | SEC fetch (stage 0) | done (code + mocked tests) | live runs blocked here: no SEC_USER_AGENT and sec.gov denied by network policy |
| 3 | Item 1A extraction (stage 1) | done (synthetic tests only) | TOC trap, heading variants, furniture removal, loud failures. NOT yet validated on real filings (no SEC access) |
| 4 | Risk segmentation (stage 2) | done (synthetic tests only) | group headers, bold lead sentences, pysbd; NOT yet validated on real filings |
| 5 | Embedding + matching (stages 3–4) | done | bge-m3 path implemented (chunk + mean-pool, truncation logged) but cannot load here; lexical TF-IDF fallback is what ran. Thresholds are placeholders |
| 6 | Sentence diff + change_type (stage 5) | done | rules documented in `diff.classify_change_type` |
| 7 | Deterministic signals (stage 6) | done | spaCy en_core_web_sm NER; keyword lexicon (+ dense prototypes when bge-m3 available) for categories |
| 8 | LLM rubric + interpretation (stage 7) | done (code) / unavailable at runtime | HF + Gemini clients written; no key and HF blocked, so every interpretation is `unavailable`. Validator unit-tested |
| 9 | Scoring + publish (stage 8) | done | byte-identical output verified (cached vs --no-cache); fixture → data/scratch only |
| 10 | Evaluation | todo | golden set needs real filings → blocked |
| 11 | Frontend | done + reviewed + fixed | build/lint/typecheck green; screenshots at 1440×900 reviewed; live SSE verified against the real API |
| 12 | API + live mode | done + reviewed + fixed | thread-held single-analysis lock, cancel between stages, fixture never served, SSE tested |
| 13 | Demo dataset | blocked (SEC access) | `scripts/build_demo.py` + `eval/citation_audit.py` ready; UI screenshots done on the fixture |
| 14 | Hardening + REPORT.md | two review rounds done | round 1: 4 HIGH + 12 MEDIUM (pipeline) and 3 MEDIUM + 14 LOW (frontend) fixed; round 2: 0 HIGH, 8 MEDIUM (pipeline) + 3 MEDIUM (frontend) fixed with tests; a third pass was not run (time), so "two consecutive clean passes" is NOT claimed |

## What's next

For the team: `.env` + a machine with SEC/HF access → `uv run python scripts/build_demo.py` → spot-check
Item 1A boundaries → `uv run python -m eval.eval --write` → citation audit (`eval/README.md`).

## How to resume

`uv run pytest` (all green), `uv run python -m pipeline.run FIXTUR` (synthetic end-to-end, writes data/scratch/),
`uv run uvicorn api.main:app --port 8000`, `cd web && npm run dev`.
