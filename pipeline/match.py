"""Stage 4: match risk blocks across the two filings.

similarity(i, j) = heading_weight * cos(heading_i, heading_j) + body_weight * cos(body_i, body_j)
Optimal one-to-one assignment with scipy's linear_sum_assignment on cost = 1 - similarity.
Assigned pairs below `match_threshold` are rejected; unmatched old blocks are "removed" risks,
unmatched new blocks are "new" risks. Thresholds differ per embedding backend (dense cosine and
TF-IDF cosine live on different scales) and are recalibrated by eval/eval.py.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from pipeline.embed import BlockEmbeddings

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.0"


@dataclass(frozen=True)
class MatchParams:
    match_threshold: float
    heading_weight: float = 0.4
    body_weight: float = 0.6

    def to_dict(self) -> dict:
        return asdict(self)


# Placeholder thresholds; eval/eval.py recalibrates and records the chosen values.
DEFAULT_PARAMS = {
    "sentence-transformers": MatchParams(match_threshold=0.62, heading_weight=0.4, body_weight=0.6),
    "lexical-fallback": MatchParams(match_threshold=0.20, heading_weight=0.4, body_weight=0.6),
}


@dataclass
class Pair:
    old_index: int
    new_index: int
    similarity: float
    heading_similarity: float
    body_similarity: float


@dataclass
class MatchResult:
    pairs: list[Pair]
    unmatched_old: list[int]
    unmatched_new: list[int]
    params: MatchParams
    backend: str
    rejected: list[Pair]

    def to_dict(self) -> dict:
        return {
            "pairs": [asdict(p) for p in self.pairs],
            "unmatched_old": self.unmatched_old,
            "unmatched_new": self.unmatched_new,
            "params": self.params.to_dict(),
            "backend": self.backend,
            "rejected": [asdict(p) for p in self.rejected],
        }

    @staticmethod
    def from_dict(d: dict) -> MatchResult:
        return MatchResult(
            pairs=[Pair(**p) for p in d["pairs"]],
            unmatched_old=list(d["unmatched_old"]),
            unmatched_new=list(d["unmatched_new"]),
            params=MatchParams(**d["params"]),
            backend=d["backend"],
            rejected=[Pair(**p) for p in d.get("rejected", [])],
        )


def params_for(backend: str, override: MatchParams | None = None) -> MatchParams:
    return override or DEFAULT_PARAMS.get(backend, DEFAULT_PARAMS["sentence-transformers"])


def similarity_matrices(
    emb: BlockEmbeddings, params: MatchParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ho, hn = (
        np.asarray(emb.heading["old"], dtype=np.float64),
        np.asarray(emb.heading["new"], dtype=np.float64),
    )
    bo, bn = (
        np.asarray(emb.body["old"], dtype=np.float64),
        np.asarray(emb.body["new"], dtype=np.float64),
    )
    if ho.size == 0 or hn.size == 0:
        z = np.zeros((ho.shape[0], hn.shape[0]))
        return z, z, z
    h = np.clip(ho @ hn.T, -1.0, 1.0)
    b = np.clip(bo @ bn.T, -1.0, 1.0)
    s = params.heading_weight * h + params.body_weight * b
    return s, h, b


def match_blocks(emb: BlockEmbeddings, params: MatchParams | None = None) -> MatchResult:
    p = params_for(emb.backend, params)
    s, h, b = similarity_matrices(emb, p)
    n_old, n_new = s.shape
    pairs: list[Pair] = []
    rejected: list[Pair] = []
    if n_old and n_new:
        rows, cols = linear_sum_assignment(1.0 - s)
        for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
            pair = Pair(
                i, j, round(float(s[i, j]), 4), round(float(h[i, j]), 4), round(float(b[i, j]), 4)
            )
            (pairs if s[i, j] >= p.match_threshold else rejected).append(pair)
    matched_old = {q.old_index for q in pairs}
    matched_new = {q.new_index for q in pairs}
    res = MatchResult(
        pairs=sorted(pairs, key=lambda q: (q.new_index, q.old_index)),
        unmatched_old=[i for i in range(n_old) if i not in matched_old],
        unmatched_new=[j for j in range(n_new) if j not in matched_new],
        params=p,
        backend=emb.backend,
        rejected=rejected,
    )
    log.info(
        "stage4: %d matched pairs, %d removed (old-only), %d new (new-only), %d assignments rejected below %.2f",
        len(res.pairs),
        len(res.unmatched_old),
        len(res.unmatched_new),
        len(rejected),
        p.match_threshold,
    )
    return res
