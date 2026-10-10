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

## D-018 Judge round 1 follow-ups (pipeline)
- Rubric Q1/Q2/Q3 no longer score when the deterministic twin signal (hedge→actual, new entities, new
  quantities) already produced a score line for the same change; Q4 has no twin and always scores when
  validated. One fact never counts twice. `RUBRIC_VERSION` 1.0.0 → 1.1.0, exported as
  `rubric_overlaps_signal` in `contract/rubric.json`.
- Highlight selection (one function, `highlights.select_highlights`) now runs over four evidence tiers:
  meaningful change + rule-based evidence, meaningful + AI-rubric-only, essentially-unchanged + rule-based,
  essentially-unchanged + AI-only. Within a tier the order is parent score (same order as the ranked list),
  then kind priority (new risk > dropped risk > potential→actual > figure > newly named), then change id,
  then position (dollar amounts before percentages before counts). This deviates from the brief's literal
  "kind priority, then parent score" because the judge read cards that did not follow the list order, and a
  card from a risk labelled "Essentially unchanged", as contradictions. Each tier takes one card per change
  first, then second cards of a different kind, so the top change can show two different facts (e.g. a
  potential→actual pair and a new dollar figure) without crowding out other risks.
- `diff.word_spans` treats whitespace, punctuation and a short list of function words as junk for anchoring
  (difflib `isjunk`), so "Westland and Eastland." vs "Westland, Eastland, and Ruritania." keeps "Eastland"
  on both sides. Diff stage 0.1.1 → 0.1.2.
- The fixture generator now computes `score_breakdown` with the real `score_change` (then prefixes labels and
  details with `FIXTURE:`), so the fixture can never disagree with the published weights again.
- `scripts/migrate_published.py` upgrades files published by an older pipeline to the current contract by
  deriving only presentation fields from the file's own content: `short_title` = deterministic truncation of
  the real heading (no LLM) and `highlights` = `select_highlights` over the file's own signals, change types
  and validated rubric answers; a note records the migration. Scores, sentences, citations and `analysis_id`
  are untouched, so the file still describes exactly the analysis that produced it. Segmentation, entity and
  status-change improvements (J1–J3) cannot be migrated; they need the documented re-run.

## D-019 Judge round 2 follow-ups
- `segment.split_sentences` merges a fragment that starts with a lowercase letter into the previous sentence
  (no sentence starts lowercase; pysbd broke "3A090.a, or .z ECCNs" at ".z"). Segment stage 0.2.0 → 0.2.1.
- `signals._quantities` ignores a number glued to a letter code ("D:5 countries" is an export-control country
  group, not a count). Signals stage 0.2.0 → 0.2.1.
- A new or dropped risk's highlight cites the first body sentence of the block (the card already shows the
  heading as its title; quoting the heading again told the reader nothing). Falls back to the heading sentence.
- Among hedge→actual candidates of one change, sentences that open with "Such", "This", "As a result"… rank
  after self-contained ones (they make poor standalone quotes). Among figures, dollar amounts come first and
  larger figures before smaller ones (the new value for "X -> Y" pairs).
- Frontend: one card per risk factor on "Biggest changes" (the contract's `highlights[]` is unchanged; the UI
  groups entries by change); a truncated fallback short title (ends with "…") is never shown when the full
  heading can be: the UI shows the heading instead. Change-type labels are neutral (no green/red, no arrows);
  only the inline diff keeps added/removed colors. The methodology page now names the yes/no rubric as the
  third place where AI is used and states the no-double-counting rule.
- Not changed on purpose: rubric points stay part of the score (the judge suggested removing them); they are
  deterministic given validated, cited answers, published in the weights table, and no longer overlap with the
  rule-based signals. The "Wording change: Medium 40" level stays on new risks so the ranking is one scale.
- Not fixable here (old-pipeline data in the published NVDA file; re-run required): the Item 1A preamble shown
  as a new risk, duplicate summary titles, "AI Diffusion IFR in"/"D:4" entities, the split ".z ECCNs"
  sentences, the double-counted rubric lines in `score_breakdown`, the LLM's choice of summary bullets.

## D-020 Shared report library (Databricks session)
- The published JSON remains the only source of truth; the Volume holds it byte-for-byte and the three Delta
  tables are a projection rebuilt at any time by `scripts/sync_to_databricks.py`.
- `analysis_id` hashes the analysis INPUTS (accessions, versions, code fingerprint, model ids, prompt), not the
  bytes, so "verify the analysis_id recomputes" is done from the file's own recorded fields (a file produced by
  an older code version still verifies; a forged provenance does not). Because that cannot detect an edit to
  the content, the `reports` row also stores `content_sha256` of the uploaded bytes and a download is rejected
  when the bytes do not match it.
