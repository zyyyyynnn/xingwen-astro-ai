from __future__ import annotations

from dataclasses import replace
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.workflow.literature_pipeline_runtime import (
    LiteraturePipelinePreparationError,
    LiteraturePipelineRuntime,
)
from graph_pipeline_test_support import build_literature_graph_fixture
from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim import LiteratureClaimPipeline
from services.paper_pipeline.claim_benchmark_cases import _build_claim_fixture
from services.paper_pipeline.relation import LiteratureRelationPipeline
from services.paper_pipeline.relation_benchmark_cases import (
    _claim_inputs,
    _relation_fixture,
    _response,
)


PROJECT_ID = UUID("11111111-1111-4111-8111-111111111111")
RUN_ID = UUID("22222222-2222-4222-8222-222222222222")
ATTEMPT_ID = UUID("33333333-3333-4333-8333-333333333333")
ARTIFACT_ID = UUID("44444444-4444-4444-8444-444444444444")
MODEL_PARAMETERS = {
    "temperature": 0,
    "max_output_tokens": 4096,
    "response_format": "json_schema",
}


def _approved_claim_fixture() -> dict[str, object]:
    benchmark = load_frozen_benchmark()
    claim = next(item for item in benchmark.claims if item.review_status.value == "approved")
    return _build_claim_fixture(benchmark, claim)


def _snapshot_bindings(versions: tuple[object, ...]) -> dict[str, UUID]:
    source_ids = sorted(
        {
            source_id
            for version in versions
            for source_id in version.content.source_snapshot_ids
        }
    )
    return {
        source_id: uuid5(NAMESPACE_URL, f"runtime-source:{source_id}")
        for source_id in source_ids
    }


def test_claim_preparation_keeps_fixture_mode_and_seals_publisher_candidate() -> None:
    fixture = _approved_claim_fixture()
    version_id = fixture["version_id"]
    version = fixture["versions"][version_id]
    snapshot_id = version.content.input_versions.source_snapshots[0].source_snapshot_id

    prepared = LiteraturePipelineRuntime(model_provider="qwen").prepare_claims(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        paper_summary_version=version,
        model_response=fixture["response"],
        model_name="benchmark-replay",
        parameters={"temperature": 0},
        persisted_source_snapshot_ids={
            snapshot_id: uuid5(NAMESPACE_URL, f"persisted:{snapshot_id}")
        },
        source_mode="fixture",
    )

    assert prepared.claims.kind == "literature_claims"
    assert prepared.publication.source_mode == "fixture"
    assert prepared.publication.producer_request.model_provider == "qwen"
    assert prepared.publication.producer_request.parameters == {
        "parameters_version": prepared.claims.producer.parameters_version,
        "parameters": {"temperature": 0},
    }
    assert compute_canonical_payload_hash(
        prepared.publication.producer_request.parameters
    ) == prepared.claims.producer.parameters_hash
    assert (
        prepared.publication.producer_request.input_hash
        == prepared.publication.candidate.content["input_hash"]
    )
    assert all(
        item.target_type == "claim"
        for item in prepared.publication.candidate.literature_evidence_materializations
    )
    bound = prepared.publication.bind_producer_execution(
        UUID("55555555-5555-4555-8555-555555555555")
    )
    assert bound.producer_execution_id == UUID("55555555-5555-4555-8555-555555555555")


def test_admitted_claim_preparation_does_not_reenter_claim_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _approved_claim_fixture()
    version_id = fixture["version_id"]
    version = fixture["versions"][version_id]
    snapshot_id = version.content.input_versions.source_snapshots[0].source_snapshot_id
    runtime = LiteraturePipelineRuntime(model_provider="qwen")
    admitted = runtime.prepare_claims(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        paper_summary_version=version,
        model_response=fixture["response"],
        model_name="benchmark-replay",
        parameters={"temperature": 0},
        persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
        source_mode="fixture",
    )

    def pipeline_must_not_run(*_: object, **__: object) -> None:
        raise AssertionError("prepare_admitted_claims must not call Claim Pipeline admission")

    monkeypatch.setattr(LiteratureClaimPipeline, "admit", pipeline_must_not_run)
    prepared = runtime.prepare_admitted_claims(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=UUID("77777777-7777-4777-8777-777777777777"),
        claims=admitted.claims,
        parameters={"temperature": 0},
        persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
        source_mode="fixture",
    )

    assert prepared.admission is None
    assert prepared.claims is admitted.claims
    assert prepared.publication.candidate.content["kind"] == "literature_claims"
    assert compute_canonical_payload_hash(
        prepared.publication.producer_request.parameters
    ) == prepared.claims.producer.parameters_hash
    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="parameters_hash does not match",
    ):
        runtime.prepare_admitted_claims(
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            attempt_id=ATTEMPT_ID,
            artifact_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            claims=admitted.claims,
            parameters={"temperature": 1},
            persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
            source_mode="fixture",
        )
    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="run_id is not closed",
    ):
        runtime.prepare_admitted_claims(
            project_id=PROJECT_ID,
            run_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            attempt_id=ATTEMPT_ID,
            artifact_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            claims=admitted.claims,
            parameters={"temperature": 0},
            persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
            source_mode="fixture",
        )


