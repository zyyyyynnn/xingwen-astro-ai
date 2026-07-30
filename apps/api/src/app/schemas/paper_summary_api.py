"""Transport projections for the B-07 PaperSummary read boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .paper_summary import PaperSummaryArtifactContent
from .core import (
    ContentHash,
    EvidenceDetail,
    Identifier,
    ProducerExecutionDetail,
    SourceMode,
    SourceSnapshotDetail,
    UtcDateTime,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class PaperSummaryRead(BaseModel):
    """A validated PaperSummary pinned to one immutable ArtifactVersion."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    summary: PaperSummaryArtifactContent
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


__all__ = ["PaperSummaryRead"]
