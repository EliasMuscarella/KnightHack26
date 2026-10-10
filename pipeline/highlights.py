"""Highlights: the handful of before/after moments shown first on a company page.

Candidates come ONLY from existing evidence already in the published change:
- deterministic signals (hypothetical_to_actual, new_quantities, new_entities),
- the change type (new / removed risk),
- validated LLM rubric "yes" answers (Q1 -> potential_became_actual, Q2 -> new_named_party,
  Q3 -> new_figure) whose citations passed the validator.
Every highlight points at verbatim sentence ids; the UI quotes them from sentence_index.

Ranking (see rank_key): kind priority potential_became_actual > new_figure > new_risk >
new_named_party > removed_risk, then parent change score (desc), then change id, then the
candidate's position within its change. At most MAX_PER_CHANGE per change and MAX_TOTAL overall.
"""

from __future__ import annotations

from pipeline.schema import Change, Highlight, SentenceLocation

KIND_PRIORITY: dict[str, int] = {
    "potential_became_actual": 0,
    "new_figure": 1,
    "new_risk": 2,
    "new_named_party": 3,
    "removed_risk": 4,
}
MAX_PER_CHANGE = 2
MAX_TOTAL = 5
RUBRIC_KIND = {"Q1": "potential_became_actual", "Q2": "new_named_party", "Q3": "new_figure"}


def _split_sides(
    ids: list[str], index: dict[str, SentenceLocation]
) -> tuple[str | None, str | None]:
    old = next((i for i in ids if i in index and index[i].side == "old"), None)
    new = next((i for i in ids if i in index and index[i].side == "new"), None)
    return old, new


def candidate_highlights(change: Change, index: dict[str, SentenceLocation]) -> list[Highlight]:
    """All highlight candidates of one change, in a deterministic order."""
    out: list[Highlight] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    def add(kind: str, old: str | None, new: str | None, detail: str | None) -> None:
        if old is not None and old not in index:
            old = None
        if new is not None and new not in index:
            new = None
        if old is None and new is None:
            return
        key = (kind, old, new)
        if key in seen:
            return
        seen.add(key)
        out.append(
            Highlight(
                change_id=change.id,
                kind=kind,
                old_sentence_id=old,
                new_sentence_id=new,
                short_title=change.short_title,
                detail=detail,
            )
        )

    sig = change.signals
    for h in sig.hypothetical_to_actual:
        add(
            "potential_became_actual",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
        )
    for h in sig.new_quantities:
        add(
            "new_figure",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
        )
    if change.change_type == "new" and change.new_block_id:
        add("new_risk", None, f"{change.new_block_id}:0", None)
    for h in sig.new_entities:
        add("new_named_party", None, (h.new_sentence_ids or [None])[0], h.value)
    if change.change_type == "removed" and change.old_block_id:
        add("removed_risk", f"{change.old_block_id}:0", None, None)
    for ans in change.interpretation.rubric:
        kind = RUBRIC_KIND.get(ans.question_id)
        if kind and ans.answer and ans.cited_sentence_ids:
            old, new = _split_sides(list(ans.cited_sentence_ids), index)
            add(kind, old, new, None)
    return out


def rank_key(h: Highlight, change: Change, position: int) -> tuple:
    return (KIND_PRIORITY[h.kind], -change.score, change.id, position)


def select_highlights(changes: list[Change], index: dict[str, SentenceLocation]) -> list[Highlight]:
    by_id = {c.id: c for c in changes}
    ranked: list[tuple[tuple, Highlight]] = []
    for c in changes:
        for pos, h in enumerate(candidate_highlights(c, index)):
            ranked.append((rank_key(h, c, pos), h))
    ranked.sort(key=lambda x: x[0])
    chosen: list[Highlight] = []
    per_change: dict[str, int] = {}
    for _, h in ranked:
        if per_change.get(h.change_id, 0) >= MAX_PER_CHANGE:
            continue
        chosen.append(h)
        per_change[h.change_id] = per_change.get(h.change_id, 0) + 1
        if len(chosen) >= MAX_TOTAL:
            break
    assert all(h.change_id in by_id for h in chosen)
    return chosen


def truncate_heading(heading: str, max_words: int = 8) -> str:
    """Deterministic fallback short title: the first `max_words` words of the official heading,
    with a visible ellipsis when cut."""
    words = heading.strip().split()
    if len(words) <= max_words:
        return heading.strip().rstrip(".;:")
    cut = " ".join(words[: max_words - 1]).rstrip(",.;:")
    return cut + "\u2026"
