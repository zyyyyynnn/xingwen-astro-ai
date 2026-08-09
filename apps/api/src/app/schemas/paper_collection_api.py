"""Transport projections for the PaperCollection read boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .paper_collection import (
    PaperCollection,
    PaperCollectionCandidate,
    PaperDuplicateGroup,
)
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


class PaperCollectionRead(BaseModel):
    """A validated domain payload pinned to one immutable ArtifactVersion."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    source_mode: SourceMode
    content_hash: ContentHash
    input_hash: ContentHash
    created_at: UtcDateTime
    collection: PaperCollection
    producer_execution: ProducerExecutionDetail
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


class PaperCollectionCandidateRead(BaseModel):
    """Candidate plus its duplicate, source and Evidence read projections."""

    model_config = MODEL_CONFIG

    candidate: PaperCollectionCandidate
    duplicate_group: PaperDuplicateGroup
    source_snapshot: SourceSnapshotDetail
    evidence: tuple[EvidenceDetail, ...] = Field(min_length=1)
