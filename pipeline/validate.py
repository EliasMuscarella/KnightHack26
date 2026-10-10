"""Citation validator for every LLM output (mandatory, deterministic).

Rules
- Every rubric "yes" must cite >= 1 sentence id that exists in the sentence index AND belongs
  to this change's blocks; otherwise the answer becomes "no" (raw_answer keeps what the model said).
- Every interpretation claim must cite >= 1 valid sentence id, else it is dropped.
- Claims or rationales containing banned language (see rubric.BANNED_PHRASES, matched as whole
  words, case-insensitive) or a percentage attached to the word "risk" are dropped.
- Claims longer than MAX_CLAIM_CHARS are dropped (keeps interpretations short and checkable).
Dropped items are counted and their reasons recorded for transparency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pipeline.rubric import QUESTIONS
from pipeline.schema import Claim, RubricAnswer

MAX_CLAIM_CHARS = 400
MAX_CLAIMS = 3

# Stems: "buy/buying/bought", "sell/selling/sold", "invest/investing/investor(s)/investment(s)"
# (but not "investigation"), "recommend/recommendation(s)", "guarantee(s/d)", "probabilit(y|ies)".
_STEMS = (
    r"buy(?:s|ing)?|bought|sell(?:s|ing)?|sold|invest(?!igat)\w*|recommend\w*|guarantee\w*|"
    r"probabilit\w*|probabl[ey]|likely|unlikely|riskier|will happen"
)
_BANNED_RE = re.compile(r"\b(" + _STEMS + r")\b", re.I)
_RISK_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?\s?%\s*(?:of\s+)?(?:\w+\s+){0,3}risk)|(risk\w*\s+(?:\w+\s+){0,3}\d+(?:\.\d+)?\s?%)",
    re.I,
)


def banned_language(text: str) -> str | None:
    m = _BANNED_RE.search(text)
    if m:
        return m.group(1).lower()
    if _RISK_PERCENT_RE.search(text):
        return "% attached to risk"
    return None


@dataclass
class ValidationResult:
    rubric: list[RubricAnswer]
    claims: list[Claim]
    dropped_claim_count: int = 0
    dropped_reasons: list[str] = field(default_factory=list)


def _valid_ids(ids: list, allowed: set[str]) -> list[str]:
    out: list[str] = []
    for sid in ids or []:
        if isinstance(sid, str) and sid in allowed and sid not in out:
            out.append(sid)
    return out


def validate_llm_output(raw: dict, allowed_sentence_ids: set[str]) -> ValidationResult:
    """`raw` is the parsed model JSON: {"rubric": [{"question_id","answer","cited_sentence_ids","rationale"}],
    "claims": [{"text","cited_sentence_ids"}]}. Unknown question ids are ignored; missing ones become "no"."""
    reasons: list[str] = []
    answers: dict[str, RubricAnswer] = {}
    for item in raw.get("rubric", []) or []:
        if not isinstance(item, dict):
            continue
        qid = str(item.get("question_id", "")).upper()
        q = next((q for q in QUESTIONS if q.id == qid), None)
        if q is None:
            continue
        raw_answer = bool(item.get("answer"))
        cited = _valid_ids(item.get("cited_sentence_ids") or [], allowed_sentence_ids)
        rationale = item.get("rationale")
        rationale = str(rationale).strip()[:MAX_CLAIM_CHARS] if rationale else None
        if rationale and banned_language(rationale):
            reasons.append(
                f"{qid} rationale removed: banned language ({banned_language(rationale)})"
            )
            rationale = None
        answer = raw_answer
        if raw_answer and not cited:
            answer = False
            reasons.append(f"{qid} 'yes' downgraded to 'no': no valid citation")
        answers[qid] = RubricAnswer(
            question_id=qid,
            question=q.text,
            answer=answer,
            cited_sentence_ids=cited if answer else cited,
            rationale=rationale,
            raw_answer=raw_answer,
        )
    for q in QUESTIONS:
        if q.id not in answers:
            answers[q.id] = RubricAnswer(
                question_id=q.id,
                question=q.text,
                answer=False,
                cited_sentence_ids=[],
                rationale=None,
                raw_answer=None,
            )
            reasons.append(f"{q.id} missing from model output: treated as 'no'")

    claims: list[Claim] = []
    dropped = 0
    for i, item in enumerate((raw.get("claims", []) or [])[:10], start=1):
        if not isinstance(item, dict):
            dropped += 1
            reasons.append(f"claim {i} dropped: malformed")
            continue
        text = str(item.get("text", "")).strip()
        cited = _valid_ids(item.get("cited_sentence_ids") or [], allowed_sentence_ids)
        if not text:
            dropped += 1
            reasons.append(f"claim {i} dropped: empty")
            continue
        if len(text) > MAX_CLAIM_CHARS:
            dropped += 1
            reasons.append(f"claim {i} dropped: longer than {MAX_CLAIM_CHARS} characters")
            continue
        bad = banned_language(text)
        if bad:
            dropped += 1
            reasons.append(f"claim {i} dropped: banned language ({bad})")
            continue
        if not cited:
            dropped += 1
            reasons.append(f"claim {i} dropped: no valid citation")
            continue
        if len(claims) >= MAX_CLAIMS:
            dropped += 1
            reasons.append(f"claim {i} dropped: more than {MAX_CLAIMS} claims")
            continue
        claims.append(Claim(text=text, cited_sentence_ids=cited))
    return ValidationResult(
        rubric=[answers[q.id] for q in QUESTIONS],
        claims=claims,
        dropped_claim_count=dropped,
        dropped_reasons=reasons,
    )
