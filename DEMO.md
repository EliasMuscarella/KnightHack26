# DEMO

The demo uses the reports committed in `data/published/`. Every quote below is the cited filing sentence copied
from the report's `sentence_index`; nothing is hand-written. `uv run python scripts/build_demo.py` runs a larger
candidate set through the pipeline, keeps the 5-8 with the most substantive changes and rewrites this file.

| Ticker | Company | Filings | Changes (new/removed/expanded/reduced/reworded) | Top score |
|---|---|---|---|---|
| NVDA | NVIDIA CORP | FY2025 → FY2026 | 29 (2/0/2/1/1) | 100 |
| SF | STIFEL FINANCIAL CORP | FY2024 → FY2025 | 28 (0/0/0/0/5) | 45 |

## Candidate demo moments (one per company)

### NVDA: NVIDIA CORP
- Change #1: **We are subject to complex laws, rules, regulations, and political and other actions, including restrictions on the export of our products, which may adversely impact our business.** (materially_reworded, score 100, categories: geopolitical, regulation)
- Why it stands out: highlight: potential_became_actual — may -> experienced
- Cited sentence (FY2026 10-K, id `0001045810-26-000021:21:94`): “Export controls increase the risk of investing in U.S. advanced semiconductor products, because by the time a new product is ready for market, it may be subject to new unilateral export controls restricting its sale, resulting in excess inventory and purchase obligations as we recently experienced with the H20.”
- Open: `/c/NVDA/a4156a06454f6dfd`

### SF: STIFEL FINANCIAL CORP
- Change #1: **Cyber attack or other security breach of our technology systems, or those of other third parties we rely on, could subject us to significant liability and reputational harm.** (materially_reworded, score 45, categories: cybersecurity)
- Why it stands out: highlight: new_named_party — EU General Data Protection Regulation
- Cited sentence (FY2025 10-K, id `0001193125-26-067130:14:34`): “In providing services to clients, we collect, use, store, and transmit sensitive client and associate information, including personal data, and are subject to an evolving matrix of U.S. federal, state, and international privacy and data-protection laws and regulations, including, where applicable, the Gramm-Leach-Bliley Act (GLBA), the EU General Data Protection Regulation (GDPR), and state consumer privacy laws such as the CCPA/CPRA.”
- Open: `/c/SF/3b93c57e20a358e4`
