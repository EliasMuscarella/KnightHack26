"""Rubric questions, score weights, banned language, and RUBRIC_VERSION, all in one place.

The score is a deterministic sum of points: each line in `score_breakdown` carries a
plain-English label and the sentence ids that justify it. Nothing here is hidden math;
`contract/rubric.json` is exported from this module for the Methodology page.
"""

from __future__ import annotations

from dataclasses import dataclass

RUBRIC_VERSION = "1.0.0"

# ---- LLM rubric questions (narrow yes/no; every "yes" must cite >= 1 sentence id) ----


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    points: int
    label: str


QUESTIONS: tuple[Question, ...] = (
    Question(
        "Q1",
        "Does the new text describe an event or condition that has already occurred, where the old text described it as a possibility?",
        10,
        "AI rubric: a possibility became an occurred event",
    ),
    Question(
        "Q2",
        "Does the new text name a specific geography, government, regulation, or counterparty not named in the old text?",
        8,
        "AI rubric: new specific geography, government, regulation, or counterparty",
    ),
    Question(
        "Q3",
        "Does the new text state or quantify a financial or operational impact not stated in the old text?",
        10,
        "AI rubric: newly stated or quantified impact",
    ),
    Question(
        "Q4",
        "Does the change narrow or remove a previously disclosed exposure?",
        6,
        "AI rubric: a previously disclosed exposure was narrowed or removed",
    ),
)

# ---- Deterministic weights ----


@dataclass(frozen=True)
class Weight:
    signal: str
    label: str
    points: int
    description: str


WEIGHTS: tuple[Weight, ...] = (
    Weight(
        "change_type:new", "New risk factor", 30, "The risk has no counterpart in the prior filing."
    ),
    Weight(
        "change_type:removed",
        "Risk factor removed",
        20,
        "The prior filing's risk has no counterpart in the new filing.",
    ),
    Weight(
        "change_type:materially_reworded",
        "Risk was materially reworded",
        20,
        "Substantial wording changes in both directions.",
    ),
    Weight(
        "change_type:expanded", "Risk was expanded", 15, "Net addition of at least 15% of the text."
    ),
    Weight(
        "change_type:reduced", "Risk was reduced", 10, "Net removal of at least 15% of the text."
    ),
    Weight("change_type:largely_unchanged", "Largely unchanged", 0, "Only minor edits."),
    Weight(
        "hypothetical_to_actual",
        "Hedged language became actual language",
        20,
        "A 'may/could/might' statement became 'has/have/resulted in' wording for the same content (first hit; +5 per additional hit, max 30).",
    ),
    Weight(
        "new_entities",
        "New named geography, organization, or law",
        4,
        "Per newly named entity (spaCy NER), max 12.",
    ),
    Weight(
        "new_quantities",
        "New quantified amount or percentage",
        5,
        "Per new dollar amount, percentage, or counted unit, max 15.",
    ),
    Weight(
        "added_text_ratio",
        "Large share of new text",
        5,
        "Added text is at least 40% of the new block (not for 'new' blocks).",
    ),
    Weight(
        "semantic_shift",
        "Meaning shifted noticeably",
        5,
        "Pair similarity below the reworded threshold.",
    ),
    Weight(
        "rubric_q1",
        QUESTIONS[0].label,
        QUESTIONS[0].points,
        "Validated 'yes' to Q1 with citations.",
    ),
    Weight(
        "rubric_q2",
        QUESTIONS[1].label,
        QUESTIONS[1].points,
        "Validated 'yes' to Q2 with citations.",
    ),
    Weight(
        "rubric_q3",
        QUESTIONS[2].label,
        QUESTIONS[2].points,
        "Validated 'yes' to Q3 with citations.",
    ),
    Weight(
        "rubric_q4",
        QUESTIONS[3].label,
        QUESTIONS[3].points,
        "Validated 'yes' to Q4 with citations.",
    ),
)
WEIGHT_BY_SIGNAL = {w.signal: w for w in WEIGHTS}

CAPS = {
    "hypothetical_to_actual": 30,
    "hypothetical_to_actual_extra": 5,
    "new_entities": 12,
    "new_quantities": 15,
    "score": 100,
}
ADDED_TEXT_RATIO_MIN = 0.40

# ---- Banned language (case-insensitive) in any LLM claim or rationale ----
BANNED_PHRASES: tuple[str, ...] = (
    "likely",
    "unlikely",
    "probability",
    "probable",
    "will happen",
    "riskier",
    "riskiest",
    "more risky",
    "less risky",
    "safer",
    "less safe",
    "chance",
    "odds",
    "buy",
    "sell",
    "invest",
    "recommend",
    "guarantee",
)
# "% of risk" / "risk ... %" patterns are handled by a regex in validate.py


def export() -> dict:
    from pipeline.config import PIPELINE_VERSION
    from pipeline.diff import DEFAULT_DIFF_PARAMS
    from pipeline.match import DEFAULT_PARAMS

    return {
        "rubric_version": RUBRIC_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "questions": [{"id": q.id, "text": q.text, "points": q.points} for q in QUESTIONS],
        "weights": [
            {"signal": w.signal, "label": w.label, "points": w.points, "description": w.description}
            for w in WEIGHTS
        ],
        "caps": CAPS,
        "banned_phrases": list(BANNED_PHRASES),
        "thresholds": {
            **{
                f"match.{k}.{kk}": vv
                for k, p in DEFAULT_PARAMS.items()
                for kk, vv in p.to_dict().items()
            },
            **{f"diff.{k}": v for k, v in DEFAULT_DIFF_PARAMS.to_dict().items()},
            "score.added_text_ratio_min": ADDED_TEXT_RATIO_MIN,
        },
    }
