from __future__ import annotations

from copy import copy, deepcopy
from dataclasses import replace
import inspect
import json

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.graph_artifact import (
    GRAPH_TAXONOMY_EDGE_TYPES,
    GRAPH_TAXONOMY_NODE_TYPES,
    GraphArtifactCandidate,
    GraphCapacityPolicy,
    GraphIntegrityStage,
    GraphIntegrityStatus,
    GraphLayoutHint,
    GraphPolicySet,
    GraphRejectionReason,
    GraphStructuralEdgeRequest,
    compute_graph_input_hash,
    graph_algorithm_parameters,
)
from app.schemas.literature_relation import LiteratureRelationStatus
from app.security import SecurityProblem

from services.graph_pipeline.pipeline import GraphPipeline
from services.graph_pipeline.ports import (
    GraphInputIntegrityError,
    PublishedGraphInputs,
    PublishedLiteratureRelationsVersion,
)

from graph_pipeline_test_support import (
    build_data_graph_fixture,
    build_literature_graph_fixture,
    stable_uuid,
)


def _accepted_candidate():
    fixture = build_literature_graph_fixture()
    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.status is GraphIntegrityStatus.passed
    assert result.candidate is not None
    return fixture, result.candidate


def _accepted_data_candidate():
    fixture = build_data_graph_fixture()
    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.status is GraphIntegrityStatus.passed
    assert result.candidate is not None
    return fixture, result.candidate


def _field_upstream_evidence_ids(dataset, field_id: str) -> set[str]:
    transformations = {
        item.evidence_id: item for item in dataset.transformation_evidence
    }
    evidence_ids: set[str] = set()
    for row in dataset.rows:
        outcome = next(
            (item for item in row.fields if item.canonical_field_id == field_id),
            None,
        )
        if outcome is None:
            assert field_id not in row.projected_field_ids
            continue
        evidence_ids.update(outcome.transformation_evidence_ids)
        for evidence_id in outcome.transformation_evidence_ids:
            evidence_ids.update(
                transformations[evidence_id].crossmatch_evidence_ids
            )
    return evidence_ids


def _assert_failure(result, stage, reason) -> None:
    assert result.status is GraphIntegrityStatus.failed
    assert result.candidate is None
    assert result.report.first_failure_stage is stage
    assert result.report.first_rejection_reason is reason
    assert len(result.report.findings) == 1


def test_reader_failure_uses_structured_stage_reason_not_message_text() -> None:
    fixture = build_literature_graph_fixture()

    class _Reader:
        def read(self, selection):
            raise GraphInputIntegrityError(
                "message mentions project, schema, and content hash",
                stage=GraphIntegrityStage.evidence_snapshot,
                reason=GraphRejectionReason.evidence_unknown,
                path="input_versions.evidence.explicit",
            )

    result = GraphPipeline(_Reader()).admit(fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_unknown,
    )
    assert result.report.findings[0].path == "input_versions.evidence.explicit"


def test_reader_security_problem_is_stably_failed_closed() -> None:
    fixture = build_literature_graph_fixture()

    class _Reader:
        def read(self, selection):
            raise SecurityProblem(
                status=404,
                code="EVIDENCE_NOT_FOUND",
                title="Resource not found",
                detail="arbitrary storage detail must not drive classification",
            )

    result = GraphPipeline(_Reader()).admit(fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_unknown,
    )
    assert result.report.findings[0].message == (
        "Graph input storage access failed (EVIDENCE_NOT_FOUND)"
    )


@pytest.mark.parametrize(
    ("pin_name", "reason"),
    (
        ("schema_version", GraphRejectionReason.unsupported_schema_version),
        ("content_hash", GraphRejectionReason.content_hash_mismatch),
        ("input_hash", GraphRejectionReason.input_hash_mismatch),
    ),
)
def test_published_input_pin_failures_have_structured_reasons(
    pin_name: str,
    reason: GraphRejectionReason,
) -> None:
    published = build_literature_graph_fixture().inputs.literature_relations
    pins = published.pins
    value = "9.9.9" if pin_name == "schema_version" else "sha256:" + "f" * 64
    updates = {pin_name: value}
    if pin_name == "content_hash":
        updates["producer_execution"] = pins.producer_execution.model_copy(
            update={"output_hash": value}
        )
    elif pin_name == "input_hash":
        updates["producer_execution"] = pins.producer_execution.model_copy(
            update={"input_hash": value}
        )

    with pytest.raises(GraphInputIntegrityError) as captured:
        PublishedLiteratureRelationsVersion(
            pins=replace(pins, **updates),
            candidate=published.candidate,
            source_snapshot_bindings=published.source_snapshot_bindings,
            evidence_bindings=published.evidence_bindings,
        )

    assert captured.value.stage is GraphIntegrityStage.artifact_version
    assert captured.value.reason is reason


