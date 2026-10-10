"""RiskDiff output contract.

This module is the SINGLE SOURCE OF TRUTH for the shape of a published comparison.
`scripts/regen_contract.py` exports it to `contract/comparison.schema.json` and generates
`web/src/types/comparison.ts`. Change this file -> rerun that script.

Design notes
- No timestamps anywhere: the same inputs + versions must produce byte-identical JSON.
- Every AI claim and every score point carries `cited_sentence_ids`; each id must exist in
  `Comparison.sentence_index` (enforced by `Comparison.check_citations`).
- Sentence id format: "{accession_number}:{block_index}:{sentence_index}".
- Block id format:    "{accession_number}:{block_index}".
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "1.0.0"

ChangeType = Literal[
    "new",
    "removed",
    "expanded",
    "reduced",
    "materially_reworded",
    "largely_unchanged",
]
CHANGE_TYPES: tuple[str, ...] = (
    "new",
    "removed",
    "expanded",
    "reduced",
    "materially_reworded",
    "largely_unchanged",
)

SentenceStatus = Literal["added", "removed", "modified", "unchanged"]
FilingSide = Literal["old", "new"]
DiffOp = Literal["equal", "insert", "delete"]

Category = Literal[
    "geopolitical",
    "supply_chain",
    "regulation",
    "cybersecurity",
    "customer_concentration",
    "competition",
    "liquidity",
    "credit",
    "interest_rates",
    "foreign_exchange",
    "artificial_intelligence",
    "intellectual_property",
    "labor",
    "climate",
    "litigation",
    "macroeconomic",
    "other",
]
CATEGORIES: tuple[str, ...] = (
    "geopolitical",
    "supply_chain",
    "regulation",
    "cybersecurity",
    "customer_concentration",
    "competition",
    "liquidity",
    "credit",
    "interest_rates",
    "foreign_exchange",
    "artificial_intelligence",
    "intellectual_property",
    "labor",
    "climate",
    "litigation",
    "macroeconomic",
    "other",
)

InterpretationStatus = Literal["ok", "unavailable", "skipped", "empty"]

SENTENCE_ID_RE = re.compile(r"^\d{10}-\d{2}-\d{6}:\d+:\d+$")
BLOCK_ID_RE = re.compile(r"^\d{10}-\d{2}-\d{6}:\d+$")
TICKER_RE = re.compile(r"^[A-Z.\-]{1,6}$")


class Strict(BaseModel):
    """Base: forbid unknown keys so the contract is exact in both directions."""

    model_config = ConfigDict(extra="forbid")


class ModelIds(Strict):
    """Exact identifiers of every model/method that influenced the output.

    These feed `analysis_id`, so switching any of them yields a different id."""

    embedding_model: str = Field(
        description="Hugging Face model id used for block embeddings, e.g. 'BAAI/bge-m3'. "
        "If the fallback lexical embedder was used this says so explicitly."
    )
    embedding_backend: Literal["sentence-transformers", "lexical-fallback"]
    ner_model: str = Field(description="NER model id, e.g. 'spacy/en_core_web_sm@3.8.0'.")
    category_method: str = Field(
        description="How categories were assigned, e.g. 'embedding-similarity:BAAI/bge-m3'."
    )
    sentence_splitter: str = Field(description="e.g. 'pysbd@0.3.4'.")
    llm_provider: Literal["huggingface", "gemini"] | None = Field(
        default=None, description="None when the LLM stage did not run."
    )
    llm_model: str | None = Field(default=None, description="Pinned LLM model id, if used.")
    prompt_sha256: str | None = Field(
        default=None, description="sha256 of the exact prompt template text used for stage 7."
    )


class Company(Strict):
    ticker: str = Field(pattern=r"^[A-Z.\-]{1,6}$")
    name: str
    cik: str = Field(pattern=r"^\d{10}$", description="10-digit zero-padded CIK.")


class FilingMeta(Strict):
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str = Field(description="'10-K' or '10-K/A'.")
    fiscal_year: int = Field(ge=1990, le=2100)
    period_of_report: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    filing_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    primary_document: str
    edgar_url: str = Field(description="Direct URL of the primary document on www.sec.gov.")
    edgar_index_url: str = Field(description="Filing index page on www.sec.gov.")
    is_amendment: bool = False
    item_1a_word_count: int = Field(ge=0)
    item_1a_char_count: int = Field(ge=0)
    block_count: int = Field(ge=0)
    section_groups: list[str] = Field(
        default_factory=list,
        description="Group headers found in Item 1A, e.g. 'Risks Related to Our Industry'.",
    )


class DiffSpan(Strict):
    """Word-level span inside a modified sentence. Old side carries equal/delete,
    new side carries equal/insert. Concatenating `text` over a side's spans reproduces
    that side's sentence text exactly."""

    op: DiffOp
    text: str


