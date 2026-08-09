from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    SourceMode,
)
from app.schemas.enums import (
    GraphEdgeType,
    GraphNodeType,
    LiteratureRelationType,
)
from app.schemas.graph_artifact import (
    GRAPH_TAXONOMY_EDGE_TYPES,
    GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES,
    GRAPH_TAXONOMY_NODE_TYPES,
    GRAPH_TAXONOMY_STRUCTURAL_EDGE_TYPES,
    GraphArtifactEdge,
    GraphRelationTraceBinding,
    GraphTaxonomy,
)
from app.schemas.literature_relation import LiteratureRelationsCandidate
from app.security import SecurityProblem
from app.services.graph_inputs import ArtifactVersionGraphInputReadAdapter
from literature_artifact_test_support import build_literature_fixture
from services.graph_pipeline import (
    EvidenceRestrictionFact,
    GraphDataVersionSelection,
    GraphIdentityError,
    GraphInputIntegrityError,
    GraphInputVersionSelection,
    GraphNodeIdentity,
    GraphNodeVersionBinding,
    PersistedEvidenceBinding,
    PersistedSourceSnapshotBinding,
    PublishedArtifactVersionPins,
    PublishedGraphInputs,
    PublishedLiteratureRelationsVersion,
    canonical_edge_order,
    canonical_evidence_use_order,
    canonical_node_order,
    claim_node_identity,
    dataset_node_identity,
    field_node_identity,
    graph_evidence_use_id,
    graph_edge_type_for_literature_relation,
    literature_relation_edge_identity,
    paper_node_identity,
    provides_field_edge_identity,
    research_goal_node_identity,
    supports_finding_edge_identity,
    uses_dataset_edge_identity,
)


_INPUT_HASH = "sha256:" + "1" * 64
_DOMAIN_OUTPUT_HASH = "sha256:" + "2" * 64
_CONTENT_HASH = "sha256:" + "3" * 64
_PARAMETERS_HASH = "sha256:" + "4" * 64
_NOW = datetime(2026, 8, 9, 8, 0, tzinfo=UTC)


class _RestrictionReader:
    def __init__(self, *, omit_last: bool = False) -> None:
        self.omit_last = omit_last

    def read_restrictions(
        self,
        *,
        project_id: str,
        evidence_ids: tuple[str, ...],
    ) -> tuple[EvidenceRestrictionFact, ...]:
        selected = evidence_ids[:-1] if self.omit_last else evidence_ids
        return tuple(
            EvidenceRestrictionFact(
                evidence_id=evidence_id,
                project_id=project_id,
                is_restricted=False,
            )
            for evidence_id in selected
        )


def _producer_execution(*, output_hash: str) -> ProducerExecutionDetail:
    return ProducerExecutionDetail(
        id="producer_execution.graph-input",
        run_id="run.graph-input",
        step_key="build_data_artifacts",
        step_attempt_id="attempt.graph-input",
        producer=ProducerReference(
            type="pipeline",
            name="data-artifact-pipeline",
            version="1.0.0",
            parameters_hash=_PARAMETERS_HASH,
        ),
        parameters={"manifest": "manifest.star"},
        parameters_hash=_PARAMETERS_HASH,
        input_hash=_INPUT_HASH,
        output_hash=output_hash,
        status="completed",
        started_at=_NOW,
        finished_at=_NOW,
    )


def test_published_pins_keep_domain_output_and_publisher_content_hash_separate() -> None:
    pins = PublishedArtifactVersionPins(
        artifact_id="artifact.dataset",
        artifact_version_id="artifact-version.dataset",
        project_id="project.graph",
        version_number=1,
        schema_version="1.0.0",
        content_hash=_CONTENT_HASH,
        input_hash=_INPUT_HASH,
        output_hash=_DOMAIN_OUTPUT_HASH,
        source_mode=SourceMode.fixture,
        producer_execution=_producer_execution(output_hash=_CONTENT_HASH),
    )

    assert pins.output_hash == _DOMAIN_OUTPUT_HASH
    assert pins.producer_execution.output_hash == pins.content_hash
    with pytest.raises(GraphInputIntegrityError, match="ProducerExecution"):
        PublishedArtifactVersionPins(
            artifact_id="artifact.dataset",
            artifact_version_id="artifact-version.dataset",
            project_id="project.graph",
            version_number=1,
            schema_version="1.0.0",
            content_hash=_CONTENT_HASH,
            input_hash=_INPUT_HASH,
            output_hash=_DOMAIN_OUTPUT_HASH,
            source_mode=SourceMode.fixture,
            producer_execution=_producer_execution(
                output_hash=_DOMAIN_OUTPUT_HASH
            ),
        )


