"""Stage 3: embed risk blocks.

Primary backend: a local open-source Hugging Face model via sentence-transformers
(default BAAI/bge-m3, 8192-token context). The model's max sequence length is read
programmatically; texts longer than that are split into token chunks and mean-pooled
(weighted by chunk length) instead of being silently truncated. Truncation counts are logged.

Fallback backend (used automatically when the model cannot be loaded, e.g. no network and no
local cache): a deterministic lexical TF-IDF embedder fitted on the two filings being compared.
The backend in use is recorded in `model_ids` and therefore in `analysis_id`.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from pipeline.config import Settings
from pipeline.types import SegmentedFiling

log = logging.getLogger(__name__)

STAGE_VERSION = "0.1.0"
LEXICAL_MODEL_ID = "lexical-tfidf-v1 (fallback: Hugging Face model unavailable)"


class Embedder(Protocol):
    model_id: str
    backend: str
    max_seq_length: int | None
    truncation_count: int

    def fit(self, corpus: list[str]) -> None: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2norm(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


@dataclass
class SentenceTransformerEmbedder:
    model_id: str
    backend: str = "sentence-transformers"
    max_seq_length: int | None = None
    truncation_count: int = 0
    chunk_overlap: int = 32
    _model: object = field(default=None, repr=False)

    @classmethod
    def load(cls, model_id: str, hf_token: str | None) -> SentenceTransformerEmbedder:
        import torch
        from sentence_transformers import SentenceTransformer

        torch.manual_seed(0)
        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
        model = SentenceTransformer(model_id, token=hf_token, device="cpu")
        model.eval()
        inst = cls(model_id=model_id, _model=model)
        inst.max_seq_length = int(model.max_seq_length)
        log.info("embedding model %s loaded; max_seq_length=%d", model_id, inst.max_seq_length)
        return inst

    def fit(self, corpus: list[str]) -> None:  # dense models need no fitting
        return None

    def _token_ids(self, text: str) -> list[int]:
        tok = self._model.tokenizer
        return tok.encode(text, add_special_tokens=False)

    def _chunks(self, text: str) -> list[str]:
        assert self.max_seq_length
        budget = self.max_seq_length - 2  # room for special tokens
        ids = self._token_ids(text)
        if len(ids) <= budget:
            return [text]
        self.truncation_count += 1
        tok = self._model.tokenizer
        step = max(1, budget - self.chunk_overlap)
        out = []
        for start in range(0, len(ids), step):
            piece = ids[start : start + budget]
            out.append(tok.decode(piece, skip_special_tokens=True))
            if start + budget >= len(ids):
                break
        return out

    def embed(self, texts: list[str]) -> np.ndarray:
        import torch

        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        pieces: list[str] = []
        owner: list[int] = []
        weights: list[int] = []
        for i, t in enumerate(texts):
            for c in self._chunks(t):
                pieces.append(c)
                owner.append(i)
                weights.append(max(1, len(c.split())))
        with torch.inference_mode():
            vecs = self._model.encode(
                pieces,
                batch_size=8,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        vecs = np.asarray(vecs, dtype=np.float32)
        dim = vecs.shape[1]
        out = np.zeros((len(texts), dim), dtype=np.float32)
        wsum = np.zeros(len(texts), dtype=np.float32)
        for v, o, w in zip(vecs, owner, weights, strict=True):
            out[o] += v * w
            wsum[o] += w
        out /= np.maximum(wsum, 1.0)[:, None]
        return _l2norm(out)


_TOKEN_RE = re.compile(r"[a-z][a-z0-9\-']+")
_STOP = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the to we our with "
    "which could may might would will can not this these those such any all other than more".split()
)


@dataclass
class LexicalEmbedder:
    """Deterministic TF-IDF (uni+bigrams, sublinear tf) fitted on the texts being compared."""

    model_id: str = LEXICAL_MODEL_ID
    backend: str = "lexical-fallback"
    max_seq_length: int | None = None
    truncation_count: int = 0
    _vocab: dict[str, int] = field(default_factory=dict, repr=False)
    _idf: np.ndarray | None = field(default=None, repr=False)

    @staticmethod
    def _terms(text: str) -> list[str]:
        toks = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP]
        return toks + [f"{a} {b}" for a, b in zip(toks, toks[1:], strict=False)]

    def fit(self, corpus: list[str]) -> None:
        df: dict[str, int] = {}
        for doc in corpus:
            for term in set(self._terms(doc)):
                df[term] = df.get(term, 0) + 1
        self._vocab = {t: i for i, t in enumerate(sorted(df))}
        n = max(1, len(corpus))
        idf = np.zeros(len(self._vocab), dtype=np.float64)
        for t, i in self._vocab.items():
            idf[i] = np.log((1 + n) / (1 + df[t])) + 1.0
        self._idf = idf

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._idf is None:
            self.fit(texts)
        m = np.zeros((len(texts), len(self._vocab)), dtype=np.float64)
        for r, text in enumerate(texts):
            counts: dict[int, int] = {}
            for term in self._terms(text):
                j = self._vocab.get(term)
                if j is not None:
                    counts[j] = counts.get(j, 0) + 1
            for j, c in counts.items():
                m[r, j] = (1.0 + np.log(c)) * self._idf[j]
        return _l2norm(m)


def load_embedder(settings: Settings) -> Embedder:
    forced = os.environ.get("RISKDIFF_EMBED_BACKEND", "").strip().lower()
    if forced == "lexical":
        log.warning(
            "RISKDIFF_EMBED_BACKEND=lexical: using the deterministic lexical fallback embedder"
        )
        return LexicalEmbedder()
    try:
        return SentenceTransformerEmbedder.load(settings.embed_model, settings.hf_token)
    except Exception as e:  # network blocked, no cache, missing deps
        log.warning(
            "Could not load embedding model %s (%s: %s). Falling back to the lexical TF-IDF embedder. "
            "Matching quality is lower; this is recorded in model_ids.",
            settings.embed_model,
            type(e).__name__,
            str(e)[:160],
        )
        return LexicalEmbedder()


@dataclass
class BlockEmbeddings:
    model_id: str
    backend: str
    max_seq_length: int | None
    truncation_count: int
    heading: dict[str, list[list[float]]]  # side -> [n_blocks, dim]
    body: dict[str, list[list[float]]]
    full: dict[str, list[list[float]]]

    def to_dict(self) -> dict:
        return {
            "model_id": self.model_id,
            "backend": self.backend,
            "max_seq_length": self.max_seq_length,
            "truncation_count": self.truncation_count,
            "heading": self.heading,
            "body": self.body,
            "full": self.full,
        }

    @staticmethod
    def from_dict(d: dict) -> BlockEmbeddings:
        return BlockEmbeddings(**d)


def _round(m: np.ndarray) -> list[list[float]]:
    return [[round(float(x), 6) for x in row] for row in m]


def embed_segments(segs: dict[str, SegmentedFiling], embedder: Embedder) -> BlockEmbeddings:
    corpus = [b.full_text for side in ("old", "new") for b in segs[side].blocks]
    embedder.fit(corpus)
    heading: dict[str, list[list[float]]] = {}
    body: dict[str, list[list[float]]] = {}
    full: dict[str, list[list[float]]] = {}
    before = embedder.truncation_count
    for side in ("old", "new"):
        blocks = segs[side].blocks
        heading[side] = _round(embedder.embed([b.heading for b in blocks]))
        body[side] = _round(embedder.embed([b.body or b.heading for b in blocks]))
        full[side] = _round(embedder.embed([b.full_text for b in blocks]))
    truncated = embedder.truncation_count - before
    if truncated:
        log.warning(
            "stage3: %d block texts exceeded max_seq_length=%s and were chunked + mean-pooled",
            truncated,
            embedder.max_seq_length,
        )
    else:
        log.info(
            "stage3: no block exceeded max_seq_length=%s (backend=%s)",
            embedder.max_seq_length,
            embedder.backend,
        )
    return BlockEmbeddings(
        model_id=embedder.model_id,
        backend=embedder.backend,
        max_seq_length=embedder.max_seq_length,
        truncation_count=truncated,
        heading=heading,
        body=body,
        full=full,
    )
