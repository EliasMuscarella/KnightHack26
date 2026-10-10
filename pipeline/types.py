"""Internal, stage-to-stage data types (not part of the published contract)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pipeline.schema import Company


class Internal(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FilingRecord(Internal):
    cik: str = Field(pattern=r"^\d{10}$")
    accession_number: str
    form: str
    filing_date: str
    report_date: str
    primary_document: str
    edgar_url: str
    edgar_index_url: str
    is_amendment: bool
    html_path: str
    html_sha256: str
    fiscal_year: int
    fiscal_year_source: str


class FetchResult(Internal):
    company: Company
    old: FilingRecord
    new: FilingRecord
    selection_note: str
    candidates_considered: list[str] = Field(default_factory=list)


class ExtractedSection(Internal):
    """Stage 1 output for one filing."""

    accession_number: str
    html: str = Field(description="Item 1A as an HTML fragment (structure preserved).")
    text: str = Field(description="Plain text of the same section (whitespace-normalized).")
    word_count: int
    char_count: int
    start_heading: str
    end_heading: str | None
    method: str
    candidates: int
    units: list[dict] = Field(
        default_factory=list, description="Linearized units (see html_units)."
    )
    dropped_units: int = 0


class SentenceRec(Internal):
    id: str
    text: str
    char_start: int
    char_end: int
    is_heading: bool


class RiskBlock(Internal):
    id: str
    accession_number: str
    index: int
    heading: str
    body: str
    section_group: str | None
    sentences: list[SentenceRec]
    char_start: int
    char_end: int

    @property
    def full_text(self) -> str:
        return (self.heading + "\n" + self.body).strip()

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())


class SegmentedFiling(Internal):
    accession_number: str
    blocks: list[RiskBlock]
    section_groups: list[str]
    text: str
    word_count: int
    char_count: int
    splitter: str
