"""Literature reasoning schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import ClaimType, LiteratureRelationType


class LiteratureClaim(BaseModel):
    claim_id: str
    paper_id: str
    claim_type: ClaimType
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class TraceStep(BaseModel):
    order: int
    claim_id: str
    rationale: str


class ReasoningTrace(BaseModel):
    trace_id: str
    relation_id: str
    steps: list[TraceStep]
    evidence_ids: list[str] = Field(default_factory=list)


class LiteratureRelation(BaseModel):
    relation_id: str
    source_claim_id: str
    target_claim_id: str
    relation_type: LiteratureRelationType
    reasoning_trace_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class LiteratureReasoningResponse(BaseModel):
    claims: list[LiteratureClaim]
    relations: list[LiteratureRelation]
    traces: list[ReasoningTrace]
