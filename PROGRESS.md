# PROGRESS

Hackathon: Knight Hacks 9. Submission due Sunday Oct 11, 2026, 10:30 AM ET.
Build started: Sat Oct 10, 2026 (overnight, no human available).

## Current state (Oct 11)

The sections below are a log; this one is what holds now.

- `data/published/` holds two real reports, `NVDA_2025_2026.json` and `SF_2024_2025.json`, pushed by the team
  (pipeline 0.1.0 / rubric 1.0.0, bge-m3 + Qwen2.5-72B) and upgraded to the current contract with
  `scripts/migrate_published.py` (derived `short_title` + `highlights` only; analysis untouched, D-018).
- Both predate the current code (their `code_fingerprint` no longer matches), so the J1–J3, I2c and later
  pipeline changes only reach them through `uv run python scripts/refresh_stale.py`.
- With `SEC_USER_AGENT` set in `.env`, this cloud sandbox now reaches `data.sec.gov`, and `HF_TOKEN` is available,
  so the re-run no longer has to happen on the team's machine. It has not been run yet.
- `EVAL.md`: determinism (FIXTUR) and the citation audit of the two published reports ran; matcher
  precision/recall needs a golden set and LLM consistency needs live LLM calls, so both are marked not run.

## Environment blockers found at start (Task 0)

| Blocker | Impact | What the team must do |
|---------|--------|-----------------------|
| No `.env` in the repo → `SEC_USER_AGENT`, `HF_TOKEN`, `GEMINI_API_KEY` all unset | Stage 0 (SEC fetch) refuses to run; LLM stage is skipped and marked unavailable | Create `.env` from `.env.example` with a real contact email in `SEC_USER_AGENT` and a Hugging Face token |
| Network policy of this cloud environment denies `www.sec.gov`, `data.sec.gov`, `efts.sec.gov` (HTTP 403 from the egress proxy) | No real filings can be downloaded tonight → no real demo dataset, no golden set, no real eval numbers | Run the pipeline on a machine with normal internet, or add those hosts under the environment's Allowed domains |
| Network policy denies `huggingface.co` and its CDN | `BAAI/bge-m3` cannot be downloaded; HF Inference Providers unreachable | Same as above. The embedder falls back to a deterministic local lexical model and records that in `model_ids`; the LLM stage is marked unavailable |
| Reachable: PyPI, npm, GitHub release assets, `generativelanguage.googleapis.com` (no key though) | Dependencies install; spaCy model installs; Gemini client can be exercised only with a key | — |

Consequence: everything is built and tested end-to-end against a clearly labeled synthetic
FIXTURE filing pair (`contract/fixtures/`). Nothing fake is ever published. (The team later
published NVDA and SF; see Current state.)

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
screens too technical. **At the time, that NVDA data was not in this repository or this sandbox** (no commits, no
`data/published/NVDA_*.json`, no stage caches, sec.gov/huggingface.co still blocked, no `.env`), so every
J-task was built and tested on synthetic cases that mirror the NVDA patterns quoted in the brief, and the
NVDA re-run + judge verification must be done on the team's machine (commands below).

