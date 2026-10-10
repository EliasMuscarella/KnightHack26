"""Stage 5: sentence-level diff inside each matched block pair, and change_type rules.

Sentence alignment: order-preserving dynamic programming (weighted longest common subsequence)
over a similarity matrix sim(a, b) = 0.5 * word-level SequenceMatcher ratio + 0.5 * embedding
cosine. Pairs below `sentence_match_threshold` cannot align. Aligned pairs whose normalized text
is identical are `unchanged`; otherwise `modified`, with word-level spans from difflib
(deterministic, autojunk disabled). Unaligned old sentences are `removed`, new ones `added`.

`classify_change_type` is the ONLY place change types are decided; its rules are in its docstring.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import dataclass

import numpy as np

from pipeline.schema import DiffSpan, DiffStats, Sentence
from pipeline.types import RiskBlock

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.1"

TOKEN_RE = re.compile(r"\s+|\w+(?:[’'\-]\w+)*|[^\w\s]")
_NORM_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class DiffParams:
    sentence_match_threshold: float = 0.45
    sentence_unchanged_threshold: float = (
        1.0  # unchanged == exact after whitespace/quote normalization
    )
    expanded_ratio: float = 0.15
    reworded_similarity: float = 0.80
    minor_ratio: float = 0.05
    reworded_total_ratio: float = 0.30
    both_sides_ratio: float = 0.25

    def to_dict(self) -> dict:
        return dict(self.__dict__)


DEFAULT_DIFF_PARAMS = DiffParams()
# TF-IDF cosine lives on a lower scale than dense cosine, so rule 8's similarity floor differs.
DIFF_PARAMS_BY_BACKEND = {
    "sentence-transformers": DEFAULT_DIFF_PARAMS,
    "lexical-fallback": DiffParams(reworded_similarity=0.45),
}


def diff_params_for(backend: str) -> DiffParams:
    return DIFF_PARAMS_BY_BACKEND.get(backend, DEFAULT_DIFF_PARAMS)


def normalize_sentence(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-")
    return _NORM_RE.sub(" ", s).strip().lower()


def words(s: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(s) if t.strip() and (t[0].isalnum())]


def lexical_ratio(a: str, b: str) -> float:
    wa, wb = [w.lower() for w in words(a)], [w.lower() for w in words(b)]
    if not wa and not wb:
        return 1.0
    return difflib.SequenceMatcher(a=wa, b=wb, autojunk=False).ratio()


def word_spans(old: str, new: str) -> tuple[list[DiffSpan], list[DiffSpan]]:
    """Word-level diff. Old side gets equal/delete spans, new side equal/insert spans; each
    side's spans concatenate back to its exact text."""
    a, b = TOKEN_RE.findall(old), TOKEN_RE.findall(new)
    assert "".join(a) == old and "".join(b) == new
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    old_spans: list[DiffSpan] = []
    new_spans: list[DiffSpan] = []

    def push(spans: list[DiffSpan], op: str, text: str) -> None:
        if not text:
            return
        if spans and spans[-1].op == op:
            spans[-1] = DiffSpan(op=op, text=spans[-1].text + text)
        else:
            spans.append(DiffSpan(op=op, text=text))

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            push(old_spans, "equal", "".join(a[i1:i2]))
            push(new_spans, "equal", "".join(b[j1:j2]))
        if tag in ("delete", "replace"):
            push(old_spans, "delete", "".join(a[i1:i2]))
        if tag in ("insert", "replace"):
            push(new_spans, "insert", "".join(b[j1:j2]))
    # whitespace-only changed spans are noise: fold them into neighbors as equal
    old_spans = _fold_ws(old_spans)
    new_spans = _fold_ws(new_spans)
    return old_spans, new_spans


def _fold_ws(spans: list[DiffSpan]) -> list[DiffSpan]:
    out: list[DiffSpan] = []
    for sp in spans:
        op = "equal" if (sp.op != "equal" and not sp.text.strip()) else sp.op
        if out and out[-1].op == op:
            out[-1] = DiffSpan(op=op, text=out[-1].text + sp.text)
        else:
            out.append(DiffSpan(op=op, text=sp.text))
    return out


