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

## D-022 Design system session (UX1–UX12)
- Tokens follow the brief's starting values with two contrast adjustments, both measured with the WCAG
  formula: `ink-muted` #6B7A90 was 4.4:1 on white and 4.1:1 on the page color, below AA for 18px regular
  text, so it is #627187 (5.0:1 / 4.6:1); the Scaled back text #B5541C was 4.3:1 on its tint #FBEDE3, so it
  is #A64B18 (5.0:1). Everything else passes as given: ink on paper 14.9:1, secondary on paper 8.3:1, New
  risk 7.2:1, Expanded 5.2:1, Dropped risk 5.5:1, Major update 13.1:1, Potential became actual 6.5:1,
  signal 14.1:1, ink on the highlighter 11.7:1, white on accent 8.9:1. The strike color stays #B5541C
  (a decoration, not text).
- Type scale: Tailwind's `text-xs` is redefined as 14px (the floor), `text-sm` 15, `text-base` 17, `text-lg`
  22, `text-xl` 32, `text-2xl` 44; `text-3xl`+ alias the page-title size so no legacy class can exceed it.
  `font-semibold`/`font-bold` resolve to 500 and only `font-title` gives 600 (the home headline). Root font
  size stays 16px so the scale is explicit rather than inherited.
- Whole added sentences are drawn fully under the highlighter (every word is new, which is what the diff
  says); removed sentences are struck whole. On long diffs this is a lot of yellow, accepted as honest.
- When a report has no language-model short title (the fallback ends in "…"), the UI derives a display
  title from the official heading: first clause (cut at the earliest of comma, semicolon, colon, "which",
  "that", "may", "might", "could", "including" that keeps at least four words), trailing function words
  dropped, capped at 12 words with a visible ellipsis. The full heading is always under the title on the
  detail page. The published JSON is untouched.
- Company display names: title-cased SEC conformed names with corporate suffixes dropped and an exceptions
  map for acronyms and house styles (`web/src/lib/names.ts`); the official name moves to the audit trail.
- The home hero is the top "Potential became actual" highlight across the local published reports, ties
  broken by change score, ticker, then position; with none, the first highlight of the alphabetically
  first company; fixture data is never used.
- Heatmap direction: a company-by-category cell is blue when the net word change (added minus removed) is
  at least 20% of the word turnover (added plus removed) in the positive direction, orange in the negative
  direction, ink otherwise (rewritten); intensity is sentences touched relative to the busiest cell. Columns
  are the ten most active categories, the rest grouped as Other. Every cell carries its numbers in a tooltip
  and for screen readers; empty cells stay blank.
- The AI summary's citations are footnote-style superscript numbers; the numbering is shared across the page
  so one sentence always has one number.
- Trends polls a same-origin Next route (`/api/trends`) every 2.5 s for up to 60 s while the store reports
  `connecting`; "not connected" shows only for `disabled` or `offline` with nothing local.
- The frontend's pure helpers (display names, hero pick, short titles, trends math) are unit-tested with
  Node's built-in runner (`npm run test:unit`, also executed from pytest).

**T11 storing and serving trend facts.**
- Two Delta tables are defined as constants in `tables.py` and created by `databricks_setup.py`:
  `topic_mentions` keyed by (analysis_id, change_id, sentence_id, topic), and `category_activity` keyed by
  (analysis_id, change_id, category). Both use the same insert-if-absent MERGE with one JSON parameter,
  chunked at 500 rows. `publish_remote` writes them after `highlights` and BEFORE the `is_current` flip, so
  a report only becomes current once all of its rows exist. The facts come from `data/derived/`, or are
  derived and written there when missing or stale.
- `/trends` on Databricks runs exactly three parameterized queries, after the cached report list: topics,
  category rows and potential→actual. Each takes `:current` plus `:ids`, a JSON array of the analysis_ids
  the API treats as current (the newest filing pair per ticker, the same rule as `/companies`); no value is
  interpolated. SQL only narrows rows. The topics query keeps one example per (topic, source, ticker) with a
  window function ordered by `aggregate.EXAMPLE_ORDER_SQL` (the same order as the Python `example_key`), and
  it pre-applies the 2-company phrase rule. Sums, grouping and ranking all happen in
  `pipeline/trends/aggregate.py`, shared with the local path. A test publishes the real NVDA and SF reports
  through the real publisher into simulated tables and checks that the Databricks body equals the local body.
  The SQL itself has never run against a real warehouse (none was available).
