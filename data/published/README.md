# data/published

Published comparisons live here as `{TICKER}_{oldFY}_{newFY}.json`, each validated against
`contract/comparison.schema.json`. They are produced only by `python -m pipeline.run <TICKER>`
(or `scripts/build_demo.py`) from real SEC filings. The synthetic FIXTURE can never be written here.

Committed reports: `NVDA_2025_2026.json` (NVIDIA) and `SF_2024_2025.json` (Stifel Financial). Both were
produced by an older pipeline version; `uv run python scripts/refresh_stale.py` re-runs them with the
current code (see `docs/INTEGRITY_REPORT.md` for what is stale).
