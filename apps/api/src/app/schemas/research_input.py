"""Research Input attachment and URL ingestion contract (B-19).

Controlled ingestion boundary for the Research Composer: URL, PDF, CSV, JSON,
image and plain-text inputs. This contract only *receives* inputs into an
immutable, content-addressed boundary and records provenance; it never
promises PDF/image comprehension, OCR, cleaning or model inference. The API
distinguishes ``accepted`` inputs from ``unsupported_processing`` and
``failed_ingestion`` states without pretending ingestion equals understanding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from .core import (
    CORE_MODEL_CONFIG,
    ContentHash,
    Identifier,
    NonEmptyString,
    UtcDateTime,
)

__all__ = [
    "BindResearchInputRequest",
    "CreateResearchInputRequest",
    "ResearchInputCreate",
    "ResearchInputDetail",
    "ResearchInputRef",
    "ResearchInputStatus",
    "ResearchInputType",
    "RESEARCH_INPUT_FILENAME_INVALID",
    "RESEARCH_INPUT_INVALID",
    "RESEARCH_INPUT_MIME_REJECTED",
    "RESEARCH_INPUT_NOT_FOUND",
    "RESEARCH_INPUT_RATE_LIMITED",
    "RESEARCH_INPUT_TOO_LARGE",
    "URL_FETCH_BLOCKED",
    "URL_FETCH_FAILED",
    "URL_FETCH_TOO_LARGE",
]


class ResearchInputType(StrEnum):
    url = "url"
    pdf = "pdf"
    csv = "csv"
    json = "json"
    image = "image"
    text = "text"


class ResearchInputStatus(StrEnum):
    """Lifecycle of a controlled research input after ingestion.

    ``accepted`` is the only state B-19 produces: ingestion succeeded and the
    content is frozen behind an immutable content hash. ``unsupported_processing``
    and ``failed_ingestion`` are reserved states the API exposes so consumers
    never mistake "uploaded" for "understood".
    """

    accepted = "accepted"
    unsupported_processing = "unsupported_processing"
    failed_ingestion = "failed_ingestion"


# Domain error codes (documented in docs/architecture/API_CONTRACT.md).
RESEARCH_INPUT_INVALID = "RESEARCH_INPUT_INVALID"
RESEARCH_INPUT_TOO_LARGE = "RESEARCH_INPUT_TOO_LARGE"
RESEARCH_INPUT_MIME_REJECTED = "RESEARCH_INPUT_MIME_REJECTED"
RESEARCH_INPUT_FILENAME_INVALID = "RESEARCH_INPUT_FILENAME_INVALID"
URL_FETCH_BLOCKED = "URL_FETCH_BLOCKED"
URL_FETCH_FAILED = "URL_FETCH_FAILED"
URL_FETCH_TOO_LARGE = "URL_FETCH_TOO_LARGE"
RESEARCH_INPUT_NOT_FOUND = "RESEARCH_INPUT_NOT_FOUND"
RESEARCH_INPUT_RATE_LIMITED = "RESEARCH_INPUT_RATE_LIMITED"

#: Input types that must arrive as a multipart file upload (never JSON body).
FILE_INPUT_TYPES = frozenset(
    {ResearchInputType.pdf, ResearchInputType.csv, ResearchInputType.json, ResearchInputType.image}
)

#: ``source_type`` values produced by ingestion (upload / url_fetch / text).
UPLOAD_SOURCE_TYPE = "upload"
URL_FETCH_SOURCE_TYPE = "url_fetch"
TEXT_SOURCE_TYPE = "text"


class ResearchInputCreate(BaseModel):
    """Client payload describing one input to ingest.

    ``type=url`` requires ``url``; ``type=text`` requires ``text_content``;
    the file types (pdf/csv/json/image) always arrive through the multipart
    transport and never carry ``url`` or ``text_content``.
    """

    model_config = CORE_MODEL_CONFIG

    type: ResearchInputType
    url: Annotated[str | None, Field(default=None, max_length=2048)]
    filename: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    mime_type: Annotated[str | None, Field(default=None, max_length=127)]
    text_content: Annotated[str | None, Field(default=None, max_length=100000)]

    @model_validator(mode="after")
    def validate_composition(self) -> ResearchInputCreate:
        if self.type is ResearchInputType.url:
            if not self.url:
                raise ValueError("url is required when type is url")
            if self.text_content:
                raise ValueError("text_content must not be set when type is url")
            return self
        if self.type is ResearchInputType.text:
            if not self.text_content:
                raise ValueError("text_content is required when type is text")
            if self.url:
                raise ValueError("url must not be set when type is text")
            return self
        if self.url or self.text_content:
            raise ValueError(
                f"type {self.type.value} requires a multipart file upload, not url or text_content"
            )
        return self


class CreateResearchInputRequest(ResearchInputCreate):
    """JSON transport for URL and text ingestion (files use multipart)."""

    project_id: Identifier


class ResearchInputRef(BaseModel):
    """Immutable reference to one ingested input; never carries binary content."""

    model_config = CORE_MODEL_CONFIG

    id: Identifier
    type: ResearchInputType
    source_type: NonEmptyString
    content_hash: ContentHash
    filename: str | None = None
    mime_type: str | None = None
    size_bytes: int = Field(ge=0)
    created_at: UtcDateTime
    source_snapshot_id: Identifier | None = None
    status: ResearchInputStatus = ResearchInputStatus.accepted


class ResearchInputDetail(ResearchInputRef):
    """Metadata-only detail read; adds the owning project and the redacted URL."""

    project_id: Identifier
    #: Sanitized source URL when ``source_type == "url_fetch"``; ``None`` otherwise.
    url: str | None = None


class BindResearchInputRequest(BaseModel):
    """Attach an ingested input reference to a ContractDraft or a Run.

    Only the reference is bound; binary content and full text never enter the
    public DTO.
    """

    model_config = CORE_MODEL_CONFIG

    project_id: Identifier
    contract_draft_id: Identifier | None = None
    run_id: Identifier | None = None

    @model_validator(mode="after")
    def require_one_target(self) -> BindResearchInputRequest:
        if self.contract_draft_id is None and self.run_id is None:
            raise ValueError("contract_draft_id or run_id must be provided")
        return self
