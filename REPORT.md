# RiskDiff — overnight build report

Built overnight for Knight Hacks 9 (submission Sunday Oct 11, 2026, 10:30 AM ET) with no human in
the loop. Read this first, then `PROGRESS.md` (status per task), `DECISIONS.md` (every call made
without you), `EVAL.md` (real numbers only), `DEMO.md` (demo dataset status).

## 1. Where things stand (honest summary)

**Working and tested end to end (on the synthetic FIXTURE filing pair):** every pipeline stage
(fetch → extract → segment → embed → match → diff → signals → LLM → score/publish), stage caching,
byte-identical reruns, the FastAPI backend with SSE live mode, and the Next.js UI (all five screens,
citation chips that jump to the cited sentence, side-by-side/inline diff, score breakdown, AI
interpretation panel, methodology page). 113 pytest tests pass; `npm run build/lint/typecheck` pass.
Two independent review rounds were run on the pipeline/API and on the frontend. Every HIGH and
MEDIUM finding from both rounds was fixed and covered by a test where practical (`DECISIONS.md`
D-015/D-016, section 9 below). The brief asked for two consecutive clean passes; the second pass
still found MEDIUM items (now fixed), and a third pass was not run for lack of time, so that bar
is not claimed.

**Not done, and why (environment blockers, not code):**

| Blocker | Consequence | Fix on your side |
|---|---|---|
| No `.env` existed in the repo: `SEC_USER_AGENT`, `HF_TOKEN`, `GEMINI_API_KEY` unset | Stage 0 refuses to contact sec.gov (by design: no invented contact email). LLM stage marked `unavailable`. | `cp .env.example .env`, fill in `SEC_USER_AGENT="RiskDiff <name> <email>"` and `HF_TOKEN` |
| The cloud sandbox's network policy denied `www.sec.gov`, `data.sec.gov`, `efts.sec.gov` and `huggingface.co` (HTTP 403 from the egress proxy) | No real filings could be downloaded, so: no demo dataset, no golden set, no matcher precision/recall, no LLM consistency numbers, no citation audit. The embedding model `BAAI/bge-m3` could not be downloaded; the pipeline ran on a deterministic lexical TF-IDF fallback (recorded in `model_ids`). | Run on a laptop with normal internet (everything below is copy-paste), or add those hosts to the environment's allowed domains |

Nothing synthetic was published: `data/published/` is empty; the FIXTURE lives in
`contract/fixtures/` and the publisher refuses to write it anywhere else.

## 2. Run everything (copy-paste)

Prerequisites: `uv` (Python 3.12 is managed for you), Node 20+ (22 tested), internet access to
sec.gov and huggingface.co.

```bash
git clone <repo> && cd KnightHack26
cp .env.example .env            # set SEC_USER_AGENT (required) and HF_TOKEN (recommended)
uv sync                         # ~6 GB: torch + sentence-transformers + spaCy model (pinned in uv.lock)
cd web && npm install && cd ..  # pinned in package-lock.json

# sanity: the synthetic fixture end to end (no network needed) -> data/scratch/FIXTUR_2024_2025.json
uv run python -m pipeline.run FIXTUR

# one real company (downloads 2 filings + the embedding model on first run; the model download is ~2.2 GB)
uv run python -m pipeline.run NVDA
#   -> data/published/NVDA_<oldFY>_<newFY>.json ; prints the path
#   rerun it: identical bytes and identical analysis_id (stage cache under data/cache/)

# the demo dataset (10 candidates -> keeps the 5-8 most substantive by pipeline output, writes DEMO.md)
uv run python scripts/build_demo.py

# tests, lint, contract check
RISKDIFF_EMBED_BACKEND=lexical uv run pytest -q      # (lexical keeps the suite offline + fast)
uv run ruff check . && uv run python scripts/regen_contract.py --check

# evaluation (needs real filings + HF_TOKEN; writes EVAL.md)
uv run python -m eval.golden_tool NVDA > /tmp/nvda_blocks.txt    # then label per eval/README.md
uv run python -m eval.eval --consistency-ticker NVDA --determinism-ticker NVDA --write
uv run python -m eval.citation_audit --sample 40                   # then judge per eval/README.md

# the app
./scripts/dev.sh                 # API on :8000 + web on :3000  (Ctrl-C stops both)
#   or separately:
uv run uvicorn api.main:app --port 8000
cd web && npm run dev            # http://localhost:3000
```

Useful flags: `--until-stage N`, `--from-stage N`, `--no-cache` (recompute deterministic stages;
raw filings and raw LLM output are still reused), `--refresh-llm` (re-query the provider; the
published bytes can change under the same analysis_id, so use deliberately), `--force` (replace a
published file whose analysis_id or bytes differ). Dev only: `RISKDIFF_SHOW_FIXTURE=1` lists the FIXTURE company in
the UI (with a loud banner), `RISKDIFF_ALLOW_FIXTURE=1` lets the API analyze `FIXTUR` live.
Speed knob for live demos on CPU: `RISKDIFF_EMBED_MODEL=BAAI/bge-small-en-v1.5` (512-token
context, ~30× faster than bge-m3; changes `analysis_id`, so publish with one model only).

## 3. What the team will see

1. Home: search + grid of published companies.
2. `/c/NVDA`: both filings (dates, accession numbers, EDGAR links), analysis id, code fingerprint,
   model ids, summary counts, filters, ranked changes with scores.
3. `/c/NVDA/<change>`: side-by-side or inline sentence diff with word-level spans; score breakdown
   (every line expandable to its cited sentence); AI interpretation (visually distinct; numbered
   citation chips that scroll to and flash the cited sentence and offer "Open in SEC filing" with a
   text fragment); deterministic signals panel.
4. `/analyze/<ticker>`: live run with the 9-stage stepper over SSE; friendly errors.
5. `/methodology`: pipeline diagram, weights table from `contract/rubric.json`, `EVAL.md`, disclaimer.

## 4. Evaluation numbers (from EVAL.md)

- Determinism: **real**. Full pipeline run twice on the fixture pair: byte-identical, identical
  `analysis_id`, zero cache misses on the second run. (Also verified cached vs `--no-cache`.)
