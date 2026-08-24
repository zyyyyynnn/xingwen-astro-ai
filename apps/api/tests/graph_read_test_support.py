"""A fully published Graph plus its readable upstream envelope.

The existing pipeline fixture only publishes the LiteratureRelations
*input* to the Graph build port; it never exposes that Relation through the
generic Artifact read port. Graph read must project ``GraphEdgeRead.relation`` for
every Literature edge, so this module republishes the same real relation admission
under one persisted UUID Project and registers the Graph, Relation, Claim and
PaperSummary ArtifactVersions in a single read port.

No unvalidated dictionary is injected: the LiteratureRelations payload is
produced by the real relation pipeline and the Graph payload by the real graph
pipeline. Only storage identities are fixture-owned.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.services.public_presentation import build_artifact_presentation
from app.schemas.enums import GraphEdgeType
from app.schemas.graph_artifact import GraphArtifactCandidate, GraphBuildScope
from app.schemas.graph_artifact import GraphStructuralEdgeRequest
from app.schemas.literature_relation import (
    LiteratureRelationsCandidate,
    LiteratureRelationStatus,
    compute_literature_relations_output_hash,
)
from graph_pipeline_test_support import (
    LiteratureGraphFixture,
    ExactPublishedGraphInputReader,
    _published_literature_version,
    _uuid_ready_claim_inputs,
    stable_uuid,
)
from literature_artifact_test_support import (
    FixtureArtifactReads,
    _artifact,
    _claim_version,
    _relation_version,
    _summary_version,
)
from services.graph_pipeline.pipeline import GraphPipeline
from services.graph_pipeline.ports import (
    GraphInputVersionSelection,
    PublishedGraphInputs,
)
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim_benchmark_cases import _build_claim_fixture
from services.paper_pipeline.relation import LiteratureClaimsArtifactVersionInput
from services.paper_pipeline.relation_benchmark_cases import (
    _REPLAY_MODEL_NAME,
    _REPLAY_PARAMETERS,
    _relation_fixture,
    _response,
)

NOW = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)
PROJECT_ID = stable_uuid("project:graph-real-relation")
RELATION_VERSION_ID = stable_uuid("artifact-version:literature-relations:accepted")
GRAPH_VERSION_ID = stable_uuid("graph-read:graph-version")
GRAPH_ARTIFACT_ID = stable_uuid("graph-read:graph-artifact")
GRAPH_RUN_ID = stable_uuid("graph-read:run")
SECOND_GRAPH_VERSION_ID = stable_uuid("graph-read:graph-version:2")
SECOND_GRAPH_ARTIFACT_ID = stable_uuid("graph-read:graph-artifact:2")


@dataclass(frozen=True, slots=True)
class GraphReadFixture:
    """One Graph ArtifactVersion with its complete readable upstream closure."""

    artifacts: FixtureArtifactReads
    candidate: GraphArtifactCandidate
    graph_version_id: str
    graph_artifact_id: str
    relation_version_id: str
    literature_edge_id: str
    structural_edge_id: str
    relation_id: str
    second_graph_version_id: str

    @property
    def graph_version(self) -> ArtifactVersionDetail:
        return self.artifacts.versions[self.graph_version_id]

    @property
    def relation_version(self) -> ArtifactVersionDetail:
        return self.artifacts.versions[self.relation_version_id]

    @property
    def second_graph_version(self) -> ArtifactVersionDetail:
        return self.artifacts.versions[self.second_graph_version_id]


def build_graph_read_fixture() -> GraphReadFixture:
    """Publish one real Graph and every ArtifactVersion it references."""

    benchmark = load_frozen_benchmark()
    claims = _project_bound_claim_inputs(benchmark)
    relation = next(
        item
        for item in benchmark.relations
        if item.status.value == LiteratureRelationStatus.accepted.value
    )
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == relation.reasoning_trace_id
    )
    relation_fixture = _relation_fixture(
        benchmark=benchmark,
        relation=relation,
        trace=trace,
        claims=claims,
    )
    admission = relation_fixture.pipeline.admit(
        literature_claim_artifact_version_ids=relation_fixture.version_ids,
        literature_claim_versions=relation_fixture.versions,
        project_id=PROJECT_ID,
        model_response=_response(relation_fixture.payload),
        model_name=_REPLAY_MODEL_NAME,
        parameters=_REPLAY_PARAMETERS,
        confidence_assessments={
            relation_fixture.confidence.assessment_id: relation_fixture.confidence
        },
    )
    relations_candidate = admission.publisher_candidate
    if relations_candidate is None:
        raise AssertionError("real relation replay did not publish a candidate")
    accepted = tuple(
        item
        for item in relations_candidate.relations
        if item.status is LiteratureRelationStatus.accepted
    )
    if len(accepted) != 1:
        raise AssertionError("real relation fixture accepted Relation count drifted")
    accepted_relation = accepted[0]

    published = _published_literature_version(
        candidate=relations_candidate,
        project_id=PROJECT_ID,
        relation_version_id=RELATION_VERSION_ID,
        reverse_bindings=False,
    )
    graph_fixture = _graph_fixture(
        published=published,
        relations_candidate=relations_candidate,
        accepted_relation_id=accepted_relation.relation_id,
    )
    result = GraphPipeline(graph_fixture.reader).admit(graph_fixture.request())
    graph_candidate = result.candidate
    if graph_candidate is None:
        raise AssertionError("real graph replay did not publish a Graph candidate")

    versions: dict[str, ArtifactVersionDetail] = {}
    artifacts: dict[str, ResearchArtifactDetail] = {}
    for version_id, summary in _summary_contents(benchmark).items():
        _register(
            versions,
            artifacts,
            _rebound(_summary_version(version_id, summary)),
            "paper_summary",
        )
    for item in claims.values():
        _register(
            versions,
            artifacts,
            _rebound(
                _claim_version(item.version.artifact_version_id, item.version.content)
            ),
            "literature_claims",
        )
    _register(
        versions,
        artifacts,
        _rebound(
            _relation_version(RELATION_VERSION_ID, relations_candidate),
            artifact_id=published.pins.artifact_id,
        ),
        "literature_relations",
    )
    _register(
        versions,
        artifacts,
        _graph_version(graph_candidate),
        "graph",
    )
    # A second, independently identified Graph ArtifactVersion carrying the same
    # admitted content. Cursor scope must not be reusable across the two.
    _register(
        versions,
        artifacts,
        _graph_version(
            graph_candidate,
            version_id=SECOND_GRAPH_VERSION_ID,
            artifact_id=SECOND_GRAPH_ARTIFACT_ID,
        ),
        "graph",
    )

    literature_edges = tuple(
        item for item in graph_candidate.edges if item.relation_trace is not None
    )
    structural_edges = tuple(
        item for item in graph_candidate.edges if item.relation_trace is None
    )
    if len(literature_edges) != 1 or not structural_edges:
        raise AssertionError("real graph fixture edge taxonomy drifted")
    return GraphReadFixture(
        artifacts=FixtureArtifactReads(versions=versions, artifacts=artifacts),
        candidate=graph_candidate,
        graph_version_id=GRAPH_VERSION_ID,
        graph_artifact_id=GRAPH_ARTIFACT_ID,
        relation_version_id=RELATION_VERSION_ID,
        literature_edge_id=literature_edges[0].edge_id,
        structural_edge_id=structural_edges[0].edge_id,
        relation_id=accepted_relation.relation_id,
        second_graph_version_id=SECOND_GRAPH_VERSION_ID,
    )


def _project_bound_claim_inputs(benchmark: object) -> dict[str, object]:
    """Rebind the UUID-ready claim inputs onto the persisted UUID Project."""

    result: dict[str, object] = {}
    for key, item in _uuid_ready_claim_inputs(benchmark).items():
        version = item.version
        result[key] = replace(
            item,
            version=LiteratureClaimsArtifactVersionInput(
                artifact_version_id=version.artifact_version_id,
                schema_version=version.schema_version,
                content_hash=version.content_hash,
                project_id=PROJECT_ID,
                content=version.content,
            ),
        )
    return result


def _summary_contents(benchmark: object) -> dict[str, object]:
    """Map every rebound PaperSummary ArtifactVersion UUID to its content."""

    result: dict[str, object] = {}
    for claim in benchmark.claims:  # type: ignore[attr-defined]
        fixture = _build_claim_fixture(benchmark, claim)
        for old_version_id, summary_input in fixture["versions"].items():
            version_id = stable_uuid(f"artifact-version:paper-summary:{old_version_id}")
            result[version_id] = summary_input.content
    return result


def _graph_fixture(
    *,
    published: object,
    relations_candidate: LiteratureRelationsCandidate,
    accepted_relation_id: str,
) -> LiteratureGraphFixture:
    """Wrap the republished relation version in the exact graph read port."""

    relation = next(
        item
        for item in relations_candidate.relations
        if item.relation_id == accepted_relation_id
    )
    claims = {item.claim_id: item for item in relations_candidate.claims}
    source_claim = claims[relation.source_claim_id]
    target_claim = claims[relation.target_claim_id]
    selection = GraphInputVersionSelection(
        project_id=PROJECT_ID,
        literature_relations_artifact_version_id=RELATION_VERSION_ID,
    )
    inputs = PublishedGraphInputs(
        selection=selection,
        literature_relations=published,  # type: ignore[arg-type]
    )
    scope = GraphBuildScope(
        literature_paper_ids=tuple(
            sorted({source_claim.paper_id, target_claim.paper_id})
        ),
        literature_claim_ids=tuple(
            sorted({source_claim.claim_id, target_claim.claim_id})
        ),
        accepted_relation_ids=(relation.relation_id,),
        structural_edges=(
            GraphStructuralEdgeRequest(
                edge_type=GraphEdgeType.supports_finding,
                source_paper_id=source_claim.paper_id,
                target_claim_id=source_claim.claim_id,
            ),
        ),
    )
    return LiteratureGraphFixture(
        inputs=inputs,
        reader=ExactPublishedGraphInputReader(inputs),
        scope=scope,
        relation_id=relation.relation_id,
        source_claim_id=source_claim.claim_id,
        target_claim_id=target_claim.claim_id,
        source_paper_id=source_claim.paper_id,
        target_paper_id=target_claim.paper_id,
    )


def _graph_version(
    candidate: GraphArtifactCandidate,
    *,
    version_id: str = GRAPH_VERSION_ID,
    artifact_id: str = GRAPH_ARTIFACT_ID,
) -> ArtifactVersionDetail:
    """Persist one admitted Graph candidate as an immutable ArtifactVersion."""

    persisted_snapshots = {
        item.source_snapshot_id: SourceSnapshotDetail(
            id=item.persisted_source_snapshot_id,
            source_id=item.source_id,
            source_type="benchmark",
            retrieved_at=NOW,
            query={"graph_fixture": item.source_snapshot_id},
            query_hash=compute_canonical_payload_hash(
                {"graph_fixture": item.source_snapshot_id}
            ),
            source_version_or_etag=item.source_version,
            content_hash=item.content_hash,
            license_note="Frozen Graph benchmark provenance",
            request_metadata={},
        )
        for item in candidate.source_snapshots
    }
    evidence = tuple(
        EvidenceDetail(
            id=stable_uuid(f"graph-read:evidence:{version_id}:{use.evidence_use_id}"),
            artifact_version_id=version_id,
            target_type="graph_edge",
            target_id=use.graph_edge_id,
            evidence_type=use.evidence_type.value,
            source_snapshot_id=persisted_snapshots[use.source_snapshot_id].id,
            locator={
                "graph_evidence_use_id": use.evidence_use_id,
                "upstream_artifact_version_id": use.upstream_artifact_version_id,
                "upstream_evidence_id": use.upstream_evidence_id,
                "upstream_target_type": use.upstream_target_type,
                "upstream_target_id": use.upstream_target_id,
                "upstream_evidence_hash": use.upstream_evidence_hash,
            },
            extraction_method="graph_admission",
            confidence=1.0,
            created_at=NOW,
        )
        for use in candidate.evidence_uses
    )
    producer = ProducerReference(
        type=candidate.producer.producer_type,
        name=candidate.producer.producer_name,
        version=candidate.producer.producer_version,
        parameters_hash=candidate.producer.parameters_hash,
    )
    content = candidate.model_dump(mode="json", exclude_none=True)
    content_hash = compute_canonical_payload_hash(content)
    return ArtifactVersionDetail(
        id=version_id,
        artifact_id=artifact_id,
        project_id=candidate.project_id,
        created_by_run_id=GRAPH_RUN_ID,
        version_number=1,
        schema_version=candidate.schema_version,
        content=content,
        presentation=build_artifact_presentation(ArtifactKind.graph, content, evidence),
        content_hash=content_hash,
        input_hash=candidate.input_hash,
        source_mode="fixture",
        producer=producer,
        source_snapshot_ids=tuple(
            item.persisted_source_snapshot_id for item in candidate.source_snapshots
        ),
        evidence_ids=tuple(item.id for item in evidence),
        supersedes_version_id=None,
        created_at=NOW,
        producer_execution=ProducerExecutionDetail(
            id=stable_uuid(f"graph-read:producer:{version_id}"),
            run_id=GRAPH_RUN_ID,
            step_key="building_graph",
            step_attempt_id=stable_uuid("graph-read:attempt"),
            producer=producer,
            parameters={},
            parameters_hash=candidate.producer.parameters_hash,
            input_hash=candidate.input_hash,
            output_hash=content_hash,
            status="completed",
            started_at=NOW,
            finished_at=NOW,
            latency_ms=1,
        ),
        source_snapshots=tuple(persisted_snapshots.values()),
        evidence=evidence,
    )


def _rebound(
    version: ArtifactVersionDetail, *, artifact_id: str | None = None
) -> ArtifactVersionDetail:
    """Move one literature ArtifactVersion onto the persisted UUID Project."""

    update: dict[str, str] = {"project_id": PROJECT_ID}
    if artifact_id is not None:
        update["artifact_id"] = artifact_id
    return version.model_copy(update=update)


def _register(
    versions: dict[str, ArtifactVersionDetail],
    artifacts: dict[str, ResearchArtifactDetail],
    version: ArtifactVersionDetail,
    kind: str,
) -> None:
    versions[version.id] = version
    artifacts[version.artifact_id] = _artifact(version, kind)


def build_multi_relation_graph_read_fixture() -> GraphReadFixture:
    """Publish a real Graph ArtifactVersion containing at least 2 accepted literature edges from 1 LiteratureRelations version."""

    benchmark = load_frozen_benchmark()
    claims = _project_bound_claim_inputs(benchmark)
    relation = next(
        item
        for item in benchmark.relations
        if item.status.value == LiteratureRelationStatus.accepted.value
    )
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == relation.reasoning_trace_id
    )
    relation_fixture = _relation_fixture(
        benchmark=benchmark,
        relation=relation,
        trace=trace,
        claims=claims,
    )
    admission = relation_fixture.pipeline.admit(
        literature_claim_artifact_version_ids=relation_fixture.version_ids,
        literature_claim_versions=relation_fixture.versions,
        project_id=PROJECT_ID,
        model_response=_response(relation_fixture.payload),
        model_name=_REPLAY_MODEL_NAME,
        parameters=_REPLAY_PARAMETERS,
        confidence_assessments={
            relation_fixture.confidence.assessment_id: relation_fixture.confidence
        },
    )
    relations_candidate = admission.publisher_candidate
    if relations_candidate is None:
        raise AssertionError("real relation replay did not publish a candidate")

    r1 = relations_candidate.relations[0]
    t1 = relations_candidate.reasoning_traces[0]

    second_relation_id = "relation.second_accepted"
    second_trace_id = "trace.second_accepted"

    ev_refs_extra = tuple(
        ref.model_copy(update={"relation_id": second_relation_id})
        for ref in relations_candidate.evidence_references
    )
    r2 = r1.model_copy(
        update={
            "relation_id": second_relation_id,
            "reasoning_trace_id": second_trace_id,
        }
    )
    t2 = t1.model_copy(
        update={
            "trace_id": second_trace_id,
            "relation_id": second_relation_id,
        }
    )
    status_counts = relations_candidate.status_counts.model_copy(update={"accepted": 2})
    rc_multi = relations_candidate.model_copy(
        update={
            "relations": (r1, r2),
            "reasoning_traces": (t1, t2),
            "evidence_references": relations_candidate.evidence_references
            + ev_refs_extra,
            "status_counts": status_counts,
        }
    )
    out_hash = compute_literature_relations_output_hash(rc_multi)
    producer = rc_multi.producer.model_copy(update={"output_hash": out_hash})
    rc_multi = rc_multi.model_copy(
        update={"output_hash": out_hash, "producer": producer}
    )
    rc_multi = LiteratureRelationsCandidate.model_validate(
        rc_multi.model_dump(mode="json", exclude_none=True)
    )

    published = _published_literature_version(
        candidate=rc_multi,
        project_id=PROJECT_ID,
        relation_version_id=RELATION_VERSION_ID,
        reverse_bindings=False,
    )

    claims_map = {item.claim_id: item for item in rc_multi.claims}
    scope = GraphBuildScope(
        literature_paper_ids=tuple(
            sorted(
                {
                    claims_map[r1.source_claim_id].paper_id,
                    claims_map[r1.target_claim_id].paper_id,
                }
            )
        ),
        literature_claim_ids=tuple(sorted({r1.source_claim_id, r1.target_claim_id})),
        accepted_relation_ids=(r1.relation_id, second_relation_id),
        structural_edges=(
            GraphStructuralEdgeRequest(
                edge_type=GraphEdgeType.supports_finding,
                source_paper_id=claims_map[r1.source_claim_id].paper_id,
                target_claim_id=r1.source_claim_id,
            ),
        ),
    )
    selection = GraphInputVersionSelection(
        project_id=PROJECT_ID,
        literature_relations_artifact_version_id=RELATION_VERSION_ID,
    )
    inputs = PublishedGraphInputs(
        selection=selection,
        literature_relations=published,
    )
    reader = ExactPublishedGraphInputReader(inputs)
    req = LiteratureGraphFixture(
        inputs=inputs,
        reader=reader,
        scope=scope,
        relation_id=r1.relation_id,
        source_claim_id="",
        target_claim_id="",
        source_paper_id="",
        target_paper_id="",
    ).request()
    graph_candidate = GraphPipeline(reader).admit(req).candidate
    if graph_candidate is None:
        raise AssertionError("real graph replay did not publish a Graph candidate")

    literature_edges = tuple(
        item for item in graph_candidate.edges if item.relation_trace is not None
    )
    if len(literature_edges) < 2:
        raise AssertionError(
            "multi-relation graph fixture expected at least 2 literature edges"
        )

    versions: dict[str, ArtifactVersionDetail] = {}
    artifacts: dict[str, ResearchArtifactDetail] = {}
    for version_id, summary in _summary_contents(benchmark).items():
        _register(
            versions,
            artifacts,
            _rebound(_summary_version(version_id, summary)),
            "paper_summary",
        )
    for item in claims.values():
        _register(
            versions,
            artifacts,
            _rebound(
                _claim_version(item.version.artifact_version_id, item.version.content)
            ),
            "literature_claims",
        )
    _register(
        versions,
        artifacts,
        _rebound(
            _relation_version(RELATION_VERSION_ID, rc_multi),
            artifact_id=published.pins.artifact_id,
        ),
        "literature_relations",
    )
    _register(
        versions,
        artifacts,
        _graph_version(graph_candidate),
        "graph",
    )
    _register(
        versions,
        artifacts,
        _graph_version(
            graph_candidate,
            version_id=SECOND_GRAPH_VERSION_ID,
            artifact_id=SECOND_GRAPH_ARTIFACT_ID,
        ),
        "graph",
    )

    structural_edges = tuple(
        item for item in graph_candidate.edges if item.relation_trace is None
    )
    return GraphReadFixture(
        artifacts=FixtureArtifactReads(versions=versions, artifacts=artifacts),
        candidate=graph_candidate,
        graph_version_id=GRAPH_VERSION_ID,
        graph_artifact_id=GRAPH_ARTIFACT_ID,
        relation_version_id=RELATION_VERSION_ID,
        literature_edge_id=literature_edges[0].edge_id,
        structural_edge_id=structural_edges[0].edge_id if structural_edges else "",
        relation_id=r1.relation_id,
        second_graph_version_id=SECOND_GRAPH_VERSION_ID,
    )


__all__ = [
    "GRAPH_ARTIFACT_ID",
    "GRAPH_VERSION_ID",
    "PROJECT_ID",
    "RELATION_VERSION_ID",
    "GraphReadFixture",
    "build_graph_read_fixture",
    "build_multi_relation_graph_read_fixture",
]