def test_summary_preparation_binds_paper_summary_id() -> None:
    fixture = _approved_claim_fixture()
    version_id = fixture["version_id"]
    version = fixture["versions"][version_id]
    summary = version.content
    snapshot_id = summary.input_versions.source_snapshots[0].source_snapshot_id

    prepared = LiteraturePipelineRuntime(model_provider="qwen").prepare_paper_summary(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        summary=summary,
        persisted_source_snapshot_ids={
            snapshot_id: uuid5(NAMESPACE_URL, f"persisted:{snapshot_id}")
        },
        parameters={
            "temperature": 0,
            "max_output_tokens": 2048,
            "response_format": "json_schema",
        },
        source_mode="fixture",
    )

    bindings = prepared.publication.candidate.literature_evidence_materializations
    assert bindings
    assert {item.target_type for item in bindings} == {"paper_summary"}
    assert {item.target_id for item in bindings} == {summary.summary_id}


def test_benchmark_summary_cannot_be_labeled_live() -> None:
    fixture = _approved_claim_fixture()
    version_id = fixture["version_id"]
    version = fixture["versions"][version_id]
    snapshot_id = version.content.input_versions.source_snapshots[0].source_snapshot_id

    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="cannot be published with source_mode=live",
    ):
        LiteraturePipelineRuntime().prepare_claims(
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            attempt_id=ATTEMPT_ID,
            artifact_id=ARTIFACT_ID,
            paper_summary_version=version,
            model_response=fixture["response"],
            model_name="benchmark-replay",
            parameters={"temperature": 0},
            persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
            source_mode="live",
        )


def test_relation_preparation_binds_only_relation_targets_and_is_deterministic() -> None:
    benchmark = load_frozen_benchmark()
    claims = _claim_inputs(benchmark)
    relation = next(item for item in benchmark.relations if item.status.value == "accepted")
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == relation.reasoning_trace_id
    )
    fixture = _relation_fixture(
        benchmark=benchmark,
        relation=relation,
        trace=trace,
        claims=claims,
    )
    versions = tuple(
        replace(item.version, project_id=str(PROJECT_ID)) for item in claims.values()
    )
    snapshot_bindings = _snapshot_bindings(versions)
    runtime = LiteraturePipelineRuntime(model_provider="qwen")

    first = runtime.prepare_relations(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        literature_claim_versions=versions,
        model_response=_response(fixture.payload),
        model_name="benchmark-replay",
        parameters=MODEL_PARAMETERS,
        confidence_assessments={fixture.confidence.assessment_id: fixture.confidence},
        persisted_source_snapshot_ids=snapshot_bindings,
        source_mode="fixture",
    )
    second = runtime.prepare_relations(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=UUID("66666666-6666-4666-8666-666666666666"),
        literature_claim_versions=versions,
        model_response=_response(fixture.payload),
        model_name="benchmark-replay",
        parameters=MODEL_PARAMETERS,
        confidence_assessments={fixture.confidence.assessment_id: fixture.confidence},
        persisted_source_snapshot_ids=snapshot_bindings,
        source_mode="fixture",
    )

    materializations = first.publication.candidate.literature_evidence_materializations
    assert materializations
    assert {item.target_type for item in materializations} == {"relation"}
    admitted_relation_id = first.relations.relations[0].relation_id
    assert {item.target_id for item in materializations} == {
        admitted_relation_id
    }
    assert (
        first.publication.candidate.content["output_hash"]
        == second.publication.candidate.content["output_hash"]
    )
    assert first.publication.publication_key != second.publication.publication_key
    assert (
        first.publication.producer_request.idempotency_key
        != second.publication.producer_request.idempotency_key
    )
    assert len(first.publication.producer_request.idempotency_key) <= 200
    assert len(first.publication.publication_key) <= 200
    assert compute_canonical_payload_hash(
        first.publication.producer_request.parameters
    ) == first.relations.producer.parameters_hash


def test_admitted_relation_preparation_does_not_reenter_relation_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark = load_frozen_benchmark()
    claims = _claim_inputs(benchmark)
    relation = next(item for item in benchmark.relations if item.status.value == "accepted")
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == relation.reasoning_trace_id
    )
    fixture = _relation_fixture(
        benchmark=benchmark,
        relation=relation,
        trace=trace,
        claims=claims,
    )
    versions = tuple(
        replace(item.version, project_id=str(PROJECT_ID)) for item in claims.values()
    )
    snapshot_bindings = _snapshot_bindings(versions)
    runtime = LiteraturePipelineRuntime(model_provider="qwen")
    admitted = runtime.prepare_relations(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        literature_claim_versions=versions,
        model_response=_response(fixture.payload),
        model_name="benchmark-replay",
        parameters=MODEL_PARAMETERS,
        confidence_assessments={fixture.confidence.assessment_id: fixture.confidence},
        persisted_source_snapshot_ids=snapshot_bindings,
        source_mode="fixture",
    )

    def pipeline_must_not_run(*_: object, **__: object) -> None:
        raise AssertionError("prepare_admitted_relations must not call Relation Pipeline admission")

    monkeypatch.setattr(LiteratureRelationPipeline, "admit", pipeline_must_not_run)
    prepared = runtime.prepare_admitted_relations(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=UUID("88888888-8888-4888-8888-888888888888"),
        relations=admitted.relations,
        parameters=MODEL_PARAMETERS,
        persisted_source_snapshot_ids=snapshot_bindings,
        source_mode="fixture",
    )

    assert prepared.admission is None
    assert prepared.relations is admitted.relations
    assert prepared.publication.candidate.content["kind"] == "literature_relations"
    assert compute_canonical_payload_hash(
        prepared.publication.producer_request.parameters
    ) == prepared.relations.producer.parameters_hash


