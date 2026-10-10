"""Stages 6-8: deterministic signals, LLM rubric/interpretation, score + publish."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from pipeline import llm as llm_mod
from pipeline import signals as signals_mod
from pipeline.config import NER_MODEL_ID, PIPELINE_VERSION, SENTENCE_SPLITTER_ID
from pipeline.diff import DEFAULT_DIFF_PARAMS
from pipeline.publish import publish
from pipeline.rubric import RUBRIC_VERSION
from pipeline.schema import (
    CATEGORIES,
    CHANGE_TYPES,
    SCHEMA_VERSION,
    Change,
    Claim,
    Comparison,
    FilingMeta,
    Interpretation,
    ModelIds,
    RubricAnswer,
    Sentence,
    SentenceLocation,
    Signals,
    Summary,
    Thresholds,
)
from pipeline.score import analysis_id, change_id, score_change
from pipeline.stages_late import get_embedder
from pipeline.types import FilingRecord, RiskBlock, SegmentedFiling

if TYPE_CHECKING:
    from pipeline.run import RunContext

log = logging.getLogger("pipeline")

DISCLAIMER = "Not investment advice. RiskDiff shows changes in disclosed risk language, not changes in actual risk."


def _records_hash(records: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _blocks(segs: dict[str, SegmentedFiling], r: dict) -> tuple[RiskBlock | None, RiskBlock | None]:
    old = segs["old"].blocks[r["old_index"]] if r["old_index"] is not None else None
    new = segs["new"].blocks[r["new_index"]] if r["new_index"] is not None else None
    return old, new


def category_method_id(backend: str, model_id: str) -> str:
    if backend == "sentence-transformers":
        return f"hybrid: {signals_mod.LEXICON_METHOD_ID} + embedding-similarity:{model_id}"
    return signals_mod.LEXICON_METHOD_ID


# ---------- stage 6 ----------


def stage6_signals(
    ctx: RunContext, segs: dict[str, SegmentedFiling], records: list[dict]
) -> list[dict]:
    emb = ctx.outputs["embeddings"]
    method = category_method_id(emb.backend, emb.model_id)

    def compute() -> list[dict]:
        scorer = None
        if emb.backend == "sentence-transformers":
            scorer = signals_mod.dense_category_scorer(get_embedder(ctx))
        nlp = signals_mod.get_nlp()
        out: list[dict] = []
        for r in records:
            old, new = _blocks(segs, r)
            st = r["stats"]
            sc = signals_mod.SignalContext(
                old=old,
                new=new,
                sentences=[Sentence.model_validate(s) for s in r["sentences"]],
                similarity=r["similarity"],
                added_word_count=st["added_word_count"],
                removed_word_count=st["removed_word_count"],
                old_word_count=st["old_word_count"],
                new_word_count=st["new_word_count"],
            )
            dense = scorer((new or old).full_text) if scorer else None
            sig, cats = signals_mod.compute_signals(sc, dense, nlp)
            out.append({"signals": sig.model_dump(mode="json"), "categories": cats})
        return out

    return ctx.cached(
        6,
        signals_mod.STAGE_VERSION,
        {"records": _records_hash(records), "ner": NER_MODEL_ID, "category_method": method},
        compute,
    )


# ---------- stage 7 ----------


def stage7_llm(
    ctx: RunContext, segs: dict[str, SegmentedFiling], records: list[dict], fetch
) -> tuple[list[dict | None], dict]:
    """Returns (per-record result dicts or None, provider info)."""
    client = ctx.outputs.get("llm_client")
    reason = ctx.outputs.get("llm_reason")
    if client is None and reason is None:
        client, reason = llm_mod.select_client(ctx.settings)
        ctx.outputs["llm_client"] = client
        ctx.outputs["llm_reason"] = reason
        if client is None:
            log.warning("%s", reason)
        else:
            log.info("LLM provider: %s (%s)", client.provider, client.model_id)
    info = {
        "provider": client.provider if client else None,
        "model_id": client.model_id if client else None,
        "prompt_sha256": llm_mod.prompt_sha256() if client else None,
        "reason": reason if client is None else None,
    }
    results: list[dict | None] = []
    calls = 0
    for r in records:
        if client is None or r["change_type"] == "largely_unchanged":
            results.append(None)
            continue
        old, new = _blocks(segs, r)
        title = (new or old).heading
        sentences = [Sentence.model_validate(s) for s in r["sentences"]]
        key_inputs = {
            "prompt_sha256": info["prompt_sha256"],
            "model_id": client.model_id,
            "old": [s.text for s in old.sentences] if old else None,
            "new": [s.text for s in new.sentences] if new else None,
            "diff": [(s.id, s.status) for s in sentences],
            "fy": [fetch.old.fiscal_year, fetch.new.fiscal_year],
        }

        def compute(title=title, old=old, new=new, sentences=sentences) -> dict:
            nonlocal calls
            calls += 1
            res = llm_mod.interpret_change(
                client, title, old, new, sentences, fetch.old.fiscal_year, fetch.new.fiscal_year
            )
            return {
                "status": res.status,
                "model_id": res.model_id,
                "attempts": res.attempts,
                "error": res.error,
                "raw": res.raw,
                "rubric": [a.model_dump(mode="json") for a in res.validation.rubric]
                if res.validation
                else [],
                "claims": [c.model_dump(mode="json") for c in res.validation.claims]
                if res.validation
                else [],
                "dropped_claim_count": res.validation.dropped_claim_count if res.validation else 0,
                "dropped_reasons": res.validation.dropped_reasons if res.validation else [],
            }

        results.append(ctx.cached(7, llm_mod.STAGE_VERSION, key_inputs, compute))
    ctx.outputs["llm_calls"] = calls
    return results, info


def build_interpretation(r: dict, llm_res: dict | None, info: dict) -> Interpretation:
    if r["change_type"] == "largely_unchanged":
        return Interpretation(
            status="skipped", reason="Not run for largely unchanged risks.", model_id=None
        )
    if info["provider"] is None:
        return Interpretation(status="unavailable", reason=info["reason"], model_id=None)
    if llm_res is None or llm_res["status"] == "error":
        return Interpretation(
            status="unavailable",
            reason=f"The model did not return valid output after {llm_mod.MAX_ATTEMPTS} attempts ({(llm_res or {}).get('error') or 'unknown error'}).",
            model_id=info["model_id"],
        )
    rubric = [RubricAnswer.model_validate(a) for a in llm_res["rubric"]]
    claims = [Claim.model_validate(c) for c in llm_res["claims"]]
    status = "ok" if claims else "empty"
    reason = (
        None
        if claims
        else f"All {llm_res['dropped_claim_count']} interpretation claims were dropped by the citation validator."
        if llm_res["dropped_claim_count"]
        else "The model returned no interpretation claims."
    )
    return Interpretation(
        status=status,
        reason=reason,
        model_id=llm_res["model_id"],
        rubric=rubric,
        claims=claims,
        dropped_claim_count=llm_res["dropped_claim_count"],
        dropped_reasons=llm_res["dropped_reasons"],
    )


# ---------- stage 8 ----------


def _filing_meta(rec: FilingRecord, section, seg: SegmentedFiling) -> FilingMeta:
    return FilingMeta(
        accession_number=rec.accession_number,
        form=rec.form,
        fiscal_year=rec.fiscal_year,
        period_of_report=rec.report_date,
        filing_date=rec.filing_date,
        primary_document=rec.primary_document,
        edgar_url=rec.edgar_url,
        edgar_index_url=rec.edgar_index_url,
        is_amendment=rec.is_amendment,
        item_1a_word_count=section.word_count,
        item_1a_char_count=section.char_count,
        block_count=len(seg.blocks),
        section_groups=list(seg.section_groups),
    )


def assemble(
    ctx: RunContext,
    ticker: str,
    records: list[dict],
    sig_rows: list[dict],
    llm_rows: list[dict | None],
    llm_info: dict,
) -> Comparison:
    fetch = ctx.outputs["fetch"]
    segs = ctx.outputs["segments"]
    sections = ctx.outputs["sections"]
    emb = ctx.outputs["embeddings"]
    matches = ctx.outputs["matches"]

    model_ids = ModelIds(
        embedding_model=emb.model_id,
        embedding_backend=emb.backend,
        ner_model=NER_MODEL_ID,
        category_method=category_method_id(emb.backend, emb.model_id),
        sentence_splitter=SENTENCE_SPLITTER_ID,
        llm_provider=llm_info["provider"],
        llm_model=llm_info["model_id"],
        prompt_sha256=llm_info["prompt_sha256"],
    )
    thresholds = Thresholds(
        match_threshold=matches.params.match_threshold,
        heading_weight=matches.params.heading_weight,
        body_weight=matches.params.body_weight,
        sentence_match_threshold=DEFAULT_DIFF_PARAMS.sentence_match_threshold,
        sentence_unchanged_threshold=DEFAULT_DIFF_PARAMS.sentence_unchanged_threshold,
        expanded_ratio=DEFAULT_DIFF_PARAMS.expanded_ratio,
        reworded_similarity=DEFAULT_DIFF_PARAMS.reworded_similarity,
    )

    sentence_index: dict[str, SentenceLocation] = {}
    for side in ("old", "new"):
        seg = segs[side]
        for b in seg.blocks:
            for s in b.sentences:
                sentence_index[s.id] = SentenceLocation(
                    id=s.id,
                    accession_number=seg.accession_number,
                    side=side,
                    block_id=b.id,
                    text=s.text,
                    char_start=s.char_start,
                    char_end=s.char_end,
                    is_heading=s.is_heading,
                )

    changes: list[Change] = []
    for r, sg, lr in zip(records, sig_rows, llm_rows, strict=True):
        old, new = _blocks(segs, r)
        sentences = [Sentence.model_validate(s) for s in r["sentences"]]
        signals = Signals.model_validate(sg["signals"])
        interpretation = build_interpretation(r, lr, llm_info)
        score, breakdown = score_change(
            r["change_type"],
            sentences,
            signals,
            interpretation,
            r["similarity"],
            DEFAULT_DIFF_PARAMS.reworded_similarity,
        )
        changes.append(
            Change(
                id=change_id(r["old_block_id"], r["new_block_id"]),
                rank=1,
                title=(new or old).heading,
                old_title=old.heading if old else None,
                new_title=new.heading if new else None,
                section_group=(new or old).section_group,
                change_type=r["change_type"],
                categories=sg["categories"],
                score=score,
                score_breakdown=breakdown,
                similarity=r["similarity"],
                heading_similarity=r["heading_similarity"],
                body_similarity=r["body_similarity"],
                old_block_id=r["old_block_id"],
                new_block_id=r["new_block_id"],
                old_text=old.full_text if old else None,
                new_text=new.full_text if new else None,
                sentences=sentences,
                stats=r["stats"],
                signals=signals,
                interpretation=interpretation,
            )
        )
    changes.sort(key=lambda c: (-c.score, c.id))
    for i, c in enumerate(changes, start=1):
        c.rank = i

    by_type = {t: 0 for t in CHANGE_TYPES}
    by_cat = {c: 0 for c in CATEGORIES}
    for c in changes:
        by_type[c.change_type] += 1
        for cat in c.categories:
            by_cat[cat] += 1
    if llm_info["provider"] is None:
        interp_status = "unavailable"
    elif any(c.interpretation.status in ("ok", "empty") for c in changes):
        interp_status = "ok"
    else:
        interp_status = "skipped"

    notes: list[str] = []
    if ctx.fixture:
        notes.append("FIXTURE: synthetic development data; not derived from any SEC filing.")
    if emb.backend == "lexical-fallback":
        notes.append(
            "Embeddings: the Hugging Face model could not be loaded in this environment, so a deterministic lexical (TF-IDF) fallback matched the risks. Heavily reworded risks may appear as removed + new."
        )
    if emb.truncation_count:
        notes.append(
            f"{emb.truncation_count} risk blocks exceeded the embedding model's maximum length and were chunked and mean-pooled."
        )
    if interp_status == "unavailable":
        notes.append(llm_info["reason"] or "LLM stage unavailable.")
    notes.append(DISCLAIMER)

    comp = Comparison(
        schema_version=SCHEMA_VERSION,
        analysis_id=analysis_id(fetch.old.accession_number, fetch.new.accession_number, model_ids),
        pipeline_version=PIPELINE_VERSION if not ctx.fixture else PIPELINE_VERSION,
        rubric_version=RUBRIC_VERSION,
        model_ids=model_ids,
        is_fixture=ctx.fixture,
        company=fetch.company,
        old_filing=_filing_meta(fetch.old, sections["old"], segs["old"]),
        new_filing=_filing_meta(fetch.new, sections["new"], segs["new"]),
        filing_selection_note=fetch.selection_note,
        summary=Summary(
            total_changes=len(changes),
            by_change_type=by_type,
            by_category=by_cat,
            old_block_count=len(segs["old"].blocks),
            new_block_count=len(segs["new"].blocks),
            matched_pairs=len(matches.pairs),
            interpretation_status=interp_status,
            max_score=max((c.score for c in changes), default=0),
        ),
        thresholds=thresholds,
        changes=changes,
        sentence_index=sentence_index,
        notes=notes,
    )
    return comp


def run_final_stages(ctx: RunContext, ticker: str):
    segs = ctx.outputs["segments"]
    records = ctx.outputs["diff_records"]
    fetch = ctx.outputs["fetch"]

    ctx.emit(6, "started", ticker=ticker)
    sig_rows = stage6_signals(ctx, segs, records)
    ctx.outputs["signal_rows"] = sig_rows
    n_h2a = sum(len(s["signals"]["hypothetical_to_actual"]) for s in sig_rows)
    n_ent = sum(len(s["signals"]["new_entities"]) for s in sig_rows)
    n_qty = sum(len(s["signals"]["new_quantities"]) for s in sig_rows)
    ctx.emit(
        6,
        "done",
        f"{n_h2a} hedge-to-actual, {n_ent} new entities, {n_qty} new quantities",
        ticker=ticker,
    )
    if ctx.until_stage <= 6:
        return ctx

    ctx.emit(7, "started", ticker=ticker)
    llm_rows, llm_info = stage7_llm(ctx, segs, records, fetch)
    ctx.outputs["llm_rows"] = llm_rows
    ctx.outputs["llm_info"] = llm_info
    if llm_info["provider"] is None:
        ctx.emit(7, "done", f"skipped: {llm_info['reason']}", ticker=ticker)
    else:
        n_ok = sum(1 for r in llm_rows if r and r["status"] in ("ok", "empty"))
        ctx.emit(
            7,
            "done",
            f"{llm_info['model_id']}: {n_ok} changes interpreted ({ctx.outputs.get('llm_calls', 0)} live calls, rest cached)",
            ticker=ticker,
        )
    if ctx.until_stage <= 7:
        return ctx

    ctx.emit(8, "started", ticker=ticker)
    comp = assemble(ctx, ticker, records, sig_rows, llm_rows, llm_info)
    path = publish(comp, ctx.settings.published_dir, ctx.settings.data_dir / "scratch")
    ctx.outputs["comparison"] = comp
    ctx.outputs["published_path"] = str(path)
    ctx.emit(
        8,
        "done",
        f"{len(comp.changes)} changes, top score {comp.summary.max_score}, analysis_id {comp.analysis_id[:12]}…",
        ticker=ticker,
    )
    return ctx
