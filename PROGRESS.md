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
| 0 | Scaffold + CLAUDE.md | in progress | |
| 1 | Data contract + fixture + TS types | todo | |
| 2 | SEC fetch (stage 0) | todo | blocked for live runs (network + SEC_USER_AGENT); unit-tested with mocked HTTP |
| 3 | Item 1A extraction (stage 1) | todo | |
| 4 | Risk segmentation (stage 2) | todo | |
| 5 | Embedding + matching (stages 3–4) | todo | bge-m3 path implemented; lexical fallback used here |
| 6 | Sentence diff + change_type (stage 5) | todo | |
| 7 | Deterministic signals (stage 6) | todo | |
| 8 | LLM rubric + interpretation (stage 7) | todo | no provider available here → unavailable |
| 9 | Scoring + publish (stage 8) | todo | |
| 10 | Evaluation | todo | golden set needs real filings → blocked |
| 11 | Frontend | todo | Opus subagent, `web/` only |
| 12 | API + live mode | todo | |
| 13 | Demo dataset | todo | blocked: needs SEC access |
| 14 | Hardening + REPORT.md | todo | |

## What's next

Task 0 commit, then Task 1 (schema, fixture, TS types), then spawn the frontend subagent.
