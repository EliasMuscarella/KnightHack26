# RiskDiff (Knight Hack IX Project)

**RiskDiff is the `git diff` for 10-K filings.**

RiskDiff is a tool that finds how the risks of a company have changed year over year according to its two
most recently published 10k reports. RiskDiff uses AI to group and rank the importance of these changes,
but all changes are cited directly from the original 10k report to ensure that all information is correct
and grounded in the truth of the 10-K. RiskDiff is an analysis tool to speed up the process of analyzing a 10-K,
not an interpretation tool.

Every public company files a 10-K each fiscal year. These documents can be anywhere from 100 to 300 pages
long, written in very esoteric language that most investors and analysts may not fully understand. 
In a company's 10-K, it lays out its risk factors. These risk factors may change slightly year over year,
but it is within these risk factors that meaningful insight can be extracted. The process of analyzing them can 
be long and tedious for investors. It's often the few sentences that are slightly reworded that are the most important.
RiskDiff aims to expedite this process by highlighting every change to investors, organizing risks by how meaningful these
changes are, and grouping the type of risk.

RiskDiff grounds all findings in the truth of the 10k. Due to the highly regulated nature of Wall Street and the risks
associated with allowing AI to interpret financial documents that would influence investment decisions, RiskDiff
does not advise investment decisions. RiskDiff is a tool that finds how the risks of a company change year
over year according to its two most recently published 10k reports. RiskDiff uses AI to group and rank the
importance of these changes, but all changes are cited directly from the original 10k report to ensure that
all information is correct.

> Not investment advice. RiskDiff shows changes in disclosed risk language, not changes in actual risk.

## The Value of 10-k Risk Factor Analysis
Lauren Cohen of Harvard Business School ran a study focused specifically on companies' risk factors year over year.
They found that portfolios that would short companies with more changes in their risk factors and buy the ones that
did not change as much would produce 188 basis points of alpha (over 22% per year)(Cohen 2019). While correlation does
not mean causation, there are possibly meaningful signals that investors can discover.

## Demo
https://www.youtube.com/watch?v=y2S0cWPg8sA

> **Deployment:** during the hackathon RiskDiff ran at **RiskDiff.compare**, with the frontend on
> Vercel and the backend on Vultr. The site is no longer live; see Quick start to run it locally.

## How It Works
Type in a ticker. RiskDiff pulls the company's two most recent 10-Ks from the SEC, splits Risk
Factors into individual risks, matches each one to last year's version (even if it was reworded or
moved), and labels it: **new, dropped, expanded, scaled back, major update, or unchanged.** Every
change is shown word for word next to last year's version, so nothing is taken out of context.
Deterministic code decides what changed and ranks it with a transparent point system; AI only
answers narrow yes/no questions and writes short explanations, and every claim must cite the exact
sentence in the filing or it is thrown out.

- **Potential → Actual:** risks that went from "could happen" last year to "did happen" this year.
- **New figures and names:** for example, NVIDIA's $4.5 billion charge, which wasn't in last year's filing.
- **Readable diffs:** new words highlighted, removed words struck through, side by side or inline.
- **Proof:** every quote links to the SEC filing with the exact sentence highlighted.
- **Trends:** the topics the most companies newly added this year, across the whole library.
- **Briefing:** pick up to 20 companies and get a printable briefing with an audit trail of the filings used.

## Quick start

**Prerequisites:** Git, Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node.js 20+.

### 1. Clone the repo

```bash
git clone https://github.com/EliasMuscarella/KnightHack26.git
cd KnightHack26
```

### 2. Set up your environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the keys below. The reports already in `data/published/` load without any
keys; the required ones are needed to analyze new companies.

| Key | Required? | What it's for |
|---|---|---|
| `SEC_USER_AGENT` | **Required** | The SEC requires a name and email on every request, e.g. `RiskDiff Jane Doe jane@example.com`. Without it, filings can't be fetched. |
| `HF_TOKEN` | **Required** | Hugging Face token for downloading the embedding model and for the AI explanations. Free at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens). |
| `GEMINI_API_KEY` | Optional | Backup AI provider if Hugging Face is unavailable. |
| `FINNHUB_API_KEY` | Optional | Home-page stock ticker tape. Hidden without it. |
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` | Optional | Shared report library across machines (see *Shared report library* below). |

The frontend needs no secrets. It talks to the backend at `http://localhost:8000` by default
(`NEXT_PUBLIC_API_URL` in `web/.env.example`).

### 3. Start the backend (terminal 1)

```bash
uv sync
uv run uvicorn api.main:app --port 8000
```

### 4. Start the frontend (terminal 2)

```bash
cd web
npm install
npm run dev
```

