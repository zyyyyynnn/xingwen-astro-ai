"""Evidence schemas."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import EvidenceType
from .manifest import ContentHash, Identifier


_SENSITIVE_METADATA_KEY_FRAGMENTS = frozenset(
    {
        "api_key",
        "apikey",
        "apitoken",
        "authheader",
        "authorization",
        "bearertoken",
        "cookie",
        "credential",
        "database_url",
        "password",
        "privatekey",
        "refresh_token",
        "secret",
        "session_token",
        "access_token",
    }
)
_TOKEN_CREDENTIAL_QUALIFIERS = frozenset(
    {
        "access",
        "api",
        "auth",
        "authentication",
        "authorization",
        "bearer",
        "refresh",
        "session",
    }
)
_KEY_CREDENTIAL_QUALIFIERS = frozenset(
    {"api", "credential", "encryption", "private", "secret", "signing"}
)
_HEADER_CREDENTIAL_QUALIFIERS = frozenset(
    {"auth", "authentication", "authorization", "bearer", "credential", "proxy"}
)


class Locator(BaseModel):
    kind: str
    value: str


class SourceSnapshot(BaseModel):
    """Phase 0 Evidence projection retained for the existing Pipeline response."""

    retrieved_at: datetime
    query_hash: str | None = None


class SourceSnapshotRecord(BaseModel):
    """Immutable pipeline source record consumed by the future publisher.

    Implements the core ``SourceSnapshot`` target entity described in
    ``docs/architecture/DATA_MODEL.md`` under a distinct name so the frozen
    Phase 0 ``SourceSnapshot`` projection above stays unchanged.
    """

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
    cache_version: Annotated[str, Field(min_length=1)] | None = None
    request_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cache_version")
    @classmethod
    def reject_blank_cache_version(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("cache_version must not be blank")
        return value

    @model_validator(mode="after")
    def reject_sensitive_request_metadata(self) -> Self:
        if any(
            _metadata_key_is_sensitive(key)
            for key in _nested_keys(self.request_metadata)
        ):
            raise ValueError("SourceSnapshotRecord request_metadata contains sensitive keys")
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


def _metadata_key_is_sensitive(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    segments = frozenset(normalized.split("_"))
    return (
        any(fragment in normalized for fragment in _SENSITIVE_METADATA_KEY_FRAGMENTS)
        or (
            bool(segments & {"token", "tokens"})
            and bool(segments & _TOKEN_CREDENTIAL_QUALIFIERS)
        )
        or (
            bool(segments & {"key", "keys"})
            and bool(segments & _KEY_CREDENTIAL_QUALIFIERS)
        )
        or (
            bool(segments & {"header", "headers"})
            and bool(segments & _HEADER_CREDENTIAL_QUALIFIERS)
        )
    )
