"""Derived trend facts: one file per published report (`data/derived/{analysis_id}.trends.json`).

NOT part of the published contract (`pipeline/schema.py`): a derived file never changes a published
JSON file or its analysis_id and can be rebuilt from the published file at any time. Every text
field is a verbatim sentence from the report (looked up by sentence id); nothing is generated."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Bump when derive.py changes what it produces; together with TOPICS_VERSION (topics.yml) it forms
# `derivation`, which is stored in every file so stale files are re-derived instead of trusted.
TRENDS_VERSION = "1.2.1"

TopicSource = Literal["lexicon", "entity", "phrase"]
MentionStatus = Literal["added", "modified"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopicMention(_Strict):
    """A topic that is newly added language in one sentence of one risk factor."""

    ticker: str
    change_id: str
    sentence_id: str
    position: int = Field(ge=0, description="Index of the sentence in change.sentences.")
    topic: str
    source: TopicSource
    matched_terms: list[str] = Field(min_length=1, description="Verbatim matched text, in order.")
    status: MentionStatus
    text: str = Field(description="The verbatim sentence (this year's filing).")
    added_spans: list[tuple[int, int]] = Field(
        description="Character offsets of the inserted text inside `text` ([[0, len]] when the "
        "whole sentence is new)."
    )


class ChangeActivity(_Strict):
    """Per risk factor: how much language was added, removed or rewritten (counts, not levels)."""

    change_id: str
    short_title: str
    categories: list[str]
    change_type: str
    score: int
    added_sentences: int = Field(ge=0)
    removed_sentences: int = Field(ge=0)
    modified_sentences: int = Field(ge=0, description="Rewritten sentence pairs.")
    added_words: int = Field(ge=0, description="Words in wholly added sentences.")
    removed_words: int = Field(ge=0, description="Words in wholly removed sentences.")
    modified_words: int = Field(
        ge=0,
        description="Words inserted (new side) plus words deleted (old side) inside rewritten "
        "sentences. added_words + removed_words + modified_words == stats.added_word_count + "
        "stats.removed_word_count.",
    )


class PotentialToActual(_Strict):
    ticker: str
    company_name: str
    change_id: str
    short_title: str
    old_sentence_id: str
    new_sentence_id: str
    old_text: str
    new_text: str
    score: int
    old_spans: list[tuple[int, int]] = Field(
        default_factory=list, description="Character ranges of deleted words inside old_text."
    )
    new_spans: list[tuple[int, int]] = Field(
        default_factory=list, description="Character ranges of inserted words inside new_text."
    )


class TrendFacts(_Strict):
    derivation: str = Field(description="'{TRENDS_VERSION}+topics{TOPICS_VERSION}'.")
    phrase_model: str = Field(description="spaCy pipeline used for key phrases.")
    analysis_id: str
    ticker: str
    company_name: str
    cik: str
    old_fiscal_year: int
    new_fiscal_year: int
    old_accession: str
    new_accession: str
    old_edgar_url: str
    new_edgar_url: str
    total_changes: int
    by_change_type: dict[str, int]
    category_activity: list[ChangeActivity]
    topic_mentions: list[TopicMention]
    potential_to_actual: list[PotentialToActual]