### 5. Open the app

Go to **http://localhost:3000**.

## Shared report library (Databricks)

Without Databricks every report lives in `data/published/` on the laptop that ran the pipeline.
With it, every teammate's pipeline run publishes to one shared place and every running copy of
the app (each laptop, a future deploy) reads all reports from there. The published JSON stays the
source of truth: it is uploaded byte-for-byte to a Unity Catalog Volume, and three Delta tables
(`reports`, `changes`, `highlights`) are derived from it for cross-company questions in SQL
(`highlights` also carries `old_spans_json` / `new_spans_json`, the removed and added word ranges
of each highlight's two sentences, so the Trends page can draw the same strike and highlighter
from the shared store as from a local file).

## Architecture

A staged Python pipeline turns two filings into one published JSON report; a FastAPI server
serves the reports; a Next.js app renders them.

```
ticker ─► 0 sec_fetch ─► 1 extract ─► 2 segment ─► 3 embed ─► 4 match
          (EDGAR)        (Item 1A)    (risks +      (bge-m3     (Hungarian on
                                       sentences)    vectors)    1 − similarity)
                                                                      │
publish ◄─ 8 score ◄─ 7 llm ◄─ 6 signals ◄─ 5 diff ◄──────────────────┘
(JSON)     (fixed     (rubric   (potential→   (sentence alignment,
            points)    + notes,  actual,       word spans,
                       cited)    figures,      change type)
                                 names)
```

## Data Pipeline

| Stage | Module | What it does |
|---|---|---|
| 0 | `pipeline/sec_fetch.py` | Ticker → CIK → the two latest original 10-Ks from EDGAR, cached on disk (SEC fair-access rules) |
| 1 | `pipeline/extract.py` | Finds the real Item 1A, skipping the table-of-contents entry, and stops at 1B/1C/2 |
| 2 | `pipeline/segment.py` | Splits Risk Factors into risk blocks (heading + body) and sentences with stable ids |
| 3 | `pipeline/embed.py` | Embeds each risk locally with sentence-transformers |
| 4 | `pipeline/match.py` | Pairs each risk with last year's version, even if reworded or moved |
| 5 | `pipeline/diff.py` | Aligns sentences, computes word-level additions/removals, assigns the change type |
| 6 | `pipeline/signals.py` | Rule-based checks: potential → actual wording, new figures, new names, category |
| 7 | `pipeline/llm.py` + `validate.py` | AI answers narrow yes/no rubric questions and writes short notes; uncited claims are dropped |
| 8 | `pipeline/score.py` + `publish.py` | Fixed-point score with a sentence-cited breakdown; writes `data/published/{TICKER}_{oldFY}_{newFY}.json` |

**Matching.** Each risk's similarity combines heading (0.4) and body (0.6) embeddings. Risks are
paired one-to-one by solving

$$\min_{\pi} \sum_i \big(1 - \text{sim}(r_i^{\text{old}}, r_{\pi(i)}^{\text{new}})\big)$$

with `scipy.optimize.linear_sum_assignment`. Pairs below the match threshold are rejected, so an
unpaired old risk is *dropped* and an unpaired new risk is *new*.

**Code decides, AI explains.** What changed and how much it matters are computed by deterministic
code. Each change earns fixed points from `pipeline/rubric.py` (a new risk is worth 30, an expanded
one 15); a cited "yes" from the AI on a rubric question adds fixed points too, and every point is
shown with the sentence that justifies it. Every quote is word for word and links to the exact
sentence on sec.gov.

**Reproducible by design.** Each stage is a pure function of its inputs and a `STAGE_VERSION`;
its cache key is a hash of both. A report's `analysis_id` hashes the two accession numbers, the
pipeline and rubric versions, the model ids and the prompt text, so the same filings and the same
code always produce byte-identical JSON.

**Data contract.** `pipeline/schema.py` (Pydantic) defines the report shape.
`scripts/regen_contract.py` exports it to `contract/comparison.schema.json` and generates
`web/src/types/comparison.ts`, so the backend and frontend can't drift apart.

**Serving.**

- `api/main.py` (FastAPI): `GET /companies`, `GET /comparison/{ticker}`, `GET /trends`,
  `POST /analyze` (live run with progress over SSE, one at a time), `GET /ticker-tape`.
- `web/` (Next.js + TypeScript + Tailwind): the company diff view (`/c/[ticker]`), Trends
  (`/trends`), Briefing (`/briefing`, a printable multi-company report) and Methodology.
- `pipeline/store/`: optional Databricks library that shares published reports across machines
  (see *Shared report library* above).
- `pipeline/trends/`: aggregates new topics and changed sentences across every company in the library.