def test_published_input_producer_failure_has_structured_reason() -> None:
    published = build_literature_graph_fixture().inputs.literature_relations
    execution = published.pins.producer_execution.model_copy(
        update={"step_key": "drifted-step"}
    )

    with pytest.raises(GraphInputIntegrityError) as captured:
        PublishedLiteratureRelationsVersion(
            pins=replace(published.pins, producer_execution=execution),
            candidate=published.candidate,
            source_snapshot_bindings=published.source_snapshot_bindings,
            evidence_bindings=published.evidence_bindings,
        )

    assert captured.value.stage is GraphIntegrityStage.artifact_version
    assert (
        captured.value.reason is GraphRejectionReason.producer_execution_mismatch
    )


def test_published_input_ownership_failure_has_structured_reason() -> None:
    inputs = build_literature_graph_fixture().inputs

    with pytest.raises(GraphInputIntegrityError) as captured:
        PublishedGraphInputs(
            selection=replace(
                inputs.selection,
                project_id=stable_uuid("another-project"),
            ),
            literature_relations=inputs.literature_relations,
        )

    assert captured.value.stage is GraphIntegrityStage.ownership
    assert captured.value.reason is GraphRejectionReason.cross_project_ownership


@pytest.mark.parametrize(
    ("binding_name", "reason"),
    (
        ("evidence_bindings", GraphRejectionReason.evidence_inconsistent),
        (
            "source_snapshot_bindings",
            GraphRejectionReason.source_snapshot_inconsistent,
        ),
    ),
)
def test_published_provenance_closure_failures_have_structured_reasons(
    binding_name: str,
    reason: GraphRejectionReason,
) -> None:
    published = build_literature_graph_fixture().inputs.literature_relations
    values = getattr(published, binding_name)
    kwargs = {
        "pins": published.pins,
        "candidate": published.candidate,
        "source_snapshot_bindings": published.source_snapshot_bindings,
        "evidence_bindings": published.evidence_bindings,
        binding_name: values[:-1],
    }

    with pytest.raises(GraphInputIntegrityError) as captured:
        PublishedLiteratureRelationsVersion(**kwargs)

    assert captured.value.stage is GraphIntegrityStage.evidence_snapshot
    assert captured.value.reason is reason


def test_real_literature_relation_literature_only_candidate_builds_four_nodes_and_two_edges() -> None:
    fixture, candidate = _accepted_candidate()

    assert len(candidate.nodes) == 4
    assert len(candidate.edges) == 2
    assert len(candidate.evidence_uses) == 3
    assert candidate.taxonomy.node_types == GRAPH_TAXONOMY_NODE_TYPES
    assert candidate.taxonomy.edge_types == GRAPH_TAXONOMY_EDGE_TYPES
    assert candidate.integrity_report.counts.node_count == 4
    assert candidate.integrity_report.counts.edge_count == 2
    assert candidate.integrity_report.counts.relation_edge_count == 1
    assert [item.node_id for item in candidate.nodes] == sorted(
        item.node_id for item in candidate.nodes
    )
    assert [item.edge_id for item in candidate.edges] == sorted(
        item.edge_id for item in candidate.edges
    )
    assert {item.node_type for item in candidate.nodes} == {
        GraphNodeType.paper,
        GraphNodeType.claim,
    }

    by_type = {item.edge_type: item for item in candidate.edges}
    structural = by_type[GraphEdgeType.supports_finding]
    relation = by_type[GraphEdgeType.extends]
    nodes = {item.node_id: item for item in candidate.nodes}
    assert nodes[structural.source_node_id].node_type is GraphNodeType.paper
    assert nodes[structural.target_node_id].node_type is GraphNodeType.claim
    assert relation.relation_trace is not None
    assert relation.relation_trace.relation_id == fixture.relation_id
    assert relation.relation_trace.source_claim_id == fixture.source_claim_id
    assert relation.relation_trace.target_claim_id == fixture.target_claim_id
    assert fixture.reader.selections == [fixture.inputs.selection]