- MERGEs are insert-if-absent only (rows of an analysis never change), rows travel as ONE JSON-text parameter
  decoded with `from_json`/`inline`, and `is_current` flips only the first time an analysis is seen. Re-publishing
  is a no-op, and syncing an older local file after a teammate published a newer analysis never flips current
  back. Flipping is per (ticker, old accession, new accession); the API shows the newest filing pair per ticker.
- The SDK's `Config` probes `<host>/.well-known/databricks-config` on construction (best-effort OAuth
  discovery a PAT never needs). Subclassing Config to skip it broke credential resolution (the SDK collects its
  attributes from the class itself), so the plain Config is used and the probe is bounded by the short SDK
  timeouts (15 s per request, 5 s retry budget); the client is built lazily, once, on first use in a background
  thread, so no request blocks on it. Measured against an unreachable host: `/store/health` answers "offline"
  within its 5 s cap, `/companies` in about 1 s with local reports, a local `/comparison` in under 50 ms, and a
  miss or `/trends` in milliseconds once the background refresh has recorded the failure.
- API read path: a local file is always served without consulting the store. The store's report list is
  refreshed in a background thread with a 60 s TTL (20 s after a failure); `/companies` waits at most 1 s for a
  cold refresh and the list is warmed at startup. When the store's current report for a ticker is a different
  analysis of the same (or newer) filing pair than the local file, the card shows the current one and the file
  is pulled to disk in the background, so the two converge within seconds; the local file is overwritten
  (that is what "becomes the new current report" means on every machine).
- `CompanyCard` in the contract is unchanged (the brief forbids contract changes); `/companies` adds
  `analysis_id`, `published_by`, `published_at` and `source` as extra keys and the web listing type declares
  them optionally.
- Host validation accepts `https://` URLs with no path on `.cloud.databricks.com`, `.gcp.databricks.com`,
  `.azuredatabricks.net`, `.databricks.azure.us`, `.databricks.azure.cn`; only that one hostname joins the
  allowlist. Catalog/schema/volume names must match `^[A-Za-z_][A-Za-z0-9_]{0,127}$` and are quoted.
- `published_by` is `git config user.name` of the publishing machine (fixed arguments, 3 s timeout) or
  "unknown". `published_at` is set at publish time in the table only; the JSON stays timestamp-free (D-012).
- No real workspace was available in this sandbox: everything ran against a fake SDK client and simulated
  tables; the real-workspace checklist is in REPORT.md.

## D-021 Trends backend (T9–T11)

