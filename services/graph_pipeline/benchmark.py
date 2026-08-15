"""Deterministic evidence-graph evaluation against frozen paper-acquisition labels.

The built-in adapter is an offline replay oracle for the tracked Benchmark and
Fixture cases.  It does not construct or seal a :class:`GraphArtifactCandidate`
and therefore cannot be passed to the Publisher.  A production GraphPipeline
adapter can implement :class:`GraphBenchmarkAdapter` and return the same
observation contract once the builder is available.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GRAPH_INTEGRITY_POLICY_VERSION,
    GRAPH_BENCHMARK_DISCLAIMER,
    GraphBenchmarkCaseKind,
    GraphBenchmarkCaseResult,
    GraphBenchmarkDenominatorScope,
    GraphBenchmarkEvaluationCase,
    GraphBenchmarkMetric,
    GraphBenchmarkReport,
    GraphBenchmarkVersionSet,
    GraphIntegrityCounts,
    GraphIntegrityFinding,
    GraphIntegrityReport,
    GraphIntegrityStage,
    GraphIntegrityStatus,
    GraphRejectionReason,
    compute_graph_benchmark_case_hash,
    compute_graph_benchmark_output_hash,
    compute_graph_integrity_report_hash,
    compute_graph_layout_hash,
)
from app.schemas.paper_benchmark import (
    BenchmarkAdmissionStatus,
    BenchmarkPackage,
    BenchmarkReviewStatus,
)
from services.paper_pipeline.benchmark import (
    load_frozen_benchmark,
    validate_frozen_benchmark,
)


_MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    allow_inf_nan=False,
    str_strip_whitespace=True,
)
_ReplayIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    ),
]
_ContentHash = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$", max_length=71),
]

_CASE_ADAPTER = TypeAdapter(tuple[GraphBenchmarkEvaluationCase, ...])
_ZERO_HASH = "sha256:" + "0" * 64

_EXPECTED_PAPER_BENCHMARK_SCHEMA_VERSION = "2.0.0"
_EXPECTED_PAPER_BENCHMARK_BENCHMARK_VERSION = "2.0.0"
_EXPECTED_PAPER_BENCHMARK_SCIENTIFIC_HASH = (
    "sha256:1a9969d31f80198f73c008eb78cdba70cb4411570345f0829552da4bcda87db9"
)
_EXPECTED_PAPER_BENCHMARK_CONTENT_HASH = (
    "sha256:a315b54f934bb3b37e8273a9a766d5c87bd494089d99d7e82b6920b782e8ad57"
)
_EXPECTED_PAPER_BENCHMARK_NODES = (
    (
        "node.claim_clark_catalog",
        GraphNodeType.claim,
        "claim.clark_crossmatched_catalog",
    ),
    (
        "node.claim_stassun_2018_method",
        GraphNodeType.claim,
        "claim.stassun_2018_tic_method",
    ),
    (
        "node.claim_stassun_2019_revision",
        GraphNodeType.claim,
        "claim.stassun_2019_gaia_revision",
    ),
    (
        "node.paper_clark_2021",
        GraphNodeType.paper,
        "paper.clark_2021_galah_tess",
    ),
    (
        "node.paper_stassun_2018",
        GraphNodeType.paper,
        "paper.stassun_2018_tic",
    ),
    (
        "node.paper_stassun_2019",
        GraphNodeType.paper,
        "paper.stassun_2019_revised_tic",
    ),
)
_EXPECTED_PAPER_BENCHMARK_EDGES = (
    (
        "edge.paper_to_initial_tic_claim",
        "node.paper_stassun_2018",
        "node.claim_stassun_2018_method",
        GraphEdgeType.supports_finding,
        ("evidence.claim_stassun_2018_method",),
        False,
        None,
        None,
    ),
    (
        "edge.revised_tic_to_initial_tic",
        "node.claim_stassun_2019_revision",
        "node.claim_stassun_2018_method",
        GraphEdgeType.extends,
        (
            "evidence.claim_stassun_2018_method",
            "evidence.claim_stassun_2019_revision",
        ),
        True,
        "relation.revised_tic_extends_initial_tic",
        "trace.revised_tic_extends_initial_tic",
    ),
)

_STAGE_PRIORITY = {
    GraphIntegrityStage.input_schema: 100,
    GraphIntegrityStage.artifact_version: 200,
    GraphIntegrityStage.ownership: 300,
    GraphIntegrityStage.taxonomy: 400,
    GraphIntegrityStage.identity: 500,
    GraphIntegrityStage.endpoint: 600,
    GraphIntegrityStage.evidence_snapshot: 700,
    GraphIntegrityStage.relation_trace: 800,
    GraphIntegrityStage.direction_type: 900,
    GraphIntegrityStage.capacity_progressive: 1000,
    GraphIntegrityStage.hash_commitment: 1100,
}


class _ReplayNode(BaseModel):
    model_config = _MODEL_CONFIG

    node_id: _ReplayIdentifier
    node_type: GraphNodeType
    ref_id: _ReplayIdentifier


class _ReplayEdge(BaseModel):
    model_config = _MODEL_CONFIG

    edge_id: _ReplayIdentifier
    source: _ReplayIdentifier
    target: _ReplayIdentifier
    edge_type: GraphEdgeType
    evidence_ids: tuple[_ReplayIdentifier, ...]
    cross_document: bool
    relation_id: _ReplayIdentifier | None = None
    reasoning_trace_id: _ReplayIdentifier | None = None


class _ReplayRelation(BaseModel):
    model_config = _MODEL_CONFIG

    relation_id: _ReplayIdentifier
    source_claim_id: _ReplayIdentifier
    target_claim_id: _ReplayIdentifier
    relation_type: GraphEdgeType
    evidence_ids: tuple[_ReplayIdentifier, ...]
    status: Literal["accepted", "candidate", "rejected"]
    review_status: Literal["approved"]
    reasoning_trace_id: _ReplayIdentifier | None = None


class _ReplayTrace(BaseModel):
    model_config = _MODEL_CONFIG

    trace_id: _ReplayIdentifier
    relation_id: _ReplayIdentifier
    premise_claim_ids: tuple[_ReplayIdentifier, _ReplayIdentifier]
    review_status: Literal["approved"]


class _ReplaySourceSnapshot(BaseModel):
    model_config = _MODEL_CONFIG

    source_snapshot_id: _ReplayIdentifier
    project_id: _ReplayIdentifier
    content_hash: _ContentHash


class _ReplayEvidence(BaseModel):
    model_config = _MODEL_CONFIG

    evidence_id: _ReplayIdentifier
    project_id: _ReplayIdentifier
    input_version_id: _ReplayIdentifier
    source_snapshot_id: _ReplayIdentifier
    source_snapshot_content_hash: _ContentHash


class _ReplayDataFieldClosure(BaseModel):
    model_config = _MODEL_CONFIG

    field_node_id: _ReplayIdentifier
    mapped_selected_evidence_ids: tuple[_ReplayIdentifier, ...]
    mapped_unselected_evidence_ids: tuple[_ReplayIdentifier, ...]
    declared_null_evidence_ids: tuple[_ReplayIdentifier, ...]
    unresolved_evidence_ids: tuple[_ReplayIdentifier, ...]
    conflict_evidence_ids: tuple[_ReplayIdentifier, ...]


class _ReplayInput(BaseModel):
    """Strict, non-production wire format used only by the offline oracle."""

    model_config = _MODEL_CONFIG

    schema_version: Literal["2.0.0"]
    paper_benchmark_schema_version: Literal["2.0.0"]
    paper_benchmark_version: Literal["2.0.0"]
    paper_benchmark_scientific_payload_hash: _ContentHash
    paper_benchmark_content_hash: _ContentHash
    project_id: _ReplayIdentifier
    reference_project_id: _ReplayIdentifier
    input_version_id: _ReplayIdentifier
    reference_input_version_id: _ReplayIdentifier
    input_version_known: bool = True
    input_version_published: bool = True
    input_artifact_kind: _ReplayIdentifier
    expected_input_artifact_kind: _ReplayIdentifier
    input_schema_version: _ReplayIdentifier
    supported_input_schema_version: _ReplayIdentifier
    input_content_hash: _ContentHash
    declared_input_content_hash: _ContentHash
    input_hash: _ContentHash
    declared_input_hash: _ContentHash
    producer_execution_matches: bool = True
    candidate_hash_matches: bool = True
    taxonomy_node_types: tuple[GraphNodeType, ...]
    taxonomy_edge_types: tuple[GraphEdgeType, ...]
    nodes: tuple[_ReplayNode, ...]
    edges: tuple[_ReplayEdge, ...]
    relations: tuple[_ReplayRelation, ...]
    reasoning_traces: tuple[_ReplayTrace, ...]
    evidence_ids: tuple[_ReplayIdentifier, ...]
    evidence: tuple[_ReplayEvidence, ...]
    source_snapshots: tuple[_ReplaySourceSnapshot, ...]
    source_snapshot_registry_complete: bool = True
    data_field_closures: tuple[_ReplayDataFieldClosure, ...] = ()
    declared_complete_item_count: int = Field(ge=0, le=80_000)
    max_nodes: int = Field(default=10_000, ge=1, le=10_000)
    max_edges: int = Field(default=20_000, ge=1, le=20_000)
    max_evidence_uses: int = Field(default=50_000, ge=1, le=50_000)
    filter_complete: bool = True
    aggregation_complete: bool = True
    progressive_complete: bool = True


@dataclass(frozen=True, slots=True)
class GraphBenchmarkObservation:
    """Adapter-neutral result consumed by the metric evaluator."""

    schema_valid: bool
    status: GraphIntegrityStatus
    nodes: tuple[_ReplayNode, ...]
    edges: tuple[_ReplayEdge, ...]
    evidence_ids: tuple[str, ...]
    relations: tuple[_ReplayRelation, ...]
    reasoning_traces: tuple[_ReplayTrace, ...]
    report: GraphIntegrityReport
    stable_order_pass: bool
    input_hash: str
    output_hash: str
    scientific_hash: str | None = None
    layout_hash: str | None = None


class GraphBenchmarkAdapter(Protocol):
    """Narrow evaluation seam for GraphPipeline benchmark adapters."""

    def evaluate_case(
        self,
        case: GraphBenchmarkEvaluationCase,
    ) -> GraphBenchmarkObservation:
        """Evaluate one immutable case without mutating or publishing state."""


FORMAL_REJECTION_EXPECTATIONS: tuple[
    tuple[str, GraphIntegrityStage, GraphRejectionReason], ...
] = tuple(
    sorted(
        (
            (
                "rejection.aggregation_incomplete",
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.aggregation_incomplete,
            ),
            (
                "rejection.candidate_hash_mismatch",
                GraphIntegrityStage.hash_commitment,
                GraphRejectionReason.candidate_hash_mismatch,
            ),
            (
                "rejection.content_hash_mismatch",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.content_hash_mismatch,
            ),
            (
                "rejection.cross_project_ownership",
                GraphIntegrityStage.ownership,
                GraphRejectionReason.cross_project_ownership,
            ),
            (
                "rejection.cross_version_reference",
                GraphIntegrityStage.ownership,
                GraphRejectionReason.cross_version_reference,
            ),
            (
                "rejection.data_duplicate_dataset_field_edge",
                GraphIntegrityStage.identity,
                GraphRejectionReason.identity_collision,
            ),
            (
                "rejection.data_evidence_union_incomplete",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_inconsistent,
            ),
            (
                "rejection.data_source_to_field",
                GraphIntegrityStage.taxonomy,
                GraphRejectionReason.taxonomy_violation,
            ),
            (
                "rejection.data_wrong_direction",
                GraphIntegrityStage.direction_type,
                GraphRejectionReason.wrong_direction,
            ),
            (
                "rejection.data_zero_evidence",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_missing,
            ),
            (
                "rejection.dangling_endpoint",
                GraphIntegrityStage.endpoint,
                GraphRejectionReason.dangling_endpoint,
            ),
            (
                "rejection.duplicate_edge_identity",
                GraphIntegrityStage.identity,
                GraphRejectionReason.duplicate_edge_identity,
            ),
            (
                "rejection.duplicate_node_identity",
                GraphIntegrityStage.identity,
                GraphRejectionReason.duplicate_node_identity,
            ),
            (
                "rejection.evidence_missing",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_missing,
            ),
            (
                "rejection.evidence_inconsistent",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_inconsistent,
            ),
            (
                "rejection.evidence_unknown",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_unknown,
            ),
            (
                "rejection.filter_hides_evidence",
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.evidence_hidden_by_filter,
            ),
            (
                "rejection.input_hash_mismatch",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.input_hash_mismatch,
            ),
            (
                "rejection.input_version_unknown",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.input_version_unknown,
            ),
            (
                "rejection.input_version_unpublished",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.input_version_unpublished,
            ),
            (
                "rejection.invalid_json",
                GraphIntegrityStage.input_schema,
                GraphRejectionReason.invalid_json,
            ),
            (
                "rejection.missing_edge",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_missing,
            ),
            (
                "rejection.nonaccepted_candidate_relation",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.relation_not_accepted,
            ),
            (
                "rejection.nonaccepted_contradicts_relation",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.relation_not_accepted,
            ),
            (
                "rejection.nonaccepted_limits_relation",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.relation_not_accepted,
            ),
            (
                "rejection.progressive_incomplete",
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.progressive_input_incomplete,
            ),
            (
                "rejection.producer_execution_mismatch",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.producer_execution_mismatch,
            ),
            (
                "rejection.provenance_version_mismatch",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.provenance_version_mismatch,
            ),
            (
                "rejection.reasoning_trace_incomplete",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.reasoning_trace_incomplete,
            ),
            (
                "rejection.reasoning_trace_mismatch",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.reasoning_trace_mismatch,
            ),
            (
                "rejection.reasoning_trace_missing",
                GraphIntegrityStage.relation_trace,
                GraphRejectionReason.reasoning_trace_missing,
            ),
            (
                "rejection.relation_type_mismatch",
                GraphIntegrityStage.direction_type,
                GraphRejectionReason.relation_type_mismatch,
            ),
            (
                "rejection.schema_invalid",
                GraphIntegrityStage.input_schema,
                GraphRejectionReason.schema_invalid,
            ),
            (
                "rejection.silent_truncation",
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.silent_truncation,
            ),
            (
                "rejection.source_snapshot_missing",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.source_snapshot_missing,
            ),
            (
                "rejection.source_snapshot_inconsistent",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.source_snapshot_inconsistent,
            ),
            (
                "rejection.source_snapshot_unknown",
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.source_snapshot_unknown,
            ),
            (
                "rejection.taxonomy_node_type",
                GraphIntegrityStage.taxonomy,
                GraphRejectionReason.taxonomy_violation,
            ),
            (
                "rejection.unsupported_schema_version",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.unsupported_schema_version,
            ),
            (
                "rejection.wrong_artifact_kind",
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.wrong_artifact_kind,
            ),
            (
                "rejection.wrong_direction",
                GraphIntegrityStage.direction_type,
                GraphRejectionReason.wrong_direction,
            ),
        )
    )
)

FORMAL_SIZE_EXPECTATIONS: tuple[
    tuple[
        str,
        GraphIntegrityStatus,
        GraphIntegrityStage | None,
        GraphRejectionReason | None,
    ],
    ...,
] = (
    ("size_boundary.exact", GraphIntegrityStatus.passed, None, None),
    (
        "size_boundary.exceeded",
        GraphIntegrityStatus.failed,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.size_limit_exceeded,
    ),
)


class FrozenGraphReplayAdapter:
    """Offline admission oracle for the fixed Paper Acquisition Benchmark/Fixture suite."""

    def __init__(self, benchmark: BenchmarkPackage) -> None:
        validate_frozen_graph_label(benchmark)
        self._benchmark = benchmark

    def evaluate_case(
        self,
        case: GraphBenchmarkEvaluationCase,
    ) -> GraphBenchmarkObservation:
        try:
            raw = json.loads(case.input_json)
        except (json.JSONDecodeError, TypeError):
            return self._failure(
                stage=GraphIntegrityStage.input_schema,
                reason=GraphRejectionReason.invalid_json,
                path="$",
                message="Replay input is not valid JSON.",
                schema_valid=False,
                raw_input_json=case.input_json,
            )
        try:
            payload = _ReplayInput.model_validate(raw)
        except ValueError:
            return self._failure(
                stage=GraphIntegrityStage.input_schema,
                reason=GraphRejectionReason.schema_invalid,
                path="$",
                message="Replay input does not satisfy the fixed schema.",
                schema_valid=False,
                raw_input_json=case.input_json,
            )

        version_failures = (
            (
                not payload.input_version_known,
                GraphRejectionReason.input_version_unknown,
                "$.input_version_id",
                "Replay input ArtifactVersion is unknown.",
            ),
            (
                not payload.input_version_published,
                GraphRejectionReason.input_version_unpublished,
                "$.input_version_id",
                "Replay input ArtifactVersion is not published.",
            ),
            (
                payload.input_artifact_kind != payload.expected_input_artifact_kind,
                GraphRejectionReason.wrong_artifact_kind,
                "$.input_artifact_kind",
                "Replay input ArtifactVersion has the wrong artifact kind.",
            ),
            (
                payload.input_schema_version
                != payload.supported_input_schema_version,
                GraphRejectionReason.unsupported_schema_version,
                "$.input_schema_version",
                "Replay input ArtifactVersion schema is unsupported.",
            ),
            (
                payload.input_content_hash != payload.declared_input_content_hash,
                GraphRejectionReason.content_hash_mismatch,
                "$.input_content_hash",
                "Replay input ArtifactVersion content hash does not match its pin.",
            ),
            (
                payload.input_hash != payload.declared_input_hash,
                GraphRejectionReason.input_hash_mismatch,
                "$.input_hash",
                "Replay input ArtifactVersion input hash does not match its pin.",
            ),
            (
                not payload.producer_execution_matches,
                GraphRejectionReason.producer_execution_mismatch,
                "$.producer_execution_matches",
                "Replay input ProducerExecution does not match its ArtifactVersion.",
            ),
        )
        for failed, reason, path, message in version_failures:
            if failed:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.artifact_version,
                    reason=reason,
                    path=path,
                    message=message,
                )
        if payload.reference_project_id != payload.project_id:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.ownership,
                reason=GraphRejectionReason.cross_project_ownership,
                path="$.reference_project_id",
                message="Replay provenance escapes the selected Project.",
            )
        if payload.reference_input_version_id != payload.input_version_id:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.ownership,
                reason=GraphRejectionReason.cross_version_reference,
                path="$.reference_input_version_id",
                message="Replay provenance escapes the selected ArtifactVersion.",
            )

        identity = (
            payload.paper_benchmark_schema_version,
            payload.paper_benchmark_version,
            payload.paper_benchmark_scientific_payload_hash,
            payload.paper_benchmark_content_hash,
        )
        expected_identity = (
            self._benchmark.schema_version,
            self._benchmark.benchmark_version,
            self._benchmark.scientific_payload_hash,
            self._benchmark.content_hash,
        )
        if identity != expected_identity:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.artifact_version,
                reason=GraphRejectionReason.content_hash_mismatch,
                path="$.paper_benchmark_content_hash",
                message="Replay input is not pinned to the frozen Paper Acquisition Benchmark identity.",
            )

        node_ids = tuple(item.node_id for item in payload.nodes)
        edge_ids = tuple(item.edge_id for item in payload.edges)
        relation_ids = tuple(item.relation_id for item in payload.relations)
        trace_ids = tuple(item.trace_id for item in payload.reasoning_traces)
        stable_order = all(
            values == tuple(sorted(values)) and len(values) == len(set(values))
            for values in (
                node_ids,
                edge_ids,
                relation_ids,
                trace_ids,
                payload.evidence_ids,
                tuple(item.evidence_id for item in payload.evidence),
                tuple(item.source_snapshot_id for item in payload.source_snapshots),
                tuple(item.field_node_id for item in payload.data_field_closures),
            )
        )

        paper_benchmark_taxonomy = (
            tuple(
                sorted(
                    self._benchmark.graph_taxonomy.allowed_node_types,
                    key=lambda item: item.value,
                )
            ),
            tuple(
                sorted(
                    self._benchmark.graph_taxonomy.allowed_edge_types,
                    key=lambda item: item.value,
                )
            ),
        )
        data_taxonomy = (
            (GraphNodeType.dataset, GraphNodeType.field),
            (GraphEdgeType.provides_field,),
        )
        declared_taxonomy = (
            payload.taxonomy_node_types,
            payload.taxonomy_edge_types,
        )
        allowed_nodes = set(payload.taxonomy_node_types)
        allowed_edges = set(payload.taxonomy_edge_types)
        taxonomy_invalid = (
            payload.taxonomy_node_types
            != tuple(sorted(payload.taxonomy_node_types, key=lambda item: item.value))
            or payload.taxonomy_edge_types
            != tuple(sorted(payload.taxonomy_edge_types, key=lambda item: item.value))
            or declared_taxonomy not in (paper_benchmark_taxonomy, data_taxonomy)
            or (
                case.kind is GraphBenchmarkCaseKind.scientific_graph
                and declared_taxonomy != paper_benchmark_taxonomy
            )
            or (
                case.kind is GraphBenchmarkCaseKind.data_mapping_fixture
                and declared_taxonomy != data_taxonomy
            )
            or any(item.node_type not in allowed_nodes for item in payload.nodes)
            or any(item.edge_type not in allowed_edges for item in payload.edges)
        )
        if taxonomy_invalid:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.taxonomy,
                reason=GraphRejectionReason.taxonomy_violation,
                path="$.nodes|$.edges",
                message="Replay graph contains a type outside frozen Paper Acquisition Benchmark taxonomy.",
                stable_order=stable_order,
            )
        if len(node_ids) != len(set(node_ids)):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.identity,
                reason=GraphRejectionReason.duplicate_node_identity,
                path="$.nodes",
                message="Replay graph contains a duplicate node identity.",
                stable_order=stable_order,
            )
        if len(edge_ids) != len(set(edge_ids)):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.identity,
                reason=GraphRejectionReason.duplicate_edge_identity,
                path="$.edges",
                message="Replay graph contains a duplicate edge identity.",
                stable_order=stable_order,
            )
        edge_identities = tuple(
            (item.source, item.target, item.edge_type) for item in payload.edges
        )
        if len(edge_identities) != len(set(edge_identities)):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.identity,
                reason=GraphRejectionReason.identity_collision,
                path="$.edges",
                message="Replay graph repeats one logical edge under another ID.",
                stable_order=stable_order,
            )

        node_by_id = {item.node_id: item for item in payload.nodes}
        for edge in payload.edges:
            if edge.source not in node_by_id or edge.target not in node_by_id:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.endpoint,
                    reason=GraphRejectionReason.dangling_endpoint,
                    path=f"$.edges[{edge.edge_id}]",
                    message="Replay edge endpoint does not resolve to one node.",
                    stable_order=stable_order,
                )

        evidence_by_id = {item.evidence_id: item for item in payload.evidence}
        snapshot_by_id = {
            item.source_snapshot_id: item for item in payload.source_snapshots
        }
        evidence_registry = set(payload.evidence_ids)
        if evidence_registry != set(evidence_by_id):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_inconsistent,
                path="$.evidence|$.evidence_ids",
                message="Replay Evidence IDs must equal the typed Evidence registry.",
                stable_order=stable_order,
            )
        if not payload.source_snapshot_registry_complete:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.source_snapshot_missing,
                path="$.source_snapshots",
                message="Replay SourceSnapshot registry is incomplete.",
                stable_order=stable_order,
            )
        for edge in payload.edges:
            if not edge.evidence_ids:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.evidence_missing,
                    path=f"$.edges[{edge.edge_id}].evidence_ids",
                    message="Every replay edge requires Evidence.",
                    stable_order=stable_order,
                )
            if not set(edge.evidence_ids) <= evidence_registry:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.evidence_unknown,
                    path=f"$.edges[{edge.edge_id}].evidence_ids",
                    message="Replay edge references unknown Evidence.",
                    stable_order=stable_order,
                )
        for evidence in payload.evidence:
            if (
                evidence.project_id != payload.project_id
                or evidence.input_version_id != payload.input_version_id
            ):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.provenance_version_mismatch,
                    path=f"$.evidence[{evidence.evidence_id}]",
                    message="Replay Evidence escapes the selected version provenance.",
                    stable_order=stable_order,
                )
            snapshot = snapshot_by_id.get(evidence.source_snapshot_id)
            if snapshot is None:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.source_snapshot_unknown,
                    path=f"$.evidence[{evidence.evidence_id}].source_snapshot_id",
                    message="Replay Evidence references an unknown SourceSnapshot.",
                    stable_order=stable_order,
                )
            if (
                snapshot.project_id != payload.project_id
                or snapshot.content_hash != evidence.source_snapshot_content_hash
            ):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.source_snapshot_inconsistent,
                    path=f"$.source_snapshots[{snapshot.source_snapshot_id}]",
                    message="Replay SourceSnapshot does not match its Evidence binding.",
                    stable_order=stable_order,
                )
        if set(case.expected_edge_ids) - set(edge_ids):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_missing,
                path="$.edges",
                message="Replay graph omits a frozen Paper Acquisition Benchmark edge and its Evidence uses.",
                stable_order=stable_order,
            )

        if declared_taxonomy == data_taxonomy:
            dataset_nodes = tuple(
                item for item in payload.nodes if item.node_type is GraphNodeType.dataset
            )
            field_nodes = tuple(
                item for item in payload.nodes if item.node_type is GraphNodeType.field
            )
            closures = {
                item.field_node_id: item for item in payload.data_field_closures
            }
            if (
                len(dataset_nodes) != 1
                or set(closures) != {item.node_id for item in field_nodes}
            ):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.aggregation_incomplete,
                    path="$.data_field_closures",
                    message=(
                        "Every FieldDictionary field requires one complete Dataset/Field "
                        "Evidence aggregation closure."
                    ),
                    stable_order=stable_order,
                )
            for field in field_nodes:
                closure = closures[field.node_id]
                categories = (
                    closure.mapped_selected_evidence_ids,
                    closure.mapped_unselected_evidence_ids,
                    closure.declared_null_evidence_ids,
                    closure.unresolved_evidence_ids,
                    closure.conflict_evidence_ids,
                )
                if any(
                    values != tuple(sorted(values))
                    or len(values) != len(set(values))
                    for values in categories
                ):
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.evidence_snapshot,
                        reason=GraphRejectionReason.evidence_inconsistent,
                        path=f"$.data_field_closures[{field.node_id}]",
                        message="Data Evidence category registries must be stable and unique.",
                        stable_order=stable_order,
                    )
                expected_union = set().union(*(set(values) for values in categories))
                field_edges = tuple(
                    edge
                    for edge in payload.edges
                    if edge.edge_type is GraphEdgeType.provides_field
                    and field.node_id in (edge.source, edge.target)
                )
                if len(field_edges) != 1:
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.identity,
                        reason=GraphRejectionReason.identity_collision,
                        path=f"$.edges[{field.node_id}]",
                        message="Each Dataset/Field pair requires exactly one edge.",
                        stable_order=stable_order,
                    )
                edge = field_edges[0]
                if not expected_union:
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.evidence_snapshot,
                        reason=GraphRejectionReason.evidence_missing,
                        path=f"$.edges[{edge.edge_id}].evidence_ids",
                        message="provides_field cannot omit its complete Evidence union.",
                        stable_order=stable_order,
                    )
                if set(edge.evidence_ids) != expected_union:
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.evidence_snapshot,
                        reason=GraphRejectionReason.evidence_inconsistent,
                        path=f"$.edges[{edge.edge_id}].evidence_ids",
                        message=(
                            "provides_field must preserve selected, unselected, null, "
                            "unresolved, and conflict Evidence."
                        ),
                        stable_order=stable_order,
                    )

        relation_by_id = {item.relation_id: item for item in payload.relations}
        trace_by_id = {item.trace_id: item for item in payload.reasoning_traces}
        for edge in payload.edges:
            if not edge.cross_document:
                continue
            relation = relation_by_id.get(edge.relation_id or "")
            if relation is None:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.relation_trace,
                    reason=GraphRejectionReason.reasoning_trace_mismatch,
                    path=f"$.edges[{edge.edge_id}].relation_id",
                    message="Cross-document edge does not bind a declared Relation.",
                    stable_order=stable_order,
                )
            if relation.status != "accepted":
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.relation_trace,
                    reason=GraphRejectionReason.relation_not_accepted,
                    path=f"$.relations[{relation.relation_id}].status",
                    message="Only accepted Relations may become Graph edges.",
                    stable_order=stable_order,
                )
            if edge.reasoning_trace_id is None:
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.relation_trace,
                    reason=GraphRejectionReason.reasoning_trace_missing,
                    path=f"$.edges[{edge.edge_id}].reasoning_trace_id",
                    message="Accepted Relation edge requires its ReasoningTrace.",
                    stable_order=stable_order,
                )
            trace = trace_by_id.get(edge.reasoning_trace_id)
            if (
                trace is None
                or relation.reasoning_trace_id != edge.reasoning_trace_id
                or trace.relation_id != relation.relation_id
            ):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.relation_trace,
                    reason=GraphRejectionReason.reasoning_trace_mismatch,
                    path=f"$.edges[{edge.edge_id}].reasoning_trace_id",
                    message="Relation and ReasoningTrace bindings do not match.",
                    stable_order=stable_order,
                )
            if trace.premise_claim_ids != (
                relation.source_claim_id,
                relation.target_claim_id,
            ):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.relation_trace,
                    reason=GraphRejectionReason.reasoning_trace_incomplete,
                    path=f"$.reasoning_traces[{trace.trace_id}]",
                    message="ReasoningTrace premises do not close the Relation.",
                    stable_order=stable_order,
                )
            if set(edge.evidence_ids) != set(relation.evidence_ids):
                return self._failure_from_payload(
                    payload,
                    stage=GraphIntegrityStage.evidence_snapshot,
                    reason=GraphRejectionReason.evidence_inconsistent,
                    path=f"$.edges[{edge.edge_id}].evidence_ids",
                    message="Relation edge Evidence does not equal its frozen closure.",
                    stable_order=stable_order,
                )

        for edge in payload.edges:
            source = node_by_id[edge.source]
            target = node_by_id[edge.target]
            if edge.cross_document:
                relation = relation_by_id[edge.relation_id or ""]
                if (source.ref_id, target.ref_id) != (
                    relation.source_claim_id,
                    relation.target_claim_id,
                ):
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.direction_type,
                        reason=GraphRejectionReason.wrong_direction,
                        path=f"$.edges[{edge.edge_id}]",
                        message="Literature edge reverses its Relation direction.",
                        stable_order=stable_order,
                    )
                if edge.edge_type is not relation.relation_type:
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.direction_type,
                        reason=GraphRejectionReason.relation_type_mismatch,
                        path=f"$.edges[{edge.edge_id}].edge_type",
                        message="Literature edge type differs from its Relation type.",
                        stable_order=stable_order,
                    )
            else:
                valid_structural = (
                    edge.edge_type is GraphEdgeType.supports_finding
                    and source.node_type is GraphNodeType.paper
                    and target.node_type is GraphNodeType.claim
                ) or (
                    edge.edge_type is GraphEdgeType.provides_field
                    and source.node_type is GraphNodeType.dataset
                    and target.node_type is GraphNodeType.field
                )
                if (
                    not valid_structural
                    or edge.relation_id is not None
                    or edge.reasoning_trace_id is not None
                ):
                    return self._failure_from_payload(
                        payload,
                        stage=GraphIntegrityStage.direction_type,
                        reason=GraphRejectionReason.wrong_direction,
                        path=f"$.edges[{edge.edge_id}]",
                        message="Structural edge violates its authoritative direction.",
                        stable_order=stable_order,
                    )

        evidence_use_count = sum(len(item.evidence_ids) for item in payload.edges)
        if (
            len(payload.nodes) > payload.max_nodes
            or len(payload.edges) > payload.max_edges
            or evidence_use_count > payload.max_evidence_uses
        ):
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.capacity_progressive,
                reason=GraphRejectionReason.size_limit_exceeded,
                path="$.max_nodes|$.max_edges|$.max_evidence_uses",
                message="Replay graph exceeds its explicit capacity boundary.",
                stable_order=stable_order,
            )
        complete_item_count = len(payload.nodes) + len(payload.edges) + evidence_use_count
        if complete_item_count != payload.declared_complete_item_count:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.capacity_progressive,
                reason=GraphRejectionReason.silent_truncation,
                path="$.declared_complete_item_count",
                message="Replay output item registries were silently truncated.",
                stable_order=stable_order,
            )
        if not payload.filter_complete:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.capacity_progressive,
                reason=GraphRejectionReason.evidence_hidden_by_filter,
                path="$.filter_complete",
                message="A build filter may not hide required Evidence.",
                stable_order=stable_order,
            )
        if not payload.aggregation_complete:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.capacity_progressive,
                reason=GraphRejectionReason.aggregation_incomplete,
                path="$.aggregation_complete",
                message="Aggregation must preserve the complete Evidence union.",
                stable_order=stable_order,
            )
        if not payload.progressive_complete:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.capacity_progressive,
                reason=GraphRejectionReason.progressive_input_incomplete,
                path="$.progressive_complete",
                message="Incomplete progressive input cannot be admitted.",
                stable_order=stable_order,
            )
        if not payload.candidate_hash_matches:
            return self._failure_from_payload(
                payload,
                stage=GraphIntegrityStage.hash_commitment,
                reason=GraphRejectionReason.candidate_hash_mismatch,
                path="$.candidate_hash_matches",
                message="Replay candidate hash commitment was tampered.",
                stable_order=stable_order,
            )

        report = _integrity_report(payload=payload)
        hashes = _passing_replay_hashes(payload=payload, report=report)
        return GraphBenchmarkObservation(
            schema_valid=True,
            status=GraphIntegrityStatus.passed,
            nodes=payload.nodes,
            edges=payload.edges,
            evidence_ids=payload.evidence_ids,
            relations=payload.relations,
            reasoning_traces=payload.reasoning_traces,
            report=report,
            stable_order_pass=stable_order,
            input_hash=hashes[0],
            scientific_hash=hashes[1],
            layout_hash=hashes[2],
            output_hash=hashes[3],
        )

    def _failure_from_payload(
        self,
        payload: _ReplayInput,
        *,
        stage: GraphIntegrityStage,
        reason: GraphRejectionReason,
        path: str,
        message: str,
        stable_order: bool = False,
    ) -> GraphBenchmarkObservation:
        return self._failure(
            stage=stage,
            reason=reason,
            path=path,
            message=message,
            schema_valid=True,
            payload=payload,
            stable_order=stable_order,
        )

    def _failure(
        self,
        *,
        stage: GraphIntegrityStage,
        reason: GraphRejectionReason,
        path: str,
        message: str,
        schema_valid: bool,
        payload: _ReplayInput | None = None,
        stable_order: bool = False,
        raw_input_json: str | None = None,
    ) -> GraphBenchmarkObservation:
        report = _integrity_report(
            payload=payload,
            stage=stage,
            reason=reason,
            path=path,
            message=message,
        )
        input_hash = compute_canonical_payload_hash(
            (
                {"input_json": raw_input_json}
                if payload is None
                else payload.model_dump(mode="json", exclude_none=True)
            )
        )
        output_hash = compute_canonical_payload_hash(
            {
                "input_hash": input_hash,
                "status": GraphIntegrityStatus.failed.value,
                "report_hash": report.content_hash,
                "nodes": [] if payload is None else [
                    item.model_dump(mode="json") for item in payload.nodes
                ],
                "edges": [] if payload is None else [
                    item.model_dump(mode="json") for item in payload.edges
                ],
                "evidence_ids": [] if payload is None else list(payload.evidence_ids),
            }
        )
        return GraphBenchmarkObservation(
            schema_valid=schema_valid,
            status=GraphIntegrityStatus.failed,
            nodes=() if payload is None else payload.nodes,
            edges=() if payload is None else payload.edges,
            evidence_ids=() if payload is None else payload.evidence_ids,
            relations=() if payload is None else payload.relations,
            reasoning_traces=() if payload is None else payload.reasoning_traces,
            report=report,
            stable_order_pass=stable_order,
            input_hash=input_hash,
            output_hash=output_hash,
        )


def validate_frozen_graph_label(benchmark: BenchmarkPackage) -> None:
    """Require the exact tracked Paper Acquisition Benchmark 6-node/2-edge Graph and status closure."""

    validate_frozen_benchmark(benchmark)
    if (
        benchmark.schema_version != _EXPECTED_PAPER_BENCHMARK_SCHEMA_VERSION
        or benchmark.benchmark_version != _EXPECTED_PAPER_BENCHMARK_BENCHMARK_VERSION
        or benchmark.scientific_payload_hash != _EXPECTED_PAPER_BENCHMARK_SCIENTIFIC_HASH
        or benchmark.content_hash != _EXPECTED_PAPER_BENCHMARK_CONTENT_HASH
    ):
        raise ValueError("frozen Paper Acquisition Benchmark Graph identity mismatch")
    nodes = benchmark.graph.nodes
    edges = benchmark.graph.edges
    actual_nodes = tuple(
        sorted(
            (item.node_id, item.node_type, item.ref_id) for item in nodes
        )
    )
    actual_edges = tuple(
        sorted(
            (
                item.edge_id,
                item.source,
                item.target,
                item.edge_type,
                tuple(item.evidence_ids),
                item.cross_document,
                item.relation_id,
                item.reasoning_trace_id,
            )
            for item in edges
        )
    )
    node_type_counts = {
        node_type: sum(item.node_type is node_type for item in nodes)
        for node_type in set(item.node_type for item in nodes)
    }
    cross_edges = tuple(item for item in edges if item.cross_document)
    structural_edges = tuple(item for item in edges if not item.cross_document)
    if (
        len(nodes) != 6
        or node_type_counts
        != {GraphNodeType.paper: 3, GraphNodeType.claim: 3}
        or len(edges) != 2
        or len(cross_edges) != 1
        or len(structural_edges) != 1
        or cross_edges[0].edge_type is not GraphEdgeType.extends
        or structural_edges[0].edge_type is not GraphEdgeType.supports_finding
        or sum(len(item.evidence_ids) for item in edges) != 3
        or actual_nodes != _EXPECTED_PAPER_BENCHMARK_NODES
        or actual_edges != _EXPECTED_PAPER_BENCHMARK_EDGES
    ):
        raise ValueError("frozen Paper Acquisition Benchmark Graph must remain exactly 6 nodes and 2 edges")
    if benchmark.graph_taxonomy.allowed_node_types != (
        GraphNodeType.paper,
        GraphNodeType.claim,
    ) or benchmark.graph_taxonomy.allowed_edge_types != (
        GraphEdgeType.supports_finding,
        GraphEdgeType.extends,
        GraphEdgeType.derived_from,
    ):
        raise ValueError("frozen Paper Acquisition Benchmark Graph taxonomy drifted")

    relations = {item.relation_id: item for item in benchmark.relations}
    traces = {item.trace_id: item for item in benchmark.reasoning_traces}
    statuses = {
        status: sum(item.status is status for item in benchmark.relations)
        for status in BenchmarkAdmissionStatus
    }
    if statuses != {
        BenchmarkAdmissionStatus.accepted: 1,
        BenchmarkAdmissionStatus.candidate: 1,
        BenchmarkAdmissionStatus.rejected: 2,
    } or any(
        item.review_status is not BenchmarkReviewStatus.approved
        for item in benchmark.relations
    ) or any(
        item.review_status is not BenchmarkReviewStatus.approved
        for item in benchmark.reasoning_traces
    ):
        raise ValueError("frozen Paper Acquisition Benchmark Relation status closure drifted")
    for item in benchmark.relations:
        item_trace = traces.get(item.reasoning_trace_id or "")
        if (
            item_trace is None
            or item_trace.relation_id != item.relation_id
            or item_trace.premise_claim_ids
            != (item.source_claim_id, item.target_claim_id)
        ):
            raise ValueError("frozen Paper Acquisition Benchmark Relation/Trace registry drifted")
    cross = cross_edges[0]
    relation = relations.get(cross.relation_id or "")
    trace = traces.get(cross.reasoning_trace_id or "")
    node_by_id = {item.node_id: item for item in nodes}
    if (
        relation is None
        or trace is None
        or relation.status is not BenchmarkAdmissionStatus.accepted
        or relation.relation_type.value != cross.edge_type.value
        or relation.reasoning_trace_id != trace.trace_id
        or trace.relation_id != relation.relation_id
        or trace.premise_claim_ids
        != (relation.source_claim_id, relation.target_claim_id)
        or node_by_id[cross.source].ref_id != relation.source_claim_id
        or node_by_id[cross.target].ref_id != relation.target_claim_id
        or set(cross.evidence_ids) != set(relation.evidence_ids)
    ):
        raise ValueError("frozen Paper Acquisition Benchmark accepted extends Relation/Trace closure drifted")


def build_frozen_graph_benchmark_cases(
    benchmark: BenchmarkPackage,
) -> tuple[GraphBenchmarkEvaluationCase, ...]:
    """Build the complete deterministic scientific, rejection, and size suite."""

    validate_frozen_graph_label(benchmark)
    base = _frozen_replay_payload(benchmark)
    expected_nodes = tuple(sorted(item.node_id for item in benchmark.graph.nodes))
    expected_edges = tuple(sorted(item.edge_id for item in benchmark.graph.edges))
    expected_evidence_count = sum(
        len(item.evidence_ids) for item in benchmark.graph.edges
    )
    cases: list[GraphBenchmarkEvaluationCase] = [
        _benchmark_case(
            case_id="scientific.paper_benchmark_full_graph",
            kind=GraphBenchmarkCaseKind.scientific_graph,
            data_level="benchmark",
            input_json=_canonical_json(base),
            expected_status=GraphIntegrityStatus.passed,
            expected_node_ids=expected_nodes,
            expected_edge_ids=expected_edges,
            expected_evidence_use_count=expected_evidence_count,
        )
    ]
    data_fixture = _synthetic_data_replay_payload(benchmark)
    data_expected_nodes = tuple(
        sorted(item["node_id"] for item in data_fixture["nodes"])
    )
    data_expected_edges = tuple(
        sorted(item["edge_id"] for item in data_fixture["edges"])
    )
    data_expected_evidence_count = sum(
        len(item["evidence_ids"]) for item in data_fixture["edges"]
    )
    cases.append(
        _benchmark_case(
            case_id="fixture.data_full_evidence_union",
            kind=GraphBenchmarkCaseKind.data_mapping_fixture,
            data_level="fixture",
            input_json=_canonical_json(data_fixture),
            expected_status=GraphIntegrityStatus.passed,
            expected_node_ids=data_expected_nodes,
            expected_edge_ids=data_expected_edges,
            expected_evidence_use_count=data_expected_evidence_count,
        )
    )

    def rejection(
        case_id: str,
        payload: dict[str, object] | str,
        stage: GraphIntegrityStage,
        reason: GraphRejectionReason,
        *,
        case_expected_nodes: tuple[str, ...] = expected_nodes,
        case_expected_edges: tuple[str, ...] = expected_edges,
        case_expected_evidence_count: int = expected_evidence_count,
    ) -> None:
        cases.append(
            _benchmark_case(
                case_id=case_id,
                kind=GraphBenchmarkCaseKind.rejection_case,
                data_level="fixture",
                input_json=(payload if isinstance(payload, str) else _canonical_json(payload)),
                expected_status=GraphIntegrityStatus.failed,
                expected_failure_stage=stage,
                expected_rejection_reason=reason,
                expected_node_ids=case_expected_nodes,
                expected_edge_ids=case_expected_edges,
                expected_evidence_use_count=case_expected_evidence_count,
            )
        )

    rejection(
        "rejection.invalid_json",
        "{invalid",
        GraphIntegrityStage.input_schema,
        GraphRejectionReason.invalid_json,
    )
    schema_invalid = deepcopy(base)
    schema_invalid.pop("schema_version")
    rejection(
        "rejection.schema_invalid",
        schema_invalid,
        GraphIntegrityStage.input_schema,
        GraphRejectionReason.schema_invalid,
    )

    unknown_version = deepcopy(base)
    unknown_version["input_version_known"] = False
    rejection(
        "rejection.input_version_unknown",
        unknown_version,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.input_version_unknown,
    )
    unpublished_version = deepcopy(base)
    unpublished_version["input_version_published"] = False
    rejection(
        "rejection.input_version_unpublished",
        unpublished_version,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.input_version_unpublished,
    )
    wrong_kind = deepcopy(base)
    wrong_kind["input_artifact_kind"] = "dataset"
    rejection(
        "rejection.wrong_artifact_kind",
        wrong_kind,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.wrong_artifact_kind,
    )
    unsupported_schema = deepcopy(base)
    unsupported_schema["input_schema_version"] = "9.9.9"
    rejection(
        "rejection.unsupported_schema_version",
        unsupported_schema,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.unsupported_schema_version,
    )
    content_hash_mismatch = deepcopy(base)
    content_hash_mismatch["input_content_hash"] = _ZERO_HASH
    rejection(
        "rejection.content_hash_mismatch",
        content_hash_mismatch,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.content_hash_mismatch,
    )
    input_hash_mismatch = deepcopy(base)
    input_hash_mismatch["input_hash"] = _ZERO_HASH
    rejection(
        "rejection.input_hash_mismatch",
        input_hash_mismatch,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.input_hash_mismatch,
    )
    producer_mismatch = deepcopy(base)
    producer_mismatch["producer_execution_matches"] = False
    rejection(
        "rejection.producer_execution_mismatch",
        producer_mismatch,
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.producer_execution_mismatch,
    )
    cross_project = deepcopy(base)
    cross_project["reference_project_id"] = "fixture.other_project"
    rejection(
        "rejection.cross_project_ownership",
        cross_project,
        GraphIntegrityStage.ownership,
        GraphRejectionReason.cross_project_ownership,
    )
    cross_version = deepcopy(base)
    cross_version["reference_input_version_id"] = "fixture.other_version"
    rejection(
        "rejection.cross_version_reference",
        cross_version,
        GraphIntegrityStage.ownership,
        GraphRejectionReason.cross_version_reference,
    )
    provenance_version = deepcopy(base)
    provenance_version["evidence"][0]["input_version_id"] = "fixture.other_version"
    rejection(
        "rejection.provenance_version_mismatch",
        provenance_version,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.provenance_version_mismatch,
    )

    taxonomy = deepcopy(base)
    taxonomy["nodes"][0]["node_type"] = GraphNodeType.source.value
    rejection(
        "rejection.taxonomy_node_type",
        taxonomy,
        GraphIntegrityStage.taxonomy,
        GraphRejectionReason.taxonomy_violation,
    )
    duplicate_node = deepcopy(base)
    duplicate_node["nodes"].append(deepcopy(duplicate_node["nodes"][0]))
    duplicate_node["nodes"] = sorted(
        duplicate_node["nodes"], key=lambda item: item["node_id"]
    )
    rejection(
        "rejection.duplicate_node_identity",
        duplicate_node,
        GraphIntegrityStage.identity,
        GraphRejectionReason.duplicate_node_identity,
    )
    duplicate_edge = deepcopy(base)
    duplicate_edge["edges"].append(deepcopy(duplicate_edge["edges"][0]))
    duplicate_edge["edges"] = sorted(
        duplicate_edge["edges"], key=lambda item: item["edge_id"]
    )
    rejection(
        "rejection.duplicate_edge_identity",
        duplicate_edge,
        GraphIntegrityStage.identity,
        GraphRejectionReason.duplicate_edge_identity,
    )
    dangling = deepcopy(base)
    _cross_edge(dangling)["target"] = "node.claim_missing"
    rejection(
        "rejection.dangling_endpoint",
        dangling,
        GraphIntegrityStage.endpoint,
        GraphRejectionReason.dangling_endpoint,
    )
    missing_edge = deepcopy(base)
    missing_edge["edges"] = [
        item for item in missing_edge["edges"] if item["cross_document"]
    ]
    rejection(
        "rejection.missing_edge",
        missing_edge,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_missing,
    )
    evidence_missing = deepcopy(base)
    _cross_edge(evidence_missing)["evidence_ids"] = []
    rejection(
        "rejection.evidence_missing",
        evidence_missing,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_missing,
    )
    evidence_unknown = deepcopy(base)
    _cross_edge(evidence_unknown)["evidence_ids"][0] = "evidence.missing"
    rejection(
        "rejection.evidence_unknown",
        evidence_unknown,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_unknown,
    )
    evidence_inconsistent = deepcopy(base)
    _cross_edge(evidence_inconsistent)["evidence_ids"] = _cross_edge(
        evidence_inconsistent
    )["evidence_ids"][:1]
    rejection(
        "rejection.evidence_inconsistent",
        evidence_inconsistent,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_inconsistent,
    )
    snapshot_inconsistent = deepcopy(data_fixture)
    snapshot_inconsistent["evidence"][0]["source_snapshot_content_hash"] = _ZERO_HASH
    rejection(
        "rejection.source_snapshot_inconsistent",
        snapshot_inconsistent,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.source_snapshot_inconsistent,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )
    snapshot_missing = deepcopy(base)
    snapshot_missing["source_snapshot_registry_complete"] = False
    snapshot_missing["source_snapshots"] = []
    rejection(
        "rejection.source_snapshot_missing",
        snapshot_missing,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.source_snapshot_missing,
    )
    snapshot_unknown = deepcopy(base)
    snapshot_unknown["evidence"][0]["source_snapshot_id"] = "snapshot.missing"
    rejection(
        "rejection.source_snapshot_unknown",
        snapshot_unknown,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.source_snapshot_unknown,
    )
    trace_missing = deepcopy(base)
    _cross_edge(trace_missing)["reasoning_trace_id"] = None
    rejection(
        "rejection.reasoning_trace_missing",
        trace_missing,
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.reasoning_trace_missing,
    )
    trace_mismatch = deepcopy(base)
    _cross_edge(trace_mismatch)["reasoning_trace_id"] = (
        "trace.clark_catalog_derived_from_tic"
    )
    rejection(
        "rejection.reasoning_trace_mismatch",
        trace_mismatch,
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.reasoning_trace_mismatch,
    )
    trace_incomplete = deepcopy(base)
    accepted_trace_id = _cross_edge(trace_incomplete)["reasoning_trace_id"]
    accepted_trace = next(
        item
        for item in trace_incomplete["reasoning_traces"]
        if item["trace_id"] == accepted_trace_id
    )
    accepted_trace["premise_claim_ids"] = list(
        reversed(accepted_trace["premise_claim_ids"])
    )
    rejection(
        "rejection.reasoning_trace_incomplete",
        trace_incomplete,
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.reasoning_trace_incomplete,
    )
    wrong_direction = deepcopy(base)
    cross = _cross_edge(wrong_direction)
    cross["source"], cross["target"] = cross["target"], cross["source"]
    rejection(
        "rejection.wrong_direction",
        wrong_direction,
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.wrong_direction,
    )
    type_mismatch = deepcopy(base)
    _cross_edge(type_mismatch)["edge_type"] = GraphEdgeType.derived_from.value
    rejection(
        "rejection.relation_type_mismatch",
        type_mismatch,
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.relation_type_mismatch,
    )

    relation_case_ids = (
        (
            "rejection.nonaccepted_candidate_relation",
            "relation.clark_catalog_derived_from_tic",
        ),
        (
            "rejection.nonaccepted_limits_relation",
            "relation.host_properties_limit_toi_interpretation",
        ),
        (
            "rejection.nonaccepted_contradicts_relation",
            "relation.observed_candidates_contradict_expected_planets",
        ),
    )
    for case_id, relation_id in relation_case_ids:
        payload = deepcopy(base)
        _append_nonaccepted_relation_edge(payload, relation_id=relation_id)
        rejection(
            case_id,
            payload,
            GraphIntegrityStage.relation_trace,
            GraphRejectionReason.relation_not_accepted,
        )

    filtered = deepcopy(base)
    filtered["filter_complete"] = False
    rejection(
        "rejection.filter_hides_evidence",
        filtered,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.evidence_hidden_by_filter,
    )
    aggregated = deepcopy(base)
    aggregated["aggregation_complete"] = False
    rejection(
        "rejection.aggregation_incomplete",
        aggregated,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.aggregation_incomplete,
    )
    progressive = deepcopy(base)
    progressive["progressive_complete"] = False
    rejection(
        "rejection.progressive_incomplete",
        progressive,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.progressive_input_incomplete,
    )
    silently_truncated = deepcopy(base)
    silently_truncated["declared_complete_item_count"] += 1
    rejection(
        "rejection.silent_truncation",
        silently_truncated,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.silent_truncation,
    )
    candidate_hash_mismatch = deepcopy(base)
    candidate_hash_mismatch["candidate_hash_matches"] = False
    rejection(
        "rejection.candidate_hash_mismatch",
        candidate_hash_mismatch,
        GraphIntegrityStage.hash_commitment,
        GraphRejectionReason.candidate_hash_mismatch,
    )

    data_wrong_direction = deepcopy(data_fixture)
    data_edge = data_wrong_direction["edges"][0]
    data_edge["source"], data_edge["target"] = (
        data_edge["target"],
        data_edge["source"],
    )
    rejection(
        "rejection.data_wrong_direction",
        data_wrong_direction,
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.wrong_direction,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )
    data_source_to_field = deepcopy(data_fixture)
    data_source_to_field["nodes"][0]["node_type"] = GraphNodeType.source.value
    data_source_to_field["taxonomy_node_types"] = sorted(
        (
            GraphNodeType.dataset.value,
            GraphNodeType.field.value,
            GraphNodeType.source.value,
        )
    )
    rejection(
        "rejection.data_source_to_field",
        data_source_to_field,
        GraphIntegrityStage.taxonomy,
        GraphRejectionReason.taxonomy_violation,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )
    data_union_incomplete = deepcopy(data_fixture)
    data_union_incomplete["edges"][0]["evidence_ids"] = (
        data_union_incomplete["edges"][0]["evidence_ids"][:-1]
    )
    rejection(
        "rejection.data_evidence_union_incomplete",
        data_union_incomplete,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_inconsistent,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )
    data_zero_evidence = deepcopy(data_fixture)
    data_zero_evidence["edges"][0]["evidence_ids"] = []
    rejection(
        "rejection.data_zero_evidence",
        data_zero_evidence,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_missing,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )
    data_duplicate_edge = deepcopy(data_fixture)
    duplicate_data_edge = deepcopy(data_duplicate_edge["edges"][0])
    duplicate_data_edge["edge_id"] = "edge.fixture_dataset_field_duplicate"
    data_duplicate_edge["edges"].append(duplicate_data_edge)
    data_duplicate_edge["edges"] = sorted(
        data_duplicate_edge["edges"], key=lambda item: item["edge_id"]
    )
    rejection(
        "rejection.data_duplicate_dataset_field_edge",
        data_duplicate_edge,
        GraphIntegrityStage.identity,
        GraphRejectionReason.identity_collision,
        case_expected_nodes=data_expected_nodes,
        case_expected_edges=data_expected_edges,
        case_expected_evidence_count=data_expected_evidence_count,
    )

    at_boundary = deepcopy(base)
    at_boundary["max_nodes"] = len(expected_nodes)
    cases.append(
        _benchmark_case(
            case_id="size_boundary.exact",
            kind=GraphBenchmarkCaseKind.size_boundary,
            data_level="fixture",
            input_json=_canonical_json(at_boundary),
            expected_status=GraphIntegrityStatus.passed,
            expected_node_ids=expected_nodes,
            expected_edge_ids=expected_edges,
            expected_evidence_use_count=expected_evidence_count,
        )
    )
    above_boundary = deepcopy(base)
    above_boundary["max_nodes"] = len(expected_nodes) - 1
    cases.append(
        _benchmark_case(
            case_id="size_boundary.exceeded",
            kind=GraphBenchmarkCaseKind.size_boundary,
            data_level="fixture",
            input_json=_canonical_json(above_boundary),
            expected_status=GraphIntegrityStatus.failed,
            expected_failure_stage=GraphIntegrityStage.capacity_progressive,
            expected_rejection_reason=GraphRejectionReason.size_limit_exceeded,
            expected_node_ids=expected_nodes,
            expected_edge_ids=expected_edges,
            expected_evidence_use_count=expected_evidence_count,
        )
    )
    return tuple(sorted(cases, key=lambda item: item.case_id))


def validate_formal_case_coverage(
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
) -> None:
    """Reject favorable subsets and any drift in the fixed case declarations."""

    validate_frozen_graph_label(benchmark)
    ordered = tuple(sorted(cases, key=lambda item: item.case_id))
    if len({item.case_id for item in ordered}) != len(ordered):
        raise ValueError("formal Graph benchmark case ids must be unique")
    scientific = tuple(
        item for item in ordered if item.kind is GraphBenchmarkCaseKind.scientific_graph
    )
    if len(scientific) != 1 or scientific[0].case_id != "scientific.paper_benchmark_full_graph":
        raise ValueError("formal Graph benchmark must cover the full Paper Acquisition Benchmark graph")
    data_mapping = tuple(
        item
        for item in ordered
        if item.kind is GraphBenchmarkCaseKind.data_mapping_fixture
    )
    if (
        len(data_mapping) != 1
        or data_mapping[0].case_id != "fixture.data_full_evidence_union"
    ):
        raise ValueError("formal Graph benchmark must cover the data Evidence union")
    expected = build_frozen_graph_benchmark_cases(benchmark)
    expected_ids = tuple(item.case_id for item in expected)
    if tuple(item.case_id for item in ordered) != expected_ids:
        raise ValueError(
            "formal Graph benchmark must include the fixed rejection and size suite exactly"
        )
    if ordered != expected:
        raise ValueError("formal Graph benchmark case payload drifted")


def evaluate_graph_benchmark(
    *,
    benchmark: BenchmarkPackage,
    cases: tuple[GraphBenchmarkEvaluationCase, ...],
    adapter: GraphBenchmarkAdapter | None = None,
) -> GraphBenchmarkReport:
    """Evaluate case outcomes and derive every aggregate from per-case facts."""

    if not cases:
        raise ValueError("Graph benchmark requires at least one case")
    validate_frozen_graph_label(benchmark)
    ordered = tuple(sorted(cases, key=lambda item: item.case_id))
    if len({item.case_id for item in ordered}) != len(ordered):
        raise ValueError("Graph benchmark case ids must be unique")
    selected_adapter = adapter or FrozenGraphReplayAdapter(benchmark)

    observations: list[GraphBenchmarkObservation] = []
    results: list[GraphBenchmarkCaseResult] = []
    for case in ordered:
        observation = selected_adapter.evaluate_case(case)
        if not isinstance(observation, GraphBenchmarkObservation):
            raise TypeError(
                "Graph benchmark adapter must return GraphBenchmarkObservation"
            )
        observations.append(observation)
        results.append(
            _case_result(
                benchmark=benchmark,
                case=case,
                observation=observation,
            )
        )

    typed_results = tuple(results)
    paired = tuple(zip(ordered, observations, typed_results, strict=True))
    scientific = tuple(
        item
        for item in paired
        if item[0].kind is GraphBenchmarkCaseKind.scientific_graph
    )
    rejections = tuple(
        item
        for item in paired
        if item[0].kind is GraphBenchmarkCaseKind.rejection_case
    )
    size_cases = tuple(
        item
        for item in paired
        if item[0].kind is GraphBenchmarkCaseKind.size_boundary
    )
    data_mapping = tuple(
        item
        for item in paired
        if item[0].kind is GraphBenchmarkCaseKind.data_mapping_fixture
    )
    stable_applicable = tuple(
        result
        for case, observation, result in paired
        if case.expected_status is GraphIntegrityStatus.passed
        and observation.schema_valid
    )

    metrics = {
        "full_graph_exact_match_rate": _metric(
            sum(
                result.expected_result_pass
                and result.node_exact_match
                and result.edge_exact_match
                and result.matched_evidence_use_count
                == result.expected_evidence_use_count
                == result.actual_evidence_use_count
                for _, _, result in scientific
            ),
            len(scientific),
            GraphBenchmarkDenominatorScope.paper_benchmark_scientific_graph_cases,
        ),
        "node_exact_match_rate": _metric(
            sum(result.matched_node_count for _, _, result in scientific),
            sum(result.expected_node_count for _, _, result in scientific),
            GraphBenchmarkDenominatorScope.paper_benchmark_expected_nodes,
        ),
        "edge_exact_match_rate": _metric(
            sum(result.matched_edge_count for _, _, result in scientific),
            sum(result.expected_edge_count for _, _, result in scientific),
            GraphBenchmarkDenominatorScope.paper_benchmark_expected_edges,
        ),
        "evidence_coverage_rate": _metric(
            sum(result.matched_evidence_use_count for _, _, result in scientific),
            sum(result.expected_evidence_use_count for _, _, result in scientific),
            GraphBenchmarkDenominatorScope.paper_benchmark_edge_evidence_uses,
        ),
        "accepted_relation_coverage_rate": _metric(
            sum(
                result.matched_accepted_relation_count
                for _, _, result in scientific
            ),
            sum(
                result.expected_accepted_relation_count
                for _, _, result in scientific
            ),
            GraphBenchmarkDenominatorScope.paper_benchmark_accepted_relations,
        ),
        "reasoning_trace_coverage_rate": _metric(
            sum(result.matched_reasoning_trace_count for _, _, result in scientific),
            sum(result.expected_reasoning_trace_count for _, _, result in scientific),
            GraphBenchmarkDenominatorScope.paper_benchmark_reasoning_traces,
        ),
        "nonaccepted_relation_exclusion_rate": _metric(
            sum(
                result.excluded_nonaccepted_relation_count
                for _, _, result in scientific
            ),
            sum(
                result.expected_nonaccepted_relation_count
                for _, _, result in scientific
            ),
            GraphBenchmarkDenominatorScope.paper_benchmark_nonaccepted_relations,
        ),
        "stable_identity_order_rate": _metric(
            sum(item.stable_order_pass for item in stable_applicable),
            len(stable_applicable),
            GraphBenchmarkDenominatorScope.schema_valid_expected_pass_cases,
        ),
        "data_mapping_fixture_pass_rate": _metric(
            sum(result.expected_result_pass for _, _, result in data_mapping),
            len(data_mapping),
            GraphBenchmarkDenominatorScope.data_mapping_fixture_cases,
        ),
        "rejection_case_pass_rate": _metric(
            sum(result.expected_result_pass for _, _, result in rejections),
            len(rejections),
            GraphBenchmarkDenominatorScope.rejection_fixture_cases,
        ),
        "size_boundary_pass_rate": _metric(
            sum(result.expected_result_pass for _, _, result in size_cases),
            len(size_cases),
            GraphBenchmarkDenominatorScope.size_boundary_fixture_cases,
        ),
        "schema_pass_rate": _metric(
            sum(result.schema_valid for result in typed_results),
            len(typed_results),
            GraphBenchmarkDenominatorScope.all_cases,
        ),
    }

    taxonomy_nodes = tuple(
        sorted(benchmark.graph_taxonomy.allowed_node_types, key=lambda item: item.value)
    )
    taxonomy_edges = tuple(
        sorted(benchmark.graph_taxonomy.allowed_edge_types, key=lambda item: item.value)
    )
    graph_versions = GraphBenchmarkVersionSet()
    input_payload = {
        "paper_benchmark_schema_version": benchmark.schema_version,
        "paper_benchmark_version": benchmark.benchmark_version,
        "paper_benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "paper_benchmark_content_hash": benchmark.content_hash,
        "graph_versions": graph_versions.model_dump(mode="json"),
        "taxonomy_node_types": [item.value for item in taxonomy_nodes],
        "taxonomy_edge_types": [item.value for item in taxonomy_edges],
        "case_content_hashes": [item.content_hash for item in ordered],
    }
    report_input_hash = compute_canonical_payload_hash(input_payload)
    report_payload: dict[str, object] = {
        "report_schema_version": "2.0.0",
        "disclaimer": GRAPH_BENCHMARK_DISCLAIMER,
        "paper_benchmark_schema_version": benchmark.schema_version,
        "paper_benchmark_version": benchmark.benchmark_version,
        "paper_benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "paper_benchmark_content_hash": benchmark.content_hash,
        "graph_versions": graph_versions.model_dump(mode="json"),
        "taxonomy_node_types": [item.value for item in taxonomy_nodes],
        "taxonomy_edge_types": [item.value for item in taxonomy_edges],
        "expected_scientific_node_count": sum(
            result.expected_node_count for _, _, result in scientific
        ),
        "expected_scientific_edge_count": sum(
            result.expected_edge_count for _, _, result in scientific
        ),
        "cases": [
            item.model_dump(mode="json", exclude_none=True) for item in typed_results
        ],
        **{
            name: metric.model_dump(mode="json", exclude_none=True)
            for name, metric in metrics.items()
        },
        "unexpected_node_count": sum(
            result.unexpected_node_count for _, _, result in scientific
        ),
        "unexpected_edge_count": sum(
            result.unexpected_edge_count for _, _, result in scientific
        ),
        "integrity_pass_count": sum(
            result.status is GraphIntegrityStatus.passed for result in typed_results
        ),
        "integrity_fail_count": sum(
            result.status is GraphIntegrityStatus.failed for result in typed_results
        ),
        "input_hash": report_input_hash,
        "output_hash": _ZERO_HASH,
    }
    report_payload["output_hash"] = compute_graph_benchmark_output_hash(
        report_payload
    )
    return GraphBenchmarkReport.model_validate_json(_canonical_json(report_payload))


def _case_result(
    *,
    benchmark: BenchmarkPackage,
    case: GraphBenchmarkEvaluationCase,
    observation: GraphBenchmarkObservation,
) -> GraphBenchmarkCaseResult:
    try:
        expected_payload = _ReplayInput.model_validate_json(case.input_json)
    except ValueError:
        expected_payload = None
    if expected_payload is None:
        expected_nodes = {
            item.node_id: (item.node_type, item.ref_id)
            for item in benchmark.graph.nodes
            if item.node_id in set(case.expected_node_ids)
        }
        expected_edges = {
            item.edge_id: (
                item.source,
                item.target,
                item.edge_type,
                tuple(sorted(item.evidence_ids)),
                item.cross_document,
                item.relation_id,
                item.reasoning_trace_id,
            )
            for item in benchmark.graph.edges
            if item.edge_id in set(case.expected_edge_ids)
        }
    else:
        expected_nodes = {
            item.node_id: (item.node_type, item.ref_id)
            for item in expected_payload.nodes
            if item.node_id in set(case.expected_node_ids)
        }
        expected_edges = {
            item.edge_id: _edge_signature(item)
            for item in expected_payload.edges
            if item.edge_id in set(case.expected_edge_ids)
        }
    actual_nodes = {
        item.node_id: (item.node_type, item.ref_id) for item in observation.nodes
    }
    actual_edges = {item.edge_id: _edge_signature(item) for item in observation.edges}
    actual_node_ids = tuple(item.node_id for item in observation.nodes)
    actual_edge_ids = tuple(item.edge_id for item in observation.edges)
    matched_node_count = sum(
        actual_nodes.get(node_id) == signature
        for node_id, signature in expected_nodes.items()
    )
    matched_edge_count = sum(
        actual_edges.get(edge_id) == signature
        for edge_id, signature in expected_edges.items()
    )
    unexpected_node_count = _unexpected_count(
        actual_node_ids,
        case.expected_node_ids,
    )
    unexpected_edge_count = _unexpected_count(
        actual_edge_ids,
        case.expected_edge_ids,
    )
    node_exact = (
        matched_node_count == len(case.expected_node_ids)
        and len(observation.nodes) == len(case.expected_node_ids)
        and unexpected_node_count == 0
    )
    edge_exact = (
        matched_edge_count == len(case.expected_edge_ids)
        and len(observation.edges) == len(case.expected_edge_ids)
        and unexpected_edge_count == 0
    )
    evidence_count = sum(len(item.evidence_ids) for item in observation.edges)
    expected_evidence_occurrences = {
        (edge_id, evidence_id)
        for edge_id, signature in expected_edges.items()
        for evidence_id in signature[3]
    }
    actual_evidence_occurrences = {
        (edge.edge_id, evidence_id)
        for edge in observation.edges
        for evidence_id in edge.evidence_ids
    }
    matched_evidence_count = len(
        expected_evidence_occurrences & actual_evidence_occurrences
    )
    accepted_relation_ids = {
        item.relation_id
        for item in benchmark.relations
        if item.status is BenchmarkAdmissionStatus.accepted
    }
    accepted_trace_ids = {
        item.reasoning_trace_id
        for item in benchmark.relations
        if item.status is BenchmarkAdmissionStatus.accepted
        and item.reasoning_trace_id is not None
    }
    nonaccepted_relation_ids = {
        item.relation_id
        for item in benchmark.relations
        if item.status is not BenchmarkAdmissionStatus.accepted
    }
    actual_relation_ids = {
        edge.relation_id
        for edge in observation.edges
        if edge.cross_document and edge.relation_id is not None
    }
    actual_trace_ids = {
        edge.reasoning_trace_id
        for edge in observation.edges
        if edge.cross_document and edge.reasoning_trace_id is not None
    }
    scientific = case.kind is GraphBenchmarkCaseKind.scientific_graph
    expected_accepted_relation_count = len(accepted_relation_ids) if scientific else 0
    expected_reasoning_trace_count = len(accepted_trace_ids) if scientific else 0
    expected_nonaccepted_relation_count = (
        len(nonaccepted_relation_ids) if scientific else 0
    )
    matched_accepted_relation_count = (
        len(actual_relation_ids & accepted_relation_ids) if scientific else 0
    )
    matched_reasoning_trace_count = (
        len(actual_trace_ids & accepted_trace_ids) if scientific else 0
    )
    excluded_nonaccepted_relation_count = (
        len(nonaccepted_relation_ids - actual_relation_ids) if scientific else 0
    )
    failure_stage = observation.report.first_failure_stage
    rejection_reason = observation.report.first_rejection_reason
    expectation_matches = (
        observation.status is case.expected_status
        and failure_stage is case.expected_failure_stage
        and rejection_reason is case.expected_rejection_reason
    )
    if case.expected_status is GraphIntegrityStatus.passed:
        expectation_matches = (
            expectation_matches
            and node_exact
            and edge_exact
            and matched_evidence_count
            == case.expected_evidence_use_count
            == evidence_count
            and observation.stable_order_pass
        )
    return GraphBenchmarkCaseResult(
        case_id=case.case_id,
        kind=case.kind,
        data_level=case.data_level,
        case_content_hash=case.content_hash,
        schema_valid=observation.schema_valid,
        expected_status=case.expected_status,
        expected_failure_stage=case.expected_failure_stage,
        expected_rejection_reason=case.expected_rejection_reason,
        status=observation.status,
        failure_stage=failure_stage,
        rejection_reason=rejection_reason,
        expected_node_count=len(case.expected_node_ids),
        actual_node_count=len(observation.nodes),
        matched_node_count=matched_node_count,
        unexpected_node_count=unexpected_node_count,
        expected_edge_count=len(case.expected_edge_ids),
        actual_edge_count=len(observation.edges),
        matched_edge_count=matched_edge_count,
        unexpected_edge_count=unexpected_edge_count,
        expected_evidence_use_count=case.expected_evidence_use_count,
        actual_evidence_use_count=evidence_count,
        matched_evidence_use_count=matched_evidence_count,
        expected_accepted_relation_count=expected_accepted_relation_count,
        matched_accepted_relation_count=matched_accepted_relation_count,
        expected_reasoning_trace_count=expected_reasoning_trace_count,
        matched_reasoning_trace_count=matched_reasoning_trace_count,
        expected_nonaccepted_relation_count=expected_nonaccepted_relation_count,
        excluded_nonaccepted_relation_count=excluded_nonaccepted_relation_count,
        node_exact_match=node_exact,
        edge_exact_match=edge_exact,
        stable_order_pass=observation.stable_order_pass,
        expected_result_pass=expectation_matches,
        input_hash=observation.input_hash,
        scientific_hash=observation.scientific_hash,
        layout_hash=observation.layout_hash,
        report_hash=observation.report.content_hash,
        output_hash=observation.output_hash,
    )


def _frozen_replay_payload(benchmark: BenchmarkPackage) -> dict[str, object]:
    return {
        "schema_version": "2.0.0",
        "paper_benchmark_schema_version": benchmark.schema_version,
        "paper_benchmark_version": benchmark.benchmark_version,
        "paper_benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "paper_benchmark_content_hash": benchmark.content_hash,
        "project_id": "benchmark.paper_benchmark.project",
        "reference_project_id": "benchmark.paper_benchmark.project",
        "input_version_id": "benchmark.paper_benchmark.literature_relations",
        "reference_input_version_id": "benchmark.paper_benchmark.literature_relations",
        "input_version_known": True,
        "input_version_published": True,
        "input_artifact_kind": "literature_relations",
        "expected_input_artifact_kind": "literature_relations",
        "input_schema_version": "1.0.0",
        "supported_input_schema_version": "1.0.0",
        "input_content_hash": benchmark.content_hash,
        "declared_input_content_hash": benchmark.content_hash,
        "input_hash": benchmark.scientific_payload_hash,
        "declared_input_hash": benchmark.scientific_payload_hash,
        "producer_execution_matches": True,
        "candidate_hash_matches": True,
        "taxonomy_node_types": sorted(
            item.value for item in benchmark.graph_taxonomy.allowed_node_types
        ),
        "taxonomy_edge_types": sorted(
            item.value for item in benchmark.graph_taxonomy.allowed_edge_types
        ),
        "nodes": sorted(
            (
                {
                    "node_id": item.node_id,
                    "node_type": item.node_type.value,
                    "ref_id": item.ref_id,
                }
                for item in benchmark.graph.nodes
            ),
            key=lambda item: item["node_id"],
        ),
        "edges": sorted(
            (
                {
                    "edge_id": item.edge_id,
                    "source": item.source,
                    "target": item.target,
                    "edge_type": item.edge_type.value,
                    "evidence_ids": sorted(item.evidence_ids),
                    "cross_document": item.cross_document,
                    "relation_id": item.relation_id,
                    "reasoning_trace_id": item.reasoning_trace_id,
                }
                for item in benchmark.graph.edges
            ),
            key=lambda item: item["edge_id"],
        ),
        "relations": sorted(
            (
                {
                    "relation_id": item.relation_id,
                    "source_claim_id": item.source_claim_id,
                    "target_claim_id": item.target_claim_id,
                    "relation_type": GraphEdgeType(item.relation_type.value).value,
                    "evidence_ids": sorted(item.evidence_ids),
                    "status": item.status.value,
                    "review_status": item.review_status.value,
                    "reasoning_trace_id": item.reasoning_trace_id,
                }
                for item in benchmark.relations
            ),
            key=lambda item: item["relation_id"],
        ),
        "reasoning_traces": sorted(
            (
                {
                    "trace_id": item.trace_id,
                    "relation_id": item.relation_id,
                    "premise_claim_ids": list(item.premise_claim_ids),
                    "review_status": item.review_status.value,
                }
                for item in benchmark.reasoning_traces
            ),
            key=lambda item: item["trace_id"],
        ),
        "evidence_ids": sorted(item.evidence_id for item in benchmark.evidence),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "project_id": "benchmark.paper_benchmark.project",
                "input_version_id": "benchmark.paper_benchmark.literature_relations",
                "source_snapshot_id": "snapshot.benchmark_paper_benchmark_public",
                "source_snapshot_content_hash": benchmark.content_hash,
            }
            for item in sorted(benchmark.evidence, key=lambda item: item.evidence_id)
        ],
        "source_snapshots": [
            {
                "source_snapshot_id": "snapshot.benchmark_paper_benchmark_public",
                "project_id": "benchmark.paper_benchmark.project",
                "content_hash": benchmark.content_hash,
            }
        ],
        "source_snapshot_registry_complete": True,
        "data_field_closures": [],
        "declared_complete_item_count": 11,
        "max_nodes": 10_000,
        "max_edges": 20_000,
        "max_evidence_uses": 50_000,
        "filter_complete": True,
        "aggregation_complete": True,
        "progressive_complete": True,
    }


def _synthetic_data_replay_payload(
    benchmark: BenchmarkPackage,
) -> dict[str, object]:
    """Build a Fixture-only Dataset/Field closure covering every value state."""

    project_id = "fixture.data_project"
    input_version_id = "fixture.dataset_field_dictionary"
    snapshot_id = "snapshot.fixture_data_public"
    snapshot_hash = compute_canonical_payload_hash(
        {"fixture": "data_source_snapshot", "version": "1.0.0"}
    )
    input_content_hash = compute_canonical_payload_hash(
        {"fixture": "dataset_field_dictionary", "version": "1.0.0"}
    )
    input_hash = compute_canonical_payload_hash(
        {"fixture": "data_mapping_input", "version": "1.0.0"}
    )
    evidence_ids = tuple(
        sorted(
            (
                "evidence.fixture_conflict",
                "evidence.fixture_declared_null",
                "evidence.fixture_mapped_selected",
                "evidence.fixture_mapped_unselected",
                "evidence.fixture_unresolved",
            )
        )
    )
    dataset_node_id = "node.fixture_dataset"
    field_node_id = "node.fixture_field_star_tic_id"
    return {
        "schema_version": "2.0.0",
        "paper_benchmark_schema_version": benchmark.schema_version,
        "paper_benchmark_version": benchmark.benchmark_version,
        "paper_benchmark_scientific_payload_hash": benchmark.scientific_payload_hash,
        "paper_benchmark_content_hash": benchmark.content_hash,
        "project_id": project_id,
        "reference_project_id": project_id,
        "input_version_id": input_version_id,
        "reference_input_version_id": input_version_id,
        "input_version_known": True,
        "input_version_published": True,
        "input_artifact_kind": "dataset",
        "expected_input_artifact_kind": "dataset",
        "input_schema_version": "1.0.0",
        "supported_input_schema_version": "1.0.0",
        "input_content_hash": input_content_hash,
        "declared_input_content_hash": input_content_hash,
        "input_hash": input_hash,
        "declared_input_hash": input_hash,
        "producer_execution_matches": True,
        "candidate_hash_matches": True,
        "taxonomy_node_types": [
            GraphNodeType.dataset.value,
            GraphNodeType.field.value,
        ],
        "taxonomy_edge_types": [GraphEdgeType.provides_field.value],
        "nodes": [
            {
                "node_id": dataset_node_id,
                "node_type": GraphNodeType.dataset.value,
                "ref_id": "artifact.fixture_dataset",
            },
            {
                "node_id": field_node_id,
                "node_type": GraphNodeType.field.value,
                "ref_id": "field_manifest.fixture:star.tic_id",
            },
        ],
        "edges": [
            {
                "edge_id": "edge.fixture_dataset_provides_star_tic_id",
                "source": dataset_node_id,
                "target": field_node_id,
                "edge_type": GraphEdgeType.provides_field.value,
                "evidence_ids": list(evidence_ids),
                "cross_document": False,
                "relation_id": None,
                "reasoning_trace_id": None,
            }
        ],
        "relations": [],
        "reasoning_traces": [],
        "evidence_ids": list(evidence_ids),
        "evidence": [
            {
                "evidence_id": evidence_id,
                "project_id": project_id,
                "input_version_id": input_version_id,
                "source_snapshot_id": snapshot_id,
                "source_snapshot_content_hash": snapshot_hash,
            }
            for evidence_id in evidence_ids
        ],
        "source_snapshots": [
            {
                "source_snapshot_id": snapshot_id,
                "project_id": project_id,
                "content_hash": snapshot_hash,
            }
        ],
        "source_snapshot_registry_complete": True,
        "data_field_closures": [
            {
                "field_node_id": field_node_id,
                "mapped_selected_evidence_ids": [
                    "evidence.fixture_mapped_selected"
                ],
                "mapped_unselected_evidence_ids": [
                    "evidence.fixture_mapped_unselected"
                ],
                "declared_null_evidence_ids": [
                    "evidence.fixture_declared_null"
                ],
                "unresolved_evidence_ids": ["evidence.fixture_unresolved"],
                "conflict_evidence_ids": ["evidence.fixture_conflict"],
            }
        ],
        "declared_complete_item_count": 8,
        "max_nodes": 10_000,
        "max_edges": 20_000,
        "max_evidence_uses": 50_000,
        "filter_complete": True,
        "aggregation_complete": True,
        "progressive_complete": True,
    }


def _append_nonaccepted_relation_edge(
    payload: dict[str, object],
    *,
    relation_id: str,
) -> None:
    relations = payload["relations"]
    assert isinstance(relations, list)
    relation = next(item for item in relations if item["relation_id"] == relation_id)
    nodes = payload["nodes"]
    assert isinstance(nodes, list)
    node_by_ref = {item["ref_id"]: item["node_id"] for item in nodes}
    for claim_id in (relation["source_claim_id"], relation["target_claim_id"]):
        if claim_id not in node_by_ref:
            node_id = "node.benchmark_" + claim_id.replace(".", "_")
            nodes.append(
                {
                    "node_id": node_id,
                    "node_type": GraphNodeType.claim.value,
                    "ref_id": claim_id,
                }
            )
            node_by_ref[claim_id] = node_id
    nodes.sort(key=lambda item: item["node_id"])
    allowed_edge_values = {
        GraphEdgeType.supports_finding.value,
        GraphEdgeType.extends.value,
        GraphEdgeType.derived_from.value,
    }
    edge_type = relation["relation_type"]
    if edge_type not in allowed_edge_values:
        edge_type = GraphEdgeType.derived_from.value
    edges = payload["edges"]
    assert isinstance(edges, list)
    edges.append(
        {
            "edge_id": "edge.benchmark_nonaccepted_"
            + relation_id.replace(".", "_"),
            "source": node_by_ref[relation["source_claim_id"]],
            "target": node_by_ref[relation["target_claim_id"]],
            "edge_type": edge_type,
            "evidence_ids": sorted(relation["evidence_ids"]),
            "cross_document": True,
            "relation_id": relation_id,
            "reasoning_trace_id": relation["reasoning_trace_id"],
        }
    )
    edges.sort(key=lambda item: item["edge_id"])


def _benchmark_case(
    *,
    case_id: str,
    kind: GraphBenchmarkCaseKind,
    data_level: Literal["benchmark", "fixture"],
    input_json: str,
    expected_status: GraphIntegrityStatus,
    expected_node_ids: tuple[str, ...],
    expected_edge_ids: tuple[str, ...],
    expected_evidence_use_count: int,
    expected_failure_stage: GraphIntegrityStage | None = None,
    expected_rejection_reason: GraphRejectionReason | None = None,
) -> GraphBenchmarkEvaluationCase:
    payload = {
        "case_id": case_id,
        "kind": kind,
        "data_level": data_level,
        "input_json": input_json,
        "expected_status": expected_status,
        "expected_failure_stage": expected_failure_stage,
        "expected_rejection_reason": expected_rejection_reason,
        "expected_node_ids": expected_node_ids,
        "expected_edge_ids": expected_edge_ids,
        "expected_evidence_use_count": expected_evidence_use_count,
    }
    hash_payload = {key: value for key, value in payload.items() if value is not None}
    return GraphBenchmarkEvaluationCase(
        **payload,
        content_hash=compute_graph_benchmark_case_hash(hash_payload),
    )


def _cross_edge(payload: dict[str, object]) -> dict[str, object]:
    edges = payload["edges"]
    assert isinstance(edges, list)
    return next(item for item in edges if item["cross_document"])


def _integrity_report(
    *,
    payload: _ReplayInput | None,
    stage: GraphIntegrityStage | None = None,
    reason: GraphRejectionReason | None = None,
    path: str | None = None,
    message: str | None = None,
) -> GraphIntegrityReport:
    relation_edges = (
        0
        if payload is None
        else sum(item.cross_document for item in payload.edges)
    )
    counts = GraphIntegrityCounts(
        input_version_count=1,
        node_count=0 if payload is None else len(payload.nodes),
        edge_count=0 if payload is None else len(payload.edges),
        evidence_use_count=(
            0
            if payload is None
            else sum(len(item.evidence_ids) for item in payload.edges)
        ),
        source_snapshot_count=(
            0 if payload is None else len(payload.source_snapshots)
        ),
        relation_edge_count=relation_edges,
    )
    findings: tuple[GraphIntegrityFinding, ...] = ()
    status = GraphIntegrityStatus.passed
    if stage is not None and reason is not None:
        status = GraphIntegrityStatus.failed
        findings = (
            GraphIntegrityFinding(
                stage=stage,
                reason=reason,
                priority=_STAGE_PRIORITY[stage],
                path=path or "$",
                message=message or reason.value,
            ),
        )
    primitive = {
        "policy_version": GRAPH_INTEGRITY_POLICY_VERSION,
        "status": status.value,
        "findings": [item.model_dump(mode="json") for item in findings],
        "first_failure_stage": None if stage is None else stage.value,
        "first_rejection_reason": None if reason is None else reason.value,
        "counts": counts.model_dump(mode="json"),
        "content_hash": _ZERO_HASH,
    }
    report_hash_payload = {
        key: value for key, value in primitive.items() if value is not None
    }
    primitive["content_hash"] = compute_graph_integrity_report_hash(
        report_hash_payload
    )
    return GraphIntegrityReport.model_validate_json(_canonical_json(primitive))


def _passing_replay_hashes(
    *,
    payload: _ReplayInput,
    report: GraphIntegrityReport,
) -> tuple[str, str, str, str]:
    canonical = payload.model_dump(mode="json", exclude_none=True)
    input_hash = compute_canonical_payload_hash(
        {
            "paper_benchmark_identity": {
                "schema_version": payload.paper_benchmark_schema_version,
                "benchmark_version": payload.paper_benchmark_version,
                "scientific_payload_hash": payload.paper_benchmark_scientific_payload_hash,
                "content_hash": payload.paper_benchmark_content_hash,
            },
            "capacity": {
                "max_nodes": payload.max_nodes,
                "max_edges": payload.max_edges,
                "max_evidence_uses": payload.max_evidence_uses,
            },
            "filter_complete": payload.filter_complete,
            "aggregation_complete": payload.aggregation_complete,
            "progressive_complete": payload.progressive_complete,
        }
    )
    scientific_hash = compute_canonical_payload_hash(
        {
            "schema_version": payload.schema_version,
            "nodes": canonical["nodes"],
            "edges": canonical["edges"],
            "relations": canonical["relations"],
            "reasoning_traces": canonical["reasoning_traces"],
            "evidence_ids": canonical["evidence_ids"],
            "capacity": {
                "max_nodes": payload.max_nodes,
                "max_edges": payload.max_edges,
                "max_evidence_uses": payload.max_evidence_uses,
            },
            "filter_complete": payload.filter_complete,
            "aggregation_complete": payload.aggregation_complete,
        }
    )
    # The replay is not a candidate seal, but its layout commitment follows
    # the authoritative schema's declarative layout boundary exactly.
    layout_hash = compute_graph_layout_hash(
        {"layout_hint": {"strategy": "none", "group_order": []}}
    )
    output_hash = compute_canonical_payload_hash(
        {
            "input_hash": input_hash,
            "scientific_hash": scientific_hash,
            "layout_hash": layout_hash,
            "report_hash": report.content_hash,
        }
    )
    return input_hash, scientific_hash, layout_hash, output_hash


def _edge_signature(edge: _ReplayEdge) -> tuple[object, ...]:
    return (
        edge.source,
        edge.target,
        edge.edge_type,
        tuple(sorted(edge.evidence_ids)),
        edge.cross_document,
        edge.relation_id,
        edge.reasoning_trace_id,
    )


def _unexpected_count(
    actual: tuple[str, ...],
    expected: tuple[str, ...],
) -> int:
    return len(set(actual) - set(expected)) + len(actual) - len(set(actual))


def _metric(
    numerator: int,
    denominator: int,
    denominator_scope: GraphBenchmarkDenominatorScope,
) -> GraphBenchmarkMetric:
    return GraphBenchmarkMetric(
        numerator=numerator,
        denominator=denominator,
        rate=None if denominator == 0 else numerator / denominator,
        denominator_scope=denominator_scope,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay the formal Evidence Graph benchmark suite."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        help="Replay an existing serialized full case suite.",
    )
    parser.add_argument(
        "--cases-output",
        type=Path,
        help="Write the canonical full case suite.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the canonical report; stdout is used when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    benchmark = load_frozen_benchmark()
    if args.cases is None:
        cases = build_frozen_graph_benchmark_cases(benchmark)
    else:
        cases = _CASE_ADAPTER.validate_json(args.cases.read_text(encoding="utf-8"))
    validate_formal_case_coverage(benchmark, cases)
    report = evaluate_graph_benchmark(benchmark=benchmark, cases=cases)

    case_content = _stable_json(
        [item.model_dump(mode="json", exclude_none=True) for item in cases]
    )
    if args.cases_output is not None:
        args.cases_output.parent.mkdir(parents=True, exist_ok=True)
        args.cases_output.write_text(case_content, encoding="utf-8", newline="\n")
    report_content = _stable_json(
        report.model_dump(mode="json", exclude_none=True)
    )
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report_content, encoding="utf-8", newline="\n")
    else:
        print(report_content, end="")
    return 0


__all__ = [
    "FORMAL_REJECTION_EXPECTATIONS",
    "FORMAL_SIZE_EXPECTATIONS",
    "FrozenGraphReplayAdapter",
    "GraphBenchmarkAdapter",
    "GraphBenchmarkObservation",
    "build_frozen_graph_benchmark_cases",
    "evaluate_graph_benchmark",
    "main",
    "validate_formal_case_coverage",
    "validate_frozen_graph_label",
]


if __name__ == "__main__":
    raise SystemExit(main())
