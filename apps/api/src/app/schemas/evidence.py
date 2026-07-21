"""Evidence schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import EvidenceType


class Locator(BaseModel):
    kind: str
    value: str


class SourceSnapshot(BaseModel):
    retrieved_at: datetime
    query_hash: str | None = None


class EvidenceResponse(BaseModel):
    id: str
    task_id: str
    type: EvidenceType
    source_id: str | None = None
    paper_id: str | None = None
    target_type: str
    target_id: str
    content: str | None = None
    locator: Locator | None = None
    quote_or_value: str | None = None
    extraction_method: str
    source_snapshot: SourceSnapshot
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