def test_version_selection_supports_literature_only_or_an_exact_data_pair() -> None:
    literature_only = GraphInputVersionSelection(
        project_id="project.graph",
        literature_relations_artifact_version_id="artifact-version.relations",
    )
    data = GraphDataVersionSelection(
        dataset_artifact_version_id="artifact-version.dataset",
        field_dictionary_artifact_version_id="artifact-version.fields",
    )
    full = GraphInputVersionSelection(
        project_id="project.graph",
        literature_relations_artifact_version_id="artifact-version.relations",
        data=data,
    )

    assert literature_only.data is None
    assert full.data is data
    with pytest.raises(GraphInputIntegrityError, match="typed"):
        GraphInputVersionSelection(
            project_id="project.graph",
            literature_relations_artifact_version_id=(
                "artifact-version.relations"
            ),
            data={  # type: ignore[arg-type]
                "dataset_artifact_version_id": "artifact-version.dataset",
                "field_dictionary_artifact_version_id": (
                    "artifact-version.fields"
                ),
            },
        )
    with pytest.raises(GraphInputIntegrityError, match="LiteratureRelations envelope"):
        PublishedGraphInputs(
            selection=literature_only,
            literature_relations={"kind": "literature_relations"},  # type: ignore[arg-type]
        )


def test_literature_only_bundle_closes_the_published_version_and_provenance() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.relation_version_id]
    candidate = LiteratureRelationsCandidate.model_validate(version.content)
    snapshot_reference_by_pipeline: dict[str, tuple[str, str, str]] = {}
    for evidence in candidate.evidence:
        reference = (
            evidence.source_id,
            evidence.source_snapshot_version,
            evidence.source_snapshot_content_hash,
        )
        previous = snapshot_reference_by_pipeline.setdefault(
            evidence.source_snapshot_id,
            reference,
        )
        assert previous == reference
    persisted_snapshot_by_reference = {
        (
            snapshot.source_id,
            snapshot.source_version_or_etag
            or snapshot.cache_version
            or snapshot.content_hash,
            snapshot.content_hash,
        ): snapshot
        for snapshot in version.source_snapshots
    }
    source_bindings = tuple(
        PersistedSourceSnapshotBinding(
            pipeline_source_snapshot_id=pipeline_id,
            source_snapshot=persisted_snapshot_by_reference[reference],
        )
        for pipeline_id, reference in snapshot_reference_by_pipeline.items()
    )
    pipeline_evidence = {
        evidence.evidence_id: evidence for evidence in candidate.evidence
    }
    evidence_bindings = tuple(
        PersistedEvidenceBinding(
            pipeline_evidence_id=str(evidence.locator["summary_evidence_id"]),
            pipeline_evidence_content_hash=compute_canonical_payload_hash(
                pipeline_evidence[
                    str(evidence.locator["summary_evidence_id"])
                ].model_dump(mode="json", exclude_none=True)
            ),
            pipeline_source_snapshot_id=pipeline_evidence[
                str(evidence.locator["summary_evidence_id"])
            ].source_snapshot_id,
            pipeline_target_type=evidence.target_type,
            pipeline_target_id=evidence.target_id,
            pipeline_locator=evidence.locator,
            evidence=evidence,
            is_restricted=False,
        )
        for evidence in version.evidence
    )
    published = PublishedLiteratureRelationsVersion(
        pins=PublishedArtifactVersionPins(
            artifact_id=version.artifact_id,
            artifact_version_id=version.id,
            project_id=version.project_id,
            version_number=version.version_number,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            input_hash=version.input_hash,
            output_hash=candidate.output_hash,
            source_mode=version.source_mode,
            producer_execution=version.producer_execution,
        ),
        candidate=candidate,
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )
    selection = GraphInputVersionSelection(
        project_id=version.project_id,
        literature_relations_artifact_version_id=version.id,
    )

    inputs = PublishedGraphInputs(
        selection=selection,
        literature_relations=published,
    )

    assert inputs.selection == selection
    assert inputs.dataset is None
    assert inputs.field_dictionary is None


def test_trusted_adapter_reads_only_the_exact_complete_literature_version() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.relation_version_id]
    selection = GraphInputVersionSelection(
        project_id=version.project_id,
        literature_relations_artifact_version_id=version.id,
    )
    adapter = ArtifactVersionGraphInputReadAdapter(
        artifacts=fixture.artifacts,  # type: ignore[arg-type]
        session_id="owner",
        evidence_restrictions=_RestrictionReader(),
    )

    inputs = adapter.read(selection)

    assert inputs.selection is selection
    assert inputs.literature_relations.pins.artifact_version_id == version.id
    assert inputs.literature_relations.candidate.kind == "literature_relations"
    assert fixture.artifacts.full_content_requests == [True]


