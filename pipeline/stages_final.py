"""Stages 6-8: deterministic signals, LLM rubric/interpretation, score + publish."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import TYPE_CHECKING

from pipeline import llm as llm_mod
from pipeline import signals as signals_mod
from pipeline.config import NER_MODEL_ID, PIPELINE_VERSION, SENTENCE_SPLITTER_ID
from pipeline.diff import diff_params_for
from pipeline.errors import PipelineError
from pipeline.highlights import select_highlights, truncate_heading
from pipeline.publish import publish
from pipeline.rubric import RUBRIC_VERSION
from pipeline.schema import (
    CATEGORIES,
    CHANGE_TYPES,
    MAX_SHORT_TITLE_WORDS,
    SCHEMA_VERSION,
    Change,
    Comparison,
    FilingMeta,
    Interpretation,
    ModelIds,
    Sentence,
    SentenceLocation,
    Signals,
    Summary,
    Thresholds,
)
from pipeline.score import analysis_id, change_id, code_fingerprint, score_change
from pipeline.stages_late import get_embedder
from pipeline.types import FilingRecord, RiskBlock, SegmentedFiling
from pipeline.validate import banned_language, validate_llm_output

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

DEFAULT_LLM_CONCURRENCY = 6
MAX_LLM_CONCURRENCY = 16


def llm_concurrency() -> int:
    """Parallel LLM calls (RISKDIFF_LLM_CONCURRENCY, default 6, clamped to 1-16)."""
    raw = (os.environ.get("RISKDIFF_LLM_CONCURRENCY") or "").strip()
    try:
        n = int(raw) if raw else DEFAULT_LLM_CONCURRENCY
    except ValueError:
        n = DEFAULT_LLM_CONCURRENCY
    return max(1, min(MAX_LLM_CONCURRENCY, n))


def _llm_key_inputs(
    prompt_hash: str,
    model_id: str,
    old: RiskBlock | None,
    new: RiskBlock | None,
    sentences: list[Sentence],
    fetch,
) -> dict:
    return {
        "prompt_sha256": prompt_hash,
        "model_id": model_id,
        "old": [[s.id, s.text] for s in old.sentences] if old else None,
        "new": [[s.id, s.text] for s in new.sentences] if new else None,
        "diff": [(s.id, s.status) for s in sentences],
        "fy": [fetch.old.fiscal_year, fetch.new.fiscal_year],
    }


def stage7_llm(
    ctx: RunContext, segs: dict[str, SegmentedFiling], records: list[dict], fetch
) -> tuple[list[dict | None], dict]:
    """Returns (per-record raw LLM results or None, provider info).

    Only the RAW parsed model output is cached (never validated claims), so the citation validator
    runs on every load. Provider errors are never cached. When every change is already cached for
    a configured model, the provider is not probed at all (offline replay stays deterministic)."""
    settings = ctx.settings
    prompt_hash = llm_mod.prompt_sha256()
    candidates = [(i, r) for i, r in enumerate(records) if r["change_type"] != "largely_unchanged"]
    prepared = []
    for i, r in candidates:
        old, new = _blocks(segs, r)
        prepared.append(
            (
                i,
                r,
                old,
                new,
                (new or old).heading,
                [Sentence.model_validate(s) for s in r["sentences"]],
            )
        )

    def cached_rows(model_id: str) -> list[dict | None] | None:
        rows: list[dict | None] = [None] * len(records)
        for i, _r, old, new, _title, sentences in prepared:
            key = ctx.cache.key(
                "llm",
                llm_mod.STAGE_VERSION,
                _llm_key_inputs(prompt_hash, model_id, old, new, sentences, fetch),
            )
            hit = ctx.cache.peek("llm", key)
            if hit is None:
                return None
            rows[i] = hit
        return rows

    client = ctx.outputs.get("llm_client")
    reason = ctx.outputs.get("llm_reason")
    results: list[dict | None] | None = None
    info: dict = {"provider": None, "model_id": None, "prompt_sha256": None, "reason": None}
    if not prepared:
        # nothing for the LLM to do (every change is largely unchanged): no provider probe, so the
        # published output does not depend on network availability
        return [None] * len(records), {
            "provider": None,
            "model_id": None,
            "prompt_sha256": None,
            "reason": "No change required the LLM stage.",
        }
    if client is None and reason is None and not ctx.refresh_llm:
        for provider, model_id in (
            ("huggingface", f"hf:{settings.llm_model}"),
            ("gemini", f"gemini:{settings.gemini_model}"),
        ):
            rows = cached_rows(model_id)
            if rows is not None:
                results = rows
                info = {
                    "provider": provider,
                    "model_id": model_id,
                    "prompt_sha256": prompt_hash,
                    "reason": None,
                }
                log.info(
                    "LLM stage: all %d changes served from cache for %s (no provider probe)",
                    len(prepared),
                    model_id,
                )
                break
    if results is None:
        if client is None and reason is None:
            client, reason = llm_mod.select_client(settings)
            ctx.outputs["llm_client"] = client
            ctx.outputs["llm_reason"] = reason
            if client is None:
                log.warning("%s", reason)
            else:
                log.info("LLM provider: %s (%s)", client.provider, client.model_id)
        info = {
            "provider": client.provider if client else None,
            "model_id": client.model_id if client else None,
            "prompt_sha256": prompt_hash if client else None,
            "reason": reason if client is None else None,
        }
        results = [None] * len(records)
        calls = 0
        if client is not None:
            todo = []
            for i, _r, old, new, title, sentences in prepared:
                key = ctx.cache.key(
                    "llm",
                    llm_mod.STAGE_VERSION,
                    _llm_key_inputs(prompt_hash, client.model_id, old, new, sentences, fetch),
                )
                hit = None if ctx.refresh_llm else ctx.cache.get("llm", key)
                if hit is not None:
                    results[i] = hit
                else:
                    todo.append((i, key, old, new, title, sentences))
            calls = len(todo)
            ctx.check_cancelled()

            def call(item):
                _i, _key, old, new, title, sentences = item
                return llm_mod.interpret_change(
                    client, title, old, new, sentences, fetch.old.fiscal_year, fetch.new.fiscal_year
                )

            # Calls are independent and each result keeps its record's slot, so running them
            # concurrently changes wall time only, never the output.
            workers = max(1, min(llm_concurrency(), len(todo) or 1))
            log.info("LLM stage: %d calls, %d at a time", len(todo), workers)
            pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="llm")
            futures = [pool.submit(call, item) for item in todo]
            finished = False
            try:
                for (i, key, *_rest), fut in zip(todo, futures, strict=True):
                    while True:
                        try:
                            res = fut.result(timeout=0.5)
                            break
                        except FuturesTimeout:
                            ctx.check_cancelled()
                    row = {
                        "status": res.status,
                        "model_id": res.model_id,
                        "provider": client.provider,
                        "attempts": res.attempts,
                        "error": res.error,
                        "raw": res.raw,
                    }
                    if res.status != "error":
                        ctx.cache.put("llm", key, row)
                    results[i] = row
                finished = True
            finally:
                # on cancel/error, drop queued calls and do not wait for in-flight ones
                pool.shutdown(wait=finished, cancel_futures=True)
        ctx.outputs["llm_calls"] = calls
    return results, info


def build_interpretation(
    r: dict, llm_res: dict | None, info: dict, allowed: dict[str, str]
) -> Interpretation:
    if r["change_type"] == "largely_unchanged":
        return Interpretation(
            status="skipped", reason="Not run for largely unchanged risks.", model_id=None
        )
    if info["provider"] is None:
        return Interpretation(status="unavailable", reason=info["reason"], model_id=None)
    if (
        llm_res is None
        or llm_res.get("status") == "error"
        or not isinstance(llm_res.get("raw"), dict)
    ):
        return Interpretation(
            status="unavailable",
            reason=f"The model did not return valid output after {llm_mod.MAX_ATTEMPTS} attempts.",
            model_id=info["model_id"],
        )
    v = validate_llm_output(
        llm_res["raw"], allowed
    )  # the validator runs on EVERY load, cached or not
    status = "ok" if v.claims else "empty"
    reason = (
        None
        if v.claims
        else (
            f"All {v.dropped_claim_count} interpretation claims were dropped by the citation validator."
            if v.dropped_claim_count
            else "The model returned no interpretation claims."
        )
    )
    return Interpretation(
        status=status,
        reason=reason,
        model_id=llm_res["model_id"],
        rubric=v.rubric,
        claims=v.claims,
        dropped_claim_count=v.dropped_claim_count,
        dropped_reasons=v.dropped_reasons,
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


def short_titles_for(
    ctx: RunContext, records: list[dict], segs: dict[str, SegmentedFiling], llm_info: dict
) -> dict[str, str]:
    """change_id -> LLM short title (raw, cached); empty when no provider. One batch call."""
    from pipeline.score import change_id

    client = ctx.outputs.get("llm_client")
    if client is None:
        return {}
    items = []
    for r in records:
        old, new = _blocks(segs, r)
        items.append((change_id(r["old_block_id"], r["new_block_id"]), (new or old).heading))
    items.sort()
    key = ctx.cache.key(
        "llm",
        llm_mod.STAGE_VERSION,
        {
            "kind": "short_titles",
            "prompt_sha256": llm_mod.short_title_prompt_sha256(),
            "model_id": client.model_id,
            "items": items,
        },
    )
    raw = None if ctx.refresh_llm else ctx.cache.get("llm", key)
    if raw is None:
        raw = llm_mod.short_titles_raw(client, items)
        if raw is None:
            return {}
        ctx.cache.put("llm", key, raw)
    return {t["change_id"]: t["short_title"] for t in raw.get("titles", []) if isinstance(t, dict)}


_STOP = frozenset(
    "a an the of to and or in on for with by our we us its their is are may could might".split()
)


def validated_short_title(heading: str, proposed: str | None) -> str:
    """Accept the LLM label only if it is short, neutral and anchored to the heading; otherwise
    fall back to a deterministic truncation of the real heading."""
    if proposed:
        t = " ".join(str(proposed).split()).strip().strip('"\u201c\u201d.')
        words = t.split()
        if 1 <= len(words) <= MAX_SHORT_TITLE_WORDS and banned_language(t) is None:
            hw = {w.strip(".,;:()\u2019'\"").lower() for w in heading.split()} - _STOP
            tw = {w.strip(".,;:()\u2019'\"").lower() for w in words} - _STOP
            if hw & tw:
                return t
    return truncate_heading(heading, MAX_SHORT_TITLE_WORDS)


def assemble(
    ctx: RunContext,
    ticker: str,
    records: list[dict],
    sig_rows: list[dict],
    llm_rows: list[dict | None],
    llm_info: dict,
) -> Comparison:
    llm_titles = short_titles_for(ctx, records, ctx.outputs["segments"], llm_info)
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
    diff_params = diff_params_for(emb.backend)
    thresholds = Thresholds(
        match_threshold=matches.params.match_threshold,
        heading_weight=matches.params.heading_weight,
        body_weight=matches.params.body_weight,
        sentence_match_threshold=diff_params.sentence_match_threshold,
        sentence_unchanged_threshold=diff_params.sentence_unchanged_threshold,
        expanded_ratio=diff_params.expanded_ratio,
        reworded_similarity=diff_params.reworded_similarity,
    )
    fingerprint = code_fingerprint()

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
        interpretation = build_interpretation(r, lr, llm_info, llm_mod.allowed_sentences(old, new))
        score, breakdown = score_change(
            r["change_type"],
            sentences,
            signals,
            interpretation,
            r["similarity"],
            diff_params.reworded_similarity,
        )
        cid = change_id(r["old_block_id"], r["new_block_id"])
        changes.append(
            Change(
                id=cid,
                rank=1,
                title=(new or old).heading,
                short_title=validated_short_title((new or old).heading, llm_titles.get(cid)),
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
    if (
        llm_info["provider"] is None
        and llm_info.get("reason") == "No change required the LLM stage."
    ):
        interp_status = "skipped"
    elif llm_info["provider"] is None:
        interp_status = "unavailable"
    elif any(c.interpretation.status in ("ok", "empty") for c in changes):
        interp_status = "ok"
    elif all(c.interpretation.status == "skipped" for c in changes):
        interp_status = "skipped"
    else:
        interp_status = "unavailable"

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
        analysis_id=analysis_id(
            fetch.old.accession_number, fetch.new.accession_number, model_ids, fingerprint
        ),
        pipeline_version=PIPELINE_VERSION,
        rubric_version=RUBRIC_VERSION,
        code_fingerprint=fingerprint,
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
        highlights=select_highlights(changes, sentence_index),
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

    errored = [r for r in llm_rows if r and r.get("status") == "error"]
    if errored and os.environ.get("RISKDIFF_ALLOW_PARTIAL_LLM", "") != "1":
        raise PipelineError(
            f"The LLM provider failed for {len(errored)} change(s) after retries; publishing would make the output "
            "depend on a transient failure. Rerun (cached changes are reused) or set RISKDIFF_ALLOW_PARTIAL_LLM=1.",
            code="llm_errors",
        )

    ctx.emit(8, "started", ticker=ticker)
    comp = assemble(ctx, ticker, records, sig_rows, llm_rows, llm_info)
    path = publish(
        comp, ctx.settings.published_dir, ctx.settings.data_dir / "scratch", force=ctx.force_publish
    )
    ctx.outputs["comparison"] = comp
    ctx.outputs["published_path"] = str(path)
    ctx.emit(
        8,
        "done",
        f"{len(comp.changes)} changes, top score {comp.summary.max_score}, analysis_id {comp.analysis_id[:12]}…",
        ticker=ticker,
    )
    return ctx