class Sentence(Strict):
    id: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}:\d+:\d+$")
    side: FilingSide
    status: SentenceStatus
    text: str
    pair_index: int = Field(
        ge=0,
        description="Display order in a unified (inline) view. Modified/unchanged pairs share "
        "the same pair_index (old entry first, then new).",
    )
    counterpart_id: str | None = Field(
        default=None,
        description="For modified/unchanged: the aligned sentence id on the other side.",
    )
    alignment_similarity: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Similarity used to align the pair, if any."
    )
    diff_spans: list[DiffSpan] | None = Field(
        default=None, description="Only for status == 'modified'."
    )


class DiffStats(Strict):
    old_sentence_count: int = Field(ge=0)
    new_sentence_count: int = Field(ge=0)
    added: int = Field(ge=0)
    removed: int = Field(ge=0)
    modified: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    old_word_count: int = Field(ge=0)
    new_word_count: int = Field(ge=0)
    added_word_count: int = Field(ge=0, description="Words in added sentences + inserted spans.")
    removed_word_count: int = Field(ge=0, description="Words in removed sentences + deleted spans.")


class SignalHit(Strict):
    """One concrete, cited detection by a deterministic signal."""

    value: str = Field(
        description="What was detected, e.g. 'may -> has', 'Taiwan', '$1.2 billion'."
    )
    detail: str | None = Field(default=None, description="Plain-English explanation.")
    old_sentence_ids: list[str] = Field(default_factory=list)
    new_sentence_ids: list[str] = Field(default_factory=list)


class Signals(Strict):
    hypothetical_to_actual: list[SignalHit] = Field(default_factory=list)
    new_entities: list[SignalHit] = Field(default_factory=list)
    new_quantities: list[SignalHit] = Field(default_factory=list)
    added_text_ratio: float = Field(ge=0.0, le=1.0)
    removed_text_ratio: float = Field(ge=0.0, le=1.0)
    semantic_shift: float = Field(
        ge=0.0, le=1.0, description="1 - pair similarity (0 for new/removed)."
    )
    category_scores: dict[str, float] = Field(
        default_factory=dict, description="Per-category similarity used to pick `categories`."
    )


class ScoreLine(Strict):
    signal: str = Field(description="Machine key, e.g. 'hypothetical_to_actual', 'rubric_q1'.")
    label: str = Field(description="Plain-English label shown in the UI.")
    points: int
    detail: str | None = None
    cited_sentence_ids: list[str] = Field(
        description="Must be non-empty whenever points != 0. Ids must exist in sentence_index."
    )


class RubricAnswer(Strict):
    question_id: str = Field(pattern=r"^Q[1-9]$")
    question: str
    answer: bool = Field(
        description="After citation validation: a 'yes' without a valid citation becomes False."
    )
    cited_sentence_ids: list[str] = Field(default_factory=list)
    rationale: str | None = Field(default=None, description="Short LLM rationale (display only).")
    raw_answer: bool | None = Field(
        default=None, description="What the model said before validation (transparency)."
    )


class Claim(Strict):
    text: str
    cited_sentence_ids: list[str] = Field(min_length=1)


