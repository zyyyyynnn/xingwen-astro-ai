"""Deterministic Versioned Evidence Graph construction and sealed admission."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from typing import Any

from pydantic import ValidationError

from app.schemas._graph_seal import _bind_graph_pipeline_authority
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import EvidenceType, GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GRAPH_TAXONOMY_EDGE_TYPES,
    GRAPH_TAXONOMY_NODE_TYPES,
    GraphAdmissionResult,
    GraphAlgorithmProducer,
    GraphArtifactCandidate,
    GraphArtifactEdge,
    GraphArtifactNode,
    GraphArtifactVersionReference,
    GraphBuildRequest,
    GraphBuildScope,
    GraphDataEdgeAggregation,
    GraphEvidenceUse,
    GraphInputRole,
    GraphInputVersionClosure,
    GraphIntegrityCounts,
    GraphIntegrityFinding,
    GraphIntegrityStage,
    GraphIntegrityStatus,
    GraphLayoutHint,
    GraphLogicalReferencePart,
    GraphNodeVersionBinding,
    GraphPolicySet,
    GraphProgressiveChunk,
    GraphProgressiveInput,
    GraphRelationTraceBinding,
    GraphRejectionReason,
    GraphSourceSnapshotReference,
    GraphTaxonomy,
    build_graph_admission_snapshot,
    compute_graph_input_hash,
    compute_graph_algorithm_parameters_hash,
    compute_graph_layout_hash,
    compute_graph_output_hash,
    compute_graph_scientific_hash,
)
from app.schemas.literature_claim import LiteratureClaimStatus
from app.schemas.literature_relation import LiteratureRelationStatus
from app.security import SecurityProblem

from .admission import (
    GraphAdmissionFailure,
    build_integrity_report,
    failed_integrity_report,
)
from .identity import (
    GraphIdentityError,
    GraphNodeIdentity,
    claim_node_identity,
    dataset_node_identity,
    field_node_identity,
    graph_edge_type_for_literature_relation,
    graph_evidence_use_id,
    literature_relation_edge_identity,
    paper_node_identity,
    provides_field_edge_identity,
    supports_finding_edge_identity,
)
from .ports import (
    GraphDataVersionSelection,
    GraphInputIntegrityError,
    GraphInputVersionSelection,
    PersistedEvidenceBinding,
    PersistedSourceSnapshotBinding,
    PublishedArtifactVersionPins,
    PublishedGraphInputs,
    VersionedGraphInputReadPort,
    graph_input_security_error,
)


def _item_id(category: str, payload: object) -> str:
    digest = compute_canonical_payload_hash(payload).removeprefix("sha256:")[:24]
    return f"item.{category}_{digest}"


def required_progressive_item_ids(
    *,
    literature_relations_artifact_version_id: str,
    dataset_artifact_version_id: str | None,
    field_dictionary_artifact_version_id: str | None,
    scope: GraphBuildScope,
) -> tuple[str, ...]:
    """Return the complete stable logical item set for progressive admission."""

    values = {
        _item_id("input", literature_relations_artifact_version_id),
        *(_item_id("paper", value) for value in scope.literature_paper_ids),
        *(_item_id("claim", value) for value in scope.literature_claim_ids),
        *(_item_id("relation", value) for value in scope.accepted_relation_ids),
        *(
            _item_id(
                "structural",
                (item.edge_type.value, item.source_paper_id, item.target_claim_id),
            )
            for item in scope.structural_edges
        ),
    }
    if dataset_artifact_version_id is not None:
        values.add(_item_id("input", dataset_artifact_version_id))
    if field_dictionary_artifact_version_id is not None:
        values.add(_item_id("input", field_dictionary_artifact_version_id))
    return tuple(sorted(values))


def build_complete_progressive_input(
    *,
    progressive_id: str,
    literature_relations_artifact_version_id: str,
    dataset_artifact_version_id: str | None,
    field_dictionary_artifact_version_id: str | None,
    scope: GraphBuildScope,
    chunk_size: int = 10_000,
    reverse_chunks: bool = False,
) -> GraphProgressiveInput:
    """Build a complete deterministic chunk envelope; order is non-semantic."""

    if chunk_size < 1 or chunk_size > 10_000:
        raise ValueError("chunk_size must be between 1 and 10000")
    item_ids = required_progressive_item_ids(
        literature_relations_artifact_version_id=(
            literature_relations_artifact_version_id
        ),
        dataset_artifact_version_id=dataset_artifact_version_id,
        field_dictionary_artifact_version_id=field_dictionary_artifact_version_id,
        scope=scope,
    )
    chunks = tuple(
        GraphProgressiveChunk(chunk_index=index, item_ids=item_ids[offset : offset + chunk_size])
        for index, offset in enumerate(range(0, len(item_ids), chunk_size))
    )
    supplied = tuple(reversed(chunks)) if reverse_chunks else chunks
    return GraphProgressiveInput(
        progressive_id=progressive_id,
        chunk_count=len(chunks),
        chunks=supplied,
        complete=True,
    )


def _empty_counts(input_version_count: int = 1) -> GraphIntegrityCounts:
    return GraphIntegrityCounts(
        input_version_count=max(1, min(input_version_count, 3)),
        node_count=0,
        edge_count=0,
        evidence_use_count=0,
        source_snapshot_count=0,
        relation_edge_count=0,
    )


def _input_failure(exc: GraphInputIntegrityError) -> GraphAdmissionFailure:
    return GraphAdmissionFailure(
        exc.stage,
        exc.reason,
        exc.path,
        str(exc),
    )


def _version_reference(
    pins: PublishedArtifactVersionPins,
    *,
    role: GraphInputRole,
) -> GraphArtifactVersionReference:
    producer = pins.producer_execution.producer
    return GraphArtifactVersionReference(
        role=role,
        artifact_id=pins.artifact_id,
        artifact_version_id=pins.artifact_version_id,
        project_id=pins.project_id,
        version_number=pins.version_number,
        kind=role.value,
        schema_version=pins.schema_version,
        content_hash=pins.content_hash,
        input_hash=pins.input_hash,
        output_hash=pins.output_hash,
        source_mode=pins.source_mode.value,
        producer_type=producer.type,
        producer_name=producer.name,
        producer_version=producer.version,
        parameters_hash=pins.producer_execution.parameters_hash,
    )


def _taxonomy() -> GraphTaxonomy:
    payload = {
        "taxonomy_id": "taxonomy.graph.evidence_graph",
        "schema_version": "2.0.0",
        "version": "2.0.0",
        "node_types": GRAPH_TAXONOMY_NODE_TYPES,
        "edge_types": GRAPH_TAXONOMY_EDGE_TYPES,
    }
    return GraphTaxonomy(
        **payload,
        content_hash=compute_canonical_payload_hash(payload),
    )


def _node(
    identity: GraphNodeIdentity,
    *,
    label: str,
    bindings: Iterable[GraphNodeVersionBinding],
) -> GraphArtifactNode:
    return GraphArtifactNode(
        node_id=identity.node_id,
        node_type=identity.node_type,
        label=label,
        logical_reference=tuple(
            GraphLogicalReferencePart(name=name, value=value)
            for name, value in identity.logical_reference
        ),
        version_bindings=tuple(
            sorted(
                bindings,
                key=lambda item: (
                    item.artifact_version_id,
                    item.domain_object_id,
                ),
            )
        ),
    )


class _Assembly:
    def __init__(self, inputs: PublishedGraphInputs) -> None:
        self.inputs = inputs
        self.nodes: dict[str, GraphArtifactNode] = {}
        self.edges: dict[str, GraphArtifactEdge] = {}
        self.evidence_uses: dict[str, GraphEvidenceUse] = {}
        self.snapshots: dict[str, GraphSourceSnapshotReference] = {}

    def add_node(self, node: GraphArtifactNode) -> None:
        existing = self.nodes.get(node.node_id)
        if existing is not None and existing != node:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.identity,
                GraphRejectionReason.identity_collision,
                f"nodes.{node.node_id}",
                "one Graph node identity resolves to different domain bindings",
            )
        if existing is not None:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.identity,
                GraphRejectionReason.duplicate_node_identity,
                f"nodes.{node.node_id}",
                "Graph node identity was requested more than once",
            )
        self.nodes[node.node_id] = node

    def add_snapshot(self, binding: PersistedSourceSnapshotBinding) -> None:
        source = binding.source_snapshot
        effective_version = (
            source.source_version_or_etag or source.cache_version or source.content_hash
        )
        reference = GraphSourceSnapshotReference(
            source_snapshot_id=binding.pipeline_source_snapshot_id,
            persisted_source_snapshot_id=binding.persisted_source_snapshot_id,
            source_id=source.source_id,
            source_version=effective_version,
            content_hash=source.content_hash,
            project_id=self.inputs.selection.project_id,
        )
        existing = self.snapshots.get(reference.source_snapshot_id)
        if existing is not None and existing != reference:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.source_snapshot_inconsistent,
                f"source_snapshots.{reference.source_snapshot_id}",
                "SourceSnapshot logical identity resolves to conflicting persisted facts",
            )
        self.snapshots[reference.source_snapshot_id] = reference

    def evidence_use(
        self,
        *,
        edge_id: str,
        pins: PublishedArtifactVersionPins,
        binding: PersistedEvidenceBinding,
    ) -> GraphEvidenceUse:
        use_id = graph_evidence_use_id(
            graph_edge_id=edge_id,
            upstream_artifact_version_id=pins.artifact_version_id,
            upstream_evidence_id=binding.persisted_evidence_id,
        )
        try:
            evidence_type = EvidenceType(binding.evidence.evidence_type)
        except ValueError as exc:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.taxonomy,
                GraphRejectionReason.taxonomy_violation,
                f"evidence.{binding.pipeline_evidence_id}.evidence_type",
                "upstream Evidence type is outside the governed taxonomy",
            ) from exc
        use = GraphEvidenceUse(
            evidence_use_id=use_id,
            graph_edge_id=edge_id,
            upstream_artifact_version_id=pins.artifact_version_id,
            upstream_evidence_id=binding.persisted_evidence_id,
            upstream_target_type=binding.evidence.target_type,
            upstream_target_id=binding.evidence.target_id,
            source_snapshot_id=binding.pipeline_source_snapshot_id,
            evidence_type=evidence_type,
            upstream_evidence_hash=binding.upstream_evidence_content_hash,
            upstream_is_restricted=binding.is_restricted,
        )
        existing = self.evidence_uses.get(use_id)
        if existing is not None and existing != use:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.identity,
                GraphRejectionReason.identity_collision,
                f"evidence_uses.{use_id}",
                "Graph Evidence-use identity resolves to conflicting provenance",
            )
        self.evidence_uses[use_id] = use
        return use

    def add_edge(self, edge: GraphArtifactEdge) -> None:
        existing = self.edges.get(edge.edge_id)
        if existing is not None:
            reason = (
                GraphRejectionReason.duplicate_edge_identity
                if existing == edge
                else GraphRejectionReason.identity_collision
            )
            raise GraphAdmissionFailure(
                GraphIntegrityStage.identity,
                reason,
                f"edges.{edge.edge_id}",
                "Graph edge identity is duplicated or ambiguous",
            )
        self.edges[edge.edge_id] = edge


def _literature_claim_version_id(inputs: PublishedGraphInputs, claim_id: str) -> str:
    for reference in inputs.literature_relations.candidate.input_versions.claim_artifact_versions:
        if claim_id in reference.claim_ids:
            return reference.artifact_version_id
    raise GraphAdmissionFailure(
        GraphIntegrityStage.artifact_version,
        GraphRejectionReason.cross_version_reference,
        f"claims.{claim_id}.artifact_version_id",
        "Claim does not resolve to one pinned LiteratureClaims ArtifactVersion",
    )


def _literature_evidence_bindings(
    inputs: PublishedGraphInputs,
    evidence_id: str,
    *,
    target_relation_ids: Iterable[str],
) -> tuple[PersistedEvidenceBinding, ...]:
    targets = frozenset(target_relation_ids)
    pipeline_evidence = next(
        (
            item
            for item in inputs.literature_relations.candidate.evidence
            if item.evidence_id == evidence_id
        ),
        None,
    )
    pipeline_content_hash = (
        compute_canonical_payload_hash(
            pipeline_evidence.model_dump(mode="json", exclude_none=True)
        )
        if pipeline_evidence is not None
        else None
    )
    matches = tuple(
        item
        for item in inputs.literature_relations.evidence_bindings
        if item.pipeline_evidence_id == evidence_id
        and item.pipeline_evidence_content_hash == pipeline_content_hash
        and item.pipeline_target_type == "relation"
        and item.pipeline_target_id in targets
        and item.pipeline_locator.get("summary_evidence_id") == evidence_id
        and item.evidence.target_type == "relation"
        and item.evidence.target_id == item.pipeline_target_id
        and item.evidence.locator == item.pipeline_locator
    )
    if (
        not targets
        or len(matches) != len(targets)
        or {item.evidence.target_id for item in matches} != targets
    ):
        raise GraphAdmissionFailure(
            GraphIntegrityStage.evidence_snapshot,
            GraphRejectionReason.evidence_missing,
            f"evidence.{evidence_id}",
            "Literature Evidence does not exactly close the selected Relation targets",
        )
    return tuple(
        sorted(
            matches,
            key=lambda item: (
                item.evidence.target_id,
                item.persisted_evidence_id,
            ),
        )
    )


def _selected_claim_failure(
    claim_id: str,
    claims: dict[str, Any],
) -> GraphAdmissionFailure | None:
    claim = claims.get(claim_id)
    if claim is not None and claim.status is LiteratureClaimStatus.accepted:
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.relation_not_accepted,
        f"claims.{claim_id}",
        "Graph Claims must be accepted and retained by the pinned input",
    )


def _selected_relation_failure(
    relation_id: str,
    relations: dict[str, Any],
) -> GraphAdmissionFailure | None:
    relation = relations.get(relation_id)
    if relation is not None and relation.status is LiteratureRelationStatus.accepted:
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.relation_not_accepted,
        f"relations.{relation_id}",
        "only an accepted LiteratureRelation can become a Graph edge",
    )


def _paper_matching_claims(
    paper_id: str,
    claims: dict[str, Any],
    selected_claim_ids: Iterable[str],
) -> tuple[Any, ...]:
    selected = frozenset(selected_claim_ids)
    return tuple(
        item
        for item in claims.values()
        if item.paper_id == paper_id
        and item.claim_id in selected
        and item.status is LiteratureClaimStatus.accepted
    )


def _paper_selection_failure(
    paper_id: str,
    claims: dict[str, Any],
    selected_claim_ids: Iterable[str],
) -> GraphAdmissionFailure | None:
    if _paper_matching_claims(paper_id, claims, selected_claim_ids):
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.endpoint,
        GraphRejectionReason.dangling_endpoint,
        f"papers.{paper_id}",
        "Paper node has no retained Claim provenance in the pinned input",
    )


def _structural_edge_failure(
    request: Any,
    claims: dict[str, Any],
    *,
    selected_claim_ids: Iterable[str],
    selected_paper_ids: Iterable[str],
) -> GraphAdmissionFailure | None:
    claim = claims.get(request.target_claim_id)
    if (
        request.source_paper_id in frozenset(selected_paper_ids)
        and request.target_claim_id in frozenset(selected_claim_ids)
        and claim is not None
        and claim.status is LiteratureClaimStatus.accepted
        and claim.paper_id == request.source_paper_id
    ):
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.wrong_direction,
        "scope.structural_edges",
        "supports_finding must preserve Paper -> its accepted Claim",
    )


def _relation_endpoint_failure(
    relation_id: str,
    relation: Any,
    claims: dict[str, Any],
    selected_claim_ids: Iterable[str],
) -> GraphAdmissionFailure | None:
    selected = frozenset(selected_claim_ids)
    endpoints = (relation.source_claim_id, relation.target_claim_id)
    if all(
        claim_id in selected
        and (claim := claims.get(claim_id)) is not None
        and claim.status is LiteratureClaimStatus.accepted
        for claim_id in endpoints
    ):
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.endpoint,
        GraphRejectionReason.dangling_endpoint,
        f"relations.{relation_id}",
        "accepted Relation endpoints must both be retained Claim nodes",
    )


def _relation_direction_failure(
    relation_id: str,
    relation: Any,
) -> GraphAdmissionFailure | None:
    if (
        relation.direction.source_claim_id == relation.source_claim_id
        and relation.direction.target_claim_id == relation.target_claim_id
    ):
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.wrong_direction,
        f"relations.{relation_id}.direction",
        "Relation direction does not equal source Claim -> target Claim",
    )


def _reasoning_trace_failure(
    relation_id: str,
    relation: Any,
    trace: Any | None,
) -> GraphAdmissionFailure | None:
    if trace is None:
        return GraphAdmissionFailure(
            GraphIntegrityStage.relation_trace,
            GraphRejectionReason.reasoning_trace_missing,
            f"relations.{relation_id}.reasoning_trace",
            "accepted Relation requires its retained ReasoningTrace",
        )
    trace_evidence_ids = {
        *trace.evidence_ids,
        *(evidence_id for step in trace.steps for evidence_id in step.evidence_ids),
    }
    if (
        trace.relation_id == relation_id
        and trace.relation_status is LiteratureRelationStatus.accepted
        and trace.premise_claim_ids
        == (relation.source_claim_id, relation.target_claim_id)
        and not trace_evidence_ids - set(relation.evidence_ids)
    ):
        return None
    return GraphAdmissionFailure(
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.reasoning_trace_mismatch,
        f"relations.{relation_id}.reasoning_trace",
        "ReasoningTrace does not close the accepted Relation premises/Evidence",
    )


def _add_literature(assembly: _Assembly, scope: GraphBuildScope) -> None:
    published = assembly.inputs.literature_relations
    candidate = published.candidate
    claims = {item.claim_id: item for item in candidate.claims}
    relations = {item.relation_id: item for item in candidate.relations}
    traces = {item.trace_id: item for item in candidate.reasoning_traces}
    for relation_id in scope.accepted_relation_ids:
        failure = _selected_relation_failure(relation_id, relations)
        if failure is not None:
            raise failure

    claim_node_by_id: dict[str, GraphArtifactNode] = {}
    paper_node_by_id: dict[str, GraphArtifactNode] = {}
    for claim_id in scope.literature_claim_ids:
        claim = claims.get(claim_id)
        failure = _selected_claim_failure(claim_id, claims)
        if failure is not None:
            raise failure
        assert claim is not None
        claim_version_id = _literature_claim_version_id(assembly.inputs, claim_id)
        identity = claim_node_identity(claim_id)
        node = _node(
            identity,
            label=f"Claim {claim_id}",
            bindings=(
                GraphNodeVersionBinding(
                    artifact_version_id=claim_version_id,
                    domain_object_id=claim_id,
                ),
            ),
        )
        assembly.add_node(node)
        claim_node_by_id[claim_id] = node

    for paper_id in scope.literature_paper_ids:
        matching_claims = _paper_matching_claims(
            paper_id,
            claims,
            scope.literature_claim_ids,
        )
        failure = _paper_selection_failure(
            paper_id,
            claims,
            scope.literature_claim_ids,
        )
        if failure is not None:
            raise failure
        summary_versions = tuple(
            sorted(
                {
                    item.source_paper_summary_artifact_version_id
                    for item in matching_claims
                }
            )
        )
        identity = paper_node_identity(paper_id)
        node = _node(
            identity,
            label=f"Paper {paper_id}",
            bindings=tuple(
                GraphNodeVersionBinding(
                    artifact_version_id=version_id,
                    domain_object_id=paper_id,
                )
                for version_id in summary_versions
            ),
        )
        assembly.add_node(node)
        paper_node_by_id[paper_id] = node

    snapshots_by_pipeline = {
        item.pipeline_source_snapshot_id: item
        for item in published.source_snapshot_bindings
    }

    for request in scope.structural_edges:
        source_node = paper_node_by_id.get(request.source_paper_id)
        target_node = claim_node_by_id.get(request.target_claim_id)
        claim = claims.get(request.target_claim_id)
        failure = _structural_edge_failure(
            request,
            claims,
            selected_claim_ids=scope.literature_claim_ids,
            selected_paper_ids=scope.literature_paper_ids,
        )
        if failure is not None:
            raise failure
        assert source_node is not None and target_node is not None and claim is not None
        edge_identity = supports_finding_edge_identity(
            paper_node_identity(request.source_paper_id),
            claim_node_identity(request.target_claim_id),
        )
        uses: list[GraphEvidenceUse] = []
        for evidence_id in sorted(claim.evidence_ids):
            target_relations = tuple(
                sorted(
                    {
                        reference.relation_id
                        for reference in candidate.evidence_references
                        if reference.claim_id == claim.claim_id
                        and reference.evidence_id == evidence_id
                        and relations[reference.relation_id].status
                        is LiteratureRelationStatus.accepted
                    }
                )
            )
            for binding in _literature_evidence_bindings(
                assembly.inputs,
                evidence_id,
                target_relation_ids=target_relations,
            ):
                snapshot = snapshots_by_pipeline.get(
                    binding.pipeline_source_snapshot_id
                )
                if snapshot is None:
                    raise GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.source_snapshot_missing,
                        f"evidence.{evidence_id}.source_snapshot",
                        "Literature Evidence SourceSnapshot binding is missing",
                    )
                assembly.add_snapshot(snapshot)
                uses.append(
                    assembly.evidence_use(
                        edge_id=edge_identity.edge_id,
                        pins=published.pins,
                        binding=binding,
                    )
                )
        assembly.add_edge(
            GraphArtifactEdge(
                edge_id=edge_identity.edge_id,
                edge_type=GraphEdgeType.supports_finding,
                source_node_id=source_node.node_id,
                target_node_id=target_node.node_id,
                evidence_use_ids=tuple(sorted(item.evidence_use_id for item in uses)),
            )
        )
    _add_literature_relations(
        assembly,
        scope,
        claims=claims,
        claim_node_by_id=claim_node_by_id,
        snapshots_by_pipeline=snapshots_by_pipeline,
    )


def _add_literature_relations(
    assembly: _Assembly,
    scope: GraphBuildScope,
    *,
    claims: dict[str, Any],
    claim_node_by_id: dict[str, GraphArtifactNode],
    snapshots_by_pipeline: dict[str, PersistedSourceSnapshotBinding],
) -> None:
    published = assembly.inputs.literature_relations
    relations = {item.relation_id: item for item in published.candidate.relations}
    traces = {item.trace_id: item for item in published.candidate.reasoning_traces}
    for relation_id in scope.accepted_relation_ids:
        relation = relations.get(relation_id)
        failure = _selected_relation_failure(relation_id, relations)
        if failure is not None:
            raise failure
        assert relation is not None
        source_node = claim_node_by_id.get(relation.source_claim_id)
        target_node = claim_node_by_id.get(relation.target_claim_id)
        failure = _relation_endpoint_failure(
            relation_id,
            relation,
            claims,
            scope.literature_claim_ids,
        )
        if failure is not None:
            raise failure
        assert source_node is not None and target_node is not None
        failure = _relation_direction_failure(relation_id, relation)
        if failure is not None:
            raise failure
        try:
            edge_type = graph_edge_type_for_literature_relation(
                relation.relation_type
            )
        except GraphIdentityError as exc:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.taxonomy,
                GraphRejectionReason.taxonomy_violation,
                f"relations.{relation_id}.relation_type",
                "accepted Relation type has no authorized Versioned Evidence Graph edge type",
            ) from exc
        trace = traces.get(relation.reasoning_trace_id or "")
        failure = _reasoning_trace_failure(relation_id, relation, trace)
        if failure is not None:
            raise failure
        assert trace is not None
        trace_evidence_ids = tuple(
            sorted(
                {
                    *trace.evidence_ids,
                    *(
                        evidence_id
                        for step in trace.steps
                        for evidence_id in step.evidence_ids
                    ),
                }
            )
        )
        identity = literature_relation_edge_identity(
            claim_node_identity(relation.source_claim_id),
            claim_node_identity(relation.target_claim_id),
            relation_type=relation.relation_type,
            relation_logical_id=relation_id,
        )
        uses: list[GraphEvidenceUse] = []
        for evidence_id in sorted(relation.evidence_ids):
            for binding in _literature_evidence_bindings(
                assembly.inputs,
                evidence_id,
                target_relation_ids=(relation_id,),
            ):
                snapshot = snapshots_by_pipeline.get(
                    binding.pipeline_source_snapshot_id
                )
                if snapshot is None:
                    raise GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.source_snapshot_missing,
                        f"relations.{relation_id}.evidence.{evidence_id}",
                        "Relation Evidence SourceSnapshot binding is missing",
                    )
                assembly.add_snapshot(snapshot)
                uses.append(
                    assembly.evidence_use(
                        edge_id=identity.edge_id,
                        pins=published.pins,
                        binding=binding,
                    )
                )
        assembly.add_edge(
            GraphArtifactEdge(
                edge_id=identity.edge_id,
                edge_type=edge_type,
                source_node_id=source_node.node_id,
                target_node_id=target_node.node_id,
                evidence_use_ids=tuple(sorted(item.evidence_use_id for item in uses)),
                relation_trace=GraphRelationTraceBinding(
                    relation_id=relation_id,
                    relation_artifact_version_id=published.pins.artifact_version_id,
                    relation_status="accepted",
                    relation_type=edge_type,
                    source_claim_id=relation.source_claim_id,
                    target_claim_id=relation.target_claim_id,
                    reasoning_trace_id=trace.trace_id,
                    premise_claim_ids=trace.premise_claim_ids,
                    trace_evidence_ids=trace_evidence_ids,
                ),
            )
        )


def _data_evidence_bindings(
    inputs: PublishedGraphInputs,
    evidence_id: str,
) -> tuple[tuple[PublishedArtifactVersionPins, PersistedEvidenceBinding], ...]:
    assert inputs.data is not None
    matches: list[tuple[PublishedArtifactVersionPins, PersistedEvidenceBinding]] = []
    for published in (inputs.data.dataset, inputs.data.field_dictionary):
        matches.extend(
            (published.pins, item)
            for item in published.evidence_bindings
            if item.pipeline_evidence_id == evidence_id
        )
    if len(matches) != 2:
        raise GraphAdmissionFailure(
            GraphIntegrityStage.evidence_snapshot,
            GraphRejectionReason.evidence_missing,
            f"data.evidence.{evidence_id}",
            "data Evidence must close both Dataset and FieldDictionary versions",
        )
    dataset = inputs.data.dataset.candidate
    transformations = {
        item.evidence_id: item for item in dataset.transformation_evidence
    }
    transformation = transformations.get(evidence_id)
    for _, binding in matches:
        persisted_matches_pipeline = (
            binding.evidence.target_type == binding.pipeline_target_type
            and binding.evidence.target_id == binding.pipeline_target_id
            and binding.evidence.locator == binding.pipeline_locator
        )
        if transformation is not None:
            valid = (
                persisted_matches_pipeline
                and binding.pipeline_evidence_content_hash
                == transformation.content_hash
                and binding.pipeline_target_type == "canonical_field"
                and binding.pipeline_target_id
                == transformation.canonical_field_id
                and binding.pipeline_locator
                == transformation.locator.model_dump(mode="json")
                and binding.pipeline_source_snapshot_id
                == transformation.locator.source_snapshot_id
            )
        else:
            locator = binding.pipeline_locator
            locator_hash = locator.get("crossmatch_content_hash")
            valid = (
                persisted_matches_pipeline
                and evidence_id in set(dataset.crossmatch_evidence_ids)
                and binding.pipeline_target_type == "crossmatch"
                and binding.pipeline_target_id == evidence_id
                and set(locator)
                == {"crossmatch_evidence_id", "crossmatch_content_hash"}
                and locator.get("crossmatch_evidence_id") == evidence_id
                and isinstance(locator_hash, str)
                and locator_hash.startswith("sha256:")
                and len(locator_hash) == 71
                and locator_hash == binding.pipeline_evidence_content_hash
                and binding.pipeline_source_snapshot_id
                in set(dataset.crossmatch_source_snapshot_ids)
            )
        if not valid:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_inconsistent,
                f"data.evidence.{evidence_id}",
                "data Evidence target/locator/Snapshot does not close its Versioned Data Artifact identity",
            )
    return tuple(sorted(matches, key=lambda item: item[0].artifact_version_id))


@dataclass(frozen=True, slots=True)
class _DataFieldClosure:
    evidence_ids: tuple[str, ...]
    aggregation: GraphDataEdgeAggregation | None
    failures: tuple[GraphAdmissionFailure, ...]


def _data_field_closure(
    inputs: PublishedGraphInputs,
    field_id: str,
) -> _DataFieldClosure:
    assert inputs.data is not None
    dataset = inputs.data.dataset.candidate
    transformations = {
        item.evidence_id: item for item in dataset.transformation_evidence
    }
    snapshot_bindings = {
        item.pipeline_source_snapshot_id: item
        for published in (inputs.data.dataset, inputs.data.field_dictionary)
        for item in published.source_snapshot_bindings
    }
    failures: list[GraphAdmissionFailure] = []
    evidence_ids: set[str] = set()
    projected_row_count = 0
    mapped_outcome_count = 0
    declared_null_outcome_count = 0
    unresolved_outcome_count = 0
    retained_candidate_count = 0
    selected_candidate_count = 0
    conflict_ids: set[str] = set()
    missing_outcome = False
    for row in dataset.rows:
        if field_id not in row.projected_field_ids:
            continue
        projected_row_count += 1
        outcome = next(
            (item for item in row.fields if item.canonical_field_id == field_id),
            None,
        )
        if outcome is None:
            missing_outcome = True
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.evidence_snapshot,
                    GraphRejectionReason.aggregation_incomplete,
                    f"data.rows.{row.row_id}.fields.{field_id}",
                    "every applicable Dataset row must retain the canonical field outcome",
                )
            )
            continue
        retained_candidate_count += len(outcome.candidate_source_value_ids)
        if outcome.status == "mapped":
            mapped_outcome_count += 1
            selected_candidate_count += 1
        elif outcome.status == "declared_null":
            declared_null_outcome_count += 1
        else:
            unresolved_outcome_count += 1
        conflict_ids.update(getattr(outcome, "conflict_ids", ()))
        evidence_ids.update(outcome.transformation_evidence_ids)
        for evidence_id in outcome.transformation_evidence_ids:
            transformation = transformations.get(evidence_id)
            if transformation is None:
                failures.append(
                    GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.evidence_unknown,
                        f"data.transformation_evidence.{evidence_id}",
                        "field outcome references unknown TransformationEvidence",
                    )
                )
                continue
            if transformation.canonical_field_id != field_id:
                failures.append(
                    GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.evidence_inconsistent,
                        f"data.transformation_evidence.{evidence_id}",
                        "TransformationEvidence belongs to another canonical field",
                    )
                )
            evidence_ids.update(transformation.crossmatch_evidence_ids)
    if not evidence_ids:
        failures.append(
            GraphAdmissionFailure(
                GraphIntegrityStage.evidence_snapshot,
                GraphRejectionReason.evidence_missing,
                f"data.fields.{field_id}",
                "provides_field cannot omit a field with no complete Evidence closure",
            )
        )
    for evidence_id in sorted(evidence_ids):
        try:
            matches = _data_evidence_bindings(inputs, evidence_id)
        except GraphAdmissionFailure as exc:
            failures.append(exc)
            continue
        for _, binding in matches:
            if binding.pipeline_source_snapshot_id not in snapshot_bindings:
                failures.append(
                    GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.source_snapshot_missing,
                        f"data.evidence.{evidence_id}.source_snapshot",
                        "data Evidence SourceSnapshot binding is missing",
                    )
                )
    aggregation = None
    if not missing_outcome:
        aggregation = GraphDataEdgeAggregation(
            projected_row_count=projected_row_count,
            mapped_outcome_count=mapped_outcome_count,
            declared_null_outcome_count=declared_null_outcome_count,
            unresolved_outcome_count=unresolved_outcome_count,
            retained_candidate_count=retained_candidate_count,
            selected_candidate_count=selected_candidate_count,
            unselected_candidate_count=(
                retained_candidate_count - selected_candidate_count
            ),
            conflict_count=len(conflict_ids),
            upstream_evidence_count=len(evidence_ids),
        )
    return _DataFieldClosure(
        evidence_ids=tuple(sorted(evidence_ids)),
        aggregation=aggregation,
        failures=tuple(failures),
    )


def _add_data(assembly: _Assembly) -> None:
    if assembly.inputs.data is None:
        return
    published_dataset = assembly.inputs.data.dataset
    published_dictionary = assembly.inputs.data.field_dictionary
    dataset = published_dataset.candidate
    dictionary = published_dictionary.candidate
    dataset_identity = dataset_node_identity(published_dataset.pins.artifact_id)
    dataset_node = _node(
        dataset_identity,
        label=f"Dataset {published_dataset.pins.artifact_id}",
        bindings=(
            GraphNodeVersionBinding(
                artifact_version_id=published_dataset.pins.artifact_version_id,
                domain_object_id=published_dataset.pins.artifact_id,
            ),
        ),
    )
    assembly.add_node(dataset_node)

    snapshot_bindings = {
        item.pipeline_source_snapshot_id: item
        for published in (published_dataset, published_dictionary)
        for item in published.source_snapshot_bindings
    }
    field_manifest_id = dictionary.manifest_pins.field_manifest_id
    for field in dictionary.field_definitions:
        field_id = field.field_id
        identity = field_node_identity(field_manifest_id, field_id)
        node = _node(
            identity,
            label=f"Field {field_id}",
            bindings=(
                GraphNodeVersionBinding(
                    artifact_version_id=(
                        published_dictionary.pins.artifact_version_id
                    ),
                    domain_object_id=field_id,
                ),
            ),
        )
        assembly.add_node(node)
        edge_identity = provides_field_edge_identity(dataset_identity, identity)
        closure = _data_field_closure(assembly.inputs, field_id)
        if closure.failures:
            raise closure.failures[0]
        assert closure.aggregation is not None

        uses: list[GraphEvidenceUse] = []
        for evidence_id in closure.evidence_ids:
            for pins, binding in _data_evidence_bindings(
                assembly.inputs, evidence_id
            ):
                snapshot = snapshot_bindings.get(binding.pipeline_source_snapshot_id)
                if snapshot is None:
                    raise GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.source_snapshot_missing,
                        f"data.evidence.{evidence_id}.source_snapshot",
                        "data Evidence SourceSnapshot binding is missing",
                    )
                assembly.add_snapshot(snapshot)
                uses.append(
                    assembly.evidence_use(
                        edge_id=edge_identity.edge_id,
                        pins=pins,
                        binding=binding,
                    )
                )
        assembly.add_edge(
            GraphArtifactEdge(
                edge_id=edge_identity.edge_id,
                edge_type=GraphEdgeType.provides_field,
                source_node_id=dataset_node.node_id,
                target_node_id=node.node_id,
                evidence_use_ids=tuple(sorted(item.evidence_use_id for item in uses)),
                data_aggregation=closure.aggregation,
            )
        )


def _input_versions(inputs: PublishedGraphInputs) -> GraphInputVersionClosure:
    values = [
        _version_reference(
            inputs.literature_relations.pins,
            role=GraphInputRole.literature_relations,
        )
    ]
    if inputs.data is not None:
        values.extend(
            (
                _version_reference(
                    inputs.data.dataset.pins,
                    role=GraphInputRole.dataset,
                ),
                _version_reference(
                    inputs.data.field_dictionary.pins,
                    role=GraphInputRole.field_dictionary,
                ),
            )
        )
    return GraphInputVersionClosure(
        project_id=inputs.selection.project_id,
        versions=tuple(sorted(values, key=lambda item: item.artifact_version_id)),
    )


def _producer(policies: GraphPolicySet, taxonomy: GraphTaxonomy) -> GraphAlgorithmProducer:
    return GraphAlgorithmProducer(
        parameters_hash=compute_graph_algorithm_parameters_hash(policies, taxonomy)
    )


def _collect_progressive_failures(
    request: GraphBuildRequest,
) -> tuple[GraphAdmissionFailure, ...]:
    failures: list[GraphAdmissionFailure] = []
    if not request.progressive.complete:
        failures.append(
            GraphAdmissionFailure(
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.progressive_input_incomplete,
                "progressive.complete",
                "incomplete progressive input cannot become a final Graph",
            )
        )
    expected = required_progressive_item_ids(
        literature_relations_artifact_version_id=(
            request.literature_relations_artifact_version_id
        ),
        dataset_artifact_version_id=request.dataset_artifact_version_id,
        field_dictionary_artifact_version_id=(
            request.field_dictionary_artifact_version_id
        ),
        scope=request.scope,
    )
    actual = tuple(
        sorted(item_id for chunk in request.progressive.chunks for item_id in chunk.item_ids)
    )
    if actual != expected:
        failures.append(
            GraphAdmissionFailure(
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.progressive_input_incomplete,
                "progressive.chunks",
                "progressive chunks must exactly cover every selected input/scope item",
            )
        )
    capacity = request.policies.capacity_policy
    if (
        len(request.progressive.chunks) > capacity.max_progressive_chunks
        or any(
            len(chunk.item_ids) > capacity.max_items_per_chunk
            for chunk in request.progressive.chunks
        )
    ):
        failures.append(
            GraphAdmissionFailure(
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.size_limit_exceeded,
                "progressive.chunks",
                "progressive chunks exceed the pinned capacity policy",
            )
        )
    return tuple(failures)


def _collect_scope_identity_failures(
    scope: GraphBuildScope,
) -> tuple[GraphAdmissionFailure, ...]:
    failures: list[GraphAdmissionFailure] = []
    for values, node_identity in (
        (scope.literature_claim_ids, claim_node_identity),
        (scope.literature_paper_ids, paper_node_identity),
    ):
        for logical_id in sorted(set(values)):
            if values.count(logical_id) > 1:
                failures.append(
                    GraphAdmissionFailure(
                        GraphIntegrityStage.identity,
                        GraphRejectionReason.duplicate_node_identity,
                        f"nodes.{node_identity(logical_id).node_id}",
                        "Graph node identity was requested more than once",
                    )
                )
    for relation_id in sorted(set(scope.accepted_relation_ids)):
        if scope.accepted_relation_ids.count(relation_id) > 1:
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.identity,
                    GraphRejectionReason.duplicate_edge_identity,
                    f"relations.{relation_id}",
                    "Graph Relation edge identity was requested more than once",
                )
            )
    structural_keys = tuple(
        (
            item.edge_type,
            item.source_paper_id,
            item.target_claim_id,
        )
        for item in scope.structural_edges
    )
    for edge_type, source_paper_id, target_claim_id in sorted(
        set(structural_keys),
        key=lambda item: (str(item[0]), item[1], item[2]),
    ):
        if structural_keys.count((edge_type, source_paper_id, target_claim_id)) > 1:
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.identity,
                    GraphRejectionReason.duplicate_edge_identity,
                    f"scope.structural_edges.{source_paper_id}.{target_claim_id}",
                    "Graph structural edge identity was requested more than once",
                )
            )
    return tuple(failures)


def _collect_literature_gate_failures(
    inputs: PublishedGraphInputs,
    scope: GraphBuildScope,
) -> tuple[GraphAdmissionFailure, ...]:
    failures: list[GraphAdmissionFailure] = []
    published = inputs.literature_relations
    candidate = published.candidate
    claims = {item.claim_id: item for item in candidate.claims}
    relations = {item.relation_id: item for item in candidate.relations}
    traces = {item.trace_id: item for item in candidate.reasoning_traces}
    snapshots = {
        item.pipeline_source_snapshot_id: item
        for item in published.source_snapshot_bindings
    }

    evidence_bindings: list[
        tuple[PublishedArtifactVersionPins, PersistedEvidenceBinding]
    ] = [(published.pins, item) for item in published.evidence_bindings]
    if inputs.data is not None:
        evidence_bindings.extend(
            (data_input.pins, item)
            for data_input in (inputs.data.dataset, inputs.data.field_dictionary)
            for item in data_input.evidence_bindings
        )
    for pins, binding in sorted(
        evidence_bindings,
        key=lambda item: (
            item[0].artifact_version_id,
            item[1].pipeline_evidence_id,
            item[1].persisted_evidence_id,
        ),
    ):
        try:
            EvidenceType(binding.evidence.evidence_type)
        except ValueError:
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.taxonomy,
                    GraphRejectionReason.taxonomy_violation,
                    f"evidence.{binding.pipeline_evidence_id}.evidence_type",
                    "upstream Evidence type is outside the governed taxonomy",
                )
            )

    for index, request in enumerate(scope.structural_edges):
        if (
            type(request.edge_type) is not GraphEdgeType
            or request.edge_type is not GraphEdgeType.supports_finding
        ):
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.taxonomy,
                    GraphRejectionReason.taxonomy_violation,
                    f"scope.structural_edges.{index}.edge_type",
                    "Versioned Evidence Graph structural scope only admits supports_finding",
                )
            )

    for claim_id in sorted(set(scope.literature_claim_ids)):
        failure = _selected_claim_failure(claim_id, claims)
        if failure is not None:
            failures.append(failure)
            continue
        try:
            _literature_claim_version_id(inputs, claim_id)
        except GraphAdmissionFailure as exc:
            failures.append(exc)

    for paper_id in sorted(set(scope.literature_paper_ids)):
        failure = _paper_selection_failure(
            paper_id,
            claims,
            scope.literature_claim_ids,
        )
        if failure is not None:
            failures.append(failure)

    for request in scope.structural_edges:
        failure = _structural_edge_failure(
            request,
            claims,
            selected_claim_ids=scope.literature_claim_ids,
            selected_paper_ids=scope.literature_paper_ids,
        )
        if failure is not None:
            failures.append(failure)

    relation_prerequisite_failed = False
    for relation_id in sorted(set(scope.accepted_relation_ids)):
        relation = relations.get(relation_id)
        failure = _selected_relation_failure(relation_id, relations)
        if failure is not None:
            relation_prerequisite_failed = True
            failures.append(failure)
            continue
        assert relation is not None
        endpoint_failure = _relation_endpoint_failure(
            relation_id,
            relation,
            claims,
            scope.literature_claim_ids,
        )
        if endpoint_failure is not None:
            failures.append(endpoint_failure)
        direction_failure = _relation_direction_failure(relation_id, relation)
        if direction_failure is not None:
            failures.append(direction_failure)
        try:
            graph_edge_type_for_literature_relation(relation.relation_type)
        except GraphIdentityError:
            failures.append(
                GraphAdmissionFailure(
                    GraphIntegrityStage.taxonomy,
                    GraphRejectionReason.taxonomy_violation,
                    f"relations.{relation_id}.relation_type",
                    "accepted Relation type has no authorized Versioned Evidence Graph edge type",
                )
            )
        trace_failure = _reasoning_trace_failure(
            relation_id,
            relation,
            traces.get(relation.reasoning_trace_id or ""),
        )
        if trace_failure is not None:
            failures.append(trace_failure)

    def close_evidence(
        evidence_id: str,
        *,
        target_relation_ids: Iterable[str],
    ) -> None:
        try:
            matches = _literature_evidence_bindings(
                inputs,
                evidence_id,
                target_relation_ids=target_relation_ids,
            )
        except GraphAdmissionFailure as exc:
            failures.append(exc)
            return
        for binding in matches:
            if binding.pipeline_source_snapshot_id not in snapshots:
                failures.append(
                    GraphAdmissionFailure(
                        GraphIntegrityStage.evidence_snapshot,
                        GraphRejectionReason.source_snapshot_missing,
                        f"evidence.{evidence_id}.source_snapshot",
                        "Literature Evidence SourceSnapshot binding is missing",
                    )
                )

    for relation_id in sorted(set(scope.accepted_relation_ids)):
        relation = relations.get(relation_id)
        if relation is None or relation.status is not LiteratureRelationStatus.accepted:
            continue
        for evidence_id in sorted(relation.evidence_ids):
            close_evidence(evidence_id, target_relation_ids=(relation_id,))

    for request in scope.structural_edges:
        claim = claims.get(request.target_claim_id)
        if claim is None or claim.status is not LiteratureClaimStatus.accepted:
            continue
        for evidence_id in sorted(claim.evidence_ids):
            target_relations = tuple(
                sorted(
                    {
                        reference.relation_id
                        for reference in candidate.evidence_references
                        if reference.claim_id == claim.claim_id
                        and reference.evidence_id == evidence_id
                        and (
                            relation := relations.get(reference.relation_id)
                        )
                        is not None
                        and relation.status is LiteratureRelationStatus.accepted
                    }
                )
            )
            if target_relations or not relation_prerequisite_failed:
                close_evidence(
                    evidence_id,
                    target_relation_ids=target_relations,
                )
    return tuple(failures)


def _collect_data_gate_failures(
    inputs: PublishedGraphInputs,
) -> tuple[GraphAdmissionFailure, ...]:
    if inputs.data is None:
        return ()
    return tuple(
        failure
        for field in inputs.data.field_dictionary.candidate.field_definitions
        for failure in _data_field_closure(inputs, field.field_id).failures
    )


def _collect_request_failures(
    request: GraphBuildRequest,
) -> tuple[GraphAdmissionFailure, ...]:
    failures = [
        *_collect_progressive_failures(request),
        *_collect_scope_identity_failures(request.scope),
    ]
    if (
        request.scope.filtered_item_count
        or request.scope.excluded_item_count
        or request.scope.exclusion_reasons
    ):
        failures.append(
            GraphAdmissionFailure(
                GraphIntegrityStage.capacity_progressive,
                GraphRejectionReason.evidence_hidden_by_filter,
                "scope.filter",
                "Graph publication scope cannot hide nodes, edges, or Evidence",
            )
        )
    return tuple(failures)


def _collect_independent_input_failures(
    request: GraphBuildRequest,
    inputs: PublishedGraphInputs,
) -> tuple[GraphAdmissionFailure, ...]:
    return (
        *_collect_literature_gate_failures(inputs, request.scope),
        *_collect_data_gate_failures(inputs),
    )


def _selection(request: GraphBuildRequest) -> GraphInputVersionSelection:
    data = None
    if request.dataset_artifact_version_id is not None:
        assert request.field_dictionary_artifact_version_id is not None
        data = GraphDataVersionSelection(
            dataset_artifact_version_id=request.dataset_artifact_version_id,
            field_dictionary_artifact_version_id=(
                request.field_dictionary_artifact_version_id
            ),
        )
    return GraphInputVersionSelection(
        project_id=request.project_id,
        literature_relations_artifact_version_id=(
            request.literature_relations_artifact_version_id
        ),
        data=data,
    )


def _assemble_candidate(
    request: GraphBuildRequest,
    inputs: PublishedGraphInputs,
) -> GraphArtifactCandidate:
    assembly = _Assembly(inputs)
    _add_literature(assembly, request.scope)
    if request.scope.include_data:
        if inputs.data is None:
            raise GraphAdmissionFailure(
                GraphIntegrityStage.artifact_version,
                GraphRejectionReason.input_version_unknown,
                "input_versions.data",
                "data scope requires the exact Dataset/FieldDictionary input pair",
            )
        _add_data(assembly)
    elif inputs.data is not None:
        raise GraphAdmissionFailure(
            GraphIntegrityStage.capacity_progressive,
            GraphRejectionReason.silent_truncation,
            "scope.include_data",
            "selected data inputs cannot be silently omitted from the Graph",
        )
    if not assembly.nodes or not assembly.edges:
        raise GraphAdmissionFailure(
            GraphIntegrityStage.endpoint,
            GraphRejectionReason.dangling_endpoint,
            "scope",
            "Graph scope must resolve to at least one Evidence-backed edge",
        )

    nodes = tuple(sorted(assembly.nodes.values(), key=lambda item: item.node_id))
    edges = tuple(sorted(assembly.edges.values(), key=lambda item: item.edge_id))
    evidence_uses = tuple(
        sorted(assembly.evidence_uses.values(), key=lambda item: item.evidence_use_id)
    )
    source_snapshots = tuple(
        sorted(assembly.snapshots.values(), key=lambda item: item.source_snapshot_id)
    )
    input_versions = _input_versions(inputs)
    relation_edge_count = sum(item.relation_trace is not None for item in edges)
    counts = GraphIntegrityCounts(
        input_version_count=len(input_versions.versions),
        node_count=len(nodes),
        edge_count=len(edges),
        evidence_use_count=len(evidence_uses),
        source_snapshot_count=len(source_snapshots),
        relation_edge_count=relation_edge_count,
    )
    capacity = request.policies.capacity_policy
    if (
        counts.input_version_count > capacity.max_input_versions
        or counts.node_count > capacity.max_nodes
        or counts.edge_count > capacity.max_edges
        or counts.evidence_use_count > capacity.max_evidence_uses
        or any(
            len(item.evidence_use_ids) > capacity.max_evidence_uses_per_edge
            for item in edges
        )
    ):
        raise GraphAdmissionFailure(
            GraphIntegrityStage.capacity_progressive,
            GraphRejectionReason.size_limit_exceeded,
            "candidate",
            "Graph exceeds the pinned capacity policy; no truncation is allowed",
        )
    report = build_integrity_report(findings=(), counts=counts)
    taxonomy = _taxonomy()
    producer = _producer(request.policies, taxonomy)
    canonical_progressive = build_complete_progressive_input(
        progressive_id=request.progressive.progressive_id,
        literature_relations_artifact_version_id=(
            request.literature_relations_artifact_version_id
        ),
        dataset_artifact_version_id=request.dataset_artifact_version_id,
        field_dictionary_artifact_version_id=(
            request.field_dictionary_artifact_version_id
        ),
        scope=request.scope,
        chunk_size=capacity.max_items_per_chunk,
    )
    payload: dict[str, Any] = {
        "kind": "graph",
        "schema_version": "2.0.0",
        "project_id": request.project_id,
        "input_versions": input_versions,
        "taxonomy": taxonomy,
        "policies": request.policies,
        "scope": request.scope,
        "nodes": nodes,
        "edges": edges,
        "evidence_uses": evidence_uses,
        "source_snapshots": source_snapshots,
        "evidence_ids": tuple(item.evidence_use_id for item in evidence_uses),
        "source_snapshot_ids": tuple(
            item.source_snapshot_id for item in source_snapshots
        ),
        "integrity_report": report,
        "progressive": canonical_progressive,
        "layout_hint": request.layout_hint,
        "producer": producer,
    }
    input_hash = compute_graph_input_hash(payload)
    scientific_hash = compute_graph_scientific_hash(payload)
    layout_hash = compute_graph_layout_hash(payload)
    payload.update(
        {
            "graph_id": f"graph.{scientific_hash.removeprefix('sha256:')[:24]}",
            "input_hash": input_hash,
            "scientific_hash": scientific_hash,
            "layout_hash": layout_hash,
            "report_hash": report.content_hash,
        }
    )
    payload["output_hash"] = compute_graph_output_hash(payload)
    provisional = GraphArtifactCandidate.model_construct(**payload)
    serialized_size = len(
        json.dumps(
            provisional.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    if serialized_size > capacity.max_serialized_bytes:
        raise GraphAdmissionFailure(
            GraphIntegrityStage.capacity_progressive,
            GraphRejectionReason.size_limit_exceeded,
            "candidate",
            "Graph exceeds the pinned serialized-byte capacity",
        )
    try:
        return GraphArtifactCandidate(**payload)
    except ValueError as exc:
        raise GraphAdmissionFailure(
            GraphIntegrityStage.hash_commitment,
            GraphRejectionReason.candidate_hash_mismatch,
            "candidate",
            f"Graph candidate failed final immutable validation: {exc}",
        ) from exc


class GraphPipeline:
    """Read exact published inputs, build one deterministic Graph, and seal it."""

    def __init__(self, reader: VersionedGraphInputReadPort) -> None:
        if not isinstance(reader, VersionedGraphInputReadPort):
            raise TypeError("GraphPipeline requires VersionedGraphInputReadPort")
        self._reader = reader

    def admit_json(self, input_json: str) -> GraphAdmissionResult:
        """Parse a strict request and preserve invalid JSON vs Schema failure."""

        if not isinstance(input_json, str):
            failure = GraphAdmissionFailure(
                GraphIntegrityStage.input_schema,
                GraphRejectionReason.invalid_json,
                "request",
                "Graph build input must be a JSON string",
            )
            report = failed_integrity_report(failure, counts=_empty_counts())
            return GraphAdmissionResult(status=report.status, report=report)
        try:
            request = GraphBuildRequest.model_validate_json(input_json)
        except ValidationError as exc:
            try:
                import json as _json

                _json.loads(input_json)
            except (ValueError, TypeError):
                failure = GraphAdmissionFailure(
                    GraphIntegrityStage.input_schema,
                    GraphRejectionReason.invalid_json,
                    "request",
                    "Graph build request is not valid JSON",
                )
                report = failed_integrity_report(failure, counts=_empty_counts())
            else:
                findings = tuple(
                    GraphIntegrityFinding(
                        stage=GraphIntegrityStage.input_schema,
                        reason=GraphRejectionReason.schema_invalid,
                        priority=100,
                        path="request."
                        + ".".join(str(part) for part in error["loc"]),
                        message=(
                            "Graph build field failed strict validation: "
                            f"{error['type']}"
                        ),
                    )
                    for error in exc.errors(
                        include_url=False,
                        include_context=False,
                        include_input=False,
                    )
                )
                report = build_integrity_report(
                    findings=findings,
                    counts=_empty_counts(),
                )
            return GraphAdmissionResult(status=report.status, report=report)
        return self.admit(request)

    def admit(
        self,
        request: GraphBuildRequest,
        *,
        _authority_minter: Any = None,
    ) -> GraphAdmissionResult:
        """Admit and seal one complete Graph; failures never return candidates."""

        input_count = 1
        if isinstance(request, GraphBuildRequest):
            input_count += int(request.dataset_artifact_version_id is not None) * 2
        failures: list[GraphAdmissionFailure] = []
        try:
            if type(request) is not GraphBuildRequest:
                raise GraphAdmissionFailure(
                    GraphIntegrityStage.input_schema,
                    GraphRejectionReason.schema_invalid,
                    "request",
                    "Graph Pipeline requires the exact GraphBuildRequest model",
                )
            failures.extend(_collect_request_failures(request))
            inputs = self._reader.read(_selection(request))
            failures.extend(_collect_independent_input_failures(request, inputs))
            if failures:
                report = failed_integrity_report(
                    tuple(failures),
                    counts=_empty_counts(input_count),
                )
                return GraphAdmissionResult(status=report.status, report=report)
            candidate = _assemble_candidate(request, inputs)
            if _authority_minter is None:
                raise GraphAdmissionFailure(
                    GraphIntegrityStage.hash_commitment,
                    GraphRejectionReason.admission_commitment_mismatch,
                    "candidate.publication_authority",
                    "Graph publication authority is unavailable",
                )
            stable_input_json = json.dumps(
                request.model_dump(mode="json", exclude_none=True),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            snapshot = build_graph_admission_snapshot(
                candidate,
                input_json=stable_input_json,
            )
            candidate = _authority_minter(
                candidate,
                snapshot,
                public_payload_hash=compute_canonical_payload_hash(
                    candidate.model_dump(mode="json", exclude_none=True)
                ),
            )
            return GraphAdmissionResult(
                status=GraphIntegrityStatus.passed,
                report=candidate.integrity_report,
                candidate=candidate,
            )
        except GraphInputIntegrityError as exc:
            failure = _input_failure(exc)
        except GraphAdmissionFailure as exc:
            failure = exc
        except SecurityProblem as exc:
            failure = _input_failure(
                graph_input_security_error(
                    code=exc.code,
                    status=exc.status,
                    path="input_versions",
                )
            )
        except (TypeError, ValueError) as exc:
            failure = GraphAdmissionFailure(
                GraphIntegrityStage.input_schema,
                GraphRejectionReason.schema_invalid,
                "request",
                f"Graph input cannot satisfy the strict contract: {exc}",
            )
        report = failed_integrity_report(
            (*failures, failure),
            counts=_empty_counts(input_count),
        )
        return GraphAdmissionResult(status=report.status, report=report)


GraphPipeline = _bind_graph_pipeline_authority(GraphPipeline)
del _bind_graph_pipeline_authority


__all__ = [
    "GraphPipeline",
    "build_complete_progressive_input",
    "required_progressive_item_ids",
]
