"""Shared provenance primitives used by Data Artifact and SourceTable schemas."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .core import Identifier as RuntimeIdentifier
from .manifest import ContentHash, Identifier, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NonEmptyString = Annotated[str, Field(min_length=1)]


class ManifestPins(BaseModel):
    model_config = MODEL_CONFIG

    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash


class DatabaseCellLocator(BaseModel):
    """Locator for one structured database cell."""

    model_config = MODEL_CONFIG

    kind: Literal["database_cell"] = "database_cell"
    source_role: Literal["left", "right", "single"]
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    source_id: Identifier
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    raw_record_content_hash: ContentHash
    raw_field: NonEmptyString


__all__ = ["DatabaseCellLocator", "ManifestPins"]
