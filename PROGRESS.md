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

## Judge-ready session (J-tasks, Oct 10 evening)

Context given by the team: NVDA was published on their machine and a finance-judge walkthrough found the
screens too technical. **That NVDA data is not in this repository or this sandbox** (no commits, no
`data/published/NVDA_*.json`, no stage caches, sec.gov/huggingface.co still blocked, no `.env`), so every
J-task was built and tested on synthetic cases that mirror the NVDA patterns quoted in the brief, and the
NVDA re-run + judge verification must be done on the team's machine (commands below).

| # | Task | Status | Notes |
|---|------|--------|-------|
| J1 | Skip Risk Factors Summary + intro paragraphs | done, tested | `segment.summary_skip_range`, intro/boilerplate never becomes a block; stage 2 → 0.2.0 |
| J2 | Entity post-filters | done, tested | `signals.clean_entity` + `merge_near_duplicates` ("D:4" dropped, trailing "in" stripped, Ruritania/Ruritanian merged) |
| J3 | In-progress → concluded detector | done, tested | `signals.status_change`; the quoted NVDA antitrust pair fires (aligned and unaligned); stage 6 → 0.2.0 |
| J4 | `highlights[]` + `short_title` | done, tested | `pipeline/highlights.py` ranking; LLM short-title batch (cached, validated) with heading-truncation fallback; contract + TS types regenerated |
| J5 | Hide FIXTURE by default | done | flag documented in `.env.example`, README, `web/.env.development` |
| J6–J10 | Finance-audience frontend | done (Opus subagent, `web/` only; verified by me) | overview leads with summary + highlight cards; detail leads with short title + AI summary + changed sentences only; vocabulary module; audit trail / analyst details collapsed; static methodology; no horizontal scroll at 1024/1280/1440 |
| J11 | Judge review + verification | done on the fixture | 131 tests, build/lint/typecheck clean, byte-identical reruns, copy greps clean; judge subagent reviewed screenshots (see REPORT.md); NVDA screens need the team's machine |

### NVDA re-run on the team's machine (required to verify J1–J4 on real data)

```bash
uv run python -m pipeline.run NVDA --from-stage 2 --force   # --force: the analysis_id changes (new stage versions)
uv run python - <<'EOF'
import json; d=json.load(open(sorted(__import__('glob').glob('data/published/NVDA_*.json'))[-1]))
print(d['summary']['by_change_type'], len(d['changes']))
for h in d['highlights']: print(h['kind'], '|', h['short_title'], '|', h['detail'])
EOF
```
Expected (not hardcoded): no duplicate titles, no intro row, ~23/24 blocks, "Commercial arrangements expose us to
counterparty risks." the only new risk; top highlights should include the China antitrust "preliminary finding"
pair (potential_became_actual), the $4.5 billion H20 charge (new_figure) and the counterparty risk (new_risk).
If one is missing, inspect `signals` of that change in the JSON and report.

## What's next

Team: run the NVDA command above, then `RISKDIFF_SHOW_FIXTURE= ./scripts/dev.sh` and walk the NVDA page as a judge.

## How to resume

`uv run pytest` (all green), `uv run python -m pipeline.run FIXTUR` (synthetic end-to-end, writes data/scratch/),
`uv run uvicorn api.main:app --port 8000`, `cd web && npm run dev`.