| # | Task | Status | Notes |
|---|------|--------|-------|
| J1 | Skip Risk Factors Summary + intro paragraphs | done, tested | `segment.summary_skip_range`, intro/boilerplate never becomes a block; stage 2 → 0.2.0 |
| J2 | Entity post-filters | done, tested | `signals.clean_entity` + `merge_near_duplicates` ("D:4" dropped, trailing "in" stripped, Ruritania/Ruritanian merged) |
| J3 | In-progress → concluded detector | done, tested | `signals.status_change`; the quoted NVDA antitrust pair fires (aligned and unaligned); stage 6 → 0.2.0 |
| J4 | `highlights[]` + `short_title` | done, tested | `pipeline/highlights.py`: four evidence tiers (meaningful + rule-based first), then score order, kind priority, position; max 2 per change / 5 total (D-018). LLM short-title batch (cached, validated) with heading-truncation fallback; contract + TS types regenerated |
| J5 | Hide FIXTURE by default | done | flag documented in `.env.example`, README, `web/.env.development` |
| J6–J10 | Finance-audience frontend | done (Opus subagent, `web/` only; verified by me) | overview leads with summary + highlight cards; detail leads with short title + AI summary + changed sentences only; vocabulary module; audit trail / analyst details collapsed; static methodology; no horizontal scroll at 1024/1280/1440 |
| J11 | Judge review + verification | done on real NVDA data (migrated file) | 137 tests, ruff clean, web build/lint/typecheck clean, FIXTUR cached vs `--no-cache` byte-identical, mechanical citation audit of NVDA+SF (32 claims, 11 rubric yes, 37 score lines, 9 highlights: 0 problems), no horizontal scroll at 1024/1280/1440, first highlight card fully visible at 1440×900 (its first fact at 1280×720); two judge rounds: 6/10 on the fixture, 6.5/10 on real NVDA screens (REPORT.md §10) |
| J11c | Judge round 2 follow-ups | done (pipeline: D-019; frontend: one card per risk, full headings over truncated titles, neutral change labels, collapsed one-sided runs, methodology AI wording, capped-total note) | remaining points are old-pipeline data (re-run) |
| J11b | Judge round 1 follow-ups | done | rubric Q1–Q3 never double-count their rule-based twin (RUBRIC_VERSION 1.1.0); content-word anchoring in `diff.word_spans` (0.1.2); fixture scores from the real scorer; `scripts/migrate_published.py`; frontend: neutral "Wording change: High/Medium/Low" chips + clarifier, "Figure changed" vs "New figure disclosed", "Risk factor 1 of 29" breadcrumb, button-style citation chips, labelled hatched cells, collapsed technical methodology, single search box on home, `devIndicators: false` |

### NVDA re-run on the team's machine (required to get J1–J3 into the published NVDA file)

What the migrated file still shows from the old pipeline: 27→29 blocks with 2 duplicate titles (Risk Factors
Summary not skipped), the intro paragraph "The following risk factors should be considered…" ranked as a
new risk, entities "AI Diffusion IFR in" and "D:4", no status-change (investigating → preliminary finding)
signal, and truncated headings instead of LLM short titles. The migrated highlights are: "may → have been"
(potential became actual, export-controls risk), the new counterparty risk, Groq newly named, the intro row
(artifact), and the $4.5 billion H20 charge. Re-run to replace all of that:

