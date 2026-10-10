"""Stage 8 tests: scoring is deterministic and cited; publish refuses the fixture; analysis_id."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.publish import load_published, publish
from pipeline.rubric import CAPS, QUESTIONS, WEIGHT_BY_SIGNAL
from pipeline.schema import (
    Claim,
    Comparison,
    Interpretation,
    ModelIds,
    RubricAnswer,
    Sentence,
    SignalHit,
    Signals,
)
from pipeline.score import analysis_id, change_id, score_change

ROOT = Path(__file__).resolve().parents[1]
NEW = "0000000000-25-000001"
OLD = "0000000000-24-000001"


def sents():
    return [
        Sentence(
            id=f"{OLD}:1:0",
            side="old",
            status="unchanged",
            text="H",
            pair_index=0,
            counterpart_id=f"{NEW}:1:0",
        ),
        Sentence(
            id=f"{NEW}:1:0",
            side="new",
            status="unchanged",
            text="H",
            pair_index=0,
            counterpart_id=f"{OLD}:1:0",
        ),
        Sentence(id=f"{NEW}:1:1", side="new", status="added", text="Added one.", pair_index=1),
        Sentence(id=f"{NEW}:1:2", side="new", status="added", text="Added two.", pair_index=2),
    ]


def test_score_lines_all_cited_and_capped():
    signals = Signals(
        hypothetical_to_actual=[
            SignalHit(
                value=f"h{i}", old_sentence_ids=[f"{OLD}:1:0"], new_sentence_ids=[f"{NEW}:1:1"]
            )
            for i in range(5)
        ],
        new_entities=[SignalHit(value=f"e{i}", new_sentence_ids=[f"{NEW}:1:1"]) for i in range(10)],
        new_quantities=[
            SignalHit(value=f"q{i}", new_sentence_ids=[f"{NEW}:1:2"]) for i in range(10)
        ],
        added_text_ratio=0.9,
        removed_text_ratio=0.0,
        semantic_shift=0.5,
    )
    interp = Interpretation(
        status="ok",
        model_id="m",
        rubric=[
            RubricAnswer(
                question_id=q.id,
                question=q.text,
                answer=True,
                cited_sentence_ids=[f"{NEW}:1:1"],
                raw_answer=True,
            )
            for q in QUESTIONS
        ],
        claims=[Claim(text="c", cited_sentence_ids=[f"{NEW}:1:1"])],
    )
    score, lines = score_change("expanded", sents(), signals, interp, 0.5, 0.8)
    by = {line.signal: line for line in lines}
    assert by["hypothetical_to_actual"].points == CAPS["hypothetical_to_actual"]
    assert by["new_entities"].points == CAPS["new_entities"]
    assert by["new_quantities"].points == CAPS["new_quantities"]
    assert by["change_type:expanded"].points == WEIGHT_BY_SIGNAL["change_type:expanded"].points
    assert all(line.cited_sentence_ids for line in lines if line.points)
    assert score == 100  # capped
    assert sum(line.points for line in lines) > 100


def test_rubric_no_without_citation_scores_nothing():
    interp = Interpretation(
        status="ok",
        model_id="m",
        rubric=[
            RubricAnswer(
                question_id="Q1", question="q", answer=False, cited_sentence_ids=[], raw_answer=True
            )
        ],
        claims=[],
    )
    signals = Signals(added_text_ratio=0.0, removed_text_ratio=0.0, semantic_shift=0.0)
    score, lines = score_change("largely_unchanged", sents(), signals, interp, 0.99, 0.8)
    assert score == 0 and lines == []


def test_analysis_id_depends_on_models_and_versions():
    base = ModelIds(
        embedding_model="BAAI/bge-m3",
        embedding_backend="sentence-transformers",
        ner_model="spacy",
        category_method="x",
        sentence_splitter="pysbd",
    )
    a = analysis_id(OLD, NEW, base)
    b = analysis_id(OLD, NEW, base.model_copy(update={"embedding_model": "lexical"}))
    c = analysis_id(
        OLD,
        NEW,
        base.model_copy(
            update={"llm_model": "hf:x", "llm_provider": "huggingface", "prompt_sha256": "abc"}
        ),
    )
    assert len({a, b, c}) == 3
    assert a == analysis_id(OLD, NEW, base)
    assert change_id(f"{OLD}:1", f"{NEW}:1") != change_id(None, f"{NEW}:1")


def test_publish_refuses_fixture_in_published_dir(tmp_path):
    comp = Comparison.model_validate_json(
        (ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json").read_text()
    )
    published, scratch = tmp_path / "published", tmp_path / "scratch"
    path = publish(comp, published, scratch)
    assert path.parent == scratch
    assert not published.exists() or not list(published.iterdir())
    with pytest.raises(ValueError, match="FIXTURE"):
        load_published(path)
    # a non-fixture document is written to the published dir in canonical form
    real = comp.model_copy(
        update={"is_fixture": False, "company": comp.company.model_copy(update={"ticker": "TEST"})}
    )
    p2 = publish(real, published, scratch)
    assert p2.parent == published and p2.name == "TEST_2024_2025.json"
    assert json.loads(p2.read_text())["company"]["ticker"] == "TEST"
    assert load_published(p2).analysis_id == real.analysis_id
