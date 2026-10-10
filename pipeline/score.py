"""Stage 8a: deterministic score and score_breakdown.

score = min(100, sum of points). Every line with points carries a plain-English label and the
sentence ids that justify it. Weights live in rubric.py; nothing here is hidden.
"""

from __future__ import annotations

import hashlib
import json

from pipeline.config import PIPELINE_VERSION
from pipeline.rubric import ADDED_TEXT_RATIO_MIN, CAPS, QUESTIONS, RUBRIC_VERSION, WEIGHT_BY_SIGNAL
from pipeline.schema import Interpretation, ModelIds, ScoreLine, Sentence, Signals


def _first_ids(
    sentences: list[Sentence], statuses: tuple[str, ...], side: str | None = None, limit: int = 3
) -> list[str]:
    out = []
    for s in sentences:
        if s.status in statuses and (side is None or s.side == side):
            out.append(s.id)
            if len(out) >= limit:
                break
    return out


def score_change(
    change_type: str,
    sentences: list[Sentence],
    signals: Signals,
    interpretation: Interpretation,
    similarity: float | None,
    reworded_similarity: float,
) -> tuple[int, list[ScoreLine]]:
    lines: list[ScoreLine] = []

    # 1. change type
    w = WEIGHT_BY_SIGNAL[f"change_type:{change_type}"]
    if w.points:
        if change_type == "new":
            cited = _first_ids(sentences, ("added",), limit=1)
            detail = "No counterpart in the prior filing"
        elif change_type == "removed":
            cited = _first_ids(sentences, ("removed",), limit=1)
            detail = "No counterpart in the new filing"
        elif change_type == "expanded":
            cited = _first_ids(sentences, ("added", "modified"), side="new")
            detail = _count_detail(sentences)
        elif change_type == "reduced":
            cited = _first_ids(sentences, ("removed", "modified"), side="old")
            detail = _count_detail(sentences)
        else:  # materially_reworded
            cited = _first_ids(sentences, ("modified", "added"), side="new")
            detail = _count_detail(sentences)
        if cited:
            lines.append(
                ScoreLine(
                    signal=f"change_type:{change_type}",
                    label=w.label,
                    points=w.points,
                    detail=detail,
                    cited_sentence_ids=cited,
                )
            )

    # 2. hedge -> actual
    hits = signals.hypothetical_to_actual
    if hits:
        base = WEIGHT_BY_SIGNAL["hypothetical_to_actual"]
        pts = min(
            CAPS["hypothetical_to_actual"],
            base.points + CAPS["hypothetical_to_actual_extra"] * (len(hits) - 1),
        )
        cited = _dedupe([sid for h in hits for sid in h.old_sentence_ids + h.new_sentence_ids])
        lines.append(
            ScoreLine(
                signal="hypothetical_to_actual",
                label=base.label,
                points=pts,
                detail="; ".join(h.value for h in hits[:3]),
                cited_sentence_ids=cited,
            )
        )

    # 3. new entities
    if signals.new_entities:
        base = WEIGHT_BY_SIGNAL["new_entities"]
        pts = min(CAPS["new_entities"], base.points * len(signals.new_entities))
        cited = _dedupe([sid for h in signals.new_entities for sid in h.new_sentence_ids])
        lines.append(
            ScoreLine(
                signal="new_entities",
                label=base.label,
                points=pts,
                detail=", ".join(h.value for h in signals.new_entities[:5]),
                cited_sentence_ids=cited,
            )
        )

    # 4. new quantities
    if signals.new_quantities:
        base = WEIGHT_BY_SIGNAL["new_quantities"]
        pts = min(CAPS["new_quantities"], base.points * len(signals.new_quantities))
        cited = _dedupe(
            [sid for h in signals.new_quantities for sid in h.old_sentence_ids + h.new_sentence_ids]
        )
        lines.append(
            ScoreLine(
                signal="new_quantities",
                label=base.label,
                points=pts,
                detail=", ".join(h.value for h in signals.new_quantities[:5]),
                cited_sentence_ids=cited,
            )
        )

    # 5. added text ratio (matched pairs only)
    if change_type not in ("new", "removed") and signals.added_text_ratio >= ADDED_TEXT_RATIO_MIN:
        base = WEIGHT_BY_SIGNAL["added_text_ratio"]
        cited = _first_ids(sentences, ("added", "modified"), side="new")
        if cited:
            lines.append(
                ScoreLine(
                    signal="added_text_ratio",
                    label=base.label,
                    points=base.points,
                    detail=f"{signals.added_text_ratio:.0%} of the new text is new",
                    cited_sentence_ids=cited,
                )
            )

    # 6. semantic shift (matched pairs only)
    if (
        similarity is not None
        and similarity < reworded_similarity
        and change_type not in ("largely_unchanged",)
    ):
        base = WEIGHT_BY_SIGNAL["semantic_shift"]
        cited = _first_ids(sentences, ("modified", "added"), side="new") or _first_ids(
            sentences, ("removed",), side="old"
        )
        if cited:
            lines.append(
                ScoreLine(
                    signal="semantic_shift",
                    label=base.label,
                    points=base.points,
                    detail=f"pair similarity {similarity:.2f}",
                    cited_sentence_ids=cited,
                )
            )

    # 7. validated rubric answers
    for ans in interpretation.rubric:
        if ans.answer and ans.cited_sentence_ids:
            q = next(q for q in QUESTIONS if q.id == ans.question_id)
            lines.append(
                ScoreLine(
                    signal=f"rubric_{ans.question_id.lower()}",
                    label=q.label,
                    points=q.points,
                    detail=ans.rationale,
                    cited_sentence_ids=list(ans.cited_sentence_ids),
                )
            )

    total = min(CAPS["score"], sum(line.points for line in lines))
    return total, lines