def test_admitted_claim_preparation_rejects_forged_candidate() -> None:
    fixture = _approved_claim_fixture()
    version_id = fixture["version_id"]
    version = fixture["versions"][version_id]
    snapshot_id = version.content.input_versions.source_snapshots[0].source_snapshot_id
    admitted = LiteraturePipelineRuntime().prepare_claims(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        paper_summary_version=version,
        model_response=fixture["response"],
        model_name="benchmark-replay",
        parameters={"temperature": 0},
        persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
        source_mode="fixture",
    )
    forged = admitted.claims.model_copy(deep=True)

    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="must be sealed by its authoritative Pipeline",
    ):
        LiteraturePipelineRuntime().prepare_admitted_claims(
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            attempt_id=ATTEMPT_ID,
            artifact_id=UUID("99999999-9999-4999-8999-999999999999"),
            claims=forged,
            parameters={"temperature": 0},
            persisted_source_snapshot_ids={snapshot_id: ARTIFACT_ID},
            source_mode="fixture",
        )


def test_admitted_relation_preparation_rejects_project_and_fixture_closure() -> None:
    benchmark = load_frozen_benchmark()
    claims = _claim_inputs(benchmark)
    relation = next(item for item in benchmark.relations if item.status.value == "accepted")
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == relation.reasoning_trace_id
    )
    fixture = _relation_fixture(
        benchmark=benchmark,
        relation=relation,
        trace=trace,
        claims=claims,
    )
    versions = tuple(
        replace(item.version, project_id=str(PROJECT_ID)) for item in claims.values()
    )
    snapshot_bindings = _snapshot_bindings(versions)
    runtime = LiteraturePipelineRuntime()
    admitted = runtime.prepare_relations(
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        literature_claim_versions=versions,
        model_response=_response(fixture.payload),
        model_name="benchmark-replay",
        parameters=MODEL_PARAMETERS,
        confidence_assessments={fixture.confidence.assessment_id: fixture.confidence},
        persisted_source_snapshot_ids=snapshot_bindings,
        source_mode="fixture",
    )

    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="project_id is not closed",
    ):
        runtime.prepare_admitted_relations(
            project_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
            run_id=RUN_ID,
            attempt_id=ATTEMPT_ID,
            artifact_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            relations=admitted.relations,
            parameters=MODEL_PARAMETERS,
            persisted_source_snapshot_ids=snapshot_bindings,
            source_mode="fixture",
        )

    with pytest.raises(
        LiteraturePipelinePreparationError,
        match="cannot be published with source_mode=live",
    ):
        runtime.prepare_admitted_relations(
            project_id=PROJECT_ID,
            run_id=RUN_ID,
            attempt_id=ATTEMPT_ID,
            artifact_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
            relations=admitted.relations,
            parameters=MODEL_PARAMETERS,
            persisted_source_snapshot_ids=snapshot_bindings,
            source_mode="live",
        )


def test_graph_preparation_uses_exact_relation_version_and_graph_owned_evidence() -> None:
    fixture = build_literature_graph_fixture()
    relation_version_id = fixture.inputs.selection.literature_relations_artifact_version_id
    prepared = LiteraturePipelineRuntime(graph_reader=fixture.reader).prepare_graph(
        project_id=fixture.inputs.selection.project_id,
        run_id=RUN_ID,
        attempt_id=ATTEMPT_ID,
        artifact_id=ARTIFACT_ID,
        literature_relations=fixture.inputs.literature_relations.candidate,
        literature_relations_artifact_version_id=relation_version_id,
        source_mode="fixture",
    )

    assert fixture.reader.selections[-1].literature_relations_artifact_version_id == (
        relation_version_id
    )
    assert prepared.request.scope.accepted_relation_ids == (fixture.relation_id,)
    assert prepared.publication.candidate.content["kind"] == "graph"
    upstream_ids = {
        item.upstream_evidence_id
        for item in prepared.candidate.evidence_uses
    }
    owned_ids = {
        item.persisted_evidence_id
        for item in prepared.publication.candidate.graph_evidence_materializations
    }
    assert owned_ids.isdisjoint(upstream_ids)
