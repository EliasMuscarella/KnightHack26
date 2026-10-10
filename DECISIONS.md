# DECISIONS

Decisions made without a human in the loop. Newest at the bottom. Each entry: context,
decision, alternatives considered, how to reverse.

## D-001 Python 3.12 managed by uv
- Context: machine has 3.11/3.12/3.13. Wheel availability (torch, spaCy, scipy) is safest on 3.12.
- Decision: `requires-python = ">=3.12,<3.13"`, `.python-version = 3.12`, `uv.lock` pins exact versions.
- Reverse: widen the range in `pyproject.toml` and re-lock.

## D-002 Dependency pinning strategy
- Decision: compatible-release specifiers (`~=`) in `pyproject.toml`; exact pins live in `uv.lock`
  (Python) and `web/package-lock.json` (Node). `diff-match-patch` is pinned exactly.

## D-003 No `.env` present; secrets are never invented
- Context: the brief says if `SEC_USER_AGENT` is missing, stop SEC fetching and do not invent an email.
- Decision: stage 0 raises `ConfigError` with a clear message when `SEC_USER_AGENT` is unset.
  All downstream work is built against a labeled FIXTURE filing pair. See PROGRESS.md.

## D-004 Network denies SEC + Hugging Face in this environment
- Context: the egress proxy returns 403 for `*.sec.gov` and `huggingface.co`.
- Decision: do not route around the policy (no mirrors, no archives, no third-party copies of
  filings: provenance would not be the SEC). Implement the real code paths, unit-test them with
  mocked HTTP, and document the blocker. Embedding falls back to a deterministic local lexical
  embedder (recorded in `model_ids`, so `analysis_id` differs from a bge-m3 run, as it should).

## D-005 Fixture filing pair for end-to-end development
- Context: no real filings can be fetched here. The pipeline still needs end-to-end exercise.
- Decision: `contract/fixtures/make_fixture_filings.py` generates two synthetic 10-K-like HTML files
  (structure imitates inline-XBRL filings; every risk heading starts with "FIXTURE:"). Ticker `FIXTUR`
  runs them through the real stages; output goes to `data/scratch/` and the publisher refuses to write
  `is_fixture=True` documents into `data/published/`.

## D-006 Sentence ids include the heading as sentence 0
- Each risk block's heading is its sentence 0 (`is_heading=True` in `sentence_index`) so headings are citable.

## D-007 Change-type rules are text-ratio based, similarity secondary
- Dense and lexical similarities live on different scales, so `classify_change_type` decides mainly on
  added/removed word ratios; pair similarity only feeds rule 8. Rules are in the function docstring.

## D-008 Matching thresholds per backend (placeholders)
- dense (bge-m3): 0.62; lexical TF-IDF: 0.20 (second-best off-diagonal similarities on the fixture are <= 0.08).
  Recalibration against the golden set is Task 10 and is blocked until real filings are available.

## D-009 Category assignment is a hybrid
- A keyword lexicon (`signals.LEXICON`) always runs; when a dense embedder is available its cosine to
  17 prototype descriptions is averaged in 50/50. The method id is recorded in `model_ids.category_method`.

## D-010 Banned-language matching uses stems
- "invest" also blocks investing/investor/investment (but not "investigation"); buy/sell/recommend/
  guarantee/probability are matched as stems too. Conservative by design: a dropped true claim is cheaper
  than a displayed piece of investment language.

## D-011 Scoring weights (initial, documented in rubric.py / contract/rubric.json)
- new 30, removed 20, materially_reworded 20, expanded 15, reduced 10; hedge→actual 20 (+5 each, cap 30);
  new entities 4 each (cap 12); new quantities 5 each (cap 15); added-text ≥40% +5; semantic shift +5;
  rubric Q1 10, Q2 8, Q3 10, Q4 6. Total capped at 100. No weight is hidden; every line is cited.

## D-012 No timestamps in published JSON
- `generated_at` would break byte-identity, so it is omitted. Provenance is `analysis_id` + versions + model ids.

## D-013 Submissions JSON cached 24h, tickers 7 days, filings forever
- A filed document never changes; the filing index does. Within the TTL a second run makes zero network calls.

## D-014 Fiscal year from inline XBRL
- `fiscal_year` is read from `dei:DocumentFiscalYearFocus` in the primary document, falling back to the
  period-of-report year. Recorded per filing as `fiscal_year_source` in the stage-0 record.

## D-015 Review round 1 (pipeline): stricter invariants
- Lexical fallback is no longer silent: a non-fixture run fails with a clear ConfigError unless
  `RISKDIFF_ALLOW_LEXICAL=1` (or `RISKDIFF_EMBED_BACKEND=lexical`). Reason: a machine without
  Hugging Face access must not quietly replace a committed dense analysis with a lexical one.