def test_trusted_adapter_translates_artifact_security_problem_structurally() -> None:
    class _DeniedArtifacts:
        def get_version(self, **kwargs):
            raise SecurityProblem(
                status=404,
                code="ARTIFACT_VERSION_NOT_FOUND",
                title="Resource not found",
                detail="message text is not an admission taxonomy",
            )

    adapter = ArtifactVersionGraphInputReadAdapter(
        artifacts=_DeniedArtifacts(),  # type: ignore[arg-type]
        session_id="owner",
        evidence_restrictions=_RestrictionReader(),
    )

    with pytest.raises(GraphInputIntegrityError) as captured:
        adapter.read(
            GraphInputVersionSelection(
                project_id="project.graph",
                literature_relations_artifact_version_id="version.missing",
            )
        )

    assert captured.value.stage.value == "artifact_version"
    assert captured.value.reason.value == "input_version_unknown"
    assert captured.value.path == "input_versions.version.missing"


def test_trusted_adapter_fails_closed_when_restriction_fact_is_missing() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.relation_version_id]
    adapter = ArtifactVersionGraphInputReadAdapter(
        artifacts=fixture.artifacts,  # type: ignore[arg-type]
        session_id="owner",
        evidence_restrictions=_RestrictionReader(omit_last=True),
    )

    with pytest.raises(GraphInputIntegrityError, match="exactly cover"):
        adapter.read(
            GraphInputVersionSelection(
                project_id=version.project_id,
                literature_relations_artifact_version_id=version.id,
            )
        )


def test_trusted_adapter_fails_data_path_without_governed_evidence_mapping() -> None:
    fixture = build_literature_fixture()
    version = fixture.artifacts.versions[fixture.relation_version_id]
    adapter = ArtifactVersionGraphInputReadAdapter(
        artifacts=fixture.artifacts,  # type: ignore[arg-type]
        session_id="owner",
        evidence_restrictions=_RestrictionReader(),
    )
    selection = GraphInputVersionSelection(
        project_id=version.project_id,
        literature_relations_artifact_version_id=version.id,
        data=GraphDataVersionSelection(
            dataset_artifact_version_id="artifact-version.dataset",
            field_dictionary_artifact_version_id="artifact-version.fields",
        ),
    )

    with pytest.raises(GraphInputIntegrityError, match="governed pipeline Evidence"):
        adapter.read(selection)


def test_persisted_evidence_hash_binds_restriction_and_all_upstream_facts() -> None:
    evidence = EvidenceDetail(
        id="evidence.persisted.1",
        artifact_version_id="artifact-version.relations",
        target_type="relation",
        target_id="relation.1",
        evidence_type="reasoning_trace",
        source_snapshot_id="snapshot.persisted.1",
        paper_id="paper.1",
        locator={"summary_evidence_id": "evidence.pipeline.1", "step": 2},
        quote_or_value={"premise": "one"},
        extraction_method="literature-relation-pipeline",
        confidence=0.83,
        created_at=_NOW,
    )
    binding = PersistedEvidenceBinding(
        pipeline_evidence_id="evidence.pipeline.1",
        pipeline_evidence_content_hash=compute_canonical_payload_hash(
            evidence.model_dump(mode="json", exclude_none=True)
        ),
        pipeline_source_snapshot_id="snapshot.pipeline.1",
        pipeline_target_type=evidence.target_type,
        pipeline_target_id=evidence.target_id,
        pipeline_locator=evidence.locator,
        evidence=evidence,
        is_restricted=False,
    )
    expected = compute_canonical_payload_hash(
        {
            "artifact_version_id": evidence.artifact_version_id,
            "target_type": evidence.target_type,
            "target_id": evidence.target_id,
            "evidence_type": evidence.evidence_type,
            "source_snapshot_id": evidence.source_snapshot_id,
            "paper_id": evidence.paper_id,
            "locator": evidence.locator,
            "quote_or_value": evidence.quote_or_value,
            "extraction_method": evidence.extraction_method,
            "confidence": evidence.confidence,
            "is_restricted": False,
        }
    )
    restricted = PersistedEvidenceBinding(
        pipeline_evidence_id="evidence.pipeline.1",
        pipeline_evidence_content_hash=binding.pipeline_evidence_content_hash,
        pipeline_source_snapshot_id="snapshot.pipeline.1",
        pipeline_target_type=evidence.target_type,
        pipeline_target_id=evidence.target_id,
        pipeline_locator=evidence.locator,
        evidence=evidence,
        is_restricted=True,
    )

    assert binding.upstream_evidence_content_hash == expected
    assert (
        restricted.upstream_evidence_content_hash
        != binding.upstream_evidence_content_hash
    )
    with pytest.raises(GraphInputIntegrityError, match="exact persisted boolean"):
        PersistedEvidenceBinding(
            pipeline_evidence_id="evidence.pipeline.1",
            pipeline_evidence_content_hash=binding.pipeline_evidence_content_hash,
            pipeline_source_snapshot_id="snapshot.pipeline.1",
            pipeline_target_type=evidence.target_type,
            pipeline_target_id=evidence.target_id,
            pipeline_locator=evidence.locator,
            evidence=evidence,
            is_restricted=1,  # type: ignore[arg-type]
        )


