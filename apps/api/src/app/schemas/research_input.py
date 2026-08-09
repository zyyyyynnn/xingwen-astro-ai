"""Contracts for research-input attachments and URL ingestion.

Controlled ingestion boundary for the Research Composer: URL, PDF, CSV, JSON,
image and plain-text inputs. This contract only *receives* inputs into an
immutable, content-addressed boundary and records provenance; it never
promises PDF/image comprehension, OCR, cleaning or model inference. The API
distinguishes ``accepted`` inputs from ``unsupported_processing`` and
``failed_ingestion`` states without pretending ingestion equals understanding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

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
    "BindResearchInputToContractRequest",
    "BindResearchInputToRunRequest",
    "CreateResearchInputMultipartRequest",
    "CreateResearchInputRequest",
    "ResearchInputCreate",
    "ResearchInputDetail",
    "ResearchInputRef",
    "ResearchInputStatus",
    "ResearchInputType",
    "TextResearchInputRequest",
    "UrlResearchInputRequest",
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

    ``accepted`` is the only state Research Input Ingestion produces: ingestion succeeded and the
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


class UrlResearchInputRequest(BaseModel):
    """JSON create for ``type=url``: a URL is fetched server-side.

    Modelled as its own type (not a nullable mega-model) so the generated JSON
    Schema *machine-level* forbids ``text_content`` and file semantics here
    instead of relying on a runtime-only validator.
    """

    model_config = CORE_MODEL_CONFIG

    type: Literal[ResearchInputType.url]
    project_id: Identifier
    url: Annotated[str, Field(min_length=1, max_length=2048)]
    filename: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    mime_type: Annotated[str | None, Field(default=None, max_length=127)]


class TextResearchInputRequest(BaseModel):
    """JSON create for ``type=text``: the body carries the text itself."""

    model_config = CORE_MODEL_CONFIG

    type: Literal[ResearchInputType.text]
    project_id: Identifier
    text_content: Annotated[str, Field(min_length=1, max_length=100000)]
    filename: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    mime_type: Annotated[str | None, Field(default=None, max_length=127)]


#: The JSON create contract. Only ``url`` and ``text`` are reachable over
#: ``application/json``; pdf/csv/json/image are multipart-only. The public name
#: *is* the union -- there is exactly one authority for the JSON body, with no
#: second mega-model or second JSON alias to drift from.
CreateResearchInputRequest = Annotated[
    UrlResearchInputRequest | TextResearchInputRequest,
    Field(discriminator="type"),
]


class CreateResearchInputMultipartRequest(BaseModel):
    """``multipart/form-data`` create for the file input types.

    ``file`` is declared as a binary string so the generated OpenAPI carries
    ``type: string, format: binary`` as a real schema, not prose.
    """

    model_config = CORE_MODEL_CONFIG

    project_id: Identifier
    type: Literal[
        ResearchInputType.pdf,
        ResearchInputType.csv,
        ResearchInputType.json,
        ResearchInputType.image,
    ]
    filename: Annotated[str | None, Field(default=None, min_length=1, max_length=255)]
    mime_type: Annotated[str | None, Field(default=None, max_length=127)]
    file: Annotated[
        bytes,
        Field(json_schema_extra={"type": "string", "format": "binary"}),
    ]


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


class BindResearchInputToContractRequest(BaseModel):
    """Attach an ingested input reference to a ContractDraft.

    ``run_id`` is pinned to ``None`` so the generated schema itself rules out
    the "both targets" case rather than deferring to a runtime validator.
    """

    model_config = CORE_MODEL_CONFIG

    project_id: Identifier
    contract_draft_id: Identifier
    run_id: None = None


class BindResearchInputToRunRequest(BaseModel):
    """Attach an ingested input reference to a Run inside the same project."""

    model_config = CORE_MODEL_CONFIG

    project_id: Identifier
    run_id: Identifier
    contract_draft_id: None = None


#: Exactly one binding target, expressed as a union so the JSON Schema forbids
#: both "neither" and "both" at the machine level. Only the reference is bound;
#: binary content and full text never enter the public DTO.
BindResearchInputRequest = Annotated[
    BindResearchInputToContractRequest | BindResearchInputToRunRequest,
    Field(union_mode="left_to_right"),
]