- Matcher precision/recall, threshold calibration, LLM rubric agreement, score stability, citation
  audit: **blocked** (need real filings + a model provider). The harness (`eval/eval.py`,
  `eval/citation_audit.py`, `eval/golden_tool.py`, `eval/golden_prompt.md`) is written and
  self-tested on the fixture path; see `eval/README.md` for the 30-minute procedure.

Do not quote any accuracy number in the pitch until `eval.eval --write` has run on real filings.

## 5. Known limitations

- **Untested on real 10-K HTML.** Extraction and segmentation were built from knowledge of
  Workiva/inline-XBRL filings and tested on synthetic documents (TOC trap, split headings, NBSP,
  page furniture with page numbers, page-split paragraphs, "(continued)" headers, ix:nonNumeric
  wrappers, layout tables). Expect to tune `pipeline/extract.py` / `pipeline/segment.py` on the
  first few real companies. Spot-check the start/end of Item 1A for each demo company
  (`uv run python -m pipeline.run NVDA --until-stage 1` then inspect `data/cache/stages/extract/`).
- **Banks (JPM, BAC, GS, C) often cross-reference Item 1A to a page range** of their annual
  report. The fallback ("Risk Factors" heading → next of Item 1B/1C/2/"Unresolved Staff
  Comments"/"Properties"/MD&A) may fail loudly for them. If so, swap in another large filer.
- **Thresholds are placeholders** (dense 0.62, lexical 0.20) until `eval.eval` recalibrates them.
- **LLM output is cached per change**; the first run of each company calls the provider once per
  non-trivial change (≈20–60 calls). Only the raw model JSON is cached; the citation validator
  reruns on every load. Temperature-0 output is not reproducible across providers/time, so the raw
  cache is the determinism anchor: back up `data/cache/stages/llm/` with the published files if you
  need to regenerate later. If the provider fails for some changes the run aborts rather than
  publishing a partial result (`RISKDIFF_ALLOW_PARTIAL_LLM=1` overrides).
- **Cross-machine byte identity is not guaranteed** for dense embeddings (BLAS/thread float
  differences can move a 4-decimal similarity). Same machine + same `uv.lock` is deterministic.
- **Hugging Face Inference Providers**: the request shape was validated against the SDK types but
  never sent live (no token here). If `Qwen/Qwen2.5-72B-Instruct` is unavailable on providers,
  set `RISKDIFF_LLM_MODEL` to another instruct model; the id is recorded in `analysis_id`.
- The categories taxonomy is keyword-lexicon (+ dense prototype similarity when bge-m3 is
  available); it is coarse by design.
- The UI is desktop-only (≥1280px).

## 6. Blockers that need you

1. `.env` with a real `SEC_USER_AGENT` (SEC requires a contact) and `HF_TOKEN`.
2. A machine with internet access to sec.gov and huggingface.co (the cloud sandbox had neither).
3. ~15 minutes of human spot-checking after `build_demo.py`: open each demo company, confirm the
   Item 1A boundaries look right, and skim the top change of each.
4. Golden-set labeling + eval run (procedure in `eval/README.md`) if you want real accuracy numbers
   in the pitch.

## 7. 90-second demo script

The brief asked for a script built on real examples from `DEMO.md`. `DEMO.md` cannot be produced
without SEC access, so the script below is a template; `scripts/build_demo.py` fills `DEMO.md`
with one real "demo moment" per company (top-ranked change + its cited sentence, quoted verbatim).
Rehearse it on `FIXTUR` (`RISKDIFF_SHOW_FIXTURE=1 ./scripts/dev.sh`), then replace the bracketed
parts with the real ones from `DEMO.md`.

> (0:00) "Every year companies rewrite their risk factors. The changes are the signal, but nobody
> reads 40 pages twice. RiskDiff is GitHub Diff for 10-K risk factors."
> (0:10) Home → click [COMPANY]. "Two filings, [FY] and [FY], straight from EDGAR; the analysis id
> means anyone can reproduce this byte for byte."
> (0:25) Point at the ranked list. "[N] risk factors; deterministic code says what changed: new,
> removed, expanded, reworded. No model decides this."
> (0:35) Open the #1 change. "Side by side, sentence by sentence, word by word. Here [the cited
> sentence from DEMO.md] replaced hedged language with what actually happened."
> (0:55) Score breakdown. "Every point is a published rule with the sentence that triggered it."
> (1:05) AI interpretation. "The model only answers four narrow questions and writes three short
> observations, and every claim carries a citation chip." Click a chip → the sentence lights up →
> "Open in SEC filing" jumps to the exact text on sec.gov.
> (1:20) Type a new ticker → live analysis stepper. "Same pipeline, live, with caching."
> (1:30) "Not investment advice: RiskDiff shows changes in disclosed risk language, not changes
> in actual risk. Methodology page has every weight and the evaluation numbers."

## 8. Suggested next steps (not built)

Portfolio view (many tickers, one table of top changes); cross-company trends (which categories
grew this year across the S&P 500); Databricks job for the batch pipeline + Delta tables for the
published JSON; 10-Q monitoring (quarterly Item 1A updates); human-in-the-loop golden set tooling.

## 9. Review rounds

- Round 1 (pipeline/API reviewer): 4 HIGH, 12 MEDIUM, 11 LOW → all HIGH/MEDIUM fixed, most LOW
  fixed (`DECISIONS.md` D-015). Round 1 (frontend reviewer): 0 HIGH, 3 MEDIUM, 14 LOW → all fixed.
- Round 2 (pipeline/API/security reviewer): 0 HIGH, 8 MEDIUM, 15 LOW. Three of the MEDIUMs were
  round-1 edits that had failed to apply after formatting (cancel check, `--force`, stage-5 cache
  keys); all 8 MEDIUM are fixed with tests, plus the LOWs that touch security or determinism
  (`DECISIONS.md` D-016). Deliberately left: per-process SEC rate limiter, paginated-history cache
  refresh, unpinned embedding revision, worded numbers in the validator.
- Round 2 (frontend reviewer): 0 HIGH, 3 MEDIUM, 7 LOW → all MEDIUM and most LOW fixed (neutral
  validator reason labels, one citation numbering for the whole page, no AI note when no model ran,
  sec.gov-only filing links, API card validation).
- Known soft spots a third pass would probably raise: cross-machine float drift in dense
  similarities; the extraction heuristics have still never met a real filing.

## 10. Judge-ready session (J1–J11)

Goal: a BNY finance judge understands a company page in five seconds. Status at the end of the session:

