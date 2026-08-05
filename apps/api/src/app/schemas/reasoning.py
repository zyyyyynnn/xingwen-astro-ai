"""Literature reasoning schemas."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .enums import ClaimType, LiteratureRelationType


class LiteratureClaim(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    # Frozen Phase 0 transport model; never a D-07 publication candidate.
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    id: str = Field(alias="claim_id")
    task_id: str
    paper_id: str
    claim_type: ClaimType
    text: str
    normalized_text: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class TraceStep(BaseModel):
    order: int
    claim_id: str
    rationale: str


class ReasoningTrace(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    # Frozen Phase 0 transport model; never a D-08 publication candidate.
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    id: str = Field(alias="trace_id")
    task_id: str
    relation_id: str
    steps: list[TraceStep]
    evidence_ids: list[str] = Field(min_length=1)
    model_name: str
    prompt_version: str


class LiteratureRelation(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    # Frozen Phase 0 transport model; never a D-08 publication candidate.
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    id: str = Field(alias="relation_id")
    task_id: str
    source_claim_id: str
    target_claim_id: str
    relation_type: LiteratureRelationType
    reasoning_trace_id: str
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class LiteratureReasoningResponse(BaseModel):
    # Phase 0 envelope contains unadmitted Claim records and is not publishable.
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    claims: list[LiteratureClaim]
    relations: list[LiteratureRelation]
    traces: list[ReasoningTrace]
