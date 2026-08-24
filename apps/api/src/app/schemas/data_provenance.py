"""Shared provenance variants for values admitted into Data Artifacts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .core import ContentHash, Identifier, NonEmptyString
from .crossmatch import CrossmatchSide
from .scientific_document import DocumentLocator, DocumentParseQuality


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class StructuredDataProvenance(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["structured"] = "structured"
    side: CrossmatchSide
    pipeline_source_snapshot_id: Identifier
    pipeline_source_snapshot_content_hash: ContentHash
    source_id: Identifier
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    raw_record_content_hash: ContentHash
    raw_field: NonEmptyString
    source_table: NonEmptyString
    reference_field: NonEmptyString | None = None
    reference_value: str | int | float | bool | None = None
    provenance_field: NonEmptyString | None = None
    provenance_value: str | int | float | bool | None = None


class DocumentDataProvenance(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["document"] = "document"
    project_id: Identifier
    research_input_id: Identifier
    research_input_content_hash: ContentHash
    document_parse_id: Identifier
    persisted_source_snapshot_id: Identifier
    pipeline_source_snapshot_id: Identifier
    pipeline_source_id: Literal["research_input"] = "research_input"
    pipeline_query_hash: ContentHash
    pipeline_source_snapshot_content_hash: ContentHash
    locator: DocumentLocator
    parse_quality: DocumentParseQuality


DataValueProvenance = Annotated[
    StructuredDataProvenance | DocumentDataProvenance,
    Field(discriminator="kind"),
]


__all__ = [
    "DataValueProvenance",
    "DocumentDataProvenance",
    "StructuredDataProvenance",
]
