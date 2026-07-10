"""Paper acquisition and summary schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import PaperAcquisitionStatus


class PaperSearchQuery(BaseModel):
    query_id: str
    keywords: list[str]
    query_string: str
    filters: dict = Field(default_factory=dict)


class PaperAcquisitionRun(BaseModel):
    run_id: str
    status: PaperAcquisitionStatus
    candidate_count: int = 0
    selected_count: int = 0
    dedupe_rule: str = "doi_or_title_year"
    used_cache: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class PaperCandidate(BaseModel):
    candidate_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    abstract: str | None = None
    source_record_id: str
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    selected: bool = False
    selection_reason: str | None = None


class PaperAcquisitionResponse(BaseModel):
    query: PaperSearchQuery
    run: PaperAcquisitionRun
    candidates: list[PaperCandidate]


class PaperSummary(BaseModel):
    research_goal: str | None = None
    method: str | None = None
    dataset: str | None = None
    findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    future_work: list[str] = Field(default_factory=list)


class PaperItem(BaseModel):
    paper_id: str
    candidate_id: str
    title: str
    year: int | None = None
    url: str | None = None
    summary: PaperSummary | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class PapersResponse(BaseModel):
    papers: list[PaperItem]
