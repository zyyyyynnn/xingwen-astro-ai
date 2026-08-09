"""Publisher-port bypass and provenance contracts for Versioned Evidence Graph artifacts."""

from __future__ import annotations

from copy import copy, deepcopy
from types import SimpleNamespace
from typing import Literal
from uuid import UUID

import pytest
from pydantic import BaseModel, ConfigDict

from app.schemas.core import ArtifactKind, GraphArtifactContent
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph import GraphEdge, GraphNode, GraphResponse
from app.schemas.graph_artifact import GraphArtifactCandidate
from app.workflow import publisher as publisher_module
from app.workflow.publisher import (
    AdmittedArtifactCandidate,
    ArtifactAdmissionContext,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    PublicationAdmissionError,
    PublicationConflictError,
    admit_artifact_candidate,
)
from services.graph_pipeline.pipeline import GraphPipeline

from graph_pipeline_test_support import (
    build_literature_graph_fixture,
    stable_uuid,
)


class ForgedGraphCandidate(BaseModel):
    """Caller-defined Graph-shaped model that must not become authoritative."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["graph"] = "graph"
    schema_version: Literal["1.0.0"] = "1.0.0"
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    def __artifact_publication_is_admitted__(self) -> bool:
        return True


def _accept(_: ArtifactAdmissionContext) -> None:
    return None


def _accepted_candidate() -> GraphArtifactCandidate:
    fixture = build_literature_graph_fixture()
    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.candidate is not None
    return result.candidate


def _bindings(
    candidate: GraphArtifactCandidate,
) -> tuple[
    tuple[ArtifactSourceSnapshotBinding, ...],
    tuple[ArtifactEvidenceBinding, ...],
]:
    persisted_snapshot_by_pipeline = {
        item.source_snapshot_id: item.persisted_source_snapshot_id
        for item in candidate.source_snapshots
    }
    snapshots = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_source_snapshot_id=item.persisted_source_snapshot_id,
        )
        for item in candidate.source_snapshots
    )
    evidence = tuple(
        ArtifactEvidenceBinding(
            target_type="graph_edge",
            target_id=item.graph_edge_id,
            pipeline_evidence_id=item.evidence_use_id,
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_evidence_id=stable_uuid(
                f"graph-owned-evidence:{item.evidence_use_id}"
            ),
            persisted_source_snapshot_id=persisted_snapshot_by_pipeline[
                item.source_snapshot_id
            ],
        )
        for item in candidate.evidence_uses
    )
    return snapshots, evidence


def _admit(
    candidate: GraphArtifactCandidate,
    *,
    snapshots: tuple[ArtifactSourceSnapshotBinding, ...] | None = None,
    evidence: tuple[ArtifactEvidenceBinding, ...] | None = None,
) -> AdmittedArtifactCandidate:
    default_snapshots, default_evidence = _bindings(candidate)
    return admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        source_snapshot_bindings=(
            default_snapshots if snapshots is None else snapshots
        ),
        evidence_bindings=default_evidence if evidence is None else evidence,
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )


def test_real_pipeline_sealed_candidate_passes_generic_publisher_port() -> None:
    candidate = _accepted_candidate()
    admitted = _admit(candidate)

    assert admitted.content == candidate.model_dump(mode="json", exclude_none=True)
    assert admitted.schema_version == candidate.schema_version
    assert admitted.quality_projection is None
    assert admitted.quality_projection_hash is None


@pytest.mark.parametrize("mutation", (None, "input_hash", "producer"))
def test_idempotent_graph_replay_requires_exact_persisted_producer_snapshot(
    mutation: str | None,
) -> None:
    input_hash = "sha256:" + "a" * 64
    parameters_hash = "sha256:" + "b" * 64
    producer = SimpleNamespace(
        producer_type="algorithm",
        producer_name="versioned-evidence-graph-pipeline",
        producer_version="1.0.0",
        parameters_hash=parameters_hash,
        input_hash=input_hash,
        model_provider=None,
        model_name=None,
        prompt_name=None,
        prompt_version=None,
        prompt_hash=None,
    )
    public_producer = {
        "type": producer.producer_type,
        "name": producer.producer_name,
        "version": producer.producer_version,
        "parameters_hash": parameters_hash,
    }
    version = SimpleNamespace(input_hash=input_hash, producer=public_producer)
    if mutation == "input_hash":
        version.input_hash = "sha256:" + "c" * 64
    elif mutation == "producer":
        version.producer = {**public_producer, "prompt_name": "fabricated"}

    if mutation is None:
        publisher_module._require_same_persisted_producer(version, producer)
    else:
        with pytest.raises(PublicationConflictError, match="producer metadata"):
            publisher_module._require_same_persisted_producer(version, producer)


def test_generic_wrapper_cannot_be_constructed_with_imported_module_token() -> None:
    with pytest.raises(PublicationAdmissionError, match="active admission port"):
        AdmittedArtifactCandidate(
            content_json='{"kind":"graph"}',
            content_hash="sha256:" + "0" * 64,
            schema_version="1.0.0",
            source_snapshot_ids=(),
            evidence_ids=(),
            _seal=publisher_module._ADMISSION_SEAL,
        )


@pytest.mark.parametrize("operation", (copy, deepcopy))
def test_generic_wrapper_copy_cannot_replay_admission_authority(operation) -> None:
    admitted = _admit(_accepted_candidate())
    copied = operation(admitted)
    publication = ArtifactPublication(
        artifact_id=UUID(stable_uuid("artifact:graph-wrapper-copy")),
        publication_key="graph.wrapper.copy",
        producer_execution_id=UUID(stable_uuid("producer:graph-wrapper-copy")),
        candidate=copied,
        source_mode="fixture",
    )

    with pytest.raises(PublicationAdmissionError, match="forged or mutated"):
        publisher_module._validated_publications((publication,))


def test_generic_wrapper_payload_tamper_is_rejected_before_publication() -> None:
    admitted = _admit(_accepted_candidate())
    object.__setattr__(admitted, "_content_json", '{"kind":"graph"}')
    publication = ArtifactPublication(
        artifact_id=UUID(stable_uuid("artifact:graph-wrapper-tamper")),
        publication_key="graph.wrapper.tamper",
        producer_execution_id=UUID(stable_uuid("producer:graph-wrapper-tamper")),
        candidate=admitted,
        source_mode="fixture",
    )

    with pytest.raises(PublicationAdmissionError, match="forged or mutated"):
        publisher_module._validated_publications((publication,))


def test_generic_wrapper_nested_materialization_tamper_is_rejected() -> None:
    admitted = _admit(_accepted_candidate())
    plans = list(admitted._graph_evidence_materializations)
    plans[0] = tuple(
        (name, "edge.forged_target" if name == "target_id" else value)
        for name, value in plans[0]
    )
    object.__setattr__(admitted, "_graph_evidence_materializations", tuple(plans))
    publication = ArtifactPublication(
        artifact_id=UUID(stable_uuid("artifact:graph-nested-tamper")),
        publication_key="graph.nested.tamper",
        producer_execution_id=UUID(stable_uuid("producer:graph-nested-tamper")),
        candidate=admitted,
        source_mode="fixture",
    )

    with pytest.raises(PublicationAdmissionError, match="forged or mutated"):
        publisher_module._validated_publications((publication,))


def test_generic_wrapper_rebuilds_materialization_views_by_value() -> None:
    admitted = _admit(_accepted_candidate())
    original_target = admitted.graph_evidence_materializations[0].target_id
    exposed_plan = admitted.graph_evidence_materializations[0]
    object.__setattr__(exposed_plan, "target_id", "edge.forged_target")
    publication = ArtifactPublication(
        artifact_id=UUID(stable_uuid("artifact:graph-rebuilt-plan")),
        publication_key="graph.rebuilt.plan",
        producer_execution_id=UUID(stable_uuid("producer:graph-rebuilt-plan")),
        candidate=admitted,
        source_mode="fixture",
    )

    assert admitted.graph_evidence_materializations[0].target_id == original_target
    assert publisher_module._validated_publications((publication,)) == (publication,)


def test_port_returns_exact_graph_owned_evidence_materialization_plan() -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    admitted = _admit(candidate, snapshots=snapshots, evidence=evidence)

    expected_snapshot_ids = {
        item.persisted_source_snapshot_id for item in snapshots
    }
    assert set(admitted.source_snapshot_ids) == expected_snapshot_ids
    assert set(admitted.evidence_ids) == {
        item.persisted_evidence_id for item in evidence
    }
    assert admitted.literature_source_snapshot_materializations == ()
    assert admitted.literature_evidence_materializations == ()

    planned_snapshots = {
        item.pipeline_source_snapshot_id: item
        for item in admitted.graph_source_snapshot_materializations
    }
    assert set(planned_snapshots) == set(candidate.source_snapshot_ids)
    for reference in candidate.source_snapshots:
        planned = planned_snapshots[reference.source_snapshot_id]
        assert planned.persisted_source_snapshot_id == (
            reference.persisted_source_snapshot_id
        )
        assert planned.source_id == reference.source_id
        assert planned.source_version == reference.source_version
        assert planned.content_hash == reference.content_hash

    planned_evidence = {
        item.pipeline_evidence_id: item
        for item in admitted.graph_evidence_materializations
    }
    uses = {item.evidence_use_id: item for item in candidate.evidence_uses}
    bindings = {item.pipeline_evidence_id: item for item in evidence}
    assert set(planned_evidence) == set(uses)
    for evidence_use_id, use in uses.items():
        planned = planned_evidence[evidence_use_id]
        binding = bindings[evidence_use_id]
        assert planned.target_id == use.graph_edge_id
        assert planned.persisted_evidence_id == binding.persisted_evidence_id
        assert planned.persisted_source_snapshot_id == (
            binding.persisted_source_snapshot_id
        )
        assert planned.upstream_artifact_version_id == (
            use.upstream_artifact_version_id
        )
        assert planned.upstream_evidence_id == use.upstream_evidence_id
        assert planned.upstream_target_type == use.upstream_target_type
        assert planned.upstream_target_id == use.upstream_target_id
        assert planned.upstream_evidence_hash == use.upstream_evidence_hash
        assert planned.evidence_type == use.evidence_type.value
        assert planned.upstream_is_restricted is use.upstream_is_restricted


@pytest.mark.parametrize("operation", (copy, deepcopy, lambda value: value.model_copy()))
def test_copied_candidate_cannot_replay_pipeline_authority(operation) -> None:
    candidate = _accepted_candidate()
    copied = operation(candidate)

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(copied)


def test_json_roundtrip_cannot_replay_pipeline_authority() -> None:
    candidate = _accepted_candidate()
    round_tripped = GraphArtifactCandidate.model_validate_json(
        candidate.model_dump_json(exclude_none=True)
    )

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(round_tripped)


def test_public_payload_tamper_invalidates_pipeline_authority() -> None:
    candidate = _accepted_candidate()
    object.__setattr__(candidate, "output_hash", "sha256:" + "f" * 64)

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(candidate)


def test_old_seal_and_context_cannot_be_replayed_on_new_candidate() -> None:
    old = _accepted_candidate()
    new = _accepted_candidate()
    object.__setattr__(new, "_artifact_publication_seal", old._artifact_publication_seal)
    object.__setattr__(
        new,
        "_artifact_publication_context",
        old._artifact_publication_context,
    )

    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(new)


def test_raw_graph_mapping_is_rejected() -> None:
    candidate = _accepted_candidate().model_dump(mode="json", exclude_none=True)

    with pytest.raises(PublicationAdmissionError, match="Pydantic"):
        admit_artifact_candidate(  # type: ignore[arg-type]
            candidate,
            schema_version="1.0.0",
            source_snapshot_ids=(),
            evidence_ids=(),
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=_accept,
        )


def test_graph_read_projection_is_rejected() -> None:
    candidate = GraphResponse(
        nodes=[
            GraphNode(
                id="node.paper",
                type=GraphNodeType.paper,
                label="Paper",
                ref_id="paper.1",
            ),
            GraphNode(
                id="node.claim",
                type=GraphNodeType.claim,
                label="Claim",
                ref_id="claim.1",
            ),
        ],
        edges=[
            GraphEdge(
                id="edge.supports",
                source="node.paper",
                target="node.claim",
                type=GraphEdgeType.supports_finding,
                evidence_ids=["evidence.1"],
            )
        ],
    )

    with pytest.raises(PublicationAdmissionError, match="Graph read projection"):
        admit_artifact_candidate(
            candidate,
            schema_version="1.0.0",
            source_snapshot_ids=("snapshot.1",),
            evidence_ids=("evidence.1",),
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=_accept,
        )


def test_core_graph_artifact_projection_cannot_bypass_evidence_graph_admission() -> None:
    candidate = GraphArtifactContent(
        kind=ArtifactKind.graph,
        node_ids=("node.paper", "node.claim"),
        edge_ids=("edge.supports",),
    )

    with pytest.raises(PublicationAdmissionError, match="authoritative Versioned Evidence Graph"):
        admit_artifact_candidate(
            candidate,
            schema_version="1.0.0",
            source_snapshot_ids=(),
            evidence_ids=(),
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=_accept,
        )


def test_forged_graph_model_and_admission_method_are_rejected() -> None:
    candidate = ForgedGraphCandidate(
        source_snapshot_ids=("snapshot.1",),
        evidence_ids=("evidence.1",),
    )

    with pytest.raises(PublicationAdmissionError, match="authoritative Versioned Evidence Graph"):
        admit_artifact_candidate(
            candidate,
            schema_version=candidate.schema_version,
            source_snapshot_ids=candidate.source_snapshot_ids,
            evidence_ids=candidate.evidence_ids,
            evidence_validator=_accept,
            domain_validator=_accept,
            quality_validator=_accept,
        )


def test_graph_publication_requires_both_explicit_binding_sets() -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)

    for supplied_snapshots, supplied_evidence in (
        (None, evidence),
        (snapshots, None),
        (None, None),
    ):
        with pytest.raises(PublicationAdmissionError, match="explicit"):
            admit_artifact_candidate(
                candidate,
                schema_version=candidate.schema_version,
                source_snapshot_ids=candidate.source_snapshot_ids,
                evidence_ids=candidate.evidence_ids,
                source_snapshot_bindings=supplied_snapshots,
                evidence_bindings=supplied_evidence,
                evidence_validator=_accept,
                domain_validator=_accept,
                quality_validator=_accept,
            )


@pytest.mark.parametrize("mutation", ("missing", "extra", "wrong_persisted"))
def test_source_snapshot_bindings_require_exact_candidate_closure(mutation: str) -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    if mutation == "missing":
        snapshots = snapshots[1:]
    elif mutation == "extra":
        snapshots = snapshots + (
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id="source_snapshot.extra",
                persisted_source_snapshot_id=stable_uuid("source-snapshot:extra"),
            ),
        )
    else:
        first = snapshots[0]
        snapshots = (
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=first.pipeline_source_snapshot_id,
                persisted_source_snapshot_id=stable_uuid("source-snapshot:wrong"),
            ),
        ) + snapshots[1:]

    with pytest.raises(PublicationAdmissionError, match="exactly cover"):
        _admit(candidate, snapshots=snapshots, evidence=evidence)


@pytest.mark.parametrize("mutation", ("missing", "extra", "wrong_target"))
def test_evidence_bindings_require_exact_edge_target_closure(mutation: str) -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    if mutation == "missing":
        evidence = evidence[1:]
    elif mutation == "extra":
        evidence = evidence + (
            ArtifactEvidenceBinding(
                target_type="graph_edge",
                target_id=candidate.edges[0].edge_id,
                pipeline_evidence_id="evidence.graph_use_extra",
                pipeline_source_snapshot_id=snapshots[0].pipeline_source_snapshot_id,
                persisted_evidence_id=stable_uuid("graph-owned-evidence:extra"),
                persisted_source_snapshot_id=snapshots[0].persisted_source_snapshot_id,
            ),
        )
    else:
        first = evidence[0]
        evidence = (
            ArtifactEvidenceBinding(
                target_type=first.target_type,
                target_id=candidate.edges[-1].edge_id + ".wrong",
                pipeline_evidence_id=first.pipeline_evidence_id,
                pipeline_source_snapshot_id=first.pipeline_source_snapshot_id,
                persisted_evidence_id=first.persisted_evidence_id,
                persisted_source_snapshot_id=first.persisted_source_snapshot_id,
            ),
        ) + evidence[1:]

    with pytest.raises(PublicationAdmissionError, match="exactly close"):
        _admit(candidate, snapshots=snapshots, evidence=evidence)


def test_evidence_binding_rejects_wrong_persisted_snapshot() -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    first = evidence[0]
    evidence = (
        ArtifactEvidenceBinding(
            target_type=first.target_type,
            target_id=first.target_id,
            pipeline_evidence_id=first.pipeline_evidence_id,
            pipeline_source_snapshot_id=first.pipeline_source_snapshot_id,
            persisted_evidence_id=first.persisted_evidence_id,
            persisted_source_snapshot_id=stable_uuid("source-snapshot:wrong"),
        ),
    ) + evidence[1:]

    with pytest.raises(PublicationAdmissionError, match="persisted SourceSnapshot"):
        _admit(candidate, snapshots=snapshots, evidence=evidence)


def test_graph_owned_evidence_id_cannot_reuse_upstream_evidence() -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    first = evidence[0]
    evidence = (
        ArtifactEvidenceBinding(
            target_type=first.target_type,
            target_id=first.target_id,
            pipeline_evidence_id=first.pipeline_evidence_id,
            pipeline_source_snapshot_id=first.pipeline_source_snapshot_id,
            persisted_evidence_id=candidate.evidence_uses[0].upstream_evidence_id,
            persisted_source_snapshot_id=first.persisted_source_snapshot_id,
        ),
    ) + evidence[1:]

    with pytest.raises(PublicationAdmissionError, match="never reuse upstream"):
        _admit(candidate, snapshots=snapshots, evidence=evidence)


def test_graph_owned_evidence_ids_must_be_unique_across_edge_targets() -> None:
    candidate = _accepted_candidate()
    snapshots, evidence = _bindings(candidate)
    first, second = evidence[:2]
    evidence = (
        first,
        ArtifactEvidenceBinding(
            target_type=second.target_type,
            target_id=second.target_id,
            pipeline_evidence_id=second.pipeline_evidence_id,
            pipeline_source_snapshot_id=second.pipeline_source_snapshot_id,
            persisted_evidence_id=first.persisted_evidence_id,
            persisted_source_snapshot_id=second.persisted_source_snapshot_id,
        ),
    ) + evidence[2:]

    with pytest.raises(PublicationAdmissionError, match="new, unique"):
        _admit(candidate, snapshots=snapshots, evidence=evidence)
