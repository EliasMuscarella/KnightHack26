# RiskDiff

**GitHub Diff for SEC filings.** RiskDiff compares Item 1A (Risk Factors) between a company's two
most recent 10-K filings and shows exactly what management added, removed, expanded, or reworded,
with every claim cited to the original filing text.

> Not investment advice. RiskDiff shows changes in disclosed risk language, not changes in actual risk.

See `CLAUDE.md` for architecture and run commands, `REPORT.md` for the demo script and current
status, `EVAL.md` for evaluation numbers, and `DEMO.md` for the demo dataset.

Status after the overnight build: the full pipeline, API and UI work end to end on a synthetic
fixture; real filings could not be fetched in the build sandbox (no `.env`, sec.gov and
huggingface.co blocked). See `REPORT.md` for exactly what to run next.

Quick start:

```bash
cp .env.example .env      # fill in SEC_USER_AGENT and HF_TOKEN
uv sync
uv run python -m pipeline.run NVDA
cd web && npm install && npm run dev
```

Development data: the synthetic FIXTURE company (`contract/fixtures/`) is hidden in normal use.
Set `RISKDIFF_SHOW_FIXTURE=1` (frontend) and `RISKDIFF_ALLOW_FIXTURE=1` (API) to work on the
screens without real filings; a "FIXTURE DATA" banner is shown whenever it is listed.

## Shared report library (Databricks)

Without Databricks every report lives in `data/published/` on the laptop that ran the pipeline.
With it, every teammate's pipeline run publishes to one shared place and every running copy of
the app (each laptop, a future deploy) reads all reports from there. The published JSON stays the
source of truth: it is uploaded byte-for-byte to a Unity Catalog Volume, and three Delta tables
(`reports`, `changes`, `highlights`) are derived from it for cross-company questions in SQL
(`highlights` also carries `old_spans_json` / `new_spans_json`, the removed and added word ranges
of each highlight's two sentences, so the Trends page can draw the same strike and highlighter
from the shared store as from a local file).

**One-time setup (one person, about ten minutes)**

1. Databricks workspace with Unity Catalog, a catalog named `riskdiff` (or set `DATABRICKS_CATALOG`),
   and a SQL warehouse (serverless is fine). Copy the warehouse id from *Connection details*.
2. A personal access token (*User settings → Developer → Access tokens*).
3. In `.env`: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` (optional
   `DATABRICKS_CATALOG`, `DATABRICKS_SCHEMA`, `DATABRICKS_VOLUME`; see `.env.example`).
4. `uv run python scripts/databricks_setup.py` creates the schema, the Volume and the tables
   (`CREATE … IF NOT EXISTS`; running it again changes nothing). On a workspace set up before
   the span columns existed it adds them to `highlights` with `ALTER TABLE … ADD COLUMNS`, only
   when `DESCRIBE TABLE` shows them missing; then `uv run python scripts/sync_to_databricks.py`
   re-publishes nothing (same analysis ids) and `uv run python scripts/derive_trends.py`
   backfills the trend tables.
5. `uv run python scripts/sync_to_databricks.py` uploads the reports already in `data/published/`.

Every other teammate only needs steps 2–3 with their own token.

**Day to day**

* `uv run python -m pipeline.run AAPL` publishes locally as before, then to the library
  (`--no-remote` skips that). Within a minute AAPL appears in everyone's report library; the
  first view on another machine pulls the JSON from the Volume, verifies it against the contract
  and its `analysis_id`, saves it under `data/published/` and serves it from there afterwards.
* The home page lists the library with who published each report and when; the footer shows
  "Shared library: connected" or "offline, showing reports on this computer". `/trends` shows
  what moved across companies, in plain English.
* Nothing requires Databricks: with the variables unset the app is exactly the local app; with
  them set but the workspace unreachable, local reports keep loading and `GET /store/health`
  says `offline`. A report that is already on disk is never fetched again.

**Guarantees:** the token is read only by the Python API and pipeline (never by `web/`, never
logged); the only outbound host added to the allowlist is the configured workspace; all SQL is
parameterized with table names from code constants; re-publishing the same analysis is a no-op
(rows are keyed by `analysis_id`, writes are `MERGE`s); a new analysis for the same filings
becomes the new current report and the old rows are kept; the tables can always be rebuilt from
the Volume with the sync script.

## Design system and frontend checks

`DESIGN.md` is binding for everything under `web/`: fonts (Public Sans, Source Serif 4 for filing text), the
14/15/17/22/32/44 type scale, neutrals, the direction-of-change colors (blue = more disclosure language,
orange = less, ink = rewritten, amber = potential became actual), the highlighter for new words, and a
checkable list of don'ts. Frontend checks:

```bash
cd web && npm run typecheck && npm run lint && npm run build
cd web && npm run test:unit        # display-name cleaner, deterministic hero pick, short titles, trends math (node --test)
```

`uv run pytest` runs the same unit tests through `tests/test_web_units.py`.
