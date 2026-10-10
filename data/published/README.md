# data/published

Published comparisons live here as `{TICKER}_{oldFY}_{newFY}.json`, each validated against
`contract/comparison.schema.json`. They are produced only by `python -m pipeline.run <TICKER>`
(or `scripts/build_demo.py`) from real SEC filings. The synthetic FIXTURE can never be written here.

This directory is empty in the overnight build because the build environment could not reach
sec.gov (see PROGRESS.md). Run the pipeline on a machine with internet access and a `.env`.
