"""Citation validator for every LLM output (mandatory, deterministic).

Rules
- Every rubric "yes" must cite >= 1 sentence id, and EVERY cited id must exist in the allowed set
  (the sentences of this change's two blocks); otherwise the answer becomes "no" (raw_answer keeps
  what the model said) and its rationale is discarded. Rationales of "no" answers are never kept:
  they would be uncited free text.
- Every interpretation claim must cite >= 1 sentence id and every cited id must be valid; a claim
  with ANY invalid or fabricated id is dropped (not repaired).
- Claims containing banned language (rubric.BANNED_PHRASES, matched as word stems, case-insensitive)
  or a percentage attached to the word "risk" are dropped.
- Every number, dollar amount, or percentage mentioned in a claim must appear in the cited
  sentences; otherwise the claim is dropped (guards against invented figures).
- Claims longer than MAX_CLAIM_CHARS are dropped; at most MAX_CLAIMS claims are kept.
Dropped items are counted and their reasons recorded for transparency.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from pipeline.rubric import BANNED_PHRASES, QUESTIONS
from pipeline.schema import Claim, RubricAnswer

VALIDATOR_VERSION = "1.2.0"
MAX_CLAIM_CHARS = 400
MAX_CLAIMS = 3

# Stems: buy/buying/bought, sell/selling/sold, invest/investing/investor(s)/investment(s) (but not
# "investigation"), recommend*, guarantee*, probabilit*, probable/probably, likely/unlikely,
# riskier/riskiest/more risky/less risky/safer/safest/less safe, chance(s), odds, "will happen".
_STEMS = (
    r"buy(?:s|ing)?|bought|sell(?:s|ing)?|sold|invest(?!igat)\w*|recommend\w*|guarantee\w*|"
    r"probabilit\w*|probabl[ey]|likely|unlikely|riskier|riskiest|more risky|less risky|safer|safest|"
    r"less safe|more safe|chances?|odds|will happen"
)
_BANNED_RE = re.compile(r"\b(" + _STEMS + r")\b", re.I)
_RISK_PERCENT_RE = re.compile(
    r"(\d+(?:\.\d+)?\s?(?:%|percent)\s*(?:of\s+)?(?:\w+\s+){0,3}risk)|(risk\w*\s+(?:\w+\s+){0,3}\d+(?:\.\d+)?\s?(?:%|percent))",
    re.I,
)
_NUMBER_RE = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")

assert all(re.search(_BANNED_RE, p) for p in BANNED_PHRASES if p != "will happen"), (
    "rubric.BANNED_PHRASES drifted from the validator"
)


_CATEGORY_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "advice wording",
        re.compile(
            r"\b(buy(?:s|ing)?|bought|sell(?:s|ing)?|sold|invest(?!igat)\w*|recommend\w*)\b", re.I
        ),
    ),
    (
        "comparative risk/safety wording",
        re.compile(
            r"\b(riskier|riskiest|more risky|less risky|safer|safest|less safe|more safe|"
            r"(?:higher|greater|increased|elevated|heightened|lower|reduced|decreased|more|less)\s+(?:levels?\s+of\s+)?risks?|"
            r"(?:more|less)\s+(?:vulnerable|exposed|likely|dangerous))\b",
            re.I,
        ),
    ),
    (
        "advice wording",
        re.compile(
            r"\b(?:investors?|holders?|shareholders?|you)\s+should\b|\bshould\s+(?:consider\s+)?(?:exit|avoid|hold|reduce|increase)\w*\b",
            re.I,
        ),
    ),
    ("guarantee wording", re.compile(r"\b(guarantee\w*)\b", re.I)),
    (
        "predictive wording",
        re.compile(
            r"\b(probabilit\w*|probabl[ey]|likely|unlikely|chances?|odds|will happen)\b", re.I
        ),
    ),
)


def banned_language(text: str) -> str | None:
    """Return a NEUTRAL category label when the text contains banned language, else None.
    The offending word itself is never returned: these labels are shown in the UI."""
    for label, rx in _CATEGORY_RES:
        if rx.search(text):
            return label
    if _RISK_PERCENT_RE.search(text):
        return "risk-percentage wording"
    return None


def _numbers(text: str) -> set[str]:
    return {
        n.strip("$%,.").replace(",", "")
        for n in _NUMBER_RE.findall(text)
        if any(ch.isdigit() for ch in n)
    }


def unsupported_numbers(claim: str, cited_texts: list[str]) -> set[str]:
    """Numbers in the claim that do not occur in any cited sentence (ignoring $, %, commas)."""
    have = set()
    for t in cited_texts:
        have |= _numbers(t)
    return {n for n in _numbers(claim) if n not in have}


@dataclass
class ValidationResult:
    rubric: list[RubricAnswer]
    claims: list[Claim]
    dropped_claim_count: int = 0
    dropped_reasons: list[str] = field(default_factory=list)


def _check_ids(ids: object, allowed: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """Return (valid unique ids in order, invalid ids)."""
    valid: list[str] = []
    invalid: list[str] = []
    for sid in ids if isinstance(ids, list) else []:
        if isinstance(sid, str) and sid in allowed:
            if sid not in valid:
                valid.append(sid)
        else:
            invalid.append(str(sid))
    return valid, invalid


def validate_llm_output(raw: dict, allowed_sentences: Mapping[str, str]) -> ValidationResult:
    """`raw` is the parsed model JSON; `allowed_sentences` maps the sentence ids of this change's
    blocks to their exact text."""
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
        cited, invalid = _check_ids(item.get("cited_sentence_ids") or [], allowed_sentences)
        rationale = item.get("rationale")
        rationale = str(rationale).strip()[:MAX_CLAIM_CHARS] if rationale else None
        answer = raw_answer
        if raw_answer and (not cited or invalid):
            answer = False
            reasons.append(
                f"{qid} 'yes' downgraded to 'no': "
                + ("invalid citation(s) " + ", ".join(invalid) if invalid else "no valid citation")
            )
        if not answer:
            rationale = None
            cited = []
        elif rationale and banned_language(rationale):
            reasons.append(
                f"{qid} rationale removed: banned language ({banned_language(rationale)})"
            )
            rationale = None
        elif rationale and unsupported_numbers(rationale, [allowed_sentences[s] for s in cited]):
            reasons.append(f"{qid} rationale removed: mentions a number not in the cited sentences")
            rationale = None
        answers[qid] = RubricAnswer(
            question_id=qid,
            question=q.text,
            answer=answer,
            cited_sentence_ids=cited,
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
        cited, invalid = _check_ids(item.get("cited_sentence_ids") or [], allowed_sentences)
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
        if invalid:
            dropped += 1
            reasons.append(f"claim {i} dropped: invalid citation(s) {', '.join(invalid)}")
            continue
        if not cited:
            dropped += 1
            reasons.append(f"claim {i} dropped: no citation")
            continue
        missing = unsupported_numbers(text, [allowed_sentences[s] for s in cited])
        if missing:
            dropped += 1
            reasons.append(
                f"claim {i} dropped: number(s) not in cited sentences: {', '.join(sorted(missing))}"
            )
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