```bash
uv run python -m pipeline.run NVDA --from-stage 2 --force   # --force: the analysis_id changes (new stage versions)
uv run python -m pipeline.run SF --from-stage 2 --force
# (older published files can be brought to the current contract without a re-run: uv run python scripts/migrate_published.py)
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

## Shared report library session (D-tasks, Oct 10 night)

| # | Task | Status | Notes |
|---|------|--------|-------|
| D1 | Databricks client | done, tested (fake SDK) | `pipeline/store/databricks.py` + `tables.py`; `databricks-sdk==0.146.0`; host validation + single-host allowlist; typed errors, timeouts, 2 retries |
| D2 | Schema bootstrap | done | `scripts/databricks_setup.py` (IF NOT EXISTS everywhere, `--dry-run`) |
| D3 | Publish to Databricks | done, tested | `pipeline/store/publisher.py`; pipeline runs it after stage 8 (`--no-remote`); exit 3 when only the remote step fails; `scripts/sync_to_databricks.py` |
| D4 | API reads from the store | done, tested | library merge, read-through pull with verification, `/store/health`, `/trends` |
| D5 | Frontend library awareness | done (Opus subagent, `web/` only; verified) | footer + audit-trail indicator, "Report library" with "Published by X · date" |
| D6 | Trends | done | two parameterized aggregates in `tables.py`, `/trends` (TTL 60 s), Trends page with empty states |
| D7 | Tests, docs, verification | done (mocks only) | 170 tests, ruff clean, web build/typecheck/lint clean, FIXTUR determinism unchanged, offline path measured with the real SDK against an unreachable host; README section, `.env.example`, DECISIONS D-020, REPORT §11 |

No Databricks credentials exist in this sandbox: everything was built and tested against a mocked SDK
client; the one-time steps for the team are in docs/REPORT.md §11 and README "Shared report library".

## Design and Trends session (UX1–UX13, Oct 11)

| # | Task | Status | Notes |
|---|------|--------|-------|
| UX1 | DESIGN.md + tokens | done | Public Sans / Source Serif 4 via next/font, scale 14/15/17/22/32/44, direction colors, highlighter; CLAUDE.md points at DESIGN.md |
| UX2 | Typography and helper-text purge | done | every page; sentence-case labels; no middle dots, arrows, uppercase tracking, glyphs; plain wordmark |
| UX3 | ChangeBadge + ChangeLevel | done | one implementation (`ui.tsx`), direction tones in `vocabulary.ts`, one legend on the company page |
| UX4 | Before/after card | done | `HighlightCard` + `MarkedText` + `Quote`: highlighter on diff spans, strikes on removed words, one column below 900px |
| UX5 | Company page | done | clean names (`names.ts`), 22px summary statement, cards only for Biggest changes, rows for All changes, quiet audit trail |
| UX6 | Change detail page | done | short title first, official heading under it, neutral AI panel with footnote citations, highlighter diff |
| UX7 | Home page | done | deterministic hero (`hero.ts`), no feature cards, library cards with display names and short titles |
| UX8 | Amazon 0 meaningful changes | blocked here (no AMZN report, no SEC access) | diagnostic recipe and decision criteria in docs/REPORT.md §12 |
| T9–T11 | Trends backend (subagent) | see its rows below / commits T9, T10, T11 | cold-start fix, derived facts, tables and serving |
| UX12 | Trends page | done (UI) | headline, shared topics with quotes, blue-orange heatmap, potential→actual list, change mix, source line, skeleton + retry |
| UX13 | Verification and outside review | done | 204 pytest + 13 node tests, ruff, build/typecheck/lint, FIXTUR byte-identical cached vs `--no-cache`, code fingerprint unchanged (`e94330fb…`), no horizontal scroll and nothing under 14px at 1440 and 1280; two review rounds (reverse-squint 6/10 → 6/10, judge → 7/10) with verdicts and responses in REPORT.md §12 |

## Frontend session (Oct 10)

| # | Task | Status | Notes |
|---|------|--------|-------|
| FE1 | Dark mode + theme toggle | done | D-028; same token names under `[data-theme="dark"]`, system/light/dark toggle, no flash before paint |
| FE2 | Company logos | done | D-027; genuine SVGs for AAPL, AMZN, NVDA, SF, CRWD in `web/public/logos/` (sources in `SOURCES.md`), monogram for every other ticker |
| FE3 | Market-style polish | done | identity rows, filing strip, stat rows on cards, table-aligned change list; no green/red, no arrows |
| FE4 | Merge with UX13 | done | five conflicts resolved keeping both sides; pushed to `main` |
| FE5 | Heatmap contrast (light) | done | D-026; every cell number >= 4.5:1 in both themes, checked by math and in Chrome by a second, independent agent |

Open, found in a browser review of both themes (not fixed):
- NVDA and SF still need the re-run below (preamble ranked as a New risk, "z ECCNs" fragment, older prompt).
- `displayTitle` (`web/src/lib/vocabulary.ts`) cuts headings into fragments such as "The technology industry, including".
- Trends topic quotes can hide the topic word behind "…" (Tariffs: the Apple and Amazon quotes never show "tariffs").
- Amazon: Trends lists it as newly adding tariff language while its page says 0 of 24 changed meaningfully, with an empty table.
- Library cards from the shared store (GOOGL, MSFT, TSLA) have no "Top change" and no bundled logo.
- CRWD reads "FY2024 and FY2026": the filer's own `dei:DocumentFiscalYearFocus` says 2024 for the year ended Jan 31, 2025 (`sec_fetch.fiscal_year_from_html` trusts it).
- Dark mode only: a faint gray heatmap cell is nearly indistinguishable from an empty cell (ΔE 1.3).

## Performance session (P-tasks, Oct 10)

| # | Task | Status | Notes |
|---|------|--------|-------|
| P1 | Parallel LLM calls + per-stage timings | done, tested | `RISKDIFF_LLM_CONCURRENCY` (default 6); timing table on stderr after `python -m pipeline.run`; see D-024. Not timed on a real ticker here (no SEC/HF access) |
| P2 | Short-titles LLM batch overlapped with stage 7 | done, tested | sent on its own thread alongside the interpretation calls when stage 7 calls anyway; same key/prompt/result; FIXTUR fake-client stages 7+8 0.62 s → 0.42 s; output identical except `code_fingerprint`/`analysis_id` (source hash, D-016); see D-029 |

## What's next

Team: `uv run python scripts/refresh_stale.py --check` on a machine with SEC and Hugging Face access re-runs NVDA and SF from their earliest changed stage (NVDA from segmentation, SF from the diff), republishes and re-derives trends; that clears the 30 remaining stale findings in INTEGRITY_REPORT.md. Then run the NVDA command above (it also removes the "The following risk factors…" preamble from the
highlights and cleans the entity noise the reviewers saw), then `RISKDIFF_SHOW_FIXTURE= ./scripts/dev.sh`
and walk the NVDA page as a judge. Smallest safe next task: docs/REPORT.md §12, "Next smallest safe task".

## How to resume

`uv run pytest` (all green), `uv run python -m pipeline.run FIXTUR` (synthetic end-to-end, writes data/scratch/),
`uv run uvicorn api.main:app --port 8000`, `cd web && npm run dev`.

## Integrity session (I1–I4, Oct 10 night)

Brief: "every claim traces back to the filing" must hold on every page; a checker proves it. This sandbox
still has only the NVDA and SF reports (no SEC, Databricks or team-library access), so the AAPL/AMZN/GOOGL/CRWD
instances named in the brief are proven as mechanisms in code and on NVDA/SF, never inspected live.

| # | Task | Status | Notes |
|---|------|--------|-------|
| I1 | Integrity checker | done | `scripts/check_integrity.py` (13 checks, stale/code classification by re-running current code on the report's data), baseline `INTEGRITY_REPORT.before.md` + `data/integrity/before.json` (135 findings), `stage_versions` recorded in every new report, `tests/test_integrity_checker.py` |
| I2a | Web fixes (Opus subagent, `web/` only) | done | Trends never throws (error boundary per section), merged `other` heatmap column, snippet windows (`snippet.ts` = port of the checker's rule, shared vectors), case/punctuation-only spans unmarked, fragment-free title fallback |
| I2b | Trends derivation + serving (Opus subagent) | done | topics only from inserted spans and only on meaningful changes, Trends company set = `/companies` set, derivation failures visible, Databricks rows filtered to the current derivation, derived files regenerated |
| I2c | Pipeline (Opus subagent) | done | aligned-only potential→actual pairs, casefold word diff (stage 5 bump), clause-boundary short titles, entity stoplist in signals, intro/summary test, January fiscal-year tests, PIPELINE_VERSION 0.2.0 |
| I3 | Re-run stale reports | script done; presentation refresh applied; real re-runs blocked here | `scripts/refresh_stale.py` (NVDA first, then by age; cache decides the earliest stage; resumable log); NVDA/SF re-runs need a machine with SEC + Hugging Face access |
| I4 | Verify | done | checker: 135 → 30 findings, all 30 stale data in the two old reports (0 code); Playwright smoke test 3/3 green against the production build with zero console errors; 265 pytest + 29 node tests, ruff, typecheck, lint, build, FIXTUR byte-identical; screenshots viewed |

## Trends backend session (T-tasks, Oct 10 night)

| # | Task | Status | Notes |
|---|------|--------|-------|
| T9 | Trends cold-start bug | done, tested | root cause in DECISIONS D-021; four health states, SWR `/trends` with disk cache, local fallback |
| T10 | Derive trend facts at publish time | done, tested | `pipeline/trends/derive.py` + `topics.yml` (31 topics); `data/derived/*.trends.json` committed for NVDA + SF; hook in the publisher (run.py untouched: it feeds analysis_id) |
| T11 | Store and serve trend facts | done, tested (fake SDK + simulated tables) | `topic_mentions` + `category_activity` tables and MERGEs, three parameterized `/trends` queries, shared `pipeline/trends/aggregate.py`, `scripts/derive_trends.py`; Databricks body == local body on NVDA + SF (simulated); never run against a real warehouse |

## Ticker tape session (branch `slider`, Oct 10)

| # | Task | Status | Notes |
|---|------|--------|-------|
| K1 | Finnhub quote service + `GET /ticker-tape` | done, tested | `api/ticker_tape.py` (50 symbols, throttled background poller, backoff, disk cache), 28 tests with fake fetch/clock; conftest strips `FINNHUB_API_KEY` so tests never poll; D-026 |
| K2 | Home-page tape | done, tested | `web/src/components/TickerTape.tsx`, `lib/tickerTape.ts` (+8 node tests), same-origin proxy `/api/ticker-tape`; home page only |
| K3 | Verify | done | pytest (all pass except `test_trends.py::test_databricks_trends_match_the_local_aggregate`, a pre-existing timing flake that also fails 2/8 on unchanged main), ruff, typecheck, lint, 37 node tests, build; live smoke: API + production web, unreachable Finnhub → tape hidden, page 200, key never logged; restart with cached quotes → 50 items shown as "last updated" |

Blocker: this sandbox's network policy denies `finnhub.io`, so real quotes were never fetched here.
To see live prices: put `FINNHUB_API_KEY` (free at finnhub.io) in `.env` and run `./scripts/dev.sh`.

## Stage 3 speedup (Oct 11)

| # | Task | Status | Notes |
|---|------|--------|-------|
| E1 | Drop unused full-text block vectors | done, independently verified | about 45–50% less stage-3 compute; published content byte-identical apart from `code_fingerprint`/`analysis_id` (D-027) |

Not done (changes embedding bits, so needs a stage-3 version bump and re-publish): length-aware batching of
long blocks (another ~50% on long filings) and running on a GPU (see the research summary in the session).


## Cleanup audit (Oct 11)

| # | Task | Status | Notes |
|---|------|--------|-------|
| C1 | Hand cursor on buttons | done | Tailwind v4 preflight leaves `<button>` on the arrow; one rule in `globals.css` gives every enabled button the pointer (checked in Chromium) |
| C2 | Dead code + tooling | done | unused web exports (legacy badge wrappers, `Stat`, `CategoryChip`, `getHealth`, `trimQuote`, ...), `ink-faint` alias, 3 unused Python helpers outside `pipeline/*.py` (code fingerprint unchanged); `package-lock.json` re-synced (`npm ci` failed); `typecheck` runs `next typegen` first; tests strip `DATABRICKS_*`; node tests forced to TAP; unused Python `playwright` dev dep removed |
| C3 | Docs | done | `REPORT.md`, `INTEGRITY_REPORT.md`, `INTEGRITY_REPORT.before.md` moved to `docs/`; duplicate `data/integrity/after.json` removed; `EVAL.md` and `DEMO.md` regenerated from the published reports (`build_demo.render_demo`, which also fixes a crash on highlight-picked moments); README, `data/published/README.md` and this file brought up to date; unused constants removed from `pipeline/*.py` (code fingerprint changes; NVDA/SF were already stale) |
