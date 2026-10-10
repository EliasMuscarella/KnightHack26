"""Stages 3-8 orchestration (split from run.py to keep stage 0-2 importable without ML deps)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

import numpy as np

from pipeline import diff as diff_mod
from pipeline import embed as embed_mod
from pipeline import match as match_mod
from pipeline.embed import BlockEmbeddings, Embedder, LexicalEmbedder
from pipeline.match import MatchResult
from pipeline.types import RiskBlock, SegmentedFiling

if TYPE_CHECKING:
    from pipeline.run import RunContext

log = logging.getLogger("pipeline")


def _blocks_hash(segs: dict[str, SegmentedFiling]) -> str:
    """Includes accession numbers and block ids: cached outputs carry ids, so identical text under
    different accessions must not share a cache entry."""
    payload = {
        side: [segs[side].accession_number, [[b.id, b.heading, b.body] for b in segs[side].blocks]]
        for side in ("old", "new")
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def _sentences_hash(segs: dict[str, SegmentedFiling]) -> str:
    payload = {
        side: [
            segs[side].accession_number,
            [[b.id, [[s.id, s.text] for s in b.sentences]] for b in segs[side].blocks],
        ]
        for side in ("old", "new")
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()


def get_embedder(ctx: RunContext) -> Embedder:
    emb = ctx.outputs.get("embedder")
    if emb is None:
        emb = embed_mod.load_embedder(ctx.settings, allow_lexical=ctx.fixture)
        ctx.outputs["embedder"] = emb
    return emb


def _embedding_identity(ctx: RunContext) -> dict:
    """What the stage-3 cache key depends on, without loading the model when it is cached."""
    emb = ctx.outputs.get("embedder")
    if emb is not None:
        return {"model_id": emb.model_id, "backend": emb.backend}
    # Not loaded yet: we must load to know which backend is in use (fallback or not).
    emb = get_embedder(ctx)
    return {"model_id": emb.model_id, "backend": emb.backend}


def stage3_embed(ctx: RunContext, segs: dict[str, SegmentedFiling]) -> BlockEmbeddings:
    ident = _embedding_identity(ctx)
    return ctx.cached(
        3,
        embed_mod.STAGE_VERSION,
        {"blocks": _blocks_hash(segs), **ident},
        lambda: embed_mod.embed_segments(segs, get_embedder(ctx)),
        load=BlockEmbeddings.from_dict,
        dump=lambda v: v.to_dict(),
    )


def stage4_match(ctx: RunContext, emb: BlockEmbeddings) -> MatchResult:
    params = match_mod.params_for(emb.backend)
    return ctx.cached(
        4,
        match_mod.STAGE_VERSION,
        {
            "heading": emb.heading,
            "body": emb.body,
            "params": params.to_dict(),
            "backend": emb.backend,
        },
        lambda: match_mod.match_blocks(emb, params),
        load=MatchResult.from_dict,
        dump=lambda v: v.to_dict(),
    )


def sentence_vectors(
    ctx: RunContext, segs: dict[str, SegmentedFiling], emb: BlockEmbeddings
) -> dict[str, dict[str, list[list[float]]]]:
    """Embed every sentence of every block (both sides) with the active embedder; cached."""

    def compute() -> dict:
        embedder = get_embedder(ctx)
        if isinstance(embedder, LexicalEmbedder):
            embedder = LexicalEmbedder()  # separate fit on the sentence corpus
            embedder.fit(
                [s.text for side in ("old", "new") for b in segs[side].blocks for s in b.sentences]
            )
        out: dict[str, dict[str, list[list[float]]]] = {"old": {}, "new": {}}
        for side in ("old", "new"):
            blocks = segs[side].blocks
            texts = [s.text for b in blocks for s in b.sentences]
            vecs = embedder.embed(texts)
            k = 0
            for b in blocks:
                n = len(b.sentences)
                out[side][b.id] = [[round(float(x), 5) for x in row] for row in vecs[k : k + n]]
                k += n
        return out

    return ctx.cached(
        5,
        diff_mod.STAGE_VERSION + "-sentvec",
        {"sentences": _sentences_hash(segs), "model_id": emb.model_id, "backend": emb.backend},
        compute,
    )


def stage5_diff(
    ctx: RunContext, segs: dict[str, SegmentedFiling], emb: BlockEmbeddings, matches: MatchResult
) -> list[dict]:
    """Return a list of change records (dicts) with sentences/stats/change_type per pair."""
    params = diff_mod.diff_params_for(emb.backend)

    def compute() -> list[dict]:
        svecs = sentence_vectors(ctx, segs, emb)
        old_blocks, new_blocks = segs["old"].blocks, segs["new"].blocks
        records: list[dict] = []

        def rec(old: RiskBlock | None, new: RiskBlock | None, pair) -> dict:
            ov = np.asarray(svecs["old"][old.id]) if old else None
            nv = np.asarray(svecs["new"][new.id]) if new else None
            d = diff_mod.diff_pair(
                old,
                new,
                similarity=pair.similarity if pair else None,
                old_vecs=ov,
                new_vecs=nv,
                params=params,
            )
            return {
                "old_block_id": old.id if old else None,
                "new_block_id": new.id if new else None,
                "old_index": old.index if old else None,
                "new_index": new.index if new else None,
                "similarity": pair.similarity if pair else None,
                "heading_similarity": pair.heading_similarity if pair else None,
                "body_similarity": pair.body_similarity if pair else None,
                "change_type": d.change_type,
                "stats": d.stats.model_dump(mode="json"),
                "sentences": [s.model_dump(mode="json") for s in d.sentences],
            }

        for p in matches.pairs:
            records.append(rec(old_blocks[p.old_index], new_blocks[p.new_index], p))
        for i in matches.unmatched_old:
            records.append(rec(old_blocks[i], None, None))
        for j in matches.unmatched_new:
            records.append(rec(None, new_blocks[j], None))
        return records

    return ctx.cached(
        5,
        diff_mod.STAGE_VERSION,
        {
            "sentences": _sentences_hash(segs),
            "matches": matches.to_dict(),
            "params": params.to_dict(),
            "model_id": emb.model_id,
        },
        compute,
    )


def run_late_stages(ctx: RunContext, ticker: str):
    segs = ctx.outputs["segments"]

    ctx.emit(3, "started", ticker=ticker)
    emb = stage3_embed(ctx, segs)
    ctx.outputs["embeddings"] = emb
    ctx.emit(
        3,
        "done",
        f"{emb.backend}: {emb.model_id}"
        + (f"; {emb.truncation_count} blocks chunked" if emb.truncation_count else ""),
        ticker=ticker,
    )
    if ctx.until_stage <= 3:
        return ctx

    ctx.emit(4, "started", ticker=ticker)
    matches = stage4_match(ctx, emb)
    ctx.outputs["matches"] = matches
    ctx.emit(
        4,
        "done",
        f"{len(matches.pairs)} matched, {len(matches.unmatched_old)} removed, {len(matches.unmatched_new)} new",
        ticker=ticker,
    )
    if ctx.until_stage <= 4:
        return ctx

    ctx.emit(5, "started", ticker=ticker)
    records = stage5_diff(ctx, segs, emb, matches)
    ctx.outputs["diff_records"] = records
    counts: dict[str, int] = {}
    for r in records:
        counts[r["change_type"]] = counts.get(r["change_type"], 0) + 1
    ctx.emit(5, "done", ", ".join(f"{v} {k}" for k, v in sorted(counts.items())), ticker=ticker)
    if ctx.until_stage <= 5:
        return ctx

    from pipeline.stages_final import run_final_stages

    return run_final_stages(ctx, ticker)