def _count_detail(sentences: list[Sentence]) -> str:
    added = sum(1 for s in sentences if s.status == "added")
    removed = sum(1 for s in sentences if s.status == "removed")
    modified = sum(1 for s in sentences if s.status == "modified" and s.side == "new")
    parts = []
    if added:
        parts.append(f"{added} sentence{'s' if added != 1 else ''} added")
    if removed:
        parts.append(f"{removed} sentence{'s' if removed != 1 else ''} removed")
    if modified:
        parts.append(f"{modified} modified")
    return ", ".join(parts) or "minor edits"


def _dedupe(ids: list[str]) -> list[str]:
    out: list[str] = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def change_id(old_block_id: str | None, new_block_id: str | None) -> str:
    return hashlib.sha256(f"{old_block_id or ''}|{new_block_id or ''}".encode()).hexdigest()[:16]


def _pipeline_source_hash() -> str:
    """sha256 over every pipeline/*.py file, so a code change without a version bump still
    changes the fingerprint (and therefore analysis_id)."""
    from pathlib import Path

    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(root.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def code_fingerprint() -> str:
    """Everything in the code that changes the output besides PIPELINE_VERSION/RUBRIC_VERSION."""
    from pipeline import diff, embed, extract, llm, match, segment, signals
    from pipeline.rubric import export
    from pipeline.validate import VALIDATOR_VERSION

    payload = {
        "pipeline_version": PIPELINE_VERSION,
        "stage_versions": {
            "extract": extract.STAGE_VERSION,
            "segment": segment.STAGE_VERSION,
            "embed": embed.STAGE_VERSION,
            "match": match.STAGE_VERSION,
            "diff": diff.STAGE_VERSION,
            "signals": signals.STAGE_VERSION,
            "llm": llm.STAGE_VERSION,
        },
        "validator_version": VALIDATOR_VERSION,
        "rubric": export(),
        "diff_params_by_backend": {k: v.to_dict() for k, v in diff.DIFF_PARAMS_BY_BACKEND.items()},
        "match_params_by_backend": {k: v.to_dict() for k, v in match.DEFAULT_PARAMS.items()},
        "questions_rendered": [q.text for q in QUESTIONS],
        "source_sha256": _pipeline_source_hash(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def analysis_id(
    old_accession: str, new_accession: str, model_ids: ModelIds, fingerprint: str | None = None
) -> str:
    payload = "|".join(
        [
            old_accession,
            new_accession,
            PIPELINE_VERSION,
            RUBRIC_VERSION,
            fingerprint or code_fingerprint(),
            model_ids.embedding_model,
            model_ids.embedding_backend,
            model_ids.ner_model,
            model_ids.category_method,
            model_ids.sentence_splitter,
            model_ids.llm_provider or "",
            model_ids.llm_model or "",
            model_ids.prompt_sha256 or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