class Interpretation(Strict):
    status: InterpretationStatus = Field(
        description="ok = LLM ran and output validated; unavailable = no provider; "
        "skipped = not run for largely_unchanged; empty = ran but every claim was dropped."
    )
    reason: str | None = None
    model_id: str | None = None
    rubric: list[RubricAnswer] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list, max_length=3)
    dropped_claim_count: int = Field(ge=0, default=0)
    dropped_reasons: list[str] = Field(default_factory=list)


class Change(Strict):
    id: str = Field(
        pattern=r"^[0-9a-f]{16}$", description="Stable hash of (old_block_id, new_block_id)."
    )
    rank: int = Field(ge=1)
    title: str = Field(description="Risk heading (new side if present, else old).")
    old_title: str | None = None
    new_title: str | None = None
    section_group: str | None = None
    change_type: ChangeType
    categories: list[Category] = Field(min_length=1, max_length=2)
    score: int = Field(ge=0, le=100)
    score_breakdown: list[ScoreLine]
    similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    heading_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    body_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    old_block_id: str | None = Field(default=None, pattern=r"^\d{10}-\d{2}-\d{6}:\d+$")
    new_block_id: str | None = Field(default=None, pattern=r"^\d{10}-\d{2}-\d{6}:\d+$")
    old_text: str | None = Field(default=None, description="Full old block text (heading + body).")
    new_text: str | None = Field(default=None, description="Full new block text (heading + body).")
    sentences: list[Sentence]
    stats: DiffStats
    signals: Signals
    interpretation: Interpretation

    @model_validator(mode="after")
    def _consistent_sides(self) -> Change:
        if self.change_type == "new" and (self.old_block_id or self.old_text):
            raise ValueError("change_type 'new' must not have an old block")
        if self.change_type == "removed" and (self.new_block_id or self.new_text):
            raise ValueError("change_type 'removed' must not have a new block")
        if self.change_type not in ("new", "removed") and not (
            self.old_block_id and self.new_block_id
        ):
            raise ValueError(f"change_type '{self.change_type}' requires both blocks")
        for line in self.score_breakdown:
            if line.points != 0 and not line.cited_sentence_ids:
                raise ValueError(f"score line '{line.signal}' has points but no citations")
        for s in self.sentences:
            if s.status == "modified" and not s.diff_spans:
                raise ValueError(f"modified sentence {s.id} lacks diff_spans")
            if s.diff_spans is not None:
                if "".join(sp.text for sp in s.diff_spans) != s.text:
                    raise ValueError(f"diff_spans of {s.id} do not reproduce its text")
                bad = {"insert"} if s.side == "old" else {"delete"}
                if any(sp.op in bad for sp in s.diff_spans):
                    raise ValueError(f"diff_spans of {s.id} contain ops for the other side")
        return self


class Summary(Strict):
    total_changes: int = Field(ge=0)
    by_change_type: dict[str, int] = Field(
        description="Counts keyed by every ChangeType (zeros included)."
    )
    by_category: dict[str, int] = Field(
        description="Counts keyed by every Category (zeros included)."
    )
    old_block_count: int = Field(ge=0)
    new_block_count: int = Field(ge=0)
    matched_pairs: int = Field(ge=0)
    interpretation_status: InterpretationStatus = Field(
        description="'ok' if the LLM stage ran for this comparison, else why not."
    )
    max_score: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _keys_complete(self) -> Summary:
        if set(self.by_change_type) != set(CHANGE_TYPES):
            raise ValueError("by_change_type must contain exactly every change type")
        if set(self.by_category) != set(CATEGORIES):
            raise ValueError("by_category must contain exactly every category")
        return self


