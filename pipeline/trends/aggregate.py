"""Shared /trends aggregation: the local path (derived files on disk) and the Databricks path
(rows fetched by three parameterized queries) both end here, so ranking, example selection and
ordering are one piece of code. Pure functions; no I/O.

Wording rule for everything this produces: "newly added", "more language", "less language".
Counts describe disclosure text, never risk levels."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pipeline.schema import CHANGE_TYPES

UNCHANGED = "largely_unchanged"


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
) -> dict[str, Any]:
    by = {ct: int(by_change_type.get(ct, 0) or 0) for ct in CHANGE_TYPES}
    return {
        "ticker": ticker,
        "name": name,
        "analysis_id": analysis_id,
        "old_fiscal_year": int(old_fiscal_year),
        "new_fiscal_year": int(new_fiscal_year),
        "total_changes": int(total_changes),
        "meaningful_changes": int(total_changes) - by[UNCHANGED],
        "by_change_type": by,
    }


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
