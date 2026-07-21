"""Source record schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .enums import SourceType


class SourceRecordItem(BaseModel):
    id: str
    task_id: str
    type: SourceType
    name: str
    url: str
    query: str
    retrieved_at: datetime
    cached: bool = False
    license_note: str | None = None


class SourcesResponse(BaseModel):
    sources: list[SourceRecordItem]