- The citation validator drops a claim if ANY cited id is invalid (no silent repair), discards the
  rationale of every "no" answer (uncited free text), and drops claims whose numbers do not appear
  in the cited sentences. Banned stems now include more/less risky, safer, chance, odds, percent-of-risk.
- Stage 7 caches only the RAW model JSON; the validator runs on every load. Provider errors are not cached.
  When every change is cached for the configured model, the provider is not probed (offline replay).
- `analysis_id` now also hashes `code_fingerprint` (all stage versions, rubric export incl. weights
  and thresholds, validator version, diff/match params, rendered questions). The fingerprint is published.
- `publish` refuses to overwrite a published file whose `analysis_id` differs unless `--force`.
- API: the single-analysis lock is a threading.Lock held by the worker thread until the pipeline
  ends; timeouts/disconnects set a cancel event checked between stages; `/comparison` and the cached
  replay go through `load_published` (fixture data is never served).
- Extraction: footers with page numbers ("Acme | 2025 Form 10-K | 17"), "(continued)" headers and
  page-split paragraphs are handled; sections over 60k words fail loudly; headings sharing a
  paragraph with their first sentence are split off.
- Hedge→actual no longer fires on bare was/were/did/currently insertions.
- 10-K/A vs 10-K for the same period: the original wins.
- Known, not fixed: cross-machine floating-point differences in dense similarities (4-decimal
  rounding) are possible; byte-identity is guaranteed on one machine + one lockfile. Documented in REPORT.md.

## D-016 Review round 2 (pipeline): fixes and policy
- Three round-1 edits had silently failed to apply after code formatting (cancel check, `--force`,
  stage-5 cache keys). They are now in place with tests (`test_cancel_event_stops_between_stages`,
  `test_cli_force_flag_exists`, `test_same_text_under_other_accessions_does_not_hit_stale_cache`).
- Raw LLM output is treated like a raw filing: `--no-cache` does NOT re-query the provider; only
  `--refresh-llm` does, because temperature-0 output is not reproducible and would change a published
  file under the same `analysis_id`. `publish` now also refuses same-id/different-bytes without `--force`.
- Provider errors after retries abort the run (`llm_errors`) unless `RISKDIFF_ALLOW_PARTIAL_LLM=1`,
  so a transient failure never publishes "unavailable" rows under a reproducible id.
- When no change needs the LLM, the provider is not probed at all (`interpretation_status = skipped`).
- Hedge→actual ignores "could have disrupted"-style modal perfects (modal within 3 tokens before the marker).
- Banned language adds comparative paraphrases ("higher/greater/increased ... risk", "more vulnerable")
  and advice phrasing ("investors should ..."); reasons shown to users name a neutral category only.
- Page-split paragraphs are re-joined even when the continuation starts with a capital letter.
- `code_fingerprint` now hashes the source of `pipeline/*.py`, so any code change moves `analysis_id`.
- API: TrustedHostMiddleware (`RISKDIFF_API_HOSTS`), health exposes only the error type, published
  interpretation reasons never contain exception text; SEC-provided path segments are validated.
- Not done (documented): per-process SEC rate limiter, paginated-history cache without refresh,
  unpinned default embedding revision (`RISKDIFF_EMBED_REVISION`), worded numbers in the validator.

## D-017 Judge-ready session: pipeline decisions (J1–J5)
- The NVDA data referenced by the brief is not in the repo or the sandbox; all J-work is verified on synthetic
  cases that reproduce the quoted NVDA patterns, and the NVDA re-run is documented for the team's machine.
- J1: the Risk Factors Summary is skipped from its heading to the first *real* risk block (heading followed by a
  plain paragraph of >= 40 words); a group header right before that block is kept. Intro/boilerplate paragraphs
  with no pending heading are skipped instead of becoming "preamble" blocks. Filings with no emphasized headings
  therefore fail loudly (as before, they produced one useless block).
- J2: entity rules live in `signals.clean_entity` (strip stopwords/punctuation, drop codes like "D:4", drop
  mostly-numeric strings) and `merge_near_duplicates` (prefix match with >= 5 chars, shorter form kept).
- J3: `status_change` fires only when the old sentence has an in-progress/possible marker, the new sentence has a
  concluded marker not preceded by a modal, and the new sentence has fewer tentative markers than the old one.
  Unaligned removed/added sentences are paired by best lexical overlap (>= 0.25).
- J4: highlight ranking is kind priority > parent score > change id > position, max 2 per change, max 5 total;
  candidates come only from signals, change type and validated rubric "yes" answers. Short titles come from one
  temperature-0 batch call (raw output cached like other LLM output); a title is accepted only if it is <= 8
  words, passes the banned-language check and shares a content word with the heading, else the heading is
  truncated deterministically with a visible ellipsis. Without a provider every short title is the fallback.
- J5: `web/.env.development` no longer sets RISKDIFF_SHOW_FIXTURE; the fixture is opt-in everywhere.