def test_shared_literature_evidence_is_selected_by_accepted_relation_target() -> None:
    fixture = build_literature_graph_fixture(
        include_shared_candidate_relation=True
    )
    published = fixture.inputs.literature_relations
    accepted = next(
        item
        for item in published.candidate.relations
        if item.status is LiteratureRelationStatus.accepted
    )
    candidate_relation = next(
        item
        for item in published.candidate.relations
        if item.status is LiteratureRelationStatus.candidate
    )
    shared = set(accepted.evidence_ids) & set(candidate_relation.evidence_ids)
    assert shared
    assert any(
        sum(
            binding.pipeline_evidence_id == evidence_id
            for binding in published.evidence_bindings
        )
        > 1
        for evidence_id in shared
    )

    result = GraphPipeline(fixture.reader).admit(fixture.request())

    assert result.status is GraphIntegrityStatus.passed
    assert result.candidate is not None
    graph_uses = {
        item.evidence_use_id: item for item in result.candidate.evidence_uses
    }
    relation_edge = next(
        item for item in result.candidate.edges if item.relation_trace is not None
    )
    assert {
        graph_uses[evidence_use_id].upstream_target_id
        for evidence_use_id in relation_edge.evidence_use_ids
    } == {accepted.relation_id}


def test_graph_algorithm_producer_uses_scalar_ledger_parameters() -> None:
    _, candidate = _accepted_candidate()
    parameters = graph_algorithm_parameters(candidate.policies, candidate.taxonomy)

    assert all(
        isinstance(value, str | int | float | bool) or value is None
        for value in parameters.values()
    )
    assert candidate.producer.parameters_hash == compute_canonical_payload_hash(
        parameters
    )


@pytest.mark.parametrize(
    ("field", "drifted_value"),
    (
        ("producer_name", "drifted-evidence-graph-pipeline"),
        ("producer_version", "9.9.9"),
        ("parameters_hash", "sha256:" + "f" * 64),
    ),
)
def test_graph_input_hash_commits_the_algorithm_producer(
    field: str,
    drifted_value: str,
) -> None:
    _, candidate = _accepted_candidate()
    payload = candidate.model_dump(mode="json", exclude_none=True)
    payload["producer"] = {**payload["producer"], field: drifted_value}

    assert compute_graph_input_hash(payload) != candidate.input_hash


def test_only_exact_pipeline_result_retains_publication_seal() -> None:
    _, candidate = _accepted_candidate()

    shallow = copy(candidate)
    deep = deepcopy(candidate)
    model_copy = candidate.model_copy()
    round_tripped = GraphArtifactCandidate.model_validate_json(
        candidate.model_dump_json(exclude_none=True)
    )

    assert candidate.__artifact_publication_is_admitted__()
    assert not shallow.__artifact_publication_is_admitted__()
    assert not deep.__artifact_publication_is_admitted__()
    assert not model_copy.__artifact_publication_is_admitted__()
    assert not round_tripped.__artifact_publication_is_admitted__()
    assert round_tripped.model_dump(mode="json") == candidate.model_dump(mode="json")


def test_pipeline_without_bound_publication_authority_fails_closed() -> None:
    fixture = build_literature_graph_fixture()
    production_admit = inspect.getclosurevars(GraphPipeline.admit).nonlocals[
        "original_admit"
    ]

    result = production_admit(GraphPipeline(fixture.reader), fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.hash_commitment,
        GraphRejectionReason.admission_commitment_mismatch,
    )
    assert result.candidate is None


