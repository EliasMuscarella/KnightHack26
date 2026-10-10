"""Shared /trends aggregation: the local path (derived files on disk) and the Databricks path
(rows fetched by three parameterized queries in pipeline.store.tables) both end here, so
grouping, ranking, example selection and ordering are one piece of code. Pure functions; no I/O.

Wording rule for everything this produces: "newly added", "more language", "less language".
Counts describe disclosure text, never risk levels."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from pipeline.schema import CHANGE_TYPES
from pipeline.trends.schema import TrendFacts

UNCHANGED = "largely_unchanged"
PHRASE_MIN_COMPANIES = 2  # a key phrase is shown only when this many companies share it
TOPICS_LIMIT = 40  # topics returned (after ranking)
# Best example of a topic for one company: most matched terms, then the shortest sentence, then
# ids (deterministic). EXAMPLE_ORDER_SQL is the same order for the Databricks window function.
EXAMPLE_ORDER_SQL = (
    "size(m.matched_terms) DESC, length(m.sentence_text) ASC, m.change_id ASC, m.sentence_id ASC"
)


def example_key(row: Mapping[str, Any]) -> tuple:
    return (-len(row["matched_terms"]), len(row["text"]), row["change_id"], row["sentence_id"])


def empty_body() -> dict[str, Any]:
    return {
        "companies": [],
        "headline": {"companies": 0, "meaningful_changes": 0, "top_topic": None},
        "topics": [],
        "category_activity": [],
        "potential_to_actual": [],
        "change_mix": [],
    }


def company_entry(
    *,
    ticker: str,
    name: str,
    analysis_id: str,
    old_fiscal_year: int,
    new_fiscal_year: int,
    total_changes: int,
    by_change_type: Mapping[str, int],
    cik: str | None = None,
    old_accession: str | None = None,
    new_accession: str | None = None,
    edgar_url_old: str | None = None,
    edgar_url_new: str | None = None,
) -> dict[str, Any]:
    by = {ct: int(by_change_type.get(ct, 0) or 0) for ct in CHANGE_TYPES}
    return {
        "ticker": ticker,
        "name": name,
        "analysis_id": analysis_id,
        "cik": str(cik).zfill(10) if cik else None,
        "old_accession": old_accession or None,
        "new_accession": new_accession or None,
        "edgar_url_old": edgar_url_old or None,
        "edgar_url_new": edgar_url_new or None,
        "old_fiscal_year": int(old_fiscal_year),
        "new_fiscal_year": int(new_fiscal_year),
        "total_changes": int(total_changes),
        "meaningful_changes": int(total_changes) - by[UNCHANGED],
        "by_change_type": by,
    }


# ---------- topics ----------


def _group_key(source: str, topic: str) -> tuple[str, str]:
    # entity names may differ in case between filings ("Entity List" / "entity list")
    return (source, topic.casefold() if source == "entity" else topic)


def topics(rows: Iterable[Mapping[str, Any]], *, limit: int = TOPICS_LIMIT) -> list[dict]:
    """rows: one per mention (local) or one pre-selected example per (topic, source, ticker) with
    `ticker_sentence_count` (Databricks). Keys: ticker, change_id, sentence_id, topic, source,
    matched_terms, status, text, added_spans, short_title[, ticker_sentence_count]."""
    groups: dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for r in rows:
        groups[_group_key(r["source"], r["topic"])][r["ticker"]].append(r)
    out = []
    for (source, _), per_ticker in groups.items():
        tickers = sorted(per_ticker)
        if source == "phrase" and len(tickers) < PHRASE_MIN_COMPANIES:
            continue
        examples, sentence_count = [], 0
        for t in tickers:
            rs = per_ticker[t]
            given = [int(r["ticker_sentence_count"]) for r in rs if r.get("ticker_sentence_count")]
            sentence_count += (
                max(given) if given else len({(r["change_id"], r["sentence_id"]) for r in rs})
            )
            best = min(rs, key=example_key)
            examples.append(
                {
                    "ticker": t,
                    "change_id": best["change_id"],
                    "sentence_id": best["sentence_id"],
                    "short_title": best.get("short_title") or "",
                    "status": best["status"],
                    "text": best["text"],
                    "added_spans": [[int(a), int(b)] for a, b in best["added_spans"]],
                    "matched_terms": list(best["matched_terms"]),
                }
            )
        out.append(
            {
                "topic": per_ticker[tickers[0]][0]["topic"],
                "source": source,
                "company_count": len(tickers),
                "sentence_count": sentence_count,
                "companies": tickers,
                "examples": examples,
            }
        )
    out.sort(
        key=lambda t: (-t["company_count"], -t["sentence_count"], t["topic"].casefold(), t["topic"])
    )
    return out[:limit]


# ---------- category activity ----------

_COUNTS = (
    "added_sentences",
    "removed_sentences",
    "modified_sentences",
    "added_words",
    "removed_words",
    "modified_words",
)


def category_activity(rows: Iterable[Mapping[str, Any]]) -> list[dict]:
    """rows: one per (ticker, change, category) with change_type, score and the six counts.
    Largely unchanged risk factors are left out. Sorted by ticker, category."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for r in rows:
        if r["change_type"] == UNCHANGED:
            continue
        groups[(r["ticker"], r["category"])].append(r)
    out = []
    for (ticker, cat), rs in sorted(groups.items()):
        by_change = {r["change_id"]: r for r in rs}  # one row per change and category
        ordered = sorted(by_change.values(), key=lambda r: (-int(r["score"]), r["change_id"]))
        entry: dict[str, Any] = {
            "ticker": ticker,
            "category": cat,
            "risk_factors": len(ordered),
            "change_ids": [r["change_id"] for r in ordered],
        }
        for k in _COUNTS:
            entry[k] = sum(int(r[k] or 0) for r in ordered)
        entry["max_score"] = max(int(r["score"] or 0) for r in ordered)
        out.append(entry)
    return out


