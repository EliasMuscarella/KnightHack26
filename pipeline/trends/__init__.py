"""Cross-company trends, derived deterministically from published reports (no LLM anywhere).

derive.py     report -> TrendFacts (topic mentions, category activity, potential->actual, change mix)
aggregate.py  TrendFacts rows (local files or Databricks rows) -> the /trends response body
topics.yml    the curated topic lexicon (TOPICS_VERSION)

Derived data is NOT part of the published contract: it never changes a published JSON file or
its analysis_id, and it can be rebuilt from the published files at any time
(`scripts/derive_trends.py`)."""