def align_sentences(sim: np.ndarray, threshold: float) -> list[tuple[int, int]]:
    """Monotonic alignment maximizing total similarity of aligned pairs (weighted LCS)."""
    n, m = sim.shape
    score = np.zeros((n + 1, m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(score[i - 1, j], score[i, j - 1])
            s = sim[i - 1, j - 1]
            if s >= threshold:
                best = max(best, score[i - 1, j - 1] + s)
            score[i, j] = best
    pairs: list[tuple[int, int]] = []
    i, j = n, m
    while i > 0 and j > 0:
        s = sim[i - 1, j - 1]
        if s >= threshold and abs(score[i, j] - (score[i - 1, j - 1] + s)) < 1e-12:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif score[i - 1, j] >= score[i, j - 1]:
            i -= 1
        else:
            j -= 1
    return pairs[::-1]


def sentence_similarity(
    old: RiskBlock, new: RiskBlock, old_vecs: np.ndarray | None, new_vecs: np.ndarray | None
) -> np.ndarray:
    n, m = len(old.sentences), len(new.sentences)
    sim = np.zeros((n, m))
    emb = None
    if old_vecs is not None and new_vecs is not None and len(old_vecs) == n and len(new_vecs) == m:
        emb = np.clip(np.asarray(old_vecs) @ np.asarray(new_vecs).T, 0.0, 1.0)
    for i, a in enumerate(old.sentences):
        for j, b in enumerate(new.sentences):
            if normalize_sentence(a.text) == normalize_sentence(b.text):
                sim[i, j] = 1.0
                continue
            lex = lexical_ratio(a.text, b.text)
            sim[i, j] = 0.5 * lex + 0.5 * float(emb[i, j]) if emb is not None else lex
    return sim


@dataclass
class PairDiff:
    sentences: list[Sentence]
    stats: DiffStats
    change_type: str


def _wc(s: str) -> int:
    return len(words(s))


def diff_pair(
    old: RiskBlock | None,
    new: RiskBlock | None,
    *,
    similarity: float | None,
    old_vecs: np.ndarray | None = None,
    new_vecs: np.ndarray | None = None,
    params: DiffParams = DEFAULT_DIFF_PARAMS,
) -> PairDiff:
    sentences: list[Sentence] = []
    added = removed = modified = unchanged = 0
    added_wc = removed_wc = 0
    pair_index = 0

    if old is None or new is None:
        side = "new" if old is None else "old"
        blk = new if old is None else old
        status = "added" if old is None else "removed"
        for s in blk.sentences:
            sentences.append(
                Sentence(id=s.id, side=side, status=status, text=s.text, pair_index=pair_index)
            )
            pair_index += 1
        if old is None:
            added, added_wc = len(blk.sentences), sum(_wc(s.text) for s in blk.sentences)
        else:
            removed, removed_wc = len(blk.sentences), sum(_wc(s.text) for s in blk.sentences)
    else:
        sim = sentence_similarity(old, new, old_vecs, new_vecs)
        aligned = align_sentences(sim, params.sentence_match_threshold)
        ai = {i: j for i, j in aligned}
        aj = {j: i for i, j in aligned}
        i = j = 0
        n, m = len(old.sentences), len(new.sentences)
        while i < n or j < m:
            if i < n and i not in ai:
                s = old.sentences[i]
                sentences.append(
                    Sentence(
                        id=s.id, side="old", status="removed", text=s.text, pair_index=pair_index
                    )
                )
                removed += 1
                removed_wc += _wc(s.text)
                pair_index += 1
                i += 1
                continue
            if j < m and j not in aj:
                s = new.sentences[j]
                sentences.append(
                    Sentence(
                        id=s.id, side="new", status="added", text=s.text, pair_index=pair_index
                    )
                )
                added += 1
                added_wc += _wc(s.text)
                pair_index += 1
                j += 1
                continue
            # both aligned: they must be aligned to each other (monotonic alignment)
            a, b = old.sentences[i], new.sentences[j]
            assert ai[i] == j, (i, j, ai)
            score = round(float(sim[i, j]), 4)
            if normalize_sentence(a.text) == normalize_sentence(b.text):
                sentences.append(
                    Sentence(
                        id=a.id,
                        side="old",
                        status="unchanged",
                        text=a.text,
                        pair_index=pair_index,
                        counterpart_id=b.id,
                        alignment_similarity=score,
                    )
                )
                sentences.append(
                    Sentence(
                        id=b.id,
                        side="new",
                        status="unchanged",
                        text=b.text,
                        pair_index=pair_index,
                        counterpart_id=a.id,
                        alignment_similarity=score,
                    )
                )
                unchanged += 1
            else:
                os_, ns_ = word_spans(a.text, b.text)
                sentences.append(
                    Sentence(
                        id=a.id,
                        side="old",
                        status="modified",
                        text=a.text,
                        pair_index=pair_index,
                        counterpart_id=b.id,
                        alignment_similarity=score,
                        diff_spans=os_,
                    )
                )
                sentences.append(
                    Sentence(
                        id=b.id,
                        side="new",
                        status="modified",
                        text=b.text,
                        pair_index=pair_index,
                        counterpart_id=a.id,
                        alignment_similarity=score,
                        diff_spans=ns_,
                    )
                )
                modified += 1
                removed_wc += sum(_wc(sp.text) for sp in os_ if sp.op == "delete")
                added_wc += sum(_wc(sp.text) for sp in ns_ if sp.op == "insert")
            pair_index += 1
            i += 1
            j += 1

    stats = DiffStats(
        old_sentence_count=len(old.sentences) if old else 0,
        new_sentence_count=len(new.sentences) if new else 0,
        added=added,
        removed=removed,
        modified=modified,
        unchanged=unchanged,
        old_word_count=_wc(old.full_text) if old else 0,
        new_word_count=_wc(new.full_text) if new else 0,
        added_word_count=added_wc,
        removed_word_count=removed_wc,
    )
    return PairDiff(
        sentences=sentences,
        stats=stats,
        change_type=classify_change_type(stats, similarity, params),
    )


def classify_change_type(
    stats: DiffStats, similarity: float | None, params: DiffParams = DEFAULT_DIFF_PARAMS
) -> str:
    """Deterministic change_type rules (the only place these are decided).

    Let added = added_word_count / new_word_count and removed = removed_word_count / old_word_count
    (words in added/removed sentences plus inserted/deleted spans of modified sentences).

    1. No old block                                      -> "new"
    2. No new block                                      -> "removed"
    3. added < minor_ratio and removed < minor_ratio     -> "largely_unchanged"   (minor_ratio = 0.05)
    4. added >= both_sides_ratio and removed >= both_sides_ratio
       (substantial change in both directions, 0.25)    -> "materially_reworded"
    5. added - removed >= 0.10 and added >= expanded_ratio (0.15)    -> "expanded"
    6. removed - added >= 0.10 and removed >= expanded_ratio (0.15)  -> "reduced"
    7. added + removed >= reworded_total_ratio (0.30)    -> "materially_reworded"
    8. similarity known and similarity < reworded_similarity (0.80)
       and added + removed >= expanded_ratio             -> "materially_reworded"
    9. otherwise (small edits)                           -> "largely_unchanged"
    """

    if stats.old_word_count == 0 and stats.new_word_count > 0:
        return "new"
    if stats.new_word_count == 0 and stats.old_word_count > 0:
        return "removed"
    added = stats.added_word_count / max(1, stats.new_word_count)
    removed = stats.removed_word_count / max(1, stats.old_word_count)
    total = added + removed
    net = added - removed
    if added < params.minor_ratio and removed < params.minor_ratio:
        return "largely_unchanged"
    if added >= params.both_sides_ratio and removed >= params.both_sides_ratio:
        return "materially_reworded"
    if net >= 0.10 and added >= params.expanded_ratio:
        return "expanded"
    if -net >= 0.10 and removed >= params.expanded_ratio:
        return "reduced"
    if total >= params.reworded_total_ratio:
        return "materially_reworded"
    if (
        similarity is not None
        and similarity < params.reworded_similarity
        and total >= params.expanded_ratio
    ):
        return "materially_reworded"
    return "largely_unchanged"
