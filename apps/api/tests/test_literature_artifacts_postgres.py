"""PostgreSQL integration coverage for literature-artifact reads."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest

from db_bootstrap import reset_current_schema
from app.config import settings
from app.schemas._hashing import compute_canonical_payload_hash
from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from app.main import create_app
from app.schemas.literature_relation import LiteratureRelationStatus
from app.services.artifacts import ArtifactReadService
from app.workflow.publisher import (
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactPublisher,
    ArtifactSourceSnapshotBinding,
    admit_artifact_candidate,
)
from fastapi.testclient import TestClient
from literature_artifact_test_support import (
    FixturePaperSummaryReads,
    _claim_version,
    _relation_version,
    _summary_version,
)
from sqlalchemy import Engine, select

from services.paper_pipeline.benchmark import load_frozen_benchmark
from services.paper_pipeline.claim import PaperSummaryArtifactVersionInput
from services.paper_pipeline.claim_benchmark_cases import (
    _REPLAY_MODEL_NAME as CLAIM_MODEL_NAME,
)
from services.paper_pipeline.claim_benchmark_cases import (
    _REPLAY_PARAMETERS as CLAIM_PARAMETERS,
)
from services.paper_pipeline.claim_benchmark_cases import (
    _build_claim_fixture,
)
from services.paper_pipeline.relation import LiteratureClaimsArtifactVersionInput
from services.paper_pipeline.relation_benchmark_cases import (
    _REPLAY_MODEL_NAME as RELATION_MODEL_NAME,
)
from services.paper_pipeline.relation_benchmark_cases import (
    _REPLAY_PARAMETERS as RELATION_PARAMETERS,
)
from services.paper_pipeline.relation_benchmark_cases import (
    _ClaimInput,
    _relation_fixture,
    _response,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    reset_current_schema(TEST_DATABASE_URL)


@pytest.fixture(scope="module")
def literature_context(postgres_engine: Engine) -> dict[str, Any]:
    project_id = uuid4()
    contract_id = uuid4()
    run_id = uuid4()
    step_id = uuid4()
    attempt_id = uuid4()
    benchmark = load_frozen_benchmark()
    accepted_relation = next(
        item
        for item in benchmark.relations
        if item.status.value == LiteratureRelationStatus.accepted.value
    )
    trace = next(
        item
        for item in benchmark.reasoning_traces
        if item.trace_id == accepted_relation.reasoning_trace_id
    )
    benchmark_claims = {item.claim_id: item for item in benchmark.claims}

    summaries = []
    claims = []
    claim_candidates = []
    relation_inputs: dict[str, _ClaimInput] = {}
    for benchmark_claim_id in (
        accepted_relation.source_claim_id,
        accepted_relation.target_claim_id,
    ):
        benchmark_claim = benchmark_claims[benchmark_claim_id]
        fixture = _build_claim_fixture(benchmark, benchmark_claim)
        summary_id = uuid4()
        claim_id = uuid4()
        original_summary = next(iter(fixture["versions"].values())).content
        summary_input = PaperSummaryArtifactVersionInput(
            artifact_version_id=str(summary_id),
            schema_version=original_summary.schema_version,
            content=original_summary,
        )
        admission = fixture["pipeline"].admit(
            paper_summary_artifact_version_id=str(summary_id),
            paper_id=benchmark_claim.paper_id,
            paper_summary_versions={str(summary_id): summary_input},
            model_response=fixture["response"],
            model_name=CLAIM_MODEL_NAME,
            parameters=CLAIM_PARAMETERS,
        )
        candidate = admission.publisher_candidate
        assert candidate is not None
        summary_version = _summary_version(str(summary_id), original_summary)
        claim_version = _claim_version(str(claim_id), candidate)
        summaries.append(summary_version)
        claims.append(claim_version)
        claim_candidates.append(candidate)
        relation_inputs[benchmark_claim_id] = _ClaimInput(
            benchmark_claim_id=benchmark_claim_id,
            record_claim=admission.records[0],
            artifact_version_id=str(claim_id),
            version=LiteratureClaimsArtifactVersionInput(
                artifact_version_id=str(claim_id),
                schema_version=candidate.schema_version,
                content_hash=claim_version.content_hash,
                project_id=str(project_id),
                content=candidate,
            ),
        )

    relation_fixture = _relation_fixture(
        benchmark=benchmark,
        relation=accepted_relation,
        trace=trace,
        claims=relation_inputs,
    )
    relation_admission = relation_fixture.pipeline.admit(
        literature_claim_artifact_version_ids=relation_fixture.version_ids,
        literature_claim_versions=relation_fixture.versions,
        project_id=str(project_id),
        model_response=_response(relation_fixture.payload),
        model_name=RELATION_MODEL_NAME,
        parameters=RELATION_PARAMETERS,
        confidence_assessments={
            relation_fixture.confidence.assessment_id: relation_fixture.confidence
        },
        available_paper_summary_artifact_version_ids=frozenset(
            str(item.id) for item in summaries
        ),
    )
    relation_candidate = relation_admission.publisher_candidate
    assert relation_candidate is not None
    relation_version = _relation_version(str(uuid4()), relation_candidate)
    versions = (*summaries, *claims, relation_version)

    factory = session_factory(postgres_engine)
    app = create_app()
    artifact_reads = ArtifactReadService(factory)
    setattr(
        artifact_reads,
        "paper_summary_reader",
        FixturePaperSummaryReads(artifact_reads),
    )
    app.state.artifact_read_service = artifact_reads
    session_now = datetime.now(UTC)
    owner, owner_credential, _ = app.state.session_service.create(
        now=session_now
    )
    _, other_credential, _ = app.state.session_service.create(
        now=session_now
    )

    artifact_ids = {
        version.artifact_id: uuid5(NAMESPACE_URL, f"artifact:{index}")
        for index, version in enumerate(versions)
    }
    snapshot_details = {
        snapshot.id: snapshot
        for version in versions
        for snapshot in version.source_snapshots
    }
    snapshot_ids = {
        key: uuid5(NAMESPACE_URL, f"snapshot:{index}")
        for index, key in enumerate(sorted(snapshot_details))
    }
    evidence_details = {
        evidence.id: evidence for version in versions for evidence in version.evidence
    }
    evidence_ids = {
        key: uuid5(NAMESPACE_URL, f"evidence:{index}")
        for index, key in enumerate(sorted(evidence_details))
    }

    with factory() as session, session.begin():
        project = build_research_project(
            project_id=project_id,
            session_id=owner.id,
            name="Literature Artifact API PostgreSQL reads",
            case_key="exoplanet_host_star",
            created_at=NOW,
            updated_at=NOW,
        )
        draft = build_contract_draft(project, created_at=NOW, updated_at=NOW)
        contract = build_research_contract(
            project,
            draft,
            contract_id=contract_id,
            content_hash=HASH_A,
            created_at=NOW,
        )
        run = ResearchRunModel(
            id=run_id,
            project_id=project_id,
            contract_id=contract_id,
            execution_mode="live",
            status="completed",
            progress=100,
            latest_event_sequence=0,
            revision=1,
            idempotency_key="literature_api-postgres-run",
            request_hash=HASH_B,
            created_at=NOW,
            updated_at=NOW,
        )
        step = RunStepModel(
            id=step_id,
            run_id=run_id,
            position=0,
            key="reasoning_literature",
            label="Reason literature",
            enter_status="reasoning_literature",
            success_status="building_graph",
            status="completed",
            progress=100,
            public_message="Completed",
            created_at=NOW,
        )
        attempt = StepAttemptModel(
            id=attempt_id,
            run_step_id=step_id,
            attempt_number=1,
            idempotency_key="literature_api-attempt",
            status="completed",
            started_at=NOW,
            finished_at=NOW + timedelta(seconds=1),
            created_at=NOW,
        )
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
        session.flush()
        session.add(run)
        session.flush()
        session.add(step)
        session.flush()
        session.add(attempt)
        session.flush()
        for key, detail in snapshot_details.items():
            session.add(
                SourceSnapshotModel(
                    id=snapshot_ids[key],
                    project_id=project_id,
                    source_id=detail.source_id,
                    source_type=detail.source_type,
                    retrieved_at=detail.retrieved_at,
                    query=detail.query,
                    query_hash=detail.query_hash,
                    source_version_or_etag=detail.source_version_or_etag,
                    content_hash=detail.content_hash,
                    license_note=detail.license_note,
                    cache_version=detail.cache_version,
                    request_metadata=detail.request_metadata,
                )
            )
        session.flush()

        for index, version in enumerate(versions):
            artifact_id = artifact_ids[version.artifact_id]
            kind = version.content["kind"]
            artifact = ResearchArtifactModel(
                id=artifact_id,
                project_id=project_id,
                kind=kind,
                title=f"Literature Artifact API {kind}",
                logical_key=f"{kind}.{index}",
                created_at=NOW,
            )
            execution_id = uuid4()
            runtime = version.producer_execution
            producer = runtime.producer
            session.add(artifact)
            session.flush()
            session.add(
                ProducerExecutionModel(
                    id=execution_id,
                    run_id=run_id,
                    run_step_id=step_id,
                    step_attempt_id=attempt_id,
                    step_key=runtime.step_key,
                    idempotency_key=f"producer-{index}",
                    lease_generation=1,
                    producer_type=producer.type,
                    producer_name=producer.name,
                    producer_version=producer.version,
                    model_provider=producer.model_provider,
                    requested_model=producer.requested_model,
                    prompt_name=producer.prompt_name,
                    prompt_version=producer.prompt_version,
                    prompt_hash=producer.prompt_hash,
                    parameters=runtime.parameters,
                    parameters_hash=runtime.parameters_hash,
                    input_hash=runtime.input_hash,
                    output_hash=runtime.output_hash,
                    status=runtime.status,
                    started_at=runtime.started_at,
                    finished_at=runtime.finished_at,
                    token_usage=runtime.token_usage,
                    latency_ms=runtime.latency_ms,
                    error_code=runtime.error_code,
                    created_at=NOW,
                )
            )
            session.flush()
            row = ArtifactVersionModel(
                id=UUID(version.id),
                artifact_id=artifact_id,
                project_id=project_id,
                created_by_run_id=run_id,
                run_step_id=step_id,
                step_attempt_id=attempt_id,
                producer_execution_id=execution_id,
                version_number=1,
                publication_key=f"publication-{index}",
                schema_version=version.schema_version,
                content=version.content,
                content_hash=version.content_hash,
                input_hash=version.input_hash,
                source_mode=version.source_mode,
                producer=version.producer.model_dump(mode="json", exclude_none=True),
                source_snapshot_ids=[
                    str(snapshot_ids[item.id]) for item in version.source_snapshots
                ],
                evidence_ids=[str(evidence_ids[item.id]) for item in version.evidence],
                created_at=NOW,
            )
            session.add(row)
            session.flush()
            artifact.latest_version_id = row.id

        for key, detail in evidence_details.items():
            session.add(
                EvidenceModel(
                    id=evidence_ids[key],
                    project_id=project_id,
                    artifact_version_id=UUID(detail.artifact_version_id),
                    target_type=detail.target_type,
                    target_id=detail.target_id,
                    evidence_type=detail.evidence_type,
                    source_snapshot_id=snapshot_ids[detail.source_snapshot_id],
                    paper_id=detail.paper_id,
                    locator=detail.locator,
                    quote_or_value=detail.quote_or_value,
                    extraction_method=detail.extraction_method,
                    confidence=detail.confidence,
                    is_restricted=False,
                    created_at=NOW,
                )
            )

    def client(credential: str) -> TestClient:
        result = TestClient(app)
        result.cookies.set(settings.SESSION_COOKIE_NAME, credential, path="/api")
        return result

    accepted = next(
        item
        for item in relation_candidate.relations
        if item.status is LiteratureRelationStatus.accepted
    )
    assert accepted.reasoning_trace_id is not None
    return {
        "factory": factory,
        "owner": client(owner_credential),
        "other": client(other_credential),
        "claim_version_id": claims[0].id,
        "relation_version_id": relation_version.id,
        "relation_id": accepted.relation_id,
        "trace_id": accepted.reasoning_trace_id,
        "relation_evidence_ids": tuple(
            str(evidence_ids[item.id]) for item in relation_version.evidence
        ),
        "project_id": project_id,
        "contract_id": contract_id,
        "claim_candidate": claim_candidates[0],
        "snapshot_ids": {key: str(value) for key, value in snapshot_ids.items()},
    }


def test_postgres_claim_relation_and_trace_reads_close_uuid_provenance(
    literature_context: dict[str, Any],
) -> None:
    owner = literature_context["owner"]
    claim = owner.get(
        f"/api/artifact-versions/{literature_context['claim_version_id']}"
        "/literature-claims"
    )
    relation = owner.get(
        f"/api/artifact-versions/{literature_context['relation_version_id']}"
        f"/literature-relations/{literature_context['relation_id']}"
    )
    trace = owner.get(
        f"/api/artifact-versions/{literature_context['relation_version_id']}"
        f"/reasoning-traces/{literature_context['trace_id']}"
    )

    assert claim.status_code == relation.status_code == trace.status_code == 200
    relation_data = relation.json()["data"]
    assert relation_data["graph_eligible"] is True
    assert relation_data["source_claim"]["claim"]["status"] == "accepted"
    assert relation_data["target_claim"]["claim"]["status"] == "accepted"
    persisted = relation_data["evidence"][0]
    UUID(persisted["id"])
    UUID(persisted["source_snapshot_id"])
    assert persisted["id"] != persisted["locator"]["summary_evidence_id"]
    assert (
        persisted["source_snapshot_id"]
        not in relation_data["relation"]["source_snapshot_ids"]
    )
    assert "chain_of_thought" not in trace.text
    assert "raw_model_response" not in trace.text


def test_postgres_literature_reads_hide_cross_session_versions(
    literature_context: dict[str, Any],
) -> None:
    response = literature_context["other"].get(
        f"/api/artifact-versions/{literature_context['relation_version_id']}"
        "/literature-relations"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "ARTIFACT_VERSION_NOT_FOUND"


def test_postgres_literature_reads_reject_missing_persisted_evidence_binding(
    literature_context: dict[str, Any],
) -> None:
    factory = literature_context["factory"]
    evidence_id = UUID(literature_context["relation_evidence_ids"][0])
    with factory() as session, session.begin():
        evidence = session.get(EvidenceModel, evidence_id)
        assert evidence is not None
        original = dict(evidence.locator)
        evidence.locator = {**original, "summary_evidence_id": "evidence.missing"}
    try:
        response = literature_context["owner"].get(
            f"/api/artifact-versions/{literature_context['relation_version_id']}"
            "/literature-relations"
        )
        assert response.status_code == 403
        assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        with factory() as session, session.begin():
            evidence = session.get(EvidenceModel, evidence_id)
            assert evidence is not None
            evidence.locator = original


def test_postgres_literature_reads_reject_swapped_persisted_evidence_snapshot(
    literature_context: dict[str, Any],
) -> None:
    factory = literature_context["factory"]
    evidence_ids = tuple(
        UUID(item) for item in literature_context["relation_evidence_ids"]
    )
    assert len(evidence_ids) >= 1
    with factory() as session, session.begin():
        first = session.get(EvidenceModel, evidence_ids[0])
        assert first is not None
        other_snapshot_id = session.scalar(
            select(SourceSnapshotModel.id).where(
                SourceSnapshotModel.project_id == first.project_id,
                SourceSnapshotModel.id != first.source_snapshot_id,
            ).limit(1)
        )
        assert other_snapshot_id is not None
        original_snapshot_id = first.source_snapshot_id
        first.source_snapshot_id = other_snapshot_id
    try:
        response = literature_context["owner"].get(
            f"/api/artifact-versions/{literature_context['relation_version_id']}"
            "/literature-relations"
        )
        assert response.status_code == 403
        assert response.json()["code"] == "PROVENANCE_SCOPE_VIOLATION"
    finally:
        with factory() as session, session.begin():
            first = session.get(EvidenceModel, evidence_ids[0])
            assert first is not None
            first.source_snapshot_id = original_snapshot_id

def test_postgres_publisher_materializes_literature_evidence_atomically(
    literature_context: dict[str, Any],
) -> None:
    factory = literature_context["factory"]
    project_id = literature_context["project_id"]
    contract_id = literature_context["contract_id"]
    candidate = literature_context["claim_candidate"]
    snapshot_ids = literature_context["snapshot_ids"]

    run_id = uuid4()
    step_id = uuid4()
    attempt_id = uuid4()
    artifact_id = uuid4()
    producer_id = uuid4()
    lease_token = uuid4()
    now = datetime.now(UTC)
    content_hash = compute_canonical_payload_hash(
        candidate.model_dump(mode="json", exclude_none=True)
    )
    atomic_snapshot_ids = {
        item: snapshot_ids.get(item, str(uuid4()))
        for item in candidate.source_snapshot_ids
    }
    candidate_snapshot_refs = {
        item.source_snapshot_id: item
        for item in candidate.input_versions.source_snapshots
    }
    with factory() as session, session.begin():
        for pipeline_id in candidate.source_snapshot_ids:
            if pipeline_id in snapshot_ids:
                continue
            reference = candidate_snapshot_refs[pipeline_id]
            session.add(
                SourceSnapshotModel(
                    id=UUID(atomic_snapshot_ids[pipeline_id]),
                    project_id=project_id,
                    source_id=reference.source_id,
                    source_type="benchmark",
                    retrieved_at=now,
                    query={"fixture": pipeline_id},
                    query_hash=compute_canonical_payload_hash(
                        {"fixture": pipeline_id}
                    ),
                    source_version_or_etag=reference.source_version,
                    content_hash=reference.content_hash,
                    license_note="Atomic publisher fixture",
                    request_metadata={"data_level": "benchmark"},
                )
            )
        session.flush()
        session.add(
            ResearchRunModel(
                id=run_id,
                project_id=project_id,
                contract_id=contract_id,
                execution_mode="live",
                status="reasoning_literature",
                progress=50,
                latest_event_sequence=0,
                revision=1,
                idempotency_key=f"literature_api-publisher-{run_id}",
                request_hash=HASH_B,
                lease_token=lease_token,
                lease_owner="literature_api-test",
                lease_generation=1,
                lease_expires_at=now + timedelta(minutes=5),
                created_at=now,
                updated_at=now,
            )
        )
        session.flush()
        session.add(
            RunStepModel(
                id=step_id,
                run_id=run_id,
                position=0,
                key="reasoning_literature",
                label="Reason literature",
                enter_status="reasoning_literature",
                success_status="building_graph",
                status="running",
                progress=50,
                public_message="Publishing",
                created_at=now,
            )
        )
        session.flush()
        session.add(
            StepAttemptModel(
                id=attempt_id,
                run_step_id=step_id,
                attempt_number=1,
                idempotency_key=f"literature_api-publisher-attempt-{run_id}",
                status="running",
                started_at=now,
                created_at=now,
            )
        )
        session.flush()
        session.add(
            ResearchArtifactModel(
                id=artifact_id,
                project_id=project_id,
                kind="literature_claims",
                title="Atomic literature claims",
                logical_key=f"literature_claims.atomic.{run_id}",
                created_at=now,
            )
        )
        session.flush()
        producer = candidate.producer
        session.add(
            ProducerExecutionModel(
                id=producer_id,
                run_id=run_id,
                run_step_id=step_id,
                step_attempt_id=attempt_id,
                step_key=producer.step_key,
                idempotency_key=f"literature_api-publisher-producer-{run_id}",
                lease_generation=1,
                producer_type=producer.producer_type,
                producer_name=producer.producer_name,
                producer_version=producer.producer_version,
                requested_model=producer.model_name,
                prompt_name=producer.prompt_name,
                prompt_version=producer.prompt_version,
                prompt_hash=producer.prompt_hash,
                parameters={},
                parameters_hash=producer.parameters_hash,
                input_hash=candidate.input_hash,
                output_hash=content_hash,
                status="completed",
                started_at=now,
                finished_at=now,
                latency_ms=0,
                created_at=now,
            )
        )

    source_bindings = tuple(
        ArtifactSourceSnapshotBinding(
            pipeline_source_snapshot_id=item,
            persisted_source_snapshot_id=atomic_snapshot_ids[item],
        )
        for item in candidate.source_snapshot_ids
    )
    evidence_bindings = tuple(
        ArtifactEvidenceBinding(
            target_type="claim",
            target_id=item.claim_id,
            pipeline_evidence_id=item.evidence_id,
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_evidence_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"atomic:{run_id}:{item.claim_id}:{item.evidence_id}",
                )
            ),
            persisted_source_snapshot_id=atomic_snapshot_ids[item.source_snapshot_id],
        )
        for item in candidate.evidence_references
    )
    admitted = admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=lambda _context: None,
        domain_validator=lambda _context: None,
        quality_validator=lambda _context: None,
        source_snapshot_bindings=source_bindings,
        evidence_bindings=evidence_bindings,
    )
    result = ArtifactPublisher(factory).publish_step_outputs(
        run_id,
        step_key="reasoning_literature",
        attempt_id=attempt_id,
        token=lease_token,
        generation=1,
        expected_status="reasoning_literature",
        expected_revision=1,
        publications=(
            ArtifactPublication(
                artifact_id=artifact_id,
                publication_key=f"atomic-{run_id}",
                producer_execution_id=producer_id,
                candidate=admitted,
                source_mode="fixture",
            ),
        ),
        public_message="Published atomically",
    )
    version_id = result.versions[0].id
    with factory() as session:
        persisted = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.artifact_version_id == version_id
                )
            )
        )
    assert {str(item.id) for item in persisted} == set(admitted.evidence_ids)
    assert all(item.artifact_version_id == version_id for item in persisted)
    response = literature_context["owner"].get(
        f"/api/artifact-versions/{version_id}/literature-claims"
    )
    assert response.status_code == 200
    assert response.json()["data"]