def test_node_identity_uses_only_type_and_authoritative_logical_reference() -> None:
    dataset = dataset_node_identity("artifact.dataset")
    same_dataset = dataset_node_identity("artifact.dataset")
    field = field_node_identity("manifest.star", "star.tic_id")

    assert dataset.node_id == same_dataset.node_id
    assert GraphNodeVersionBinding(
        node_id=dataset.node_id,
        upstream_artifact_version_id="artifact-version.dataset",
    ).node_id == GraphNodeVersionBinding(
        node_id=dataset.node_id,
        upstream_artifact_version_id="artifact-version.dataset.revised",
    ).node_id
    assert field.node_id != field_node_identity(
        "manifest.star.revised", "star.tic_id"
    ).node_id
    assert field.node_id != field_node_identity(
        "manifest.star", "star.gaia_source_id"
    ).node_id
    with pytest.raises(GraphIdentityError, match="does not generate"):
        GraphNodeIdentity(
            node_type=GraphNodeType.source,
            logical_reference=(("source_id", "source.gaia"),),
        )


def test_structural_edges_enforce_the_authoritative_directions() -> None:
    goal = research_goal_node_identity("contract.1.goal.1")
    dataset = dataset_node_identity("artifact.dataset")
    field = field_node_identity("manifest.star", "star.tic_id")
    paper = paper_node_identity("paper.1")
    claim = claim_node_identity("claim.1")

    assert uses_dataset_edge_identity(goal, dataset).source is goal
    assert provides_field_edge_identity(dataset, field).source is dataset
    assert supports_finding_edge_identity(paper, claim).source is paper
    with pytest.raises(GraphIdentityError, match="requires research_goal -> dataset"):
        uses_dataset_edge_identity(dataset, goal)
    with pytest.raises(GraphIdentityError, match="requires dataset -> field"):
        provides_field_edge_identity(field, dataset)
    with pytest.raises(GraphIdentityError, match="requires paper -> claim"):
        supports_finding_edge_identity(claim, paper)


@pytest.mark.parametrize("relation_type", tuple(LiteratureRelationType))
def test_relation_edge_is_source_to_target_direction_sensitive(
    relation_type: LiteratureRelationType,
) -> None:
    source = claim_node_identity("claim.source")
    target = claim_node_identity("claim.target")
    forward = literature_relation_edge_identity(
        source,
        target,
        relation_type=relation_type,
        relation_logical_id="relation.1",
    )
    reversed_edge = literature_relation_edge_identity(
        target,
        source,
        relation_type=relation_type,
        relation_logical_id="relation.1",
    )
    other_relation = literature_relation_edge_identity(
        source,
        target,
        relation_type=relation_type,
        relation_logical_id="relation.2",
    )

    assert forward.edge_id != reversed_edge.edge_id
    assert forward.edge_id != other_relation.edge_id
    assert graph_edge_type_for_literature_relation(
        relation_type
    ) is GraphEdgeType(relation_type.value)
    edge_type = graph_edge_type_for_literature_relation(relation_type)
    trace = GraphRelationTraceBinding(
        relation_id="relation.1",
        relation_artifact_version_id="11111111-1111-4111-8111-111111111111",
        relation_type=edge_type,
        source_claim_id="claim.source",
        target_claim_id="claim.target",
        reasoning_trace_id="trace.1",
        premise_claim_ids=("claim.source", "claim.target"),
        trace_evidence_ids=("evidence.1",),
    )
    assert GraphArtifactEdge(
        edge_id=forward.edge_id,
        edge_type=edge_type,
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        evidence_use_ids=("evidence.graph-use",),
        relation_trace=trace,
    ).relation_trace == trace
    with pytest.raises(GraphIdentityError, match="self-referential"):
        literature_relation_edge_identity(
            source,
            source,
            relation_type=relation_type,
            relation_logical_id="relation.self",
        )


