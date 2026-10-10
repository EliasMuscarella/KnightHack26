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