def test_invalid_json_and_multiple_schema_failures_are_stable() -> None:
    fixture = build_literature_graph_fixture()
    pipeline = GraphPipeline(fixture.reader)

    invalid = pipeline.admit_json("{")
    assert invalid.status is GraphIntegrityStatus.failed
    assert invalid.report.first_rejection_reason is GraphRejectionReason.invalid_json
    assert len(invalid.report.findings) == 1

    payload = fixture.request().model_dump(mode="json", exclude_none=True)
    payload["project_id"] = "not-a-uuid"
    payload["literature_relations_artifact_version_id"] = "also-not-a-uuid"
    first = pipeline.admit_json(json.dumps(payload, ensure_ascii=False))
    second = pipeline.admit_json(
        json.dumps(dict(reversed(tuple(payload.items()))), ensure_ascii=False)
    )

    assert first.status is GraphIntegrityStatus.failed
    assert first.candidate is None
    assert len(first.report.findings) == 2
    assert all(
        item.reason is GraphRejectionReason.schema_invalid
        for item in first.report.findings
    )
    assert tuple(item.path for item in first.report.findings) == tuple(
        sorted(item.path for item in first.report.findings)
    )
    assert first.report == second.report


def test_multi_gate_failures_are_complete_prioritized_and_order_invariant() -> None:
    reports = []
    for reverse in (False, True):
        fixture = build_literature_graph_fixture()
        request = fixture.request(
            policies=GraphPolicySet(
                capacity_policy=GraphCapacityPolicy(max_items_per_chunk=1)
            )
        )
        duplicated_claims = (
            *request.scope.literature_claim_ids,
            request.scope.literature_claim_ids[0],
        )
        object.__setattr__(
            request.scope,
            "literature_claim_ids",
            tuple(reversed(duplicated_claims)) if reverse else duplicated_claims,
        )

        published = fixture.inputs.literature_relations
        object.__setattr__(published.candidate, "reasoning_traces", ())
        bindings = tuple(
            sorted(
                published.evidence_bindings,
                key=lambda item: item.pipeline_evidence_id,
            )
        )
        taxonomy_binding, missing_binding = bindings
        object.__setattr__(
            taxonomy_binding.evidence,
            "evidence_type",
            "not_a_governed_evidence_type",
        )
        retained_bindings = tuple(
            item
            for item in published.evidence_bindings
            if item is not missing_binding
        )
        object.__setattr__(
            published,
            "evidence_bindings",
            tuple(reversed(retained_bindings)) if reverse else retained_bindings,
        )
        object.__setattr__(
            published,
            "source_snapshot_bindings",
            tuple(reversed(published.source_snapshot_bindings))
            if reverse
            else published.source_snapshot_bindings,
        )

        result = GraphPipeline(fixture.reader).admit(request)

        assert result.status is GraphIntegrityStatus.failed
        assert result.candidate is None
        assert tuple(item.stage for item in result.report.findings) == (
            GraphIntegrityStage.taxonomy,
            GraphIntegrityStage.identity,
            GraphIntegrityStage.evidence_snapshot,
            GraphIntegrityStage.relation_trace,
            GraphIntegrityStage.capacity_progressive,
        )
        assert tuple(item.reason for item in result.report.findings) == (
            GraphRejectionReason.taxonomy_violation,
            GraphRejectionReason.duplicate_node_identity,
            GraphRejectionReason.evidence_missing,
            GraphRejectionReason.reasoning_trace_missing,
            GraphRejectionReason.size_limit_exceeded,
        )
        assert result.report.first_failure_stage is GraphIntegrityStage.taxonomy
        assert (
            result.report.first_rejection_reason
            is GraphRejectionReason.taxonomy_violation
        )
        reports.append(result.report)

    assert reports[0] == reports[1]


def test_binding_and_progressive_chunk_permutations_are_canonical() -> None:
    normal = build_literature_graph_fixture()
    reversed_bindings = build_literature_graph_fixture(
        reverse_published_bindings=True
    )

    request = normal.request(chunk_size=2)
    reversed_request = reversed_bindings.request(
        chunk_size=2,
        reverse_chunks=True,
    )
    assert request == reversed_request
    normal_result = GraphPipeline(normal.reader).admit(request)
    reversed_result = GraphPipeline(reversed_bindings.reader).admit(
        reversed_request
    )

    assert normal_result.candidate is not None
    assert reversed_result.candidate is not None
    assert normal_result.candidate.model_dump(mode="json") == (
        reversed_result.candidate.model_dump(mode="json")
    )