def test_graph_taxonomy_is_the_exact_authorized_set() -> None:
    expected_literature = frozenset(
        GraphEdgeType(item.value) for item in LiteratureRelationType
    )
    assert GRAPH_TAXONOMY_LITERATURE_EDGE_TYPES == expected_literature
    assert set(GRAPH_TAXONOMY_EDGE_TYPES) == (
        GRAPH_TAXONOMY_STRUCTURAL_EDGE_TYPES | expected_literature
    )

    payload = {
        "taxonomy_id": "taxonomy.graph.evidence_graph",
        "schema_version": "2.0.0",
        "version": "2.0.0",
        "node_types": GRAPH_TAXONOMY_NODE_TYPES,
        "edge_types": GRAPH_TAXONOMY_EDGE_TYPES,
    }
    taxonomy = GraphTaxonomy(
        **payload,
        content_hash=compute_canonical_payload_hash(payload),
    )
    assert taxonomy.node_types == GRAPH_TAXONOMY_NODE_TYPES
    assert taxonomy.edge_types == GRAPH_TAXONOMY_EDGE_TYPES

    for extra_edge_type in (
        GraphEdgeType.cites,
        GraphEdgeType.corrected_by_feedback,
    ):
        edge_types = tuple(
            sorted(
                (*GRAPH_TAXONOMY_EDGE_TYPES, extra_edge_type),
                key=lambda item: item.value,
            )
        )
        extra_payload = {**payload, "edge_types": edge_types}
        with pytest.raises(ValidationError) as taxonomy_error:
            GraphTaxonomy(
                **extra_payload,
                content_hash=compute_canonical_payload_hash(extra_payload),
            )
        assert any(
            error["type"] in {"literal_error", "too_long"}
            for error in taxonomy_error.value.errors()
        )
        with pytest.raises(ValidationError) as edge_error:
            GraphArtifactEdge(
                edge_id=f"edge.{extra_edge_type.value}",
                edge_type=extra_edge_type,
                source_node_id="node.claim.source",
                target_node_id="node.claim.target",
                evidence_use_ids=("evidence.graph-use",),
            )
        assert any(
            error["type"] == "literal_error" for error in edge_error.value.errors()
        )

    node_types = tuple(
        sorted((*GRAPH_TAXONOMY_NODE_TYPES, GraphNodeType.finding), key=lambda item: item.value)
    )
    extra_payload = {**payload, "node_types": node_types}
    with pytest.raises(ValidationError) as node_error:
        GraphTaxonomy(
            **extra_payload,
            content_hash=compute_canonical_payload_hash(extra_payload),
        )
    assert any(
        error["type"] in {"literal_error", "too_long"}
        for error in node_error.value.errors()
    )


def test_evidence_use_identity_and_all_registry_orders_are_canonical() -> None:
    goal = research_goal_node_identity("contract.1.goal.1")
    dataset = dataset_node_identity("artifact.dataset")
    field = field_node_identity("manifest.star", "star.tic_id")
    uses = uses_dataset_edge_identity(goal, dataset)
    provides = provides_field_edge_identity(dataset, field)
    evidence_primary = graph_evidence_use_id(
        graph_edge_id=provides.edge_id,
        upstream_artifact_version_id="artifact-version.dataset",
        upstream_evidence_id="evidence.persisted.1",
    )
    evidence_revised = graph_evidence_use_id(
        graph_edge_id=provides.edge_id,
        upstream_artifact_version_id="artifact-version.dataset.revised",
        upstream_evidence_id="evidence.persisted.1",
    )

    assert evidence_primary != evidence_revised
    assert canonical_node_order(node for node in (field, goal, dataset)) == tuple(
        sorted((field, goal, dataset), key=lambda node: node.node_id)
    )
    assert canonical_edge_order(edge for edge in (provides, uses)) == tuple(
        sorted((provides, uses), key=lambda edge: edge.edge_id)
    )
    assert canonical_evidence_use_order((evidence_revised, evidence_primary)) == tuple(
        sorted((evidence_primary, evidence_revised))
    )
    with pytest.raises(GraphIdentityError, match="must be unique"):
        canonical_node_order((dataset, dataset))
    with pytest.raises(GraphIdentityError, match="must be unique"):
        canonical_edge_order((uses, uses))
    with pytest.raises(GraphIdentityError, match="must be unique"):
        canonical_evidence_use_order((evidence_primary, evidence_primary))
