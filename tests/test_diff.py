"""Stage 5 tests: word spans, alignment, change_type rules."""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.diff import (
    DEFAULT_DIFF_PARAMS,
    align_sentences,
    classify_change_type,
    diff_pair,
    word_spans,
)
from pipeline.schema import DiffStats
from pipeline.types import RiskBlock, SentenceRec


def block(acc: str, idx: int, heading: str, body: list[str]) -> RiskBlock:
    texts = [heading] + body
    sents = []
    pos = 0
    for i, t in enumerate(texts):
        sents.append(
            SentenceRec(
                id=f"{acc}:{idx}:{i}",
                text=t,
                char_start=pos,
                char_end=pos + len(t),
                is_heading=i == 0,
            )
        )
        pos += len(t) + 1
    return RiskBlock(
        id=f"{acc}:{idx}",
        accession_number=acc,
        index=idx,
        heading=heading,
        body="\n".join(body),
        section_group=None,
        sentences=sents,
        char_start=0,
        char_end=pos,
    )


OLD = "0000000000-24-000001"
NEW = "0000000000-25-000001"


def test_word_spans_are_precise_and_reproduce_text():
    old = "Natural disasters or trade restrictions may affect our suppliers."
    new = "Natural disasters, political instability, or trade restrictions have affected and may continue to affect our suppliers."
    os_, ns_ = word_spans(old, new)
    assert "".join(s.text for s in os_) == old
    assert "".join(s.text for s in ns_) == new
    assert [s.text for s in os_ if s.op == "delete"] == []
    # punctuation alone is never a change: the commas around the inserted words stay equal
    assert [s.text.strip() for s in ns_ if s.op == "insert"] == [
        "political instability",
        "have affected and",
        "continue to",
    ]
    assert not any(s.op == "insert" for s in os_) and not any(s.op == "delete" for s in ns_)


def test_word_spans_replace():
    os_, ns_ = word_spans("Approximately 40% of our revenue.", "Approximately 30% of our revenue.")
    assert [s.text for s in os_ if s.op == "delete"] == ["40"]
    assert [s.text for s in ns_ if s.op == "insert"] == ["30"]


def test_alignment_is_monotonic_and_thresholded():
    sim = np.array([[1.0, 0.1, 0.1], [0.1, 0.2, 0.9], [0.1, 0.95, 0.1]])
    # best monotonic: (0,0) + (1,2) = 1.9 vs (0,0) + (2,1) = 1.95 -> picks (2,1)
    assert align_sentences(sim, 0.45) == [(0, 0), (2, 1)]
    assert align_sentences(sim, 0.96) == [(0, 0)]


def test_diff_pair_statuses_and_pair_index():
    old = block(
        OLD,
        1,
        "Heading one.",
        [
            "Sentence A stays.",
            "Sentence B will be removed entirely from the text.",
            "Sentence C gets a small edit here.",
        ],
    )
    new = block(
        NEW,
        1,
        "Heading one.",
        [
            "Sentence A stays.",
            "Sentence C gets a small change here.",
            "Sentence D is brand new content added to the block.",
        ],
    )
    d = diff_pair(old, new, similarity=0.9)
    by_id = {s.id: s for s in d.sentences}
    assert by_id[f"{OLD}:1:0"].status == "unchanged" and by_id[f"{NEW}:1:0"].status == "unchanged"
    assert by_id[f"{OLD}:1:2"].status == "removed"
    assert by_id[f"{OLD}:1:3"].status == "modified" and by_id[f"{NEW}:1:2"].status == "modified"
    assert by_id[f"{NEW}:1:3"].status == "added"
    assert by_id[f"{OLD}:1:3"].counterpart_id == f"{NEW}:1:2"
    assert by_id[f"{NEW}:1:2"].diff_spans is not None
    # unified order: pairs share pair_index, old before new
    order = [(s.pair_index, s.side, s.status) for s in d.sentences]
    assert order == [
        (0, "old", "unchanged"),
        (0, "new", "unchanged"),
        (1, "old", "unchanged"),
        (1, "new", "unchanged"),
        (2, "old", "removed"),
        (3, "old", "modified"),
        (3, "new", "modified"),
        (4, "new", "added"),
    ]
    assert (
        d.stats.added == 1
        and d.stats.removed == 1
        and d.stats.modified == 1
        and d.stats.unchanged == 2
    )


def test_new_and_removed_blocks():
    b = block(NEW, 3, "A brand new risk.", ["Body sentence one.", "Body sentence two."])
    d = diff_pair(None, b, similarity=None)
    assert d.change_type == "new" and all(s.status == "added" for s in d.sentences)
    d2 = diff_pair(b, None, similarity=None)
    assert d2.change_type == "removed" and all(s.status == "removed" for s in d2.sentences)


def stats(old_wc, new_wc, added_wc, removed_wc):
    return DiffStats(
        old_sentence_count=1,
        new_sentence_count=1,
        added=0,
        removed=0,
        modified=0,
        unchanged=0,
        old_word_count=old_wc,
        new_word_count=new_wc,
        added_word_count=added_wc,
        removed_word_count=removed_wc,
    )


@pytest.mark.parametrize(
    "old_wc,new_wc,added,removed,sim,expected",
    [
        (100, 100, 0, 0, 1.0, "largely_unchanged"),
        (100, 102, 3, 1, 0.98, "largely_unchanged"),  # rule 3: both under 5%
        (100, 140, 45, 2, 0.85, "expanded"),  # rule 5
        (140, 100, 2, 45, 0.85, "reduced"),  # rule 6
        (100, 110, 40, 32, 0.6, "materially_reworded"),  # rule 4: both sides >= 25%
        (100, 100, 18, 14, 0.9, "materially_reworded"),  # rule 7: total >= 30%, net small
        (100, 100, 10, 8, 0.7, "materially_reworded"),  # rule 8: low similarity + >= 15% changed
        (100, 100, 10, 8, 0.9, "largely_unchanged"),  # rule 9
        (0, 50, 50, 0, None, "new"),
        (50, 0, 0, 50, None, "removed"),
    ],
)
def test_change_type_rules(old_wc, new_wc, added, removed, sim, expected):
    assert (
        classify_change_type(stats(old_wc, new_wc, added, removed), sim, DEFAULT_DIFF_PARAMS)
        == expected
    )


def test_content_words_anchor_the_word_diff():
    old = "We rely on foundries located in Westland and Eastland."
    new = "We rely on foundries located in Westland, Eastland, and Ruritania."
    os_, ns_ = word_spans(old, new)
    assert "".join(s.text for s in os_) == old and "".join(s.text for s in ns_) == new
    assert "Eastland" not in "".join(s.text for s in os_ if s.op == "delete")
    assert "Ruritania" in "".join(s.text for s in ns_ if s.op == "insert")
