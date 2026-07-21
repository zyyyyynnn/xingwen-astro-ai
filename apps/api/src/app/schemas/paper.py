"""Paper acquisition and summary schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import PaperAcquisitionStatus


class PaperSearchQuery(BaseModel):
    """Phase 0 paper query domain model with the legacy v1 wire alias."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(alias="query_id")
    task_id: str
    case_key: str
    keywords: list[str]
    source_types: list[str]
    query_string: str
    filters: dict
    created_at: datetime


class PaperAcquisitionRun(BaseModel):
    """One reproducible paper acquisition run."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(alias="run_id")
    task_id: str
    query_id: str
    status: PaperAcquisitionStatus
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    dedupe_rule: str
    used_cache: bool
    started_at: datetime
    finished_at: datetime | None = None


class PaperCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(alias="candidate_id")
    task_id: str
    run_id: str
    source_record_id: str
    external_id: str | None = None
    title: str
    authors: list[str]
    year: int | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    abstract: str | None = None
    relevance_score: float = Field(ge=0.0, le=1.0)
    dedupe_key: str
    selected: bool
    selection_reason: str | None = None


class PaperAcquisitionResponse(BaseModel):
    query: PaperSearchQuery
    run: PaperAcquisitionRun
    candidates: list[PaperCandidate]


class PaperSummary(BaseModel):
    id: str
    paper_id: str
    research_goal: str
    method: str
    dataset: str
    findings: list[str]
    limitations: list[str]
    future_work: list[str]
    evidence_ids: list[str] = Field(min_length=1)
    model_name: str
    prompt_version: str


class PaperItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = Field(alias="paper_id")
    candidate_id: str
    task_id: str
    title: str
    authors: list[str]
    year: int | None = None
    url: str | None = None
    source_ids: list[str] = Field(min_length=1)
    summary: PaperSummary | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class PapersResponse(BaseModel):
    papers: list[PaperItem]