| Task | Status |
|---|---|
| J1 skip Risk Factors Summary + intro | done, unit-tested on an NVDA-shaped synthetic layout |
| J2 entity post-filters ("D:4", trailing "in", near-duplicates) | done, unit-tested |
| J3 in-progress → concluded detector (the China antitrust pair) | done, unit-tested on the quoted sentence pair |
| J4 `highlights[]` + `short_title` in the contract, ranked deterministically | done; fixture carries 5 highlights |
| J5 FIXTURE hidden unless `RISKDIFF_SHOW_FIXTURE=1` | done |
| J6–J10 finance-audience frontend | see below |
| J11 verification + judge review | see below |

**Data in the repo.** The team pushed `data/published/NVDA_2025_2026.json` and `SF_2024_2025.json`, produced by
pipeline 0.1.0 / rubric 1.0.0 (bge-m3 embeddings, Qwen2.5-72B via Hugging Face). This sandbox still cannot
re-run the pipeline (sec.gov and huggingface.co blocked, no stage caches, no `.env`), so both files were brought
to the current contract with `scripts/migrate_published.py`: it derives `short_title` (deterministic truncation
of the real heading, no LLM) and `highlights[]` (`select_highlights` over the file's own signals, change types
and validated rubric answers) and records a note. Scores, sentences, citations and `analysis_id` are untouched.
The J1–J3 pipeline improvements reach the NVDA file only through the re-run (the analysis id changes because
stage versions changed, hence `--force`):

```bash
uv run python -m pipeline.run NVDA --from-stage 2 --force
uv run python -m pipeline.run SF --from-stage 2 --force
./scripts/dev.sh            # then open http://localhost:3000/c/NVDA
```

### NVDA: before and after (migrated file; the re-run will change the "after" column again)

| | Team's file (pipeline 0.1.0) | After migration | Expected after re-run (not verified here) |
|---|---|---|---|
| Blocks old → new | 27 → 29 (2 duplicate titles: summary not skipped) | same | ~23/24, no duplicates |
| Changes | 29: 2 new, 2 expanded, 1 reworded, 1 reduced, 23 unchanged | same | the intro paragraph no longer a "new" risk |
| Entities | "AI Diffusion IFR in", "D:4", "Groq", "Groq, Inc", … | same | junk dropped, near-duplicates merged |
| Short titles | none | truncated headings | LLM titles (validated) with the same fallback |
| Highlights | none | 5 (below) | antitrust "preliminary finding" pair should join via `status_change` |
| analysis_id | `13acfdfe2afda6d2…` | unchanged (presentation fields only) | new |

Migrated NVDA highlights, in order (no special-casing; `select_highlights` over the file):

1. Potential → Actual, "We are subject to complex laws, rules…" (score 100): "Such requests **may** be expensive"
   → "Such requests **have been** and are likely to be expensive".
2. New risk, "Commercial arrangements expose us to counterparty risks" (40).
3. Newly named, "Failure to meet the evolving needs of…" (31): Groq.
4. New risk, "The following risk factors should be considered…" (30): the intro paragraph; an old-pipeline artifact
   that J1 removes on re-run.
5. New figure disclosed, "We are subject to complex laws, rules…" (100): the $4.5 billion H20 charge.

(After the round-2 ranking changes the first card quotes "Export controls increase the risk of investing in U.S.
advanced semiconductor products…" instead of "Such requests…", and the counterparty card quotes the
financial-guarantee sentence instead of the heading.)

So of the three facts the brief asked about: the **$4.5 billion H20 charge** and the **counterparty risk** appear;
the **China antitrust pair** (investigating → published preliminary finding) does not, because the file was
produced before the `status_change` detector existed. It fires on the quoted sentence pair in the unit tests.

### Judge round 1 (fixture screenshots; verdict 6/10)

Points raised and what was done:

| Point | Response |
|---|---|
| Score points did not match the published weights (+10 for two names, +15 for one figure) | fixture scores were hand-written; the generator now calls the real `score_change` |
| A rule-based signal and an AI check scored the same fact twice | rubric Q1–Q3 skipped when the twin signal already scored (`RUBRIC_VERSION` 1.1.0) |
| "High / Medium / Low" read as a risk rating | neutral outlined chip "Wording change: High", clarifier line above the list, scoring subline kept |
| "New figure disclosed" on a figure that merely changed | "Figure changed" when both years have the sentence |
| Two cards about the same risk; new and dropped risks absent | ranking tiers: one card per change first; new/dropped risk is the primary card of such a change |
| Counts disagreed ("2 modified" vs "1 modified"; "6 meaningful" vs "Change 1 of 7") | fixture stats now computed; breadcrumb says "Risk factor 1 of 29" |
| "Eastland" struck on the left while present on the right | content words anchor the word diff (diff stage 0.1.2) |
| "!" glyph on Potential → Actual read as an alert | glyph removed, outlined chip |
| Citation chips looked like code | button-style chips, hover underline, hint line "Click a number to see the sentence…" |
| Methodology was a technical dump with a "blocked / HF_TOKEN not set" box | technical detail and evaluation status collapsed by default under a neutral line |
| Two search boxes on the home page | header search hidden on `/` |
| Stray black "N" circle | Next dev indicator disabled |
| Hatched boxes unexplained | captions "no sentence last year / this year" |
| "worth reading" implied judgment | reworded to "whose wording moved the most" |

### Judge round 2 (real NVDA screenshots)

Verdict: **6.5 / 10** (round 1 was 6/10 on fixture screens). The judge's 5-second read of the NVIDIA page:
"NVIDIA changed a handful of its risk factors, and a regulatory one moved from 'could happen' to 'has
happened'"; what was missing above the fold was the word "export", China and the $4.5 billion charge, because
the headline was truncated and the lead quote began "Such requests". No buy/sell language, probabilities or
"riskier" anywhere; the "Wording change: High 100" pills still read like a score to the judge.

