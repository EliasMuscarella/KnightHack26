"""Stage 3-4 tests: chunk + mean-pool, lexical fallback, matching behavior."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from pipeline.embed import (
    BlockEmbeddings,
    LexicalEmbedder,
    SentenceTransformerEmbedder,
    embed_segments,
)
from pipeline.extract import extract_item_1a
from pipeline.match import MatchParams, match_blocks
from pipeline.segment import segment

FIX = Path(__file__).resolve().parents[1] / "contract" / "fixtures"


class FakeTokenizer:
    vocab: dict[str, int] = {}
    inverse: dict[int, str] = {}

    def encode(self, text, add_special_tokens=False):
        ids = []
        for w in text.split():
            if w not in self.vocab:
                self.vocab[w] = len(self.vocab)
                self.inverse[self.vocab[w]] = w
            ids.append(self.vocab[w])
        return ids

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(self.inverse[i] for i in ids)


class FakeModel:
    """Embeds by bag-of-token-ids so chunk order does not matter."""

    max_seq_length = 10
    tokenizer = FakeTokenizer()

    def encode(self, pieces, **kw):
        out = []
        for p in pieces:
            v = np.zeros(1000)
            for tok in self.tokenizer.encode(p):
                v[tok] += 1
            out.append(v / (np.linalg.norm(v) or 1))
        return np.array(out)

    def eval(self):
        return self


def test_chunking_and_mean_pooling_counts_truncations():
    emb = SentenceTransformerEmbedder(
        model_id="fake/model", _model=FakeModel(), max_seq_length=10, chunk_overlap=0
    )
    short = "one two three"
    long = " ".join(f"w{i}" for i in range(25))  # 25 tokens > budget of 8
    vecs = emb.embed([short, long])
    assert vecs.shape[0] == 2
    assert emb.truncation_count == 1
    np.testing.assert_allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-6)
    # mean-pooled long vector stays close to the single-shot embedding of the same text
    single = FakeModel().encode([long])[0]
    assert float(vecs[1] @ single) > 0.95


def segs():
    out = {}
    for side, name, acc in (
        ("old", "FIXTURE_10K_FY2024.htm", "0000000000-24-000001"),
        ("new", "FIXTURE_10K_FY2025.htm", "0000000000-25-000001"),
    ):
        out[side] = segment(extract_item_1a((FIX / name).read_bytes(), acc))
    return out


def test_lexical_matching_on_fixture_pair():
    s = segs()
    emb = embed_segments(s, LexicalEmbedder())
    assert emb.backend == "lexical-fallback"
    res = match_blocks(emb)
    by_old = {p.old_index: p for p in res.pairs}
    heads_old = [b.heading for b in s["old"].blocks]
    heads_new = [b.heading for b in s["new"].blocks]
    # identical heading, small body edits -> matched with high similarity
    i = heads_old.index("FIXTURE: The widget market is intensely competitive.")
    assert i in by_old and heads_new[by_old[i].new_index] == heads_old[i]
    assert by_old[i].similarity > 0.95
    # removed risk (acquisition) and new risk (AI) are detected
    acq = heads_old.index(
        "FIXTURE: The pending acquisition of Gadgetron Inc. may not be completed on the expected timeline."
    )
    ai = heads_new.index(
        "FIXTURE: Our use of artificial intelligence may create legal, regulatory, and reputational exposure."
    )
    assert acq in res.unmatched_old
    assert ai in res.unmatched_new
    # reworded security heading still matches its counterpart
    sec_old = heads_old.index("FIXTURE: Security breaches could harm our business.")
    assert sec_old in by_old
    assert heads_new[by_old[sec_old].new_index].startswith("FIXTURE: Cybersecurity incidents")
    # every pair is one-to-one
    assert len({p.new_index for p in res.pairs}) == len(res.pairs)


def test_threshold_rejects_weak_assignments():
    emb = BlockEmbeddings(
        model_id="x",
        backend="sentence-transformers",
        max_seq_length=10,
        truncation_count=0,
        heading={"old": [[1, 0], [0, 1]], "new": [[1, 0], [0.2, 0.98]]},
        body={"old": [[1, 0], [0, 1]], "new": [[1, 0], [0.9, 0.1]]},
        full={"old": [[1, 0], [0, 1]], "new": [[1, 0], [0.9, 0.1]]},
    )
    res = match_blocks(emb, MatchParams(match_threshold=0.8))
    assert [(p.old_index, p.new_index) for p in res.pairs] == [(0, 0)]
    assert res.unmatched_old == [1] and res.unmatched_new == [1]
    assert len(res.rejected) == 1


def test_matching_is_deterministic():
    s = segs()
    a = match_blocks(embed_segments(s, LexicalEmbedder())).to_dict()
    b = match_blocks(embed_segments(s, LexicalEmbedder())).to_dict()
    assert a == b
