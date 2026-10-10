# DEMO

**Status: not yet built.** The demo dataset requires real 10-K filings from SEC EDGAR, which this
build environment could not reach (see `PROGRESS.md` → blockers). Nothing synthetic is listed here.

To build it on a machine with internet access and a `.env` containing `SEC_USER_AGENT` (and `HF_TOKEN`):

```bash
uv run python scripts/build_demo.py            # runs NVDA, AAPL, MSFT, META, AMZN, TSLA, AMD, INTC, JPM, GS
```

The script keeps the 5–8 companies with the most substantive changes **as judged by the pipeline's
own output** (count of changes scoring >= 30, then the sum of the top-5 scores), moves the rest to
`data/scratch/`, and rewrites this file with one candidate demo moment per company: the top-ranked
change and its first cited sentence quoted verbatim from `sentence_index`.

Then run the citation audit (`uv run python -m eval.citation_audit`) and update `EVAL.md`
(`uv run python -m eval.eval --write`).