Status of the round-1 points as the judge saw them: fixed: counts agree, "!" glyph, methodology collapsed, one
search box, "N" circle gone; partly: level pill wording, "New figure disclosed" ("5 countries" came from "D:5"),
citation chips (FY tag still monospace), hatched boxes (labelled but a wall of them on long changes); not fixed
in the data: double counting (the file's `score_breakdown` was computed by rubric 1.0.0) and two cards for one
risk; cannot tell: fixture weights, "Eastland".

New points and responses:

| Judge's point | Response |
|---|---|
| Preamble "The following risk factors should be considered…" shown as a new risk and a top change | old-pipeline data; J1 (segment 0.2.x) drops it on re-run. Not special-cased |
| One risk factor takes two of five cards | UI groups highlights by risk factor: one card, several facts (contract unchanged) |
| Headlines cut to five words lose the meaning | a truncated fallback title is never shown when the full heading fits: the UI shows the heading (two lines) until the LLM titles arrive with the re-run |
| Methodology says AI is used in "two narrow places" while AI checks add points | copy now names three places and states the no-double-counting rule; the rubric points stay (deterministic, published, cited) |
| "Not in last year's filing" on a new sentence inside an existing risk | kind-aware captions ("This figure did not appear in last year's version", "No matching sentence last year") |
| Broken sentences ("… or ." + "z ECCNs"); "AI Diffusion IFR in", "D:4"; "5 countries" from "D:5" | splitter never starts a sentence with a lowercase letter (segment 0.2.1); letter-code numbers are not quantities (signals 0.2.1); entity cleanup was J2. All need the re-run to reach the file |
| Counterparty card quotes only the heading; summary leads with the reassuring sentence | new-risk cards now quote the first body sentence ("We have entered … financial guarantees … asked to offer financing arrangements"); the AI bullets are the model's validated output and are regenerated on re-run |
| Lead Potential → Actual example is the weakest one | self-contained sentences rank before "Such…/This…" openers; the SAMR "preliminary finding" pair needs the status-change detector (J3) on re-run |
| 13,000 px page with a wall of striped boxes | side-by-side view collapses a run of one-sided sentences into one row with a single placeholder |
| Green "New risk" / red "Scaled back" with arrows read as good/bad | change-type labels are neutral and glyph-free; the inline diff keeps its colors |
| "Change level" vs "Wording change"; "This is the first risk factor"; "(for technical judges)"; level on a new risk | first three reworded; the level stays on new risks (one ranking scale) |
| Total "lands on exactly 100, nothing says whether that is a cap" | total line says "capped at 100 (points add to N)" when it is |
| Companies below the fold at 1280×720 on home | left as is (the judge called it acceptable) |

Verification after the round-2 fixes: 137 tests, ruff clean, web typecheck/lint/build clean, FIXTUR cached vs
`--no-cache` byte-identical, no horizontal scroll at 1024/1280/1440 on all five pages, no page errors. At
1440×900 the whole first card (two facts) is above the fold; at 1280×720 the first fact of it is, with the second
fact starting at the fold. The frontend subagent questioned the counterparty summary bullet "The company has not
entered into any financing arrangements"; its cited sentence is literally "We have not entered into any financing
arrangements." (0001045810-26-000021:17:2), so the claim stands.

Demo advice recorded from the judge: open with the counterparty new risk (card → detail → the financial-guarantee
sentence), then the export-controls China section with the $4.5 billion line and a citation click; do not
scroll "How this was scored" on the old file until the re-run replaces it.

## 11. Shared report library (Databricks session, D1–D7)

Goal: any teammate's `uv run python -m pipeline.run AAPL` lands in one shared library that every running copy of
the app reads, with local files still the fast path and the app fully working without Databricks.

**Ran against mocks only.** This sandbox has no Databricks workspace or credentials, so every component was built
and tested against a fake SDK client (Files API + Statement Execution) and simulated Delta tables. Nothing was
uploaded anywhere. What the team must do once (about ten minutes, one person):

1. Databricks workspace with Unity Catalog; create catalog `riskdiff` (or set `DATABRICKS_CATALOG`); create a SQL
   warehouse (serverless) and copy its id.
2. Personal access token → `.env`: `DATABRICKS_HOST=https://<workspace host>`, `DATABRICKS_TOKEN`,
   `DATABRICKS_WAREHOUSE_ID`.
3. `uv run python scripts/databricks_setup.py` (twice, to see the second run is a no-op).
4. `uv run python scripts/sync_to_databricks.py` (uploads NVDA and SF), then the delete-local-and-reload check:
   move `data/published/NVDA_2025_2026.json` aside, start the API, open `/c/NVDA`; the file reappears byte-identical
   (`cmp`) and the page loads; `GET /store/health` → `{"remote": "ok"}`; `/trends` shows 2 companies.
5. Every other teammate: their own token in `.env`; nothing else.

If a step fails, the error names the typed store error (`store_auth`, `store_unavailable`, `store_query`,
`store_integrity`) and never the token.

**What was built**

| Piece | Where |
|---|---|
| Client wrapper (upload/download/list/execute/health, timeouts, 2 retries, typed errors) | `pipeline/store/databricks.py` |
| Table definitions, row builders, parameterized MERGE/flip/list/trends SQL | `pipeline/store/tables.py` |
| Publish step (upload → MERGE reports, changes, highlights → flip current) | `pipeline/store/publisher.py`, hooked in `pipeline/run.py` (`--no-remote`, exit 3 on remote-only failure) |
| Setup + sync scripts | `scripts/databricks_setup.py`, `scripts/sync_to_databricks.py` |
| API: library merge, read-through pull with verification, `/store/health`, `/trends` | `api/main.py` |
| Settings + host validation + single-host allowlist | `pipeline/config.py`, `pipeline/http.py` |
| Frontend: library labels, publisher/date, store indicator, Trends page | `web/` (see D5/D6 below) |
| Tests (fake SDK, simulated tables, fake store for the API) | `tests/test_store.py`, `tests/test_store_publish.py`, `tests/test_api_store.py` |

**Invariants and the session's additional rules, checked**

* Only one host joins the allowlist: the hostname of `DATABRICKS_HOST`, after validation (https, no path, known
  Databricks domain); `check_host` still refuses every other host, including other workspaces on the same domain
  (test `test_allowlist_admits_only_the_configured_workspace`).
* All SQL is parameterized (`:name` markers, typed parameters); identifiers are code constants plus the validated,
  back-quoted catalog/schema/volume names; rows travel as one JSON parameter. No user input reaches SQL (tickers
  are validated before any lookup and are never interpolated).
* The Volume file is the exact local bytes (`upload_report` sends `path.read_bytes()`; the publisher never
  re-serializes); tables are derived and rebuildable with the sync script.
* A downloaded report is used only after contract validation, `analysis_id` recomputation from its own fields
  and the content-hash check against the `reports` row (tests cover a tampered file, a forged provenance, a
  wrong id, a fixture and a path outside the Volume).
* Databricks is never required: with no variables set `/store/health` says `disabled` and everything is local;
  with it configured but unreachable, local reports load, the list refresh fails in the background and the
  footer says offline; a local file is always served without touching the store (test
  `test_local_hit_never_touches_the_store`).
* Credentials: read only in `pipeline/config.py` (server side), never logged (`redacted()` prints presence only),
  never in `web/` (`grep DATABRICKS web/src` is empty), never in git (`.env` is ignored; `.env.example` has
  placeholders).
* The published JSON contract did not change; `CompanyCard` is unchanged and the API adds the library fields as
  extra keys.
* Determinism: the remote step runs after the local publish and adds nothing to the JSON (`published_at`
  exists only in the table), so the byte-identical/identical-`analysis_id` guarantee is untouched.

**Measured here with the real SDK against an unreachable workspace** (`DATABRICKS_HOST` set to a non-existent
Azure workspace, local NVDA on disk): `/store/health` → `offline` at its 5 s cap; `/companies` → local NVDA in
1.0 s; `/comparison/NVDA` → 200 in 47 ms (never touches the store); after the background refresh recorded the
failure, `/comparison/ACME` (a miss) → 404 in 3 ms and `/trends` → `available: false, remote: offline` in 2 ms;
the token never appears in the log.

**Next smallest safe task:** run the five steps above against a real workspace and record the output in this
section; then add a nightly `scripts/sync_to_databricks.py` run (or a `--rebuild-tables` flag that re-derives the
three tables from the Volume) so the tables can be regenerated after a schema change.

## 12. Design system and Trends session (UX1–UX13)

Goal: nothing looks templated, color means direction of disclosure change, the highlighter is the one
visual idea, and Trends loads on the first visit with real cross-company content. Verdicts from the outside
reviews are pasted at the end of this section.

### Amazon: "0 meaningful changes" (Task 8)

**Not verifiable in this sandbox.** There is no AMZN report in `data/published/`, no stage cache, and
sec.gov is not reachable here, so neither the extracted Item 1A texts nor the block matches could be
inspected, and nothing was special-cased. What the result would mean, and how to settle it on a machine
with the report (about five minutes):

1. Block counts. `uv run python -m pipeline.run AMZN --until-stage 2 -v` prints "old: N risk blocks, new: M
   risk blocks". Amazon's Item 1A has roughly 30 bold-headed risks under three group headings
   ("Business and Industry Risks", "Operating Risks", "Legal and Regulatory Risks"). Fewer than about 20
   blocks on either side means the segmenter missed headings (Amazon's headings are bold lead sentences
   that end in a period; `segment.split_lead_heading` handles that shape, so a miss would be a styling
   variant worth a test). One or two blocks means extraction stopped early (check `END_RE` against the
   filing's "Item 1B" heading).
2. Extraction size. In the stage-1 cache (`data/cache/stages/extract/*.json`, field `text`), both years
   should be about 9,000 to 12,000 words. A much smaller new-year text means a boundary problem.
3. Matches. In the published JSON, `summary.matched_pairs` should be close to the block count, and the
   per-change `similarity` values high (above 0.9) for a stable filing. Many unmatched blocks with
   similar headings would point at the matcher, not at Amazon.
4. The classification itself. With `pipeline/diff.py`'s rules a matched block is "largely unchanged" when
   both the added-word share and the removed-word share are under 5%, or when the edits are small enough
   not to reach the expanded (15% with a 10-point net), reduced, or reworded (30% total) thresholds.
   Amazon edits its risk factors lightly most years, so every block landing under those thresholds is
   plausible. To confirm it is real: sort the changes by `stats.added_word_count` and read the two largest;
   if each shows a handful of inserted words in otherwise identical sentences, record those two sentence
   pairs here as the evidence. If instead a block shows whole new paragraphs while its `change_type` is
   `largely_unchanged`, that is a diff-stage bug: open an issue with the block id and the two texts.

The home-page card already states the case plainly ("No meaningful changes this year, across N risk
factors") instead of showing an error.

### Files by task

| Task | Files |
|------|-------|
| UX1 | `DESIGN.md`, `CLAUDE.md` (one line), `web/src/app/globals.css`, `web/src/app/layout.tsx`, `web/src/components/Wordmark.tsx` |
| UX2 | every page and component under `web/src/` (helper purge, sentence case, no dots/arrows/glyphs), `web/src/lib/copy.ts` |
| UX3 | `web/src/components/ui.tsx` (`ChangeBadge`, `ChangeLevel`, `Legend`), `web/src/lib/vocabulary.ts` (tones, `levelSegments`, `LEGEND`) |
| UX4 | `web/src/components/HighlightCard.tsx`, `MarkedText.tsx`, `Quote.tsx`, `web/src/lib/diffDisplay.ts`, `web/src/lib/sentences.ts` |
| UX5 | `web/src/components/Overview.tsx`, `ChangeList.tsx`, `web/src/lib/names.ts`, `web/src/lib/vocabulary.ts` (`displayTitle`, `shortTitleFromHeading`) |
| UX6 | `web/src/app/c/[ticker]/[changeId]/page.tsx`, `web/src/components/ChangeDetail.tsx`, `ChangePanels.tsx`, `citations.tsx` |
| UX7 | `web/src/app/(home)/page.tsx`, `web/src/components/CompanyGrid.tsx`, `web/src/lib/hero.ts`, `web/src/lib/data.ts` |
| UX8 | `REPORT.md` §12 (diagnostic recipe; no code, see root causes) |
| T9 | `api/main.py` (`StoreState`, `TrendsService`, `/store/health`, `/trends`), `pipeline/store/databricks.py`, `tests/test_api_store.py` |
| T10 | `pipeline/trends/{derive,schema,aggregate}.py`, `pipeline/trends/topics.yml`, `data/derived/*.trends.json`, `tests/test_trends.py` |
| T11 | `pipeline/store/tables.py` (`topic_mentions`, `category_activity`, trends queries, span columns), `pipeline/store/publisher.py`, `scripts/derive_trends.py`, `scripts/databricks_setup.py` |
| UX12 | `web/src/app/trends/page.tsx`, `web/src/app/api/trends/route.ts`, `web/src/components/TrendsView.tsx`, `web/src/lib/trends.ts`, `web/src/lib/api.ts`, `web/src/lib/types.ts` |
| UX13 | `web/src/lib/__tests__/*.test.ts`, `tests/test_web_units.py`, `web/package.json` (`test:unit`), screenshots in the session scratchpad, this section |

### Root causes

**Trends cold start (T9, reproduced by the subagent before fixing; details in DECISIONS.md D-021).**
`/store/health` ran the first Databricks check synchronously under a 5 s wait and reported the timeout as
`offline`, so while the client was still being built or the warehouse was starting, "not finished" was
shown as "not connected"; `/trends` then had no result to fall back on. The fix separates `connecting`
from `offline`, serves the last good result (memory, then `data/cache/trends/trends.json`) while a
refresh runs in the background, and computes from local reports when there is no remote result yet. The
page shows a skeleton and polls for `connecting`, and "not connected" only for `disabled` or `offline`
with nothing local.

**Amazon "0 meaningful changes" (UX8).** Not reproducible here: no AMZN report, no stage cache, no SEC
access. The recipe above says how to settle it in five minutes with the report in hand and what each
outcome means. Nothing was special-cased.

### Design choices and token changes

- Tokens are the brief's values except two contrast adjustments recorded in DESIGN.md: muted text
  `#6B7A90` → `#627187` (was 4.1:1 on the page color) and Scaled back text `#B5541C` → `#A64B18`
  (4.3:1 on its tint). A mid gray `#8A95A8` and a mid orange `#D08A5A` were added for fills only
  (bars, meters, heatmap), because the strong orange and the ink fill made "Scaled back" and
  "Major update" bars read as "Dropped risk" and "New risk".
- The highlighter is a `linear-gradient(transparent 35%, #FFD95A 35%)` stroke on `<mark class="hl">`;
  removed words are `<del class="strike">` in `#B5541C`. Both come from the diff spans; nothing else on
  the site is yellow except the wordmark.
- The home hero is the top Potential → Actual highlight across local reports, chosen by
  `pickHero` (kind, then score, ticker, position); never a hardcoded company.
- Company display names come from `names.ts` (title case, suffixes dropped, exceptions map); the official
  SEC name stays in the audit trail.
- Two deliberate departures from the brief after the reviews, with reasons in D-023: the wording-change
  meter is ink only, and the amber badge carries a ring.

### Invariants and the brief's additional rules

Confirmed on the final build: every quote is verbatim (`sentence_index` text, visible ellipsis and
"Show full sentence" when trimmed); the highlighter and strike are drawn only over diff-identified spans;
no company, sentence or number is hardcoded (hero, topics and examples come from the reports); trend
topics are deterministic (`topics.yml`, `TOPICS_VERSION`) and every mention keeps ticker, change id,
sentence id and verbatim text with a link to the change; wording says "newly added" and "most widespread
new disclosures", never "impact", "biggest risk" or "riskier"; all SQL is parameterized (the store tests
assert no literal values); the published contract and `analysis_id` are unchanged (code fingerprint
`e94330fb…` before and after; FIXTUR cached vs `--no-cache` byte-identical); nothing under 14px, no
horizontal scroll at 1280 or 1440, visible focus rings, color never the only carrier (badges carry words,
meters carry aria-labels, heatmap cells carry their numbers), reduced motion disables every animation.

### Top shared topics (real data, two reports in the library)

No topic was newly added by more than one company; the page says so. Ranked by companies, then new
sentences:

| Topic | Source | Companies | New sentences |
|-------|--------|-----------|---------------|
| Counterparty and credit risk | lexicon | 1 (NVDA) | 4 |
| AI regulation | lexicon | 1 (SF) | 1 |
| Biden Administration | name | 1 (NVDA) | 1 |
| DOL | name | 1 (SF) | 1 |
| Government shutdown | lexicon | 1 (SF) | 1 |

One Potential → Actual pair in the library (NVDA export controls). Change mix: NVDA 2 new, 2 expanded,
1 major update, 1 scaled back; SF 5 major updates.

### Review round 1 (before fixes)

**Reverse-squint (blind, screenshots only): 6/10 for "does not look templated".** Strongest idea: the
highlighter on serif filing text against a sans UI, carried into the wordmark; "the home page leads with a
real two-column diff specimen instead of feature cards. That is the best decision in the product."
Tells: the same rounded white card for every highlight (boxes inside a box on the first card), pill tags on
everything, signal-strength meter glyph, the same ▸ disclosure pattern three times, the lavender-free but
still boxed AI summary, the four-column methodology, gray helper sentences, ten identical half-full bars on
Trends, "Ink" in the legend while the swatch was gray, "See the change" vs "See the full change", ASCII
"->" in score lines, Home active on company pages, the Trends potential-to-actual quote without marks.
Typography: company H1 underweighted against its lede; last-year gray serif with thin strike close to
illegible in long runs. Color: yellow collides with amber.

**Judge (BNY MD, 90 seconds).** Understood the product and the NVIDIA story (export controls, the
$4.5 billion H20 charge, counterparty risk, Groq). Confusion: the hero showed only "Export" highlighted so
the "actual" event was invisible; the Trends potential-to-actual pair had no marks; badges differ between
cards and list ("Potential → Actual" vs "Major update"); "Newly named" read as "renamed"; the preamble
paragraph counted as a New risk; levels looked backwards relative to sentence counts; three yellows;
unlabeled heatmap swatches; "Topics several companies newly added" followed by "No topic was…"; names
mixed with themes; "Computed from reports on this computer". Nothing read as a rating or advice.

**Fixed after round 1:** marks on the Trends potential-to-actual pair (spans carried through the trend
facts and the store); hero and cards keep the marked words inside the trim window so "resulting in excess
inventory… H20" shows; ruled sections instead of nested cards; change-type badge beside the fact badge on
every card so cards and list agree; "Newly named: Groq" with the name; equal-square meter; legend swatches
match the fills ("Gray: rewritten both ways") and include the amber tint and a highlighter sample;
labeled heatmap legend with a note on double-tagged risk factors; section retitled "New topics in the
library" with bars hidden when every count is one; "a name" / "a phrase" tags; "See the full change"
everywhere; arrows in score lines; Home active only on "/"; 600-weight page titles; merged one-sided runs
full width; the level note no longer speaks of "points"; fewer helper sentences.

### Review round 2 (after fixes)

**Reverse-squint: 6/10, unchanged.** "Mostly not" template-built; remaining tells: the stock hero shape
with an empty right half, the two library cards with an empty third slot, the four-step and
three-column methodology, helper sentences, repeated "Wording change" and "Edited" labels, the ▸ triangles,
and three data glitches read as unfinished: "New risk" twice, the preamble as a top change, a removed
fragment starting mid-word. The hero highlighter looked misaligned (the screenshot caught the 650 ms
stroke animation half drawn). Ranked fixes 1–10: hero highlighter; keep the two-column grid for
one-sided runs; group runs under one header; remove the doubled badge and the preamble; a distinct color
for Potential → Actual; an ink-only meter; a column header for the level; drop the repeated source line
and "Edited" labels; a dense list instead of library cards; one bold H1 style.

**Judge: 7/10 for "would I trust this in front of a client".** "Verbatim quotes, footnoted AI points and
the 'Open in SEC filing' link on every change make it defensible. But the doubled 'New risk' badge and
the boilerplate intro ranked as a top NVIDIA change are exactly the kind of slip a client would catch."
Praise: "the old and new sentence side by side with a highlighter, under 'Potential → Actual' and
'$4.5 billion', gave me the H20 story in ten seconds, which is the whole pitch." Fixes asked: filter the
boilerplate and the doubled badge; harmonize amber vs highlighter and label the meter as wording-only
where it appears. Nothing read as a rating, prediction or advice.

**Fixed after round 2 (verified on screenshots, not re-reviewed; the brief allows one re-run):** one
badge per fact; a ring on the amber badge; ink-only meter; company title at 44px; the badge detail on
library cards; no repeated source line under cards; quieter labels inside merged runs; "Source: the local
report library"; "a name" tags; a line relating heatmap cells to the change-mix bars; a 450 ms stroke
with a 120 ms delay, and the screenshot script now waits for animations.

**Not fixable here, needs the team's NVDA re-run (data):** the preamble ranked as a New risk (the
segmenter fix is in the pipeline already, `segment` 0.2.1), entity noise ("Biden Administration", "DOL",
"AI Diffusion IFR in"), the "z ECCNs" fragment, and the LLM short titles ("Defects in our products have
caused"). **Kept as the brief asked:** library cards, the orange family, "Major update", the methodology
columns (D-023).

### Commands (backfill, rebuild)

```bash
uv run python scripts/derive_trends.py --local-only   # data/derived/{analysis_id}.trends.json for every local report
uv run python scripts/derive_trends.py                # same, plus MERGE into topic_mentions / category_activity when Databricks is configured
uv run python scripts/databricks_setup.py             # tables, Volume; adds the highlights span columns to an existing table
uv run python scripts/sync_to_databricks.py           # upload local reports (idempotent)
rm -f data/cache/trends/trends.json                   # drop the /trends disk cache (it also invalidates itself on TRENDS_VERSION)
cd web && npm run test:unit && npm run typecheck && npm run lint && npm run build
```

### Next smallest safe task

Re-run NVDA on a machine with SEC access (`uv run python -m pipeline.run NVDA --force`), publish, and
re-derive trends. That single run removes the three data findings both reviewers flagged (preamble as a
New risk, entity noise, the mid-word fragment) without touching any code.

## 13. Integrity session (I1–I4)

Goal: every quote visibly contains its evidence, every before/after pair is a true pair, counts agree
everywhere, no page crashes, and a checker proves it. This sandbox holds only the NVDA and SF reports
and has no SEC, Hugging Face or Databricks access, so the AAPL/AMZN/GOOGL/CRWD instances from the live
walkthrough were proven as mechanisms in code and on NVDA/SF, never inspected live.

### 1. Violations before → after, by check id

| Check | Before | After | Remaining classification |
|-------|-------:|------:|--------------------------|
| SNIP-TOPIC | 1 | 0 | |
| SNIP-CHANGE | 0 | 0 | |
| TOPIC-NEW | 20 | 0 | |
| TOPIC-MEANINGFUL | 25 | 0 | |
| PAIR | 0 | 0 | |
| CASE | 31 | 21 | all stale data (old diff in the two published files) |
| YEARS | 0 | 0 | |
| COUNTS | 0 | 0 | |
| TITLES | 50 | 0 | |
| PREAMBLE | 1 | 1 | stale data (NVDA intro paragraph; segment 0.2.2 skips it) |
| ENTITY | 5 | 6 | all stale data (old signals in the two files; current code drops them) |
| STALE | 2 | 2 | NVDA (re-run from stage 2), SF (from stage 5) |
| HEATMAP | 0 | 0 | |
| **Total** | **135** | **30** | **30 stale data, 0 code, 0 data** |

Baseline: `INTEGRITY_REPORT.before.md` / `data/integrity/before.json`. Final: `INTEGRITY_REPORT.md` /
`data/integrity/latest.json` (copy in `after.json`). The checker exits 1 while the 30 stale findings
remain; they clear with the re-run below, not with code.

### 2. Root causes (one line each, with the proving example)

- Topics counted on words that were not inserted: `topic_mentions` scanned whole modified sentences.
  NVDA `a4156a06454f6dfd` sentence `0001045810-26-000021:21:7`, phrase "CSP market" (only "CSP" inserted).
- Topics counted on essentially unchanged risk factors (the "Amazon: no meaningful changes, yet newly
  added Tariffs" mechanism): NVDA `472606c9d458f2e9` sentence `…21:15:15` "…agreement with OpenAI." in a
  `largely_unchanged` change.
- Case-only highlights: `word_spans` compared tokens exactly. NVDA `a4156a06454f6dfd`,
  `0001045810-25-000023:19:95` → `0001045810-26-000021:21:91`: "Excessive or shifting export" deleted,
  "Export" inserted.
- Unrelated before/after pairs (the Alphabet symptom): signals paired an added sentence with the best
  lexically overlapping hedged old sentence at ratio ≥ 0.25 counting function words; proven by a
  synthetic boilerplate pair and removed; the aligned NVDA antitrust pair `…19:41` → `…21:41` still fires.
- Fragment titles: the fallback cut the heading at 8 words plus "…" and the frontend's clause cutter
  then produced "We are subject to complex laws"; 50 of 57 titles. Now the longest clause of 4–10 words.
- Entity noise still emitted by current code: "Biden Administration", "Trump Administration"
  (NVDA `…21:71`), "SEC" (SF `61ffb76925cf3bc2`); "AI Diffusion IFR in" and "D:4" were already stale.
- Trends crash: `ActualItem` reduced over `old_spans` without a default; duplicate heatmap key: the
  catch-all column reused the real category key `other`.
- Snippets cut before their evidence: prefix trimming (SF "Gramm-Leach-Bliley Act" shown without the
  term; the live Apple/Amazon "tariff" and NVIDIA changed-words cases are the same rule).
- Counts that disagree (CrowdStrike): the local Trends path dropped a company whose facts failed to
  derive, and the Databricks path built its company set from store rows while `/companies` merges local
  and remote; both closed, the live instance not inspected.
- Fiscal-year labels (CrowdStrike "FY2024 and FY2026"): no defect found in selection or labeling on
  synthetic January fiscal-year cases; one real defect fixed on the way (a prior-year
  `DocumentFiscalYearFocus` fact listed first won). Needs the real submissions JSON and filings.

### 3. Files changed, by task

- I1: `scripts/check_integrity.py`, `tests/test_integrity_checker.py`, `tests/fixtures/snippet_vectors.json`,
  `pipeline/schema.py` + `pipeline/stages_final.py` (`stage_versions` recorded), `contract/`,
  `web/src/types/comparison.ts`, `INTEGRITY_REPORT.before.md`, `data/integrity/before.json`.
- I2a (web): `web/src/lib/{snippet,diffDisplay,trends,vocabulary}.ts`,
  `web/src/components/{SectionBoundary,MarkedText,Quote,HighlightCard,ChangeDetail,TrendsView,ChangeList,CompanyGrid}.tsx`,
  the overview and change pages, `web/src/lib/__tests__/*`.
- I2b (trends/API): `pipeline/trends/{derive,aggregate,schema}.py`, `api/main.py`,
  `pipeline/store/{tables,publisher}.py`, `scripts/derive_trends.py`, `tests/test_trends_rules.py`,
  `tests/test_trends.py`, `tests/test_api_store.py`, `data/derived/*.trends.json`.
- I2c (pipeline): `pipeline/{diff,signals,highlights,segment,sec_fetch,config}.py`,
  `tests/test_{diff,signals,highlights}.py`, `tests/test_integrity_pipeline.py`.
- I3: `scripts/refresh_stale.py`, `scripts/migrate_published.py`, `data/published/*.json` (titles,
  highlights), `data/derived/*.trends.json`.
- I4: `web/e2e/smoke.spec.ts`, `web/playwright.config.ts`, `web/package.json` (`test:e2e`,
  `@playwright/test` 1.63.0), `INTEGRITY_REPORT.md`, `data/integrity/latest.json`, `DECISIONS.md`
  (D-024, D-025), `PROGRESS.md`, this section.

### 4. Reports re-run

None could be re-run here (no sec.gov, no Hugging Face). `scripts/refresh_stale.py` is ready and
tested with a fake runner; on the team's machine:

```bash
uv run python scripts/refresh_stale.py --check        # NVDA from stage 2, SF from stage 5, then the rest by age
uv run python scripts/check_integrity.py --api http://127.0.0.1:8000
```

What did change locally: NVDA and SF had their presentation fields refreshed by
`scripts/migrate_published.py` (short titles and highlights; analysis ids `13acfdfe…` and `c07038f7…`
unchanged). Their derived trend facts were regenerated under derivation `1.2.2+topics1`.

### 5. Remaining exceptions and why they are acceptable for now

No accepted exceptions. The 30 remaining findings are stale data in the two old published files
(21 case-only spans, the intro paragraph, 6 entity values, 2 version records); every one disappears
with the re-run above, and the checker will prove it. The live Trends source line and company logos
added by the team's concurrent push were merged without conflict and are outside this brief.

### 6. NVDA highlights now shown

1. Potential → Actual: "We are subject to complex laws, rules, regulations" (export controls, "may → experienced").
2. New risk: "Commercial arrangements expose us to counterparty risks".
3. Newly named: Groq, under "Failure to meet the evolving needs of our industry".
4. New risk: "The following risk factors" (the Item 1A intro, stale; the re-run removes it).
5. New figure disclosed: $4.5 billion, under "We are subject to complex laws, rules, regulations".

The China antitrust "preliminary finding" pair does NOT appear yet: the published NVDA file carries
signals from stage 6 version 0.1.x, before the status-change detector existed, and the migration only
re-selects highlights from the file's own signals. The pair is aligned (`…19:41` → `…21:41`) and the
current detector fires on it in `tests/test_integrity_pipeline.py`, so the re-run will surface it.

### 7. Invariants confirmed

- SEC text is the only source: every quote on every page is the verbatim sentence text; windows are
  exact substrings with visible ellipses; the smoke test and the checker read the same files.
- The LLM never decides what changed or the score: untouched; the LLM title is now validated harder.
- Citation validator unchanged and still on every LLM output.
- No probability or advice language added anywhere (grep of the new copy; the footer disclaimer only).
- Nothing fabricated: the two reports keep their analyses; only derived presentation fields moved.
- Determinism: FIXTUR cached vs `--no-cache` byte-identical on the final tree; `stage_versions`
  recorded; same inputs + same versions → same `analysis_id`.
- Contract: changed only through `pipeline/schema.py` (`stage_versions`, ten-word titles) with regenerated
  JSON Schema and TS types.
- SEC fair access, outbound allowlist, ticker validation, no raw HTML, secrets only via env, CORS/one
  analysis/timeouts, pinned dependencies (one added, exact), no shell from user input: unchanged; the
  refresh script passes validated tickers as argv.
- No company, filing or sentence is special-cased in any rule.

### 8. Next smallest safe task

Run `uv run python scripts/refresh_stale.py --check` on a machine with SEC and Hugging Face access,
then the checker: expected result zero findings, the intro row gone, the China antitrust pair shown.
After that, give `Quote` and the Trends pair an optional anchor on the signal's own words
(`detail` "may → experienced") so a potential-to-actual window centers on the "actual" span rather
than the first changed word.
