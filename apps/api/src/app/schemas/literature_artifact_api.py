"""Transport projections for version-pinned literature-artifact reads."""

from __future__ import annotations

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
from .literature_claim import LiteratureClaimCandidate
from .literature_relation import (
    LiteratureReasoningTraceCandidate,
    LiteratureRelationCandidate,
)
from .manifest import SemanticVersion

MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class LiteratureArtifactVersionContext(BaseModel):
    """Immutable publication context shared by one paged domain item."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    version_number: int = Field(ge=1)
    supersedes_version_id: Identifier | None
    source_mode: SourceMode
    schema_version: SemanticVersion
    content_hash: ContentHash
    input_hash: ContentHash
    output_hash: ContentHash
    created_at: UtcDateTime
    producer_execution: ProducerExecutionDetail


class LiteraturePaperSummaryReference(BaseModel):
    """Pinned PaperSummary identity used by an admitted LiteratureClaim."""

    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    summary_id: Identifier
    paper_id: Identifier
    schema_version: Identifier
    content_hash: ContentHash
    output_hash: ContentHash


class LiteratureClaimRead(BaseModel):
    """One Claim with its pinned Summary and persisted provenance projection."""

    model_config = MODEL_CONFIG

    version: LiteratureArtifactVersionContext
    claim: LiteratureClaimCandidate
    paper_summary: LiteraturePaperSummaryReference
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


class LiteratureRelationRead(BaseModel):
    """One Relation with both Claim endpoints and its auditable Trace."""

    model_config = MODEL_CONFIG

    version: LiteratureArtifactVersionContext
    relation: LiteratureRelationCandidate
    source_claim: LiteratureClaimRead | None
    target_claim: LiteratureClaimRead | None
    reasoning_trace: LiteratureReasoningTraceCandidate | None
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]
    graph_eligible: bool


class LiteratureReasoningTraceRead(BaseModel):
    """One public Trace linked to its Relation, Claims, and Evidence."""

    model_config = MODEL_CONFIG

    version: LiteratureArtifactVersionContext
    trace: LiteratureReasoningTraceCandidate
    relation: LiteratureRelationCandidate
    source_claim: LiteratureClaimRead
    target_claim: LiteratureClaimRead
    source_snapshots: tuple[SourceSnapshotDetail, ...]
    evidence: tuple[EvidenceDetail, ...]


__all__ = [
    "LiteratureArtifactVersionContext",
    "LiteratureClaimRead",
    "LiteraturePaperSummaryReference",
    "LiteratureReasoningTraceRead",
    "LiteratureRelationRead",
]