class Thresholds(Strict):
    """Matching + diff parameters in force for this run (transparency; recalibrated in eval)."""

    match_threshold: float = Field(
        ge=0.0, le=1.0, description="Min combined similarity to accept a match."
    )
    heading_weight: float = Field(ge=0.0, le=1.0)
    body_weight: float = Field(ge=0.0, le=1.0)
    sentence_match_threshold: float = Field(
        ge=0.0, le=1.0, description="Min similarity to align two sentences."
    )
    sentence_unchanged_threshold: float = Field(
        ge=0.0, le=1.0, description="At/above this an aligned pair is 'unchanged'."
    )
    expanded_ratio: float = Field(
        description="added/removed ratio rules; see diff.classify_change_type."
    )
    reworded_similarity: float = Field(ge=0.0, le=1.0)


class SentenceLocation(Strict):
    id: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}:\d+:\d+$")
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    side: FilingSide
    block_id: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}:\d+$")
    text: str = Field(description="Exact sentence text as extracted from the filing.")
    char_start: int = Field(ge=0, description="Offset into the extracted Item 1A plain text.")
    char_end: int = Field(ge=0)
    is_heading: bool = False


class Comparison(Strict):
    schema_version: str
    analysis_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    pipeline_version: str
    rubric_version: str
    model_ids: ModelIds
    is_fixture: bool = Field(
        default=False,
        description="True ONLY for the hand-made dev fixture. Published data must have False.",
    )
    company: Company
    old_filing: FilingMeta
    new_filing: FilingMeta
    filing_selection_note: str = Field(
        description="How the two filings were chosen (e.g. 'two most recent original 10-Ks; amendments excluded')."
    )
    summary: Summary
    thresholds: Thresholds
    changes: list[Change] = Field(description="Ranked by score desc, then stable id.")
    sentence_index: dict[str, SentenceLocation]
    notes: list[str] = Field(
        default_factory=list,
        description="Plain-language caveats, e.g. 'LLM stage unavailable: no provider configured'.",
    )

    @model_validator(mode="after")
    def check_citations(self) -> Comparison:
        idx = self.sentence_index
        for sid, loc in idx.items():
            if sid != loc.id:
                raise ValueError(f"sentence_index key {sid} != entry id {loc.id}")
        ranks = [c.rank for c in self.changes]
        if ranks != list(range(1, len(self.changes) + 1)):
            raise ValueError("changes must be ranked 1..N in order")
        for c in self.changes:
            for line in c.score_breakdown:
                for sid in line.cited_sentence_ids:
                    if sid not in idx:
                        raise ValueError(f"score line cites unknown sentence {sid}")
            for ans in c.interpretation.rubric:
                if ans.answer and not ans.cited_sentence_ids:
                    raise ValueError(f"rubric {ans.question_id} is 'yes' without citations")
                for sid in ans.cited_sentence_ids:
                    if sid not in idx:
                        raise ValueError(f"rubric cites unknown sentence {sid}")
            for claim in c.interpretation.claims:
                for sid in claim.cited_sentence_ids:
                    if sid not in idx:
                        raise ValueError(f"claim cites unknown sentence {sid}")
            for hits in (
                c.signals.hypothetical_to_actual,
                c.signals.new_entities,
                c.signals.new_quantities,
            ):
                for h in hits:
                    for sid in h.old_sentence_ids + h.new_sentence_ids:
                        if sid not in idx:
                            raise ValueError(f"signal cites unknown sentence {sid}")
            for s in c.sentences:
                if s.id not in idx:
                    raise ValueError(f"change sentence {s.id} missing from sentence_index")
        if self.summary.total_changes != len(self.changes):
            raise ValueError("summary.total_changes != len(changes)")
        return self


# ---- Lightweight API payloads (not part of the published file) ----


class CompanyCard(Strict):
    ticker: str
    name: str
    old_fiscal_year: int
    new_fiscal_year: int
    total_changes: int
    by_change_type: dict[str, int]
    file: str


class StageEvent(Strict):
    """One SSE event emitted by POST /analyze."""

    stage: int = Field(ge=0, le=8)
    name: str
    status: Literal["started", "done", "cached", "error"]
    message: str | None = None
    ticker: str | None = None


def canonical_json(model: BaseModel) -> str:
    """Deterministic serialization used for publishing and hashing."""
    import json

    return (
        json.dumps(
            model.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    )
