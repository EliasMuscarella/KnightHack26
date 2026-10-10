# RiskDiff — overnight build report

Built overnight for Knight Hacks 9 (submission Sunday Oct 11, 2026, 10:30 AM ET) with no human in
the loop. Read this first, then `PROGRESS.md` (status per task), `DECISIONS.md` (every call made
without you), `EVAL.md` (real numbers only), `DEMO.md` (demo dataset status).

## 1. Where things stand (honest summary)

**Working and tested end to end (on the synthetic FIXTURE filing pair):** every pipeline stage
(fetch → extract → segment → embed → match → diff → signals → LLM → score/publish), stage caching,
byte-identical reruns, the FastAPI backend with SSE live mode, and the Next.js UI (all five screens,
citation chips that jump to the cited sentence, side-by-side/inline diff, score breakdown, AI
interpretation panel, methodology page). 104 pytest tests pass; `npm run build/lint/typecheck` pass.
Two independent review rounds were run on the pipeline/API and the frontend; all HIGH and MEDIUM
findings from round 1 were fixed (see `DECISIONS.md` D-015 and the round-2 section below).

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

Useful flags: `--until-stage N`, `--from-stage N`, `--no-cache`, `--force` (replace a published
file whose analysis_id differs). Dev only: `RISKDIFF_SHOW_FIXTURE=1` lists the FIXTURE company in
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
  reruns on every load.
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
  fixed (see `DECISIONS.md` D-015). Round 1 (frontend reviewer): 0 HIGH, 3 MEDIUM, 14 LOW → all fixed.
- Round 2: see the section appended below.