def test_layout_is_non_scientific_and_progressive_partition_is_output_invariant() -> None:
    fixture = build_literature_graph_fixture()
    baseline_result = GraphPipeline(fixture.reader).admit(fixture.request())
    layout_result = GraphPipeline(fixture.reader).admit(
        fixture.request(
            layout_hint=GraphLayoutHint(
                strategy="group_by_node_type",
                group_order=(GraphNodeType.claim, GraphNodeType.paper),
            )
        )
    )
    progressive_result = GraphPipeline(fixture.reader).admit(
        fixture.request(chunk_size=1, reverse_chunks=True)
    )
    assert baseline_result.candidate is not None
    assert layout_result.candidate is not None
    assert progressive_result.candidate is not None
    baseline = baseline_result.candidate
    layout = layout_result.candidate
    progressive = progressive_result.candidate

    assert layout.graph_id == baseline.graph_id
    assert layout.scientific_hash == baseline.scientific_hash
    assert layout.input_hash == baseline.input_hash
    assert layout.nodes == baseline.nodes
    assert layout.edges == baseline.edges
    assert layout.evidence_uses == baseline.evidence_uses
    assert layout.layout_hash != baseline.layout_hash
    assert layout.output_hash != baseline.output_hash

    assert progressive.graph_id == baseline.graph_id
    assert progressive.scientific_hash == baseline.scientific_hash
    assert progressive.input_hash == baseline.input_hash
    assert progressive.layout_hash == baseline.layout_hash
    assert progressive.nodes == baseline.nodes
    assert progressive.edges == baseline.edges
    assert progressive.progressive == baseline.progressive
    assert progressive.integrity_report == baseline.integrity_report
    assert progressive.report_hash == baseline.report_hash
    assert progressive.output_hash == baseline.output_hash
    assert progressive.model_dump(mode="json") == baseline.model_dump(mode="json")


def test_incomplete_progressive_and_nonzero_filter_fail_closed() -> None:
    fixture = build_literature_graph_fixture()
    complete = fixture.request().progressive
    incomplete = complete.model_copy(update={"complete": False})
    incomplete_result = GraphPipeline(fixture.reader).admit(
        fixture.request(progressive=incomplete)
    )
    _assert_failure(
        incomplete_result,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.progressive_input_incomplete,
    )

    payload = fixture.request().model_dump(mode="json", exclude_none=True)
    payload["scope"]["filtered_item_count"] = 1
    filtered_result = GraphPipeline(fixture.reader).admit_json(
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )
    _assert_failure(
        filtered_result,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.evidence_hidden_by_filter,
    )


def test_progressive_request_chunk_capacity_is_enforced_before_normalization() -> None:
    fixture = build_literature_graph_fixture()
    chunk_count_policies = GraphPolicySet(
        capacity_policy=GraphCapacityPolicy(max_progressive_chunks=1)
    )
    chunk_size_policies = GraphPolicySet(
        capacity_policy=GraphCapacityPolicy(max_items_per_chunk=1)
    )

    for result in (
        GraphPipeline(fixture.reader).admit(
            fixture.request(policies=chunk_count_policies, chunk_size=1)
        ),
        GraphPipeline(fixture.reader).admit(
            fixture.request(policies=chunk_size_policies, chunk_size=2)
        ),
    ):
        _assert_failure(
            result,
            GraphIntegrityStage.capacity_progressive,
            GraphRejectionReason.size_limit_exceeded,
        )


def test_real_literature_relation_nonaccepted_relation_is_rejected() -> None:
    fixture = build_literature_graph_fixture(
        relation_status=LiteratureRelationStatus.candidate
    )
    result = GraphPipeline(fixture.reader).admit(fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.relation_trace,
        GraphRejectionReason.relation_not_accepted,
    )


def test_missing_persisted_evidence_binding_is_rejected() -> None:
    fixture = build_literature_graph_fixture()
    published = fixture.inputs.literature_relations
    missing_id = next(
        item.evidence_id
        for item in published.candidate.evidence
        if item.evidence_id in set(
            next(
                claim
                for claim in published.candidate.claims
                if claim.claim_id == fixture.source_claim_id
            ).evidence_ids
        )
    )
    object.__setattr__(
        published,
        "evidence_bindings",
        tuple(
            item
            for item in published.evidence_bindings
            if item.pipeline_evidence_id != missing_id
        ),
    )

    result = GraphPipeline(fixture.reader).admit(fixture.request())
    _assert_failure(
        result,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_missing,
    )


