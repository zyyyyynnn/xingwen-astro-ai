"""Transport projection for canonical scientific ArtifactVersion reads."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from .core import (
    ContentHash,
    EvidenceDetail,
    Identifier,
    ProducerExecutionDetail,
    SourceMode,
    SourceSnapshotDetail,
    UtcDateTime,
)
from .scientific_skills import (
    AnalysisReportArtifactContent,
    ModelEvaluationArtifactContent,
    VisualizationArtifactContent,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
ScientificReadContent = Annotated[
    AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | ModelEvaluationArtifactContent,
    Field(discriminator="kind"),
]


class ScientificArtifactRead(BaseModel):
    """One verified scientific payload pinned to its immutable publication."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    version_number: int = Field(ge=1)
    supersedes_version_id: Identifier | None
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    content: ScientificReadContent
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


__all__ = ["ScientificArtifactRead", "ScientificReadContent"]