# ---------- potential -> actual ----------

_P2A_KEYS = (
    "ticker",
    "company_name",
    "change_id",
    "short_title",
    "old_sentence_id",
    "new_sentence_id",
    "old_text",
    "new_text",
    "score",
)


def _spans(x: Any) -> list[list[int]]:
    """Spans as [[start, end], ...] from a list (local) or a JSON string (Delta column)."""
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError:
            return []
    try:
        return [[int(a), int(b)] for a, b in (x or []) if int(b) > int(a) >= 0]
    except (TypeError, ValueError):
        return []


def potential_to_actual(rows: Iterable[Mapping[str, Any]]) -> list[dict]:
    out = [
        {
            **{k: (int(r[k] or 0) if k == "score" else (r[k] or "")) for k in _P2A_KEYS},
            "old_spans": _spans(r.get("old_spans", r.get("old_spans_json"))),
            "new_spans": _spans(r.get("new_spans", r.get("new_spans_json"))),
        }
        for r in rows
        if r.get("old_text") and r.get("new_text")
    ]
    out.sort(key=lambda r: (-r["score"], r["ticker"], r["change_id"], r["new_sentence_id"]))
    return out


# ---------- the body ----------


def build_body(
    companies: Iterable[Mapping[str, Any]],
    *,
    topics: list[dict[str, Any]] | None = None,
    category_activity: list[dict[str, Any]] | None = None,
    potential_to_actual: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    comps = sorted((dict(c) for c in companies), key=lambda c: c["ticker"])
    topics = topics or []
    top = topics[0] if topics else None
    return {
        "companies": comps,
        "headline": {
            "companies": len(comps),
            "meaningful_changes": sum(c["meaningful_changes"] for c in comps),
            "top_topic": (
                {"topic": top["topic"], "company_count": top["company_count"]} if top else None
            ),
        },
        "topics": topics,
        "category_activity": category_activity or [],
        "potential_to_actual": potential_to_actual or [],
        "change_mix": [
            {"ticker": c["ticker"], "by_change_type": dict(c["by_change_type"])} for c in comps
        ],
    }


def body_from_facts(facts: Iterable[TrendFacts]) -> dict[str, Any]:
    """The local path: derived files of the current local reports -> the /trends body."""
    facts = list(facts)
    mentions, activity, p2a = [], [], []
    for f in facts:
        titles = {a.change_id: a.short_title for a in f.category_activity}
        for m in f.topic_mentions:
            mentions.append(
                {
                    "ticker": m.ticker,
                    "change_id": m.change_id,
                    "sentence_id": m.sentence_id,
                    "topic": m.topic,
                    "source": m.source,
                    "matched_terms": m.matched_terms,
                    "status": m.status,
                    "text": m.text,
                    "added_spans": m.added_spans,
                    "short_title": titles.get(m.change_id, ""),
                }
            )
        for a in f.category_activity:
            for cat in a.categories:
                activity.append({"ticker": f.ticker, "category": cat, **a.model_dump()})
        p2a.extend(p.model_dump() for p in f.potential_to_actual)
    companies = [
        company_entry(
            ticker=f.ticker,
            name=f.company_name,
            analysis_id=f.analysis_id,
            old_fiscal_year=f.old_fiscal_year,
            new_fiscal_year=f.new_fiscal_year,
            total_changes=f.total_changes,
            by_change_type=f.by_change_type,
            cik=f.cik,
            old_accession=f.old_accession,
            new_accession=f.new_accession,
            edgar_url_old=f.old_edgar_url,
            edgar_url_new=f.new_edgar_url,
        )
        for f in facts
    ]
    return build_body(
        companies,
        topics=topics(mentions),
        category_activity=category_activity(activity),
        potential_to_actual=potential_to_actual(p2a),
    )


def _json_list(v: Any) -> list:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v:
        try:
            out = json.loads(v)
        except ValueError:
            return []
        return out if isinstance(out, list) else []
    return []


def body_from_rows(
    companies: list[dict], topic_rows: list[dict], activity_rows: list[dict], p2a_rows: list[dict]
) -> dict[str, Any]:
    """The Databricks path: rows of the three queries (tables.trends_*_sql) -> the /trends body."""
    mentions = [
        {
            "ticker": r["ticker"],
            "change_id": r["change_id"],
            "sentence_id": r["sentence_id"],
            "topic": r["topic"],
            "source": r["topic_source"],
            "matched_terms": [str(x) for x in _json_list(r.get("matched_terms"))],
            "status": r["status"],
            "text": r["sentence_text"] or "",
            "added_spans": [tuple(x) for x in _json_list(r.get("added_spans_json"))],
            "short_title": r.get("short_title") or "",
            "ticker_sentence_count": int(r.get("ticker_sentence_count") or 0),
        }
        for r in topic_rows
        if r.get("topic_source") in ("lexicon", "entity", "phrase")
    ]
    return build_body(
        companies,
        topics=topics(mentions),
        category_activity=category_activity(activity_rows),
        potential_to_actual=potential_to_actual(p2a_rows),
    )
