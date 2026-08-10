"""Transport projections for version-pinned data-artifact reads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .core import (
    ContentHash,
    EvidenceDetail,
    Identifier,
    ProducerExecutionDetail,
    SemanticVersion,
    SourceMode,
    SourceSnapshotDetail,
    UtcDateTime,
)
from .data_artifacts import (
    DatasetArtifactCandidate,
    DatasetRow,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
)
from .data_quality import DataQualityProjection


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class DataArtifactReadBase(BaseModel):
    """A typed candidate pinned to one immutable ArtifactVersion."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    schema_version: SemanticVersion
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]
    quality_projection: DataQualityProjection


class DatasetArtifactRead(DataArtifactReadBase):
    dataset: DatasetArtifactCandidate


class FieldDictionaryArtifactRead(DataArtifactReadBase):
    field_dictionary: FieldDictionaryArtifactCandidate


class SourceCollectionArtifactRead(DataArtifactReadBase):
    source_collection: SourceCollectionArtifactCandidate


class DataArtifactRowRead(BaseModel):
    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    row: DatasetRow


class CreateArtifactExportRequest(BaseModel):
    model_config = MODEL_CONFIG

    format: Literal["csv", "json", "provenance_report"]


class ArtifactExportRead(BaseModel):
    model_config = MODEL_CONFIG

    id: Identifier
    artifact_version_id: Identifier
    project_id: Identifier
    format: Literal["csv", "json", "provenance_report"]
    status: Literal["completed", "expired"]
    content_hash: ContentHash
    generated_at: UtcDateTime
    expires_at: UtcDateTime
    download_url: str | None = None


class ArtifactExportDownload(BaseModel):
    model_config = MODEL_CONFIG

    export: ArtifactExportRead
    content: bytes = Field(repr=False)
    media_type: str
    filename: str