def test_structural_edge_wrong_direction_is_rejected() -> None:
    fixture = build_literature_graph_fixture()
    wrong_edge = GraphStructuralEdgeRequest(
        edge_type=GraphEdgeType.supports_finding,
        source_paper_id=fixture.target_paper_id,
        target_claim_id=fixture.source_claim_id,
    )
    wrong_scope = fixture.scope.model_copy(
        update={"structural_edges": (wrong_edge,)}
    )
    result = GraphPipeline(fixture.reader).admit(
        fixture.request(scope=wrong_scope)
    )

    _assert_failure(
        result,
        GraphIntegrityStage.direction_type,
        GraphRejectionReason.wrong_direction,
    )


def test_node_capacity_exact_boundary_passes_and_one_below_fails() -> None:
    fixture = build_literature_graph_fixture()
    exact = GraphPolicySet(
        capacity_policy=GraphCapacityPolicy(
            max_nodes=4,
            max_edges=2,
            max_evidence_uses=3,
            max_evidence_uses_per_edge=2,
        )
    )
    below = GraphPolicySet(
        capacity_policy=GraphCapacityPolicy(
            max_nodes=3,
            max_edges=2,
            max_evidence_uses=3,
            max_evidence_uses_per_edge=2,
        )
    )

    exact_result = GraphPipeline(fixture.reader).admit(
        fixture.request(policies=exact)
    )
    below_result = GraphPipeline(fixture.reader).admit(
        fixture.request(policies=below)
    )

    assert exact_result.status is GraphIntegrityStatus.passed
    assert exact_result.candidate is not None
    _assert_failure(
        below_result,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.size_limit_exceeded,
    )


def test_real_data_artifact_quality_data_maps_dataset_and_every_canonical_field_once() -> None:
    fixture, candidate = _accepted_data_candidate()
    assert fixture.inputs.data is not None
    dataset_version = fixture.inputs.data.dataset
    dictionary_version = fixture.inputs.data.field_dictionary

    nodes = {item.node_id: item for item in candidate.nodes}
    dataset_nodes = [
        item for item in candidate.nodes if item.node_type is GraphNodeType.dataset
    ]
    field_nodes = [
        item for item in candidate.nodes if item.node_type is GraphNodeType.field
    ]
    assert len(dataset_nodes) == 1
    assert {
        part.name: part.value for part in dataset_nodes[0].logical_reference
    } == {"artifact_id": dataset_version.pins.artifact_id}
    assert dataset_nodes[0].version_bindings[0].artifact_version_id == (
        dataset_version.pins.artifact_version_id
    )

    expected_fields = set(dictionary_version.candidate.requested_fields)
    actual_fields = {
        next(
            part.value
            for part in item.logical_reference
            if part.name == "canonical_field_id"
        )
        for item in field_nodes
    }
    assert actual_fields == expected_fields
    assert all(
        {
            part.name: part.value for part in node.logical_reference
        }["field_manifest_id"]
        == dictionary_version.candidate.manifest_pins.field_manifest_id
        for node in field_nodes
    )

    provides = [
        item
        for item in candidate.edges
        if item.edge_type is GraphEdgeType.provides_field
    ]
    assert len(provides) == len(expected_fields)
    assert len({item.target_node_id for item in provides}) == len(expected_fields)
    assert all(item.source_node_id == dataset_nodes[0].node_id for item in provides)
    assert all(nodes[item.target_node_id].node_type is GraphNodeType.field for item in provides)
    assert {
        item.node_type for item in candidate.nodes
    } <= {
        GraphNodeType.dataset,
        GraphNodeType.field,
        GraphNodeType.paper,
        GraphNodeType.claim,
    }
    assert GraphNodeType.source not in {item.node_type for item in candidate.nodes}
    assert not {
        "row",
        "value",
        "source",
    } & {item.node_type.value for item in candidate.nodes}


