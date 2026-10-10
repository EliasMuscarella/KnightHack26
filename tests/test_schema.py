"""Contract tests: fixture validates; the contract rejects uncited or inconsistent data."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline.schema import Comparison, canonical_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "contract" / "fixtures" / "FIXTURE_comparison.json"


@pytest.fixture()
def fixture_doc() -> dict:
    return json.loads(FIXTURE.read_text())


def test_fixture_validates_and_is_canonical(fixture_doc: dict) -> None:
    comp = Comparison.model_validate(fixture_doc)
    assert comp.is_fixture is True
    assert canonical_json(comp) == FIXTURE.read_text(), "fixture file is not in canonical form"


def test_every_fixture_string_is_labeled(fixture_doc: dict) -> None:
    free_text_keys = {"title", "old_title", "new_title", "text", "label", "detail", "value", "reason", "name", "question", "rationale"}

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "diff_spans":
                    continue  # spans are fragments of an already-labeled sentence
                if k in free_text_keys and isinstance(v, str):
                    assert v.startswith("FIXTURE:"), f"{path}.{k} = {v!r} lacks FIXTURE prefix"
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(fixture_doc)


def test_score_line_without_citation_is_rejected(fixture_doc: dict) -> None:
    doc = json.loads(json.dumps(fixture_doc))
    line = doc["changes"][0]["score_breakdown"][0]
    assert line["points"] != 0
    line["cited_sentence_ids"] = []
    with pytest.raises(ValidationError, match="no citations"):
        Comparison.model_validate(doc)


def test_unknown_citation_is_rejected(fixture_doc: dict) -> None:
    doc = json.loads(json.dumps(fixture_doc))
    change = next(c for c in doc["changes"] if c["interpretation"]["claims"])
    change["interpretation"]["claims"][0]["cited_sentence_ids"] = ["0000000000-25-000001:99:99"]
    with pytest.raises(ValidationError, match="unknown sentence"):
        Comparison.model_validate(doc)


def test_rubric_yes_without_citation_is_rejected(fixture_doc: dict) -> None:
    doc = json.loads(json.dumps(fixture_doc))
    change = next(c for c in doc["changes"] if c["interpretation"]["rubric"])
    ans = next(a for a in change["interpretation"]["rubric"] if a["answer"])
    ans["cited_sentence_ids"] = []
    with pytest.raises(ValidationError, match="without citations"):
        Comparison.model_validate(doc)


def test_diff_spans_must_reproduce_text(fixture_doc: dict) -> None:
    doc = json.loads(json.dumps(fixture_doc))
    sent = next(s for c in doc["changes"] for s in c["sentences"] if s["status"] == "modified")
    sent["diff_spans"][0]["text"] += "x"
    with pytest.raises(ValidationError, match="do not reproduce"):
        Comparison.model_validate(doc)


def test_unknown_field_is_rejected(fixture_doc: dict) -> None:
    doc = json.loads(json.dumps(fixture_doc))
    doc["changes"][0]["extra_field"] = 1
    with pytest.raises(ValidationError):
        Comparison.model_validate(doc)


def test_schema_file_matches_models() -> None:
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "regen_contract.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