- The local path aggregates `data/derived/*.trends.json` for the current local reports, using `list_local`
  (newest pair per ticker). A missing or stale file is derived from the published file and written. The
  memo/disk fingerprint is (derivation, phrase model, aggregate version, analysis_ids), so cached answers
  need no file reads.
- Aggregation rules:
  - Topics are sorted by company_count desc, sentence_count desc, then topic, and capped at 40. Entity names
    merge case-insensitively across companies. Phrases appear only when 2+ companies share them.
  - Each topic carries one example per company: the sentence with the most matched terms, then the shortest.
  - Category activity leaves out `largely_unchanged` risk factors and sums the six counts per
    (ticker, category). `change_ids` are ordered by score desc.
  - Potential→actual is sorted by score desc, then ticker.
- Companies also carry `cik`, `old_accession`, `new_accession`, `edgar_url_old` and `edgar_url_new` (added at
  the coordinator's request). The Databricks `reports` table has no EDGAR URL columns, so both URLs are null
  on the remote path and the UI builds the index URL from cik + accession. The table schema was not altered.
- `scripts/derive_trends.py` is the idempotent backfill: local files first, then every current Volume report
  (verified download) plus the MERGEs. `--local-only` skips Databricks. Exit codes: 0 ok, 1 some failed,
  2 bad Databricks config. Databricks not configured is not an error.
- Every `status`/`source` combination `/trends` can return:
  - `disabled` + `local`: always, with data (or empty lists if there are no local reports).
  - `ok` + `databricks`.
  - `connecting`, `ok` or `offline` + `databricks`: a cached remote result, possibly stale while it revalidates.
  - `connecting`, `ok` or `offline` + `local` with data: no remote result yet.
  - `connecting` or `ok` + `null` with empty lists: no remote result and no local reports (retry).
  - `offline` + `local` with empty lists.
  - any status + `null` with empty lists: an unexpected internal error (never a 5xx).

## D-023 Outside review responses (UX13)

- The wording-change meter is ink only (fill = magnitude); direction stays in the badge. Both the
  reverse-squint reviewer and the judge read direction-colored segments as a severity gauge, and the gray
  rewrite fill made a High row look fainter than a Medium one. This departs from the brief's "meter in the
  change's direction color" on purpose; the badge beside it still carries the direction color.
- "Potential became actual" keeps the brief's amber tint and gains a 1px inset ring, so it stops reading as
  a highlighted word. The amber family was kept (the brief fixed it); the ring is the distinction.
- A highlight whose kind badge would repeat the change-type badge ("New risk" + "New risk") shows one badge.
- Potential-to-actual rows in the trends facts carry the removed and added word ranges (`old_spans`,
  `new_spans`), and the Databricks `highlights` table gains `old_spans_json` / `new_spans_json`, so the
  library view draws the same marks from the store as from a local file. `TRENDS_VERSION` 1.1.0; the
  setup script adds the columns to an existing table only when `DESCRIBE TABLE` shows them missing. The
  published report contract and `analysis_id` are untouched (code fingerprint unchanged).
- Merged one-sided sentence runs on the detail page render full width with one line ("5 sentences removed
  this year. Nothing to compare in this year's filing.") instead of a column beside an empty column; the
  per-sentence "Removed"/"Added" labels are hidden inside such a run. The reverse-squint reviewer would
  rather keep the two-column grid; the judge did not object. Kept full width: a 21-sentence column of
  struck text beside a 21-row empty column was the worse read on a projector.
- Kept as the brief asked, despite review notes: library cards on the home page ("cards are the only
  boxes"), the orange family for less disclosure language, the "Major update" label, and the
  four-step / three-column methodology layout. Recorded here rather than changed.
- Not fixable in this sandbox (data, needs the team's NVDA re-run): the section preamble ("The following
  risk factors should be considered…") ranked as a New risk, entity topics such as "Biden Administration"
  and "DOL", and a removed sentence starting mid-word ("z ECCNs"). All three come from the published NVDA
  file, which this environment cannot regenerate (no SEC access).

## D-024 Integrity session: root causes proven before fixing (I1–I4)

Method: `scripts/check_integrity.py` (I1) ran on the two real reports in the repo (NVDA FY2025→FY2026,
SF FY2024→FY2025), the derived trend facts re-derived with the current code, and the running API.
Baseline: 135 findings (`INTEGRITY_REPORT.before.md`). Each finding is classified by re-running the
current pipeline code on the report's own data: `stale` when the current code no longer produces it,
`code` when it still does. The live site's other reports (AAPL, AMZN, GOOGL, CRWD) are not in this
repository and the sandbox has no SEC or Databricks access, so for those the mechanism is proven in
code and on NVDA/SF, and the live instance is named as "not inspected here".

- **Topics counted on words that were not inserted (TOPIC-NEW, 20 findings, code).** `topic_mentions`
  scanned the whole text of added and modified sentences. Evidence: NVDA change `a4156a06454f6dfd`,
  sentence `0001045810-26-000021:21:7`, phrase "CSP market" where only "CSP" is inserted; NVDA
  `6ef9abded50fdc62`, sentence `0001045810-26-000021:18:1`, phrase "exceptional talent" in a sentence
  with no inserted words at all. Rule now: the matched term must lie wholly inside an inserted span and
  no synonym may appear in last year's text of the risk factor (old text taken from the old-side
  sentences when `old_text` is absent).
- **Topics counted on essentially unchanged risk factors (TOPIC-MEANINGFUL, 25 findings, code).**
  Evidence: NVDA `472606c9d458f2e9` (largely unchanged) sentence `0001045810-26-000021:15:15` "We are
  finalizing an investment and partnership agreement with OpenAI." counted "OpenAI". This is the
  mechanism behind "Amazon: No meaningful changes" yet "4 companies newly added Tariffs": a small
  insertion inside an essentially unchanged risk factor. Rule now: topics are derived only for changes
  whose type is not `largely_unchanged`, so a company with zero meaningful changes has zero mentions.
  The brief's hypothesis ("counted when the word appears anywhere in a modified sentence") was half
  right: the freshness guard against last year's whole block text did hold, but the inserted-span
  condition and the meaningful-change condition were both missing.
- **Case-only highlights (CASE, 30 findings, code).** `diff.word_spans` compared tokens exactly.
  Evidence: NVDA `a4156a06454f6dfd`, old `0001045810-25-000023:19:10` vs new `0001045810-26-000021:21:10`:
  deleted "Excessive or shifting export", inserted "Export". The diff now compares casefolded tokens and
  folds whitespace- and punctuation-only changes into equal (stage 5 version bumped).
- **Potential → actual pairs that are not aligned pairs (PAIR, 0 findings on NVDA/SF, code).** Not
  reproduced on NVDA/SF (both of its hits are aligned), but the code paired a newly added sentence with
  the best lexically overlapping hedged old sentence at ratio ≥ 0.25 counting function words, and
  `_candidate_pairs` added (removed, added) pairs; two unrelated sentences sharing 10-K boilerplate
  qualify. That is the Alphabet symptom (advertising demand vs legal fines). Rule now: only aligned
  pairs (new sentence `modified` with its `counterpart_id`), and the derived potential-to-actual rows
  apply the same guard. The NVDA antitrust pair (`0001045810-25-000023:19:41` → `0001045810-26-000021:21:41`)
  is aligned, so the status-change detector still fires on it.
- **Short titles that are fragments (TITLES, 50 findings, code).** The deterministic fallback cut the
  heading at 8 words and appended "…" ("We are subject to complex laws, rules…"); the frontend's clause
  cutter then produced "We are subject to complex laws". Rule now (pipeline and frontend, same spec):
  the longest clause of 4–10 words ending at a natural boundary and not on a dangling word, never an
  ellipsis, never the bare company name; the LLM title is rejected by the same predicate.
- **Entity noise (ENTITY, 5 findings).** "AI Diffusion IFR in" and "D:4" are stale (the J2 post-filter
  already drops them). "Biden Administration", "Trump Administration" (NVDA `a4156a06454f6dfd`,
  sentence `0001045810-26-000021:21:71`) and "SEC" (SF `61ffb76925cf3bc2`) were still emitted by
  `signals.new_entities` while the Trends side already stop-listed them: the stoplist and the
  administration pattern now live in the signals post-filter too.
- **Intro paragraph as a risk (PREAMBLE, 1 finding, stale).** NVDA `692187bd48c050c3` = block
  `0001045810-26-000021:0`, heading "The following risk factors should be considered in addition to the
  other information in this Annual Report on Form 10-K." Segment 0.2.x skips it; confirmed by a unit test
  built from the two real sentences; the published file needs the re-run.
- **Trends crash and duplicate heatmap key (code, frontend).** `ActualItem` reduced over `old_spans`
  without a default, so a payload row without span fields (older API or older store rows) threw;
  the catch-all heatmap column reused the key `other`, which is also a real pipeline category. Fixed in
  the frontend with an error boundary per section and a merged `other` column.
- **Snippets cut before their evidence (SNIP-TOPIC 1 finding, code).** Prefix trimming
  (`trimQuote`) dropped the topic term (SF "Gramm-Leach-Bliley Act") and, on the live site, Apple's and
  Amazon's "tariff" and NVIDIA's changed words. Display now uses one window rule (`snippet_window`,
  reference in the checker, port in `web/src/lib/snippet.ts`) that always contains the earliest
  evidence span, with ellipses on both trimmed sides.
- **Counts that disagree (COUNTS, 0 findings here).** Two code paths can drop a company from Trends
  while Home lists it: the local path skipped a report whose facts failed to derive, and the Databricks
  path built the company set from store rows only while `/companies` merges local and remote. Both are
  closed (same merged set everywhere; a company without facts stays listed with a warning). The live
  CrowdStrike case could not be inspected.
- **Fiscal-year labels (YEARS, 0 findings here).** The CRWD "FY2024 and FY2026" label could not be
  reproduced without its filings; `fiscal_year_from_html` and the 10-K selection were tested on
  synthetic January fiscal-year-end cases instead (see the pipeline agent's notes in this section
  once landed). No guess-fix was applied.
- **Stage versions are now recorded in each report** (`stage_versions`, optional in the contract),
  so STALE can name the earliest stage exactly for every report published from now on; for the two
  existing reports the earliest stage is inferred from the findings (NVDA: 2, the intro paragraph).

## D-025 Integrity session: rules adopted while fixing (I2–I4)

Amends D-021: topic mentions are no longer derived for `largely_unchanged` changes, and a term counts
only when it lies wholly inside inserted text (see D-024 for the proofs).

Pipeline (stage versions: diff 0.1.3, signals 0.2.2, segment 0.2.2, sec_fetch 0.1.1; PIPELINE_VERSION 0.2.0):
- **Potential → actual only from aligned pairs.** A hedge-to-actual or status-change signal needs a
  `modified` new sentence whose `counterpart_id` is the old sentence. The lexical pairing of added
  sentences with hedged old sentences (ratio ≥ 0.25 over all words) and the (removed, added) pairing
  are gone. A concluded marker must also be new on the new side (NVDA `…19:30/…21:30` carried "have been
  imposed" in both years and fired before).
- **Word diff compares casefolded tokens** and folds whitespace- and punctuation-only changes into
  equal; the content-word anchoring of D-018 stays, chosen only when it marks fewer content words than
  the plain alignment. The checker's CASE rule therefore ignores function words (and, or, to, we, is…),
  which the anchoring may re-mark around a changed content word; they are never evidence.
- **Short titles** (pipeline `highlights.short_title_from_heading`, frontend `shortTitleFromHeading`,
  same spec, parity on all 57 published headings): the longest clause of 4–10 words ending at a natural
  boundary, trailing dangling words removed, and, when the cut lands right before a conjunction, a
  trailing "<conjunction> <word>" pair removed too ("…regulations, and political | and other actions"
  → "…regulations"; "incidents or breaches," stays). Never an ellipsis, never the bare company name. The
  LLM title is accepted only when `title_problems` is empty; the schema allows ten words.
- **Entity stoplist** lives in `signals` (regulators, legislatures, courts, generic government, U.S.
  aliases, one-name administrations) and the trends derivation applies the same `is_generic_entity`
  on top of its own list, so the company page and Trends agree. An agency ("Federal Aviation
  Administration") is not a bare administration; a state name is kept.
- **Item 1A introduction**: a heading-like unit before the first real risk heading whose text or first
  body paragraph matches the intro patterns is skipped (test built from NVDA's real intro). The
  "Risk Factors Summary" skip is unchanged.
- **Fiscal year** comes from the `dei:DocumentFiscalYearFocus` fact whose context matches the
  document's own period, else a single distinct value, else the period year; a prior-year comparative
  fact listed first no longer wins. No defect explaining CrowdStrike's "FY2024 and FY2026" was found
  in selection or labeling on synthetic January fiscal-year cases; that case needs its submissions
  JSON and both filings (not available here).

Trends (TRENDS_VERSION 1.2.2):
- Topics: inserted-span containment, meaningful changes only, last year's text from the old-side
  sentences when `old_text` is absent; potential-to-actual rows keep aligned pairs only.
- One company set: `/companies` and `/trends` are built from the same merged current library; a
  company without facts stays listed and is named in `warnings`.
- Delta rows carry their `derivation`; the queries read only the current derivation, so rows of an
  older derivation are never served (`databricks_setup.py` adds the column to existing tables).

Data and process:
- The two local reports were refreshed with `scripts/migrate_published.py` (titles and highlights:
  presentation fields derived from the file's own content, as in D-018; a title that is an exact
  prefix of its heading is a truncation by construction and follows the current rule). Their
  analysis, scores, sentences and analysis ids are unchanged; `scripts/refresh_stale.py` performs the
  real re-run from the earliest changed stage on a machine with SEC and Hugging Face access.
- `stage_versions` is recorded in every report published from now on (optional contract field), so
  STALE names the earliest stage exactly; for the two existing reports it is inferred from findings
  (NVDA: 2, the intro paragraph; SF: 5, case-only spans).
- The checker evaluates display rules through the frontend's own functions when Node is available
  (`snippetWindow`, `heatmapColumns`) and through Python ports otherwise, with shared vectors.
- `@playwright/test` 1.63.0 was added as a pinned dev dependency so the required smoke test can run;
  it uses the Chromium already in the environment (no download).

## D-026 Home-page market ticker tape (Finnhub)
- Context: the team asked for a scrolling stock tape (about 50 popular stocks, current price, up/down)
  on the home page only, using Finnhub if it can be made reliable.
- Decisions (confirmed with the team): Finnhub free tier via the API process; top 50 US-listed
  companies by market cap as a fixed, hand-refreshed list (`api/ticker_tape.py`); up/down use the
  existing blue/orange direction tokens with ▲/▼ and a sign, not green/red (DESIGN.md); branch `slider`.
- Reliability: the browser never calls Finnhub. One background thread refreshes one symbol about every
  1.2 s (about 50 calls/min, under the free limit of 60/min), backs off on 429 and on repeated failures,
  stops on a rejected key, keeps the last good quote per symbol, and persists the snapshot to
  `data/cache/ticker_tape.json` so a restart shows last prices (marked stale) immediately.
  `GET /ticker-tape` reads the in-memory snapshot and never fails; the tape hides itself when there is
  no data, so the home page never depends on Finnhub.
- Scope: market prices are display context only. They never enter a comparison, a score or an
  `analysis_id`, and the tape carries no advice or risk language.
- Security: `finnhub.io` added to the outbound allowlist in CLAUDE.md; key only from `FINNHUB_API_KEY`,
  sent in the `X-Finnhub-Token` header (not the URL), never logged or returned; symbols come only from
  the fixed list (no user input, no SSRF).
- Reverse: unset `FINNHUB_API_KEY` (the tape disappears), or remove `<TickerTape>` from the home page.

## D-027 Stage 3 no longer computes unused full-text block vectors
- Context: `embed_segments` embedded heading, body and full text for every block, but only heading
  and body are read (stage 4 matching). The full-text pass was about 45% of stage-3 compute, and stage 3
  is the slowest step of a live run on CPU.
- Decision: drop the full-text pass and the `full` field of `BlockEmbeddings`. `from_dict` ignores a
  `full` key in older stage-3 cache entries. `embed.STAGE_VERSION` is not bumped: the vectors that are
  used are bit-identical, and a bump would change `stage_versions` in published reports.
- Verified by an independent check: no reader of `full` anywhere; on the lexical backend and on an
  offline dense sentence-transformers proxy (chunking exercised), heading/body vectors, stage-5/6
  vectors and the published JSON are byte-identical except `code_fingerprint`/`analysis_id`, which
  hash every `pipeline/*.py` file and change with any code edit by design. Old cache entries load and
  give byte-identical output. `embed_segments` time fell 45–50% on the proxy. Not run on real bge-m3
  (huggingface.co blocked in the sandbox).
- Caveat: code from before this change crashes on a stage-3 cache entry written after it (missing
  `full`); use `--no-cache` or clear `data/cache/` when running an older checkout on the same data dir.
- Reverse: restore the full-text pass and field.