**T9 cold-start root cause (observed, not assumed).** Reproduced against the pre-T9 code with the real
`DatabricksStore` and a fake SDK client that takes 1.5 s to build (the SDK's `Config` probe) and a
warehouse that is STARTING for 4 s (timeouts scaled 5x down): right after startup `/store/health` answered
`offline` and `/trends` answered `available: false, remote: offline`; a second call a few seconds later said
`ok` with data. Three mechanisms, all in `api/main.py`:
1. `/store/health` ran the check synchronously under a 5 s `wait_for` and mapped the TIMEOUT to "offline":
   while the first check was still building the client / waiting on the workspace, "not finished" was
   reported as "offline".
2. `/trends` computed three warehouse statements synchronously under a 20 s `wait_for`, with no previous
   result to fall back on; a cold warehouse (serverless start, or the startup list refresh queued ahead)
   exceeded it and the timeout was rendered as `available: false` ("not connected").
3. The abandoned worker thread kept running and cached its result when the warehouse came up, which is
   why a refresh "fixed" it. Nothing survived an API restart, so every restart repeated it.

**T9 fix.** Health is a non-blocking state machine with four states (`disabled` = no env vars;
`connecting` = first check pending / client being built / warehouse STARTING, STOPPED or STOPPING;
`ok`; `offline` = a check or statement failed after the store's retries, or the config is unusable).
Requests read the last known state and start a background check when it is older than 15 s (3 s while
connecting); `/store/health` waits at most 0.25 s for an in-flight check and returns
`{"remote", "warehouse_state"}`. A successful statement marks the store `ok`/RUNNING; a failed one marks
it `offline`. `/trends` is stale-while-revalidate: the last good remote result is served from memory or
`data/cache/trends/trends.json` (scoped by a hash of host+catalog+schema+warehouse, so another workspace's
cache is never shown), refreshed in the background after 60 s (20 s back-off after a failure), with
`computed_at` and `source`. With no remote result yet, the local aggregate is served (`source: "local"`);
with nothing local either and the store connecting, empty lists and `source: null` (the page retries).
Only a store that is already `ok` gets a 2 s wait for its very first remote result. A bad
`DATABRICKS_HOST` is now `offline` (it was `disabled`; "disabled" now strictly means "not configured").
`/trends` never returns 5xx: any unexpected error becomes an empty answer with `source: null`.

**T10 derived trend facts.**
- `pipeline/trends/derive.py` → `TrendFacts` (`pipeline/trends/schema.py`, NOT in the contract), written as
  `data/derived/{analysis_id}.trends.json` with `canonical_json`. Each file stores `derivation`
  (`TRENDS_VERSION` + `TOPICS_VERSION`) and `phrase_model` (spaCy id + version); a file whose values differ
  from the running code is re-derived and never trusted.
- **The post-publish hook is in `pipeline/store/publisher.publish_remote_if_enabled`, not in
  `pipeline/run.py`.** `score._pipeline_source_hash()` hashes every top-level `pipeline/*.py` into
  `code_fingerprint`. Editing `run.py` was measured to change the fingerprint (e94330… → efdbd9…), which
  would change every future `analysis_id`. `run.py` already calls `publish_remote_if_enabled` right after
  the local publish (never for the fixture), so derivation runs there, before the remote step, and its
  outcome is in the result's `trend_facts` key. A derivation failure is logged and never undoes the publish.
  `pipeline/trends/` and `pipeline/store/` are sub-packages and are not hashed.
- **`data/derived/` is committed** (it is not ignored; only `data/cache/` and `data/scratch/` are). The
  two files (~90 KB each) let a fresh clone serve `/trends` with no spaCy run. A test makes sure they equal a
  fresh derivation.
- **Topic rule ("newly added language").** A topic counts for a risk factor only when it appears in this
  year's added or modified sentences and NONE of its synonyms appears in that risk factor's `old_text`
  (whole word, case-insensitive). Terms match whole words only (`(?<!\w)…(?!\w)`), multi-word terms match
  across whitespace or a hyphen, and curly or straight apostrophes are both accepted. This applies to every
  change, including `largely_unchanged` ones: a single new sentence about tariffs is still new language.
- **Lexicon precision.** 31 topics in `topics.yml`. The brief's "duties" became `import/customs/
  countervailing/anti-dumping duties`, because "duties" alone matches "fiduciary duties" (SF is a broker).
  "visa(s)" became `work visa(s)`, `visa restrictions/programs/policies`, because "Visa" is also a card
  network. "strike(s)" became `strikes` and `labor strike(s)`, because "strike" is also a verb. Two topics
  were added: Digital assets and Bank capital rules.
- **Entities.** Each entity is normalized: quotes and a leading "the" are stripped, then the alias map is
  applied (U.S./US/USA → United States, USG → U.S. government, PRC → China, EU, UK). Next comes the
  pipeline's own `signals.clean_entity`, which drops old-pipeline artifacts such as "D:4", and corporate
  suffixes are removed ("Groq, Inc" → "Groq"). Entities on `ENTITY_STOPLIST` / `ENTITY_STOP_PATTERNS` are
  dropped (SEC, GAAP, FASB, IRS, United States, Nasdaq, NYSE, Congress, Exchange/Securities Act, quarters,
  fiscal years, months, years). The company's own name is excluded when the entity contains an
  *identifying* token of the name or the ticker; generic name words such as "Corp" or "Financial" do not
  count, so FINRA is not dropped for Stifel Financial. An entity that matches a lexicon synonym reinforces
  that topic (source `lexicon`) and must pass that topic's "absent last year" check.
- **Phrases.** spaCy `en_core_web_sm` noun chunks with NER disabled. Leading determiners, pronouns,
  numbers, stop words and generic adjectives ("new", "additional") are stripped, and the chunk must end on a
  noun. Phrases have 2–4 tokens. Only nouns are lemmatized: participles keep their surface form, because the
  model turns "binding" into "bind", and "data" stays "data" instead of the model's "datum". Phrases are
  dropped when they are on `PHRASE_STOPLIST`, are made only of `GENERIC_TOKENS`, contain a `BANNED_TOKENS`
  word, contain the company's own name, repeat an entity of the same risk factor, are covered by a lexicon
  topic, or appear in last year's text. Every phrase is stored; the API shows one only when 2+ companies
  share it.
- **Word counts partition the diff.** `added_words` counts wholly added sentences, `removed_words` wholly
  removed ones, and `modified_words` counts inserted plus deleted words inside rewritten pairs. Together
  they equal `stats.added_word_count + stats.removed_word_count`, which is tested on NVDA and SF.
- Potential→actual comes from the report's `potential_became_actual` highlights (verbatim sentences via
  `sentence_index`). The change mix comes from `summary.by_change_type`. The EDGAR primary-document URLs
  are stored so `/trends` can link quotes to the filing.
