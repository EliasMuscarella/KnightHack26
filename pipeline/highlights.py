"""Highlights: the <= 5 cards shown as "Biggest changes" on a company page (Task J4).

Candidates come only from evidence that already exists on a change: deterministic signals
(hedge-to-actual pairs, quantities, named entities), the change type itself (a new or removed
risk cites the heading sentence `{block_id}:0`), and validated AI rubric answers (kind from the
question, sentences from its citations). Nothing is generated here.

Selection (see select_highlights) runs over four tiers in order:
  1. meaningful change (not "largely_unchanged") + rule-based evidence
  2. meaningful change + AI-rubric-only evidence
  3. essentially unchanged risk + rule-based evidence
  4. essentially unchanged risk + AI-rubric-only evidence
so the cards agree with the "N of M risk factors changed meaningfully" line and rule-based
evidence outranks an AI answer. Within a tier, rank_key orders candidates by parent change
score (desc, the same order as the ranked list), then kind priority (new risk > dropped risk >
potential became actual > figure > newly named), then change id, then the candidate's position
(dollar amounts before percentages before counts). Each tier takes one card per change first,
then second cards of a different kind. At most MAX_PER_CHANGE per change and MAX_TOTAL overall.
A potential_became_actual highlight must carry BOTH a last-year and a this-year sentence: the
before/after is the point of that card, so rubric-only candidates with one side are dropped.
"""

from __future__ import annotations

from pipeline.schema import Change, Highlight, SentenceLocation

KIND_PRIORITY: dict[str, int] = {
    "new_risk": 0,
    "removed_risk": 1,
    "potential_became_actual": 2,
    "new_figure": 3,
    "new_named_party": 4,
}
MAX_PER_CHANGE = 2
MAX_TOTAL = 5
RUBRIC_KIND = {"Q1": "potential_became_actual", "Q2": "new_named_party", "Q3": "new_figure"}
MEANINGFUL = ("new", "removed", "expanded", "reduced", "materially_reworded")


def _split_sides(
    ids: list[str], index: dict[str, SentenceLocation]
) -> tuple[str | None, str | None]:
    old = next((i for i in ids if i in index and index[i].side == "old"), None)
    new = next((i for i in ids if i in index and index[i].side == "new"), None)
    return old, new


def _figure_order(value: str | None) -> int:
    """Dollar amounts before percentages before other quantities (a finance reader's order)."""
    v = value or ""
    if "$" in v:
        return 0
    if "%" in v or "percent" in v.lower():
        return 1
    return 2


def candidate_highlights(
    change: Change, index: dict[str, SentenceLocation]
) -> list[tuple[Highlight, bool]]:
    """All highlight candidates of one change, in a deterministic order.

    Each item is (highlight, rule_based): rule_based is True when the card rests on a
    deterministic signal or on the change type itself, False when its only evidence is a
    validated AI rubric answer.
    """
    out: list[tuple[Highlight, bool]] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    def add(
        kind: str, old: str | None, new: str | None, detail: str | None, rule_based: bool
    ) -> None:
        if old is not None and old not in index:
            old = None
        if new is not None and new not in index:
            new = None
        if old is None and new is None:
            return
        if kind == "potential_became_actual" and (old is None or new is None):
            return  # a before/after card needs both sides
        key = (kind, old, new)
        if key in seen:
            return
        seen.add(key)
        out.append(
            (
                Highlight(
                    change_id=change.id,
                    kind=kind,
                    old_sentence_id=old,
                    new_sentence_id=new,
                    short_title=change.short_title,
                    detail=detail,
                ),
                rule_based,
            )
        )

    sig = change.signals
    if change.change_type == "new" and change.new_block_id:
        add("new_risk", None, f"{change.new_block_id}:0", None, True)
    if change.change_type == "removed" and change.old_block_id:
        add("removed_risk", f"{change.old_block_id}:0", None, None, True)
    for h in sig.hypothetical_to_actual:
        add(
            "potential_became_actual",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
            True,
        )
    for h in sorted(sig.new_quantities, key=lambda h: _figure_order(h.value)):
        add(
            "new_figure",
            (h.old_sentence_ids or [None])[0],
            (h.new_sentence_ids or [None])[0],
            h.value,
            True,
        )
    for h in sig.new_entities:
        add("new_named_party", None, (h.new_sentence_ids or [None])[0], h.value, True)
    for ans in change.interpretation.rubric:
        kind = RUBRIC_KIND.get(ans.question_id)
        if kind and ans.answer and ans.cited_sentence_ids:
            old, new = _split_sides(list(ans.cited_sentence_ids), index)
            add(kind, old, new, None, False)
    return out


def rank_key(h: Highlight, change: Change, position: int) -> tuple:
    """Order within a tier: biggest change first (same order as the ranked list), then kind."""
    return (-change.score, KIND_PRIORITY[h.kind], change.id, position)


def select_highlights(changes: list[Change], index: dict[str, SentenceLocation]) -> list[Highlight]:
    by_id = {c.id: c for c in changes}
    # tiers: (meaningful change?, rule-based evidence?) -> candidates ranked within the tier
    tiers: dict[tuple[bool, bool], list[tuple[tuple, Highlight]]] = {
        (m, r): [] for m in (True, False) for r in (True, False)
    }
    for c in changes:
        meaningful = c.change_type in MEANINGFUL
        for pos, (h, rule_based) in enumerate(candidate_highlights(c, index)):
            tiers[(meaningful, rule_based)].append((rank_key(h, c, pos), h))

    chosen: list[Highlight] = []
    per_change: dict[str, int] = {}
    seen_kind: set[tuple[str, str]] = set()

    def take(h: Highlight) -> None:
        chosen.append(h)
        seen_kind.add((h.change_id, h.kind))
        per_change[h.change_id] = per_change.get(h.change_id, 0) + 1

    for key in ((True, True), (True, False), (False, True), (False, False)):
        ranked = sorted(tiers[key], key=lambda x: x[0])
        for _, h in ranked:  # pass 1: the best candidate of each change in this tier
            if len(chosen) >= MAX_TOTAL:
                break
            if h.change_id not in per_change:
                take(h)
        for _, h in ranked:  # pass 2: a second card for a change, of a different kind
            if len(chosen) >= MAX_TOTAL:
                break
            if (
                h in chosen
                or per_change.get(h.change_id, 0) >= MAX_PER_CHANGE
                or (h.change_id, h.kind) in seen_kind
            ):
                continue
            take(h)
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
