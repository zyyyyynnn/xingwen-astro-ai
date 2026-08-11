"""Version-pinned Evidence Graph reads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactVersionDetail, EvidenceDetail, SourceSnapshotDetail
from app.schemas.graph_artifact import (
    GraphArtifactCandidate,
    GraphArtifactEdge,
    GraphArtifactVersionReference,
    GraphEdgeType,
    GraphInputRole,
    GraphNodeType,
    GraphRelationTraceBinding,
)
from app.schemas.graph_artifact_api import (
    GraphArtifactRead,
    GraphArtifactVersionContext,
    GraphEdgeRead,
    GraphEvidenceUseRead,
    GraphNodeRead,
)
from app.schemas.literature_artifact_api import LiteratureRelationRead
from app.schemas.literature_relation import LiteratureRelationStatus
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService

_MAX_PAGE_SIZE = 100
_MAX_CONTENT_BYTES = 8 * 1024 * 1024
_ORDERING = "stable_id.asc.v1.0"
_CURSOR_VERSION = 1


@dataclass(frozen=True, slots=True)
class _GraphContext:
    version: ArtifactVersionDetail
    candidate: GraphArtifactCandidate
    version_context: GraphArtifactVersionContext
    snapshots: Mapping[str, SourceSnapshotDetail]
    evidence_by_use: Mapping[str, EvidenceDetail]
    input_versions: Mapping[str, GraphArtifactVersionReference]


class GraphArtifactReadService:
    """Read Graph content without rebuilding it or consulting dynamic latest."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def get_graph(self, *, version_id: str, session_id: str) -> GraphArtifactRead:
        context = self._context(version_id=version_id, session_id=session_id)
        candidate = context.candidate
        return GraphArtifactRead(
            version=context.version_context,
            graph_id=candidate.graph_id,
            project_id=candidate.project_id,
            input_versions=candidate.input_versions,
            taxonomy=candidate.taxonomy,
            policies=candidate.policies,
            scope=candidate.scope,
            integrity_report=candidate.integrity_report,
            progressive=candidate.progressive,
            layout_hint=candidate.layout_hint,
            node_count=len(candidate.nodes),
            edge_count=len(candidate.edges),
            evidence_use_count=len(candidate.evidence_uses),
        )

    def list_nodes(
        self,
        *,
        version_id: str,
        session_id: str,
        node_type: GraphNodeType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[GraphNodeRead, ...], str | None, bool]:
        context = self._context(version_id=version_id, session_id=session_id)
        selected = tuple(
            item
            for item in context.candidate.nodes
            if node_type is None or item.node_type is node_type
        )
        page, next_cursor, has_more = _page(
            selected,
            version_id=context.version.id,
            collection="nodes",
            filters={"node_type": node_type.value if node_type else None},
            cursor=cursor,
            limit=limit,
        )
        return (
            tuple(
                GraphNodeRead(version=context.version_context, node=item)
                for item in page
            ),
            next_cursor,
            has_more,
        )

    def list_edges(
        self,
        *,
        version_id: str,
        session_id: str,
        edge_type: GraphEdgeType | None,
        node_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[GraphEdgeRead, ...], str | None, bool]:
        context = self._context(version_id=version_id, session_id=session_id)
        selected = tuple(
            item
            for item in context.candidate.edges
            if (edge_type is None or item.edge_type is edge_type)
            and (
                node_id is None
                or item.source_node_id == node_id
                or item.target_node_id == node_id
            )
        )
        page, next_cursor, has_more = _page(
            selected,
            version_id=context.version.id,
            collection="edges",
            filters={
                "edge_type": edge_type.value if edge_type else None,
                "node_id": node_id,
            },
            cursor=cursor,
            limit=limit,
        )
        reads = self._edge_reads(context, page, session_id=session_id)
        return reads, next_cursor, has_more

    def get_node(
        self, *, version_id: str, node_id: str, session_id: str
    ) -> GraphNodeRead:
        context = self._context(version_id=version_id, session_id=session_id)
        node = next(
            (item for item in context.candidate.nodes if item.node_id == node_id),
            None,
        )
        if node is None:
            raise _not_found("GRAPH_NODE_NOT_FOUND")
        return GraphNodeRead(version=context.version_context, node=node)

    def get_edge(
        self, *, version_id: str, edge_id: str, session_id: str
    ) -> GraphEdgeRead:
        context = self._context(version_id=version_id, session_id=session_id)
        edge = next(
            (item for item in context.candidate.edges if item.edge_id == edge_id),
            None,
        )
        if edge is None:
            raise _not_found("GRAPH_EDGE_NOT_FOUND")
        return self._edge_reads(context, (edge,), session_id=session_id)[0]

    def _edge_reads(
        self,
        context: _GraphContext,
        edges: Sequence[GraphArtifactEdge],
        *,
        session_id: str,
    ) -> tuple[GraphEdgeRead, ...]:
        if not edges:
            return ()

        relation_requests: dict[str, set[str]] = {}
        for edge in edges:
            if edge.relation_trace is not None:
                relation_requests.setdefault(
                    edge.relation_trace.relation_artifact_version_id, set()
                ).add(edge.relation_trace.relation_id)

        relations_by_version_and_id: dict[
            tuple[str, str], LiteratureRelationRead
        ] = {}
        literature_service = LiteratureArtifactReadService(self._artifacts)
        for rel_version_id, rel_ids in relation_requests.items():
            try:
                rel_map = literature_service.get_relations(
                    version_id=rel_version_id,
                    relation_ids=rel_ids,
                    session_id=session_id,
                )
            except SecurityProblem as exc:
                raise _provenance_problem() from exc
            for rel_id, rel_read in rel_map.items():
                relations_by_version_and_id[(rel_version_id, rel_id)] = rel_read

        result: list[GraphEdgeRead] = []
        for edge in edges:
            uses = tuple(
                GraphEvidenceUseRead(
                    use=use,
                    evidence=context.evidence_by_use[use.evidence_use_id],
                    source_snapshot=context.snapshots[use.source_snapshot_id],
                )
                for use in context.candidate.evidence_uses
                if use.graph_edge_id == edge.edge_id
            )
            if tuple(sorted(item.use.evidence_use_id for item in uses)) != (
                edge.evidence_use_ids
            ):
                raise _provenance_problem()

            relation: LiteratureRelationRead | None = None
            if edge.relation_trace is not None:
                key = (
                    edge.relation_trace.relation_artifact_version_id,
                    edge.relation_trace.relation_id,
                )
                relation = relations_by_version_and_id.get(key)
                if relation is None:
                    raise _provenance_problem()
                _validate_relation_trace_projection(
                    edge.relation_trace,
                    relation,
                    project_id=context.version.project_id,
                    reference=context.input_versions.get(
                        edge.relation_trace.relation_artifact_version_id
                    ),
                )
            result.append(
                GraphEdgeRead(
                    version=context.version_context,
                    edge=edge,
                    evidence=uses,
                    relation=relation,
                )
            )
        return tuple(result)

    def _context(self, *, version_id: str, session_id: str) -> _GraphContext:
        version = self._artifacts.get_version(
            version_id=version_id, session_id=session_id, full_content=True
        )
        try:
            artifact = self._artifacts.get_artifact(
                artifact_id=version.artifact_id, session_id=session_id
            )
            if (
                artifact.kind.value != "graph"
                or artifact.project_id != version.project_id
            ):
                raise _kind_problem()
            content_bytes = len(
                json.dumps(
                    version.content,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            if content_bytes > _MAX_CONTENT_BYTES:
                raise _capacity_problem()
            candidate = GraphArtifactCandidate.model_validate_json(
                json.dumps(
                    version.content,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        except SecurityProblem:
            raise
        except (ValidationError, ValueError, TypeError) as exc:
            raise _schema_problem() from exc

        if (
            version.schema_version != candidate.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.input_hash != candidate.input_hash
            or candidate.project_id != version.project_id
            or set(version.source_snapshot_ids)
            != {
                item.persisted_source_snapshot_id for item in candidate.source_snapshots
            }
            or len(version.evidence_ids) != len(candidate.evidence_ids)
        ):
            raise _provenance_problem()
        _validate_runtime_producer(version, candidate)

        snapshots = {item.id: item for item in version.source_snapshots}
        if set(snapshots) != set(version.source_snapshot_ids):
            raise _provenance_problem()
        snapshot_by_pipeline: dict[str, SourceSnapshotDetail] = {}
        for reference in candidate.source_snapshots:
            persisted = snapshots.get(reference.persisted_source_snapshot_id)
            if (
                persisted is None
                or persisted.source_id != reference.source_id
                or (
                    persisted.source_version_or_etag
                    or persisted.cache_version
                    or persisted.content_hash
                )
                != reference.source_version
                or persisted.content_hash != reference.content_hash
                or version.project_id != reference.project_id
            ):
                raise _provenance_problem()
            snapshot_by_pipeline[reference.source_snapshot_id] = persisted
        if set(snapshot_by_pipeline) != set(candidate.source_snapshot_ids):
            raise _provenance_problem()

        evidence_rows = {item.id: item for item in version.evidence}
        if set(evidence_rows) != set(version.evidence_ids):
            raise _provenance_problem()
        evidence_rows_by_use: dict[str, EvidenceDetail] = {}
        for row in version.evidence:
            use_id = row.locator.get("graph_evidence_use_id")
            if not isinstance(use_id, str) or use_id in evidence_rows_by_use:
                raise _provenance_problem()
            evidence_rows_by_use[use_id] = row
        evidence_by_use: dict[str, EvidenceDetail] = {}
        for use in candidate.evidence_uses:
            row = evidence_rows_by_use.get(use.evidence_use_id)
            snapshot = snapshot_by_pipeline.get(use.source_snapshot_id)
            if (
                row is None
                or snapshot is None
                or row.artifact_version_id != version.id
                or row.target_type != "graph_edge"
                or row.target_id != use.graph_edge_id
                or row.evidence_type != use.evidence_type.value
                or row.source_snapshot_id != snapshot.id
                or row.locator.get("graph_evidence_use_id") != use.evidence_use_id
                or row.locator.get("upstream_evidence_id") != use.upstream_evidence_id
                or row.locator.get("upstream_artifact_version_id")
                != use.upstream_artifact_version_id
                or row.locator.get("upstream_target_type") != use.upstream_target_type
                or row.locator.get("upstream_target_id") != use.upstream_target_id
                or row.locator.get("upstream_evidence_hash")
                != use.upstream_evidence_hash
                or row.extraction_method != "graph_admission"
            ):
                raise _provenance_problem()
            evidence_by_use[use.evidence_use_id] = row
        if set(evidence_by_use) != set(candidate.evidence_ids):
            raise _provenance_problem()

        input_versions, binding_versions = self._resolve_input_versions(
            candidate, version, session_id=session_id
        )
        _validate_input_version_closure(
            candidate, input_versions, binding_versions=binding_versions
        )

        version_context = GraphArtifactVersionContext(
            artifact_version_id=version.id,
            artifact_id=version.artifact_id,
            project_id=version.project_id,
            version_number=version.version_number,
            supersedes_version_id=version.supersedes_version_id,
            source_mode=version.source_mode,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            scientific_hash=candidate.scientific_hash,
            layout_hash=candidate.layout_hash,
            report_hash=candidate.report_hash,
            output_hash=candidate.output_hash,
            created_at=version.created_at,
            producer_execution=version.producer_execution,
        )
        return _GraphContext(
            version=version,
            candidate=candidate,
            version_context=version_context,
            snapshots=snapshot_by_pipeline,
            evidence_by_use=evidence_by_use,
            input_versions=input_versions,
        )

    def _resolve_input_versions(
        self,
        candidate: GraphArtifactCandidate,
        version: ArtifactVersionDetail,
        *,
        session_id: str,
    ) -> tuple[
        Mapping[str, GraphArtifactVersionReference],
        frozenset[str],
    ]:
        """Re-close every frozen Graph input pin against persisted storage.

        The Graph candidate only carries a copy of its upstream
        ``GraphArtifactVersionReference`` facts. A read must therefore prove
        that each referenced ArtifactVersion still exists in the same Project
        and still matches every frozen pin, otherwise the projection would
        silently serve a Graph whose declared inputs have drifted, been
        superseded, or been deleted.
        """

        resolved: dict[str, GraphArtifactVersionReference] = {}
        bindable: set[str] = set()
        for reference in candidate.input_versions.versions:
            if reference.project_id != version.project_id:
                raise _provenance_problem()
            try:
                upstream = self._artifacts.get_version(
                    version_id=reference.artifact_version_id,
                    session_id=session_id,
                    full_content=True,
                )
                artifact = self._artifacts.get_artifact(
                    artifact_id=upstream.artifact_id, session_id=session_id
                )
            except SecurityProblem as exc:
                raise _provenance_problem() from exc
            runtime = upstream.producer_execution
            if (
                upstream.id != reference.artifact_version_id
                or upstream.artifact_id != reference.artifact_id
                or upstream.project_id != reference.project_id
                or artifact.id != reference.artifact_id
                or artifact.project_id != reference.project_id
                or artifact.kind.value != reference.kind
                or upstream.version_number != reference.version_number
                or upstream.schema_version != reference.schema_version
                or upstream.content_hash != reference.content_hash
                or upstream.content_hash
                != compute_canonical_payload_hash(upstream.content)
                or upstream.input_hash != reference.input_hash
                or upstream.source_mode.value != reference.source_mode
                or runtime.producer.type != reference.producer_type
                or runtime.producer.name != reference.producer_name
                or runtime.producer.version != reference.producer_version
                or runtime.parameters_hash != reference.parameters_hash
                or runtime.input_hash != reference.input_hash
                or runtime.output_hash != reference.content_hash
                or runtime.status != "completed"
                or runtime.run_id != upstream.created_by_run_id
                or upstream.producer != runtime.producer
            ):
                raise _provenance_problem()
            if _upstream_output_hash(upstream.content) != reference.output_hash:
                raise _provenance_problem()
            resolved[reference.artifact_version_id] = reference
            bindable.add(reference.artifact_version_id)
            bindable.update(
                _transitive_binding_versions(reference, upstream.content)
            )
        if len(resolved) != len(candidate.input_versions.versions):
            raise _provenance_problem()
        return resolved, frozenset(bindable)


def _validate_runtime_producer(
    version: ArtifactVersionDetail, candidate: GraphArtifactCandidate
) -> None:
    runtime = version.producer_execution
    producer = candidate.producer
    if (
        version.producer != runtime.producer
        or runtime.run_id != version.created_by_run_id
        or runtime.producer.type != producer.producer_type
        or runtime.producer.name != producer.producer_name
        or runtime.producer.version != producer.producer_version
        or runtime.parameters_hash != producer.parameters_hash
        or runtime.input_hash != candidate.input_hash
        or runtime.output_hash != version.content_hash
        or runtime.status != "completed"
    ):
        raise _schema_problem()


def _transitive_binding_versions(
    reference: GraphArtifactVersionReference,
    content: Mapping[str, Any],
) -> frozenset[str]:
    """Collect the upstream-declared versions a Graph node may legally bind.

    Binds Claim nodes to the LiteratureClaims version and Paper nodes to
    the PaperSummary version, both of which the pinned LiteratureRelations
    ArtifactVersion itself declares. Those declarations are read from the
    resolved upstream content, never from the Graph body, so a tampered Graph
    cannot widen its own closure.
    """

    if reference.role is not GraphInputRole.literature_relations:
        return frozenset()
    declared = content.get("input_versions")
    if not isinstance(declared, Mapping):
        raise _provenance_problem()
    claim_versions = declared.get("claim_artifact_versions")
    if not isinstance(claim_versions, (list, tuple)):
        raise _provenance_problem()
    result: set[str] = set()
    for item in claim_versions:
        if not isinstance(item, Mapping):
            raise _provenance_problem()
        version_id = item.get("artifact_version_id")
        if not isinstance(version_id, str):
            raise _provenance_problem()
        result.add(version_id)
        summaries = item.get("paper_summary_artifact_version_ids") or ()
        if not isinstance(summaries, (list, tuple)):
            raise _provenance_problem()
        for summary_id in summaries:
            if not isinstance(summary_id, str):
                raise _provenance_problem()
            result.add(summary_id)
    return frozenset(result)


def _upstream_output_hash(content: Mapping[str, Any]) -> str | None:
    """Read the upstream candidate's own domain output hash from its content."""

    value = content.get("output_hash")
    return value if isinstance(value, str) else None


def _validate_input_version_closure(
    candidate: GraphArtifactCandidate,
    input_versions: Mapping[str, GraphArtifactVersionReference],
    *,
    binding_versions: frozenset[str],
) -> None:
    """Force every version-bearing Graph reference into the resolved registry.

    ``_resolve_input_versions`` proves the declared pins are still true. This
    check proves the Graph body cannot reference an ArtifactVersion outside
    that proven set, so no node binding, Evidence-use or Relation trace can
    escape the closure the Graph committed to.
    """

    registry = set(input_versions)
    for node in candidate.nodes:
        if any(
            binding.artifact_version_id not in binding_versions
            for binding in node.version_bindings
        ):
            raise _provenance_problem()
    if any(
        use.upstream_artifact_version_id not in registry
        for use in candidate.evidence_uses
    ):
        raise _provenance_problem()
    literature = tuple(
        reference
        for reference in input_versions.values()
        if reference.role is GraphInputRole.literature_relations
    )
    if len(literature) != 1:
        raise _provenance_problem()
    for edge in candidate.edges:
        binding = edge.relation_trace
        if binding is None:
            continue
        if binding.relation_artifact_version_id != literature[0].artifact_version_id:
            raise _provenance_problem()


def _validate_relation_trace_projection(
    binding: GraphRelationTraceBinding,
    relation: LiteratureRelationRead,
    *,
    project_id: str,
    reference: GraphArtifactVersionReference | None,
) -> None:
    """Bind the projected Relation/Trace to the Graph edge's declared closure.

    The Graph edge only stores identifiers. A Literature edge must therefore
    prove that the separately read ``LiteratureRelationRead`` is the exact
    accepted Relation, Trace and direction the Graph committed to, in the same
    project, and that the version it was read from is the exact frozen input
    pin. Any divergence is a dangling or cross-scope reference, never a
    scientific fact this API may repair.
    """

    candidate = relation.relation
    trace = relation.reasoning_trace
    if reference is None or reference.role is not GraphInputRole.literature_relations:
        raise _provenance_problem()
    projected = relation.version
    if (
        projected.artifact_version_id != reference.artifact_version_id
        or projected.artifact_id != reference.artifact_id
        or projected.project_id != reference.project_id
        or projected.version_number != reference.version_number
        or projected.schema_version != reference.schema_version
        or projected.content_hash != reference.content_hash
        or projected.input_hash != reference.input_hash
        or projected.output_hash != reference.output_hash
        or projected.source_mode.value != reference.source_mode
        or projected.producer_execution.producer.type != reference.producer_type
        or projected.producer_execution.producer.name != reference.producer_name
        or projected.producer_execution.producer.version != reference.producer_version
        or projected.producer_execution.parameters_hash != reference.parameters_hash
    ):
        raise _provenance_problem()
    if (
        relation.version.artifact_version_id != binding.relation_artifact_version_id
        or relation.version.project_id != project_id
        or candidate.relation_id != binding.relation_id
        or candidate.status is not LiteratureRelationStatus.accepted
        or binding.relation_status != LiteratureRelationStatus.accepted.value
        or candidate.relation_type.value != binding.relation_type.value
        or candidate.source_claim_id != binding.source_claim_id
        or candidate.target_claim_id != binding.target_claim_id
        or candidate.reasoning_trace_id != binding.reasoning_trace_id
        or relation.graph_eligible is not True
    ):
        raise _provenance_problem()
    if (
        trace is None
        or trace.trace_id != binding.reasoning_trace_id
        or trace.relation_id != binding.relation_id
        or trace.relation_status is not LiteratureRelationStatus.accepted
        or trace.premise_claim_ids != binding.premise_claim_ids
    ):
        raise _provenance_problem()
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
    if trace_evidence_ids != binding.trace_evidence_ids:
        raise _provenance_problem()
    if (
        relation.source_claim is None
        or relation.target_claim is None
        or relation.source_claim.claim.claim_id != binding.source_claim_id
        or relation.target_claim.claim.claim_id != binding.target_claim_id
    ):
        raise _provenance_problem()


def _page(
    items: tuple[Any, ...],
    *,
    version_id: str,
    collection: str,
    filters: Mapping[str, Any],
    cursor: str | None,
    limit: int,
) -> tuple[tuple[Any, ...], str | None, bool]:
    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise _problem(
            422,
            "SCHEMA_VALIDATION_FAILED",
            "Request validation failed",
            "limit must be between 1 and 100",
        )
    ordered = tuple(
        sorted(
            items,
            key=lambda item: item.node_id if collection == "nodes" else item.edge_id,
        )
    )
    start = 0
    if cursor:
        last_id = _decode_cursor(
            cursor,
            version_id=version_id,
            collection=collection,
            filters=filters,
        )
        keys = tuple(
            item.node_id if collection == "nodes" else item.edge_id for item in ordered
        )
        try:
            start = keys.index(last_id) + 1
        except ValueError as exc:
            raise _invalid_cursor() from exc
    selected = ordered[start : start + limit]
    has_more = start + limit < len(ordered)
    next_cursor = (
        _encode_cursor(
            version_id=version_id,
            collection=collection,
            filters=filters,
            last_id=selected[-1].node_id
            if collection == "nodes"
            else selected[-1].edge_id,
        )
        if selected and has_more
        else None
    )
    return selected, next_cursor, has_more


def _cursor_signature(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {key: value for key, value in payload.items() if key != "signature"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    key = settings.CURSOR_SIGNING_KEY.get_secret_value().encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _encode_cursor(
    *,
    version_id: str,
    collection: str,
    filters: Mapping[str, Any],
    last_id: str,
) -> str:
    payload: dict[str, Any] = {
        "v": _CURSOR_VERSION,
        "version_id": version_id,
        "collection": collection,
        "ordering": _ORDERING,
        "filters": dict(filters),
        "last_id": last_id,
    }
    payload["signature"] = _cursor_signature(payload)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(
    value: str,
    *,
    version_id: str,
    collection: str,
    filters: Mapping[str, Any],
) -> str:
    try:
        if not value or len(value) > 4096:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        raw_bytes = base64.b64decode(padded, altchars=b"-_", validate=True)
        payload = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        if set(payload) != {
            "v",
            "version_id",
            "collection",
            "ordering",
            "filters",
            "last_id",
            "signature",
        }:
            raise ValueError
        if (
            payload["v"] != _CURSOR_VERSION
            or payload["version_id"] != version_id
            or payload["collection"] != collection
            or payload["ordering"] != _ORDERING
            or payload["filters"] != dict(filters)
            or not isinstance(payload["last_id"], str)
            or not payload["last_id"]
            or not isinstance(payload["signature"], str)
        ):
            raise ValueError
        expected_sig = _cursor_signature(payload)
        if not hmac.compare_digest(payload["signature"], expected_sig):
            raise ValueError
        return payload["last_id"]
    except (
        ValueError,
        TypeError,
        binascii.Error,
        json.JSONDecodeError,
        UnicodeError,
    ) as exc:
        raise _invalid_cursor() from exc


def _schema_problem() -> SecurityProblem:
    return _problem(
        422,
        "GRAPH_SCHEMA_INVALID",
        "Graph Schema invalid",
        "The Graph ArtifactVersion content is not a valid Graph candidate",
    )


def _provenance_problem() -> SecurityProblem:
    return _problem(
        403,
        "PROVENANCE_SCOPE_VIOLATION",
        "Provenance access denied",
        "The Graph provenance graph is incomplete or outside the authorized project",
    )


def _kind_problem() -> SecurityProblem:
    return _problem(
        409,
        "ARTIFACT_KIND_MISMATCH",
        "Artifact kind mismatch",
        "The ArtifactVersion is not a graph",
    )


def _capacity_problem() -> SecurityProblem:
    return _problem(
        413,
        "GRAPH_ARTIFACT_SIZE_LIMIT_EXCEEDED",
        "Graph Artifact size limit exceeded",
        "The Graph ArtifactVersion exceeds the read size limit",
    )


def _invalid_cursor() -> SecurityProblem:
    return _problem(
        400,
        "INVALID_CURSOR",
        "Invalid cursor",
        "The cursor is invalid or outside this Graph query scope",
    )


def _not_found(code: str) -> SecurityProblem:
    return _problem(
        404,
        code,
        "Graph resource not found",
        "The requested Graph resource was not found",
    )


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


__all__ = ["GraphArtifactReadService"]
