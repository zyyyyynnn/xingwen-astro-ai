"""Evidence schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import EvidenceType
from .manifest import ContentHash, Identifier


class Locator(BaseModel):
    kind: str
    value: str


class SourceSnapshotSummary(BaseModel):
    """Phase 0 Evidence projection retained for the existing v1 response."""

    retrieved_at: datetime
    query_hash: str | None = None


class SourceSnapshot(BaseModel):
    """Immutable pipeline source record consumed by the future publisher."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: Identifier
    source_id: Identifier
    source_type: str = Field(min_length=1)
    retrieved_at: datetime
    query: str = Field(min_length=1)
    query_hash: ContentHash
    source_version_or_etag: str | None = None
    content_hash: ContentHash
    license_note: str = Field(min_length=1)
    cache_version: str | None = None
    request_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_sensitive_request_metadata(self) -> Self:
        forbidden = {
            "authorization",
            "proxy-authorization",
            "cookie",
            "set-cookie",
            "api_key",
            "apikey",
            "access_token",
            "refresh_token",
            "secret",
        }
        keys = {
            key.casefold().replace("-", "_")
            for key in _nested_keys(self.request_metadata)
        }
        if keys & forbidden:
            raise ValueError("SourceSnapshot request_metadata contains sensitive keys")
        return self


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


def _nested_keys(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(
            str(key)
            for key, nested in value.items()
        ) + tuple(
            child
            for nested in value.values()
            for child in _nested_keys(nested)
        )
    if isinstance(value, (list, tuple)):
        return tuple(child for nested in value for child in _nested_keys(nested))
    return ()
