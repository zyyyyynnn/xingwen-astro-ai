"""Source record schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .enums import SourceType


class SourceRecordItem(BaseModel):
    id: str
    type: SourceType
    name: str
    url: str
    query: str
    retrieved_at: datetime
    cached: bool = False


class SourcesResponse(BaseModel):
    sources: list[SourceRecordItem]