def test_data_edges_preserve_all_value_states_and_both_version_evidence_uses() -> None:
    fixture, candidate = _accepted_data_candidate()
    assert fixture.inputs.data is not None
    dataset_version = fixture.inputs.data.dataset
    dictionary_version = fixture.inputs.data.field_dictionary
    dataset = dataset_version.candidate

    outcomes = {item.status for row in dataset.rows for item in row.fields}
    selection_statuses = {
        item.selection_status.value for item in dataset.transformation_evidence
    }
    assert {"mapped", "declared_null", "unresolved"} <= outcomes
    assert {"selected", "unselected", "conflict"} <= selection_statuses
    assert dataset.conflicts
    assert any(not row.projected_field_ids for row in dataset.rows)

    nodes = {item.node_id: item for item in candidate.nodes}
    uses = {item.evidence_use_id: item for item in candidate.evidence_uses}
    provides = [
        item
        for item in candidate.edges
        if item.edge_type is GraphEdgeType.provides_field
    ]
    for edge in provides:
        field_node = nodes[edge.target_node_id]
        field_id = next(
            part.value
            for part in field_node.logical_reference
            if part.name == "canonical_field_id"
        )
        pipeline_evidence_ids = _field_upstream_evidence_ids(dataset, field_id)
        assert pipeline_evidence_ids
        applicable_outcomes = tuple(
            next(
                outcome
                for outcome in row.fields
                if outcome.canonical_field_id == field_id
            )
            for row in dataset.rows
            if field_id in row.projected_field_ids
        )
        aggregation = edge.data_aggregation
        assert aggregation is not None
        assert aggregation.projected_row_count == len(applicable_outcomes)
        assert aggregation.mapped_outcome_count == sum(
            outcome.status == "mapped" for outcome in applicable_outcomes
        )
        assert aggregation.declared_null_outcome_count == sum(
            outcome.status == "declared_null" for outcome in applicable_outcomes
        )
        assert aggregation.unresolved_outcome_count == sum(
            outcome.status == "unresolved" for outcome in applicable_outcomes
        )
        assert aggregation.retained_candidate_count == sum(
            len(outcome.candidate_source_value_ids)
            for outcome in applicable_outcomes
        )
        assert aggregation.selected_candidate_count == sum(
            outcome.status == "mapped" for outcome in applicable_outcomes
        )
        assert aggregation.unselected_candidate_count == (
            aggregation.retained_candidate_count
            - aggregation.selected_candidate_count
        )
        assert aggregation.conflict_count == len(
            {
                conflict_id
                for outcome in applicable_outcomes
                for conflict_id in getattr(outcome, "conflict_ids", ())
            }
        )
        assert aggregation.upstream_evidence_count == len(pipeline_evidence_ids)
        expected_bindings = {
            (
                dataset_version.pins.artifact_version_id,
                stable_uuid(f"evidence:dataset:{evidence_id}"),
            )
            for evidence_id in pipeline_evidence_ids
        } | {
            (
                dictionary_version.pins.artifact_version_id,
                stable_uuid(f"evidence:field_dictionary:{evidence_id}"),
            )
            for evidence_id in pipeline_evidence_ids
        }
        actual_bindings = {
            (
                uses[evidence_use_id].upstream_artifact_version_id,
                uses[evidence_use_id].upstream_evidence_id,
            )
            for evidence_use_id in edge.evidence_use_ids
        }
        assert actual_bindings == expected_bindings
        assert len(edge.evidence_use_ids) == 2 * len(pipeline_evidence_ids)
        assert edge.evidence_use_ids == tuple(sorted(edge.evidence_use_ids))

    assert [item.evidence_use_id for item in candidate.evidence_uses] == sorted(
        item.evidence_use_id for item in candidate.evidence_uses
    )
    assert len(candidate.evidence_uses) == len(
        {item.evidence_use_id for item in candidate.evidence_uses}
    )


