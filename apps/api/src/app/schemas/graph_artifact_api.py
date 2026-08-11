"""Transport projections for version-pinned Evidence Graph reads."""

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
from .graph_artifact import (
    GraphArtifactEdge,
    GraphArtifactNode,
    GraphBuildScope,
    GraphEvidenceUse,
    GraphInputVersionClosure,
    GraphIntegrityReport,
    GraphLayoutHint,
    GraphPolicySet,
    GraphProgressiveInput,
    GraphTaxonomy,
)
from .literature_artifact_api import LiteratureRelationRead

MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)


class GraphArtifactVersionContext(BaseModel):
    model_config = MODEL_CONFIG

    artifact_version_id: Identifier
    artifact_id: Identifier
    project_id: Identifier
    version_number: int = Field(ge=1)
    supersedes_version_id: Identifier | None
    source_mode: SourceMode
    schema_version: str
    content_hash: ContentHash
    input_hash: ContentHash
    scientific_hash: ContentHash
    layout_hash: ContentHash
    report_hash: ContentHash
    output_hash: ContentHash
    created_at: UtcDateTime
    producer_execution: ProducerExecutionDetail


class GraphArtifactRead(BaseModel):
    """Fixed Graph metadata; nodes and edges are read through bounded pages."""

    model_config = MODEL_CONFIG

    version: GraphArtifactVersionContext
    graph_id: Identifier
    project_id: Identifier
    input_versions: GraphInputVersionClosure
    taxonomy: GraphTaxonomy
    policies: GraphPolicySet
    scope: GraphBuildScope
    integrity_report: GraphIntegrityReport
    progressive: GraphProgressiveInput
    layout_hint: GraphLayoutHint
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    evidence_use_count: int = Field(ge=0)


class GraphNodeRead(BaseModel):
    model_config = MODEL_CONFIG

    version: GraphArtifactVersionContext
    node: GraphArtifactNode


class GraphEvidenceUseRead(BaseModel):
    model_config = MODEL_CONFIG

    use: GraphEvidenceUse
    evidence: EvidenceDetail
    source_snapshot: SourceSnapshotDetail


class GraphEdgeRead(BaseModel):
    model_config = MODEL_CONFIG

    version: GraphArtifactVersionContext
    edge: GraphArtifactEdge
    evidence: tuple[GraphEvidenceUseRead, ...]
    relation: LiteratureRelationRead | None = None


__all__ = [
    "GraphArtifactRead",
    "GraphArtifactVersionContext",
    "GraphEdgeRead",
    "GraphEvidenceUseRead",
    "GraphNodeRead",
]