@pytest.mark.parametrize("tamper", ("target", "locator", "snapshot"))
def test_transformation_evidence_storage_identity_fails_closed(tamper: str) -> None:
    fixture = build_data_graph_fixture()
    assert fixture.inputs.data is not None
    published = fixture.inputs.data.dataset
    transformation = published.candidate.transformation_evidence[0]
    binding = next(
        item
        for item in published.evidence_bindings
        if item.pipeline_evidence_id == transformation.evidence_id
    )
    if tamper == "target":
        changed = replace(
            binding,
            evidence=binding.evidence.model_copy(
                update={"target_id": "field.not-the-transformation-target"}
            ),
        )
    elif tamper == "locator":
        changed = replace(
            binding,
            evidence=binding.evidence.model_copy(
                update={"locator": {**binding.evidence.locator, "raw_field": "wrong"}}
            ),
        )
    else:
        other_snapshot = next(
            item
            for item in published.candidate.source_snapshot_ids
            if item != binding.pipeline_source_snapshot_id
        )
        changed = replace(
            binding,
            pipeline_source_snapshot_id=other_snapshot,
        )
    object.__setattr__(
        published,
        "evidence_bindings",
        tuple(
            changed if item is binding else item
            for item in published.evidence_bindings
        ),
    )

    result = GraphPipeline(fixture.reader).admit(fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_inconsistent,
    )


def test_crossmatch_evidence_content_identity_fails_closed() -> None:
    fixture = build_data_graph_fixture()
    assert fixture.inputs.data is not None
    published = fixture.inputs.data.dataset
    crossmatch_id = published.candidate.crossmatch_evidence_ids[0]
    binding = next(
        item
        for item in published.evidence_bindings
        if item.pipeline_evidence_id == crossmatch_id
    )
    changed_locator = {
        **binding.pipeline_locator,
        "crossmatch_content_hash": "sha256:" + "f" * 64,
    }
    changed = replace(
        binding,
        pipeline_locator=changed_locator,
        evidence=binding.evidence.model_copy(update={"locator": changed_locator}),
    )
    object.__setattr__(
        published,
        "evidence_bindings",
        tuple(
            changed if item is binding else item
            for item in published.evidence_bindings
        ),
    )

    result = GraphPipeline(fixture.reader).admit(fixture.request())

    _assert_failure(
        result,
        GraphIntegrityStage.evidence_snapshot,
        GraphRejectionReason.evidence_inconsistent,
    )


def test_data_binding_permutations_produce_identical_graph_and_hashes() -> None:
    normal = build_data_graph_fixture()
    reversed_bindings = build_data_graph_fixture(
        reverse_published_bindings=True,
        reverse_data_bindings=True,
    )

    normal_result = GraphPipeline(normal.reader).admit(normal.request())
    reversed_result = GraphPipeline(reversed_bindings.reader).admit(
        reversed_bindings.request(reverse_chunks=True)
    )

    assert normal_result.status is GraphIntegrityStatus.passed
    assert reversed_result.status is GraphIntegrityStatus.passed
    assert normal_result.candidate is not None
    assert reversed_result.candidate is not None
    assert normal_result.candidate.model_dump(mode="json") == (
        reversed_result.candidate.model_dump(mode="json")
    )


def test_data_field_with_unbound_evidence_fails_closed() -> None:
    fixture = build_data_graph_fixture()
    assert fixture.inputs.data is not None
    data = fixture.inputs.data
    field_id = "star.name"
    missing_ids = _field_upstream_evidence_ids(data.dataset.candidate, field_id)
    assert missing_ids
    for published in (data.dataset, data.field_dictionary):
        object.__setattr__(
            published,
            "evidence_bindings",
            tuple(
                item
                for item in published.evidence_bindings
                if item.pipeline_evidence_id not in missing_ids
            ),
        )

    result = GraphPipeline(fixture.reader).admit(fixture.request())
    assert result.status is GraphIntegrityStatus.failed
    assert result.candidate is None
    assert result.report.first_failure_stage is GraphIntegrityStage.evidence_snapshot
    assert (
        result.report.first_rejection_reason
        is GraphRejectionReason.evidence_missing
    )
    assert {
        item.path.removeprefix("data.evidence.")
        for item in result.report.findings
        if item.reason is GraphRejectionReason.evidence_missing
    } == missing_ids


def test_data_scope_filter_cannot_hide_field_or_its_evidence() -> None:
    fixture = build_data_graph_fixture()
    payload = fixture.request().model_dump(mode="json", exclude_none=True)
    payload["scope"]["filtered_item_count"] = 1

    result = GraphPipeline(fixture.reader).admit_json(
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )

    _assert_failure(
        result,
        GraphIntegrityStage.capacity_progressive,
        GraphRejectionReason.evidence_hidden_by_filter,
    )
