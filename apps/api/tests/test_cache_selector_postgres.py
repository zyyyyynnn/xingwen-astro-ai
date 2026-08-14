"""PostgreSQL contract tests for CacheRecord and recoverable-failure selection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app.db.models import (
    ArtifactVersionModel,
    CacheRecordModel,
    CacheSelectionAuditModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    SourceSnapshotModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.data_quality import DataQualityProjection
from app.workflow.cache import (
    CacheRecordAdmissionError,
    CacheRecordStore,
    CacheSelectionNotAllowedError,
    CacheSelector,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
PARAMETERS = {"temperature": 0}
PARAMETERS_HASH = compute_canonical_payload_hash(PARAMETERS)
ARTIFACT_KINDS = (
    "dataset",
    "field_dictionary",
    "source_collection",
    "paper_collection",
    "paper_summary",
    "literature_relations",
    "reasoning_traces",
    "graph",
)


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def _contract_input(
    artifact_kind: str,
    *,
    research_goal: str = "Reuse a strictly matching historical astronomy result",
    allowed_sources: tuple[str, ...] = ("nasa_exoplanet_archive",),
    evidence_minimum: float = 1.0,
    completeness_minimum: float = 1.0,
) -> ResearchContractInput:
    return ResearchContractInput.model_validate(
        {
            "research_goal": research_goal,
            "target_objects": ["host_star"],
            "data_requirements": {"unit_policy": "canonical"},
            "requested_fields": ["star.mass"],
            "source_scope": {"allowed_sources": list(allowed_sources)},
            "paper_search_scope": {"max_candidates": 20},
            "output_requirements": [artifact_kind],
            "evidence_requirements": {
                "require_locator": True,
                "require_source_snapshot": True,
                "minimum_coverage": evidence_minimum,
            },
            "quality_constraints": {
                "source_completeness_min": completeness_minimum,
                "unit_consistency_min": 1.0,
            },
        }
    )


def _persist_contract(
    session,
    *,
    project: ResearchProjectModel,
    value: ResearchContractInput,
    version: int,
) -> ResearchContractModel:
    now = datetime.now(UTC)
    draft = ResearchContractDraftModel(
        id=uuid4(),
        project_id=project.id,
        session_id=project.session_id,
        version=version,
        intent=f"cache test contract {version}",
        status="confirmed",
        contract=value.model_dump(mode="json"),
        warnings=[],
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=1),
        idempotency_key=f"cache-draft-{uuid4()}",
        request_hash=HASH_A,
    )
    contract = ResearchContractModel(
        id=uuid4(),
        project_id=project.id,
        version=version,
        content_hash=compute_research_contract_content_hash(value),
        content=value.model_dump(mode="json"),
        created_from_draft_id=draft.id,
        idempotency_key=f"cache-contract-{uuid4()}",
        request_hash=HASH_B,
    )
    session.add(draft)
    session.flush()
    session.add(contract)
    session.flush()
    return contract


def _quality_projection(
    contract: ResearchContractModel,
    *,
    artifact_kind: str,
    content_hash: str,
) -> DataQualityProjection:
    payload = {
        "schema_version": "1.0.0",
        "candidate_kind": artifact_kind,
        "candidate_id": f"candidate-{uuid4()}",
        "candidate_input_hash": HASH_B,
        "candidate_output_hash": content_hash,
        "candidate_content_hash": content_hash,
        "quality_input_hash": HASH_A,
        "quality_result_id": f"quality-{uuid4()}",
        "quality_result_input_hash": HASH_A,
        "quality_result_output_hash": HASH_B,
        "quality_result_content_hash": HASH_C,
        "evaluation_plan_content_hash": HASH_A,
        "evaluation_commitment": HASH_B,
        "bundle_commitment": HASH_C,
        "rule_set": {"id": "rules", "version": "1.0.0", "content_hash": HASH_A},
        "research_contract": {
            "id": str(contract.id),
            "version": contract.version,
            "content_hash": contract.content_hash,
        },
        "overall_status": "pass",
    }
    payload["content_hash"] = compute_canonical_payload_hash(payload)
    return DataQualityProjection.model_validate(payload)


def _producer_values(*, status: str, output_hash: str | None) -> dict[str, object]:
    return {
        "producer_type": "model",
        "producer_name": "cache-test-producer",
        "producer_version": "1.0.0",
        "model_provider": "test-provider",
        "model_name": "test-model",
        "prompt_name": "artifact-generation",
        "prompt_version": "1.0.0",
        "prompt_hash": HASH_A,
        "parameters": PARAMETERS,
        "parameters_hash": PARAMETERS_HASH,
        "input_hash": HASH_B,
        "output_hash": output_hash,
        "status": status,
    }


def _public_producer(values: dict[str, object]) -> dict[str, object]:
    return {
        "type": values["producer_type"],
        "name": values["producer_name"],
        "version": values["producer_version"],
        "parameters_hash": values["parameters_hash"],
        "model_provider": values["model_provider"],
        "model_name": values["model_name"],
        "prompt_name": values["prompt_name"],
        "prompt_version": values["prompt_version"],
        "prompt_hash": values["prompt_hash"],
    }


def _persist_run_execution(
    session,
    *,
    project: ResearchProjectModel,
    contract: ResearchContractModel,
    completed: bool,
    cache_policy: str,
) -> tuple[ResearchRunModel, RunStepModel, StepAttemptModel, ProducerExecutionModel]:
    now = datetime.now(UTC)
    run = ResearchRunModel(
        id=uuid4(),
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        status="completed" if completed else "failed",
        progress=100 if completed else 35,
        derivation_kind="original",
        cache_policy=cache_policy,
        started_at=now - timedelta(seconds=5),
        finished_at=now,
        latest_event_sequence=1,
        failure_code=None if completed else "UPSTREAM_TIMEOUT",
        failure_summary=None if completed else "Live source timed out",
        revision=1,
        lease_generation=1,
        idempotency_key=f"cache-run-{uuid4()}",
        request_hash=HASH_C,
    )
    session.add(run)
    session.flush()
    step = RunStepModel(
        id=uuid4(),
        run_id=run.id,
        position=0,
        key="planning",
        label="Planning",
        enter_status="planning",
        success_status="completed",
        max_attempts=1,
        status="completed" if completed else "failed",
        progress=100 if completed else 35,
        started_at=now - timedelta(seconds=4),
        finished_at=now,
        input_hash=HASH_B,
        failure_code=None if completed else "UPSTREAM_TIMEOUT",
        public_message="Completed" if completed else "Live source timed out",
    )
    session.add(step)
    session.flush()
    attempt = StepAttemptModel(
        id=uuid4(),
        run_step_id=step.id,
        attempt_number=1,
        idempotency_key=f"cache-attempt-{uuid4()}",
        status="completed" if completed else "failed",
        started_at=now - timedelta(seconds=3),
        finished_at=now,
        error_class=None if completed else "TimeoutError",
        error_code=None if completed else "UPSTREAM_TIMEOUT",
        retryable=not completed,
        upstream_request_id=None if completed else "upstream-cache-test",
    )
    session.add(attempt)
    session.flush()
    content_hash = compute_canonical_payload_hash({"kind": "placeholder"})
    producer_values = _producer_values(
        status="completed" if completed else "failed",
        output_hash=content_hash if completed else None,
    )
    producer = ProducerExecutionModel(
        id=uuid4(),
        run_id=run.id,
        run_step_id=step.id,
        step_attempt_id=attempt.id,
        step_key=step.key,
        idempotency_key=f"cache-producer-{uuid4()}",
        lease_generation=1,
        started_at=now - timedelta(seconds=2),
        finished_at=now,
        error_code=None if completed else "UPSTREAM_TIMEOUT",
        **producer_values,
    )
    session.add(producer)
    session.add(
        RunEventModel(
            run_id=run.id,
            sequence=1,
            event_type="run.completed" if completed else "run.failed",
            step_key=step.key,
            progress=run.progress,
            public_message="Run completed" if completed else "Live source timed out",
            artifact_version_ids=[],
        )
    )
    session.flush()
    return run, step, attempt, producer


def _seed_case(
    engine: Engine,
    artifact_kind: str,
    *,
    current_contract: ResearchContractInput | None = None,
    current_cache_policy: str = "fallback_on_recoverable_failure",
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    factory = session_factory(engine)
    with factory() as session, session.begin():
        project = ResearchProjectModel(
            id=uuid4(),
            session_id=f"cache-session-{uuid4()}",
            name="Cache selector test",
            description="",
            case_key="exoplanet_host_star",
            revision=1,
            idempotency_key=f"cache-project-{uuid4()}",
            request_hash=HASH_A,
        )
        session.add(project)
        session.flush()
        origin_input = _contract_input(artifact_kind)
        origin_contract = _persist_contract(
            session, project=project, value=origin_input, version=1
        )
        selected_input = current_contract or origin_input
        if selected_input == origin_input:
            selected_contract = origin_contract
        else:
            selected_contract = _persist_contract(
                session, project=project, value=selected_input, version=2
            )
        origin_run, origin_step, origin_attempt, origin_producer = (
            _persist_run_execution(
                session,
                project=project,
                contract=origin_contract,
                completed=True,
                cache_policy="disabled",
            )
        )
        failed_run, _, _, failed_producer = _persist_run_execution(
            session,
            project=project,
            contract=selected_contract,
            completed=False,
            cache_policy=current_cache_policy,
        )
        content = {"kind": artifact_kind}
        content_hash = compute_canonical_payload_hash(content)
        origin_producer.output_hash = content_hash
        snapshot = SourceSnapshotModel(
            id=uuid4(),
            project_id=project.id,
            source_id="nasa_exoplanet_archive",
            source_type="api",
            retrieved_at=datetime.now(UTC),
            query={"target": "host_star"},
            query_hash=HASH_A,
            source_version_or_etag="test-etag",
            content_hash=HASH_B,
            license_note="public test source",
            request_metadata={"source_mode": "live"},
        )
        evidence_id = uuid4()
        artifact = ResearchArtifactModel(
            id=uuid4(),
            project_id=project.id,
            kind=artifact_kind,
            title=f"Cache {artifact_kind}",
            logical_key=f"cache.{artifact_kind}.{uuid4()}",
        )
        session.add_all((snapshot, artifact))
        session.flush()
        projection = (
            _quality_projection(
                origin_contract,
                artifact_kind=artifact_kind,
                content_hash=content_hash,
            )
            if artifact_kind in {"dataset", "field_dictionary", "source_collection"}
            else None
        )
        version = ArtifactVersionModel(
            id=uuid4(),
            artifact_id=artifact.id,
            project_id=project.id,
            created_by_run_id=origin_run.id,
            run_step_id=origin_step.id,
            step_attempt_id=origin_attempt.id,
            producer_execution_id=origin_producer.id,
            version_number=1,
            publication_key=f"cache-publication-{uuid4()}",
            schema_version="1.0.0",
            content=content,
            content_hash=content_hash,
            input_hash=HASH_B,
            source_mode="live",
            producer=_public_producer(_producer_values(status="completed", output_hash=content_hash)),
            source_snapshot_ids=[str(snapshot.id)],
            evidence_ids=[str(evidence_id)],
            quality_projection=(
                projection.model_dump(mode="json") if projection is not None else None
            ),
            quality_projection_hash=(
                projection.content_hash if projection is not None else None
            ),
        )
        session.add(version)
        session.flush()
        session.add(
            EvidenceModel(
                id=evidence_id,
                project_id=project.id,
                artifact_version_id=version.id,
                target_type="artifact",
                target_id=str(artifact.id),
                evidence_type="source_record",
                source_snapshot_id=snapshot.id,
                locator={"row": 1},
                quote_or_value={"value": "test"},
                extraction_method="cache-test",
                confidence=1.0,
                is_restricted=False,
            )
        )
        artifact.latest_version_id = version.id
        session.flush()
        return (
            project.id,
            failed_run.id,
            origin_run.id,
            version.id,
            failed_producer.id,
        )


@pytest.mark.parametrize("artifact_kind", ARTIFACT_KINDS)
def test_selector_hits_all_governed_artifact_families_without_republishing(
    postgres_engine: Engine, artifact_kind: str
) -> None:
    project_id, failed_run_id, origin_run_id, version_id, producer_id = _seed_case(
        postgres_engine, artifact_kind
    )
    factory = session_factory(postgres_engine)
    record = CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    with factory() as session:
        version_count = session.scalar(select(func.count()).select_from(ArtifactVersionModel))

    result = CacheSelector(factory).select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind=artifact_kind,
        failed_producer_execution_id=producer_id,
    )

    assert result.outcome == "selected"
    assert result.reason == "CACHE_SELECTED"
    assert result.failed_producer_execution_id == producer_id
    assert result.cache_record_id == record.id
    assert result.origin_run_id == origin_run_id
    assert result.origin_artifact_version_id == version_id
    assert result.live_failure_code == "UPSTREAM_TIMEOUT"
    assert record.source_snapshot_hash.startswith("sha256:")
    with factory() as session:
        failed_run = session.get(ResearchRunModel, failed_run_id)
        origin_run = session.get(ResearchRunModel, origin_run_id)
        events = tuple(
            session.scalars(
                select(RunEventModel)
                .where(RunEventModel.run_id == failed_run_id)
                .order_by(RunEventModel.sequence)
            )
        )
        assert failed_run is not None and failed_run.status == "failed"
        assert failed_run.failure_code == "UPSTREAM_TIMEOUT"
        assert origin_run is not None and origin_run.status == "completed"
        assert [event.event_type for event in events] == ["run.failed", "cache.selected"]
        assert events[-1].artifact_version_ids == [str(version_id)]
        assert session.scalar(select(func.count()).select_from(ArtifactVersionModel)) == version_count
        assert session.scalar(
            select(func.count()).select_from(CacheSelectionAuditModel).where(
                CacheSelectionAuditModel.run_id == failed_run_id
            )
        ) == 1
        assert record.project_id == project_id


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("contract", "CACHE_CONTRACT_MISMATCH"),
        ("input", "CACHE_INPUT_MISMATCH"),
        ("prompt", "CACHE_PROMPT_IDENTITY_MISMATCH"),
        ("source", "CACHE_SOURCE_SCOPE_MISMATCH"),
        ("quality", "CACHE_QUALITY_CONSTRAINTS_MISMATCH"),
        ("evidence", "CACHE_EVIDENCE_REQUIREMENTS_MISMATCH"),
    ),
)
def test_selector_records_stable_strict_mismatch_reasons(
    postgres_engine: Engine, mutation: str, expected_reason: str
) -> None:
    kind = "paper_summary"
    current_contract = None
    if mutation == "contract":
        current_contract = _contract_input(
            kind, research_goal="A materially different current research objective"
        )
    elif mutation == "source":
        current_contract = _contract_input(kind, allowed_sources=("crossref",))
    elif mutation == "quality":
        current_contract = _contract_input(kind, completeness_minimum=0.75)
    elif mutation == "evidence":
        current_contract = _contract_input(kind, evidence_minimum=0.5)
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, kind, current_contract=current_contract
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    if mutation in {"input", "prompt"}:
        with factory() as session, session.begin():
            producer = session.scalar(
                select(ProducerExecutionModel)
                .where(
                    ProducerExecutionModel.run_id == failed_run_id,
                    ProducerExecutionModel.status == "failed",
                )
            )
            assert producer is not None
            if mutation == "input":
                producer.input_hash = HASH_C
                step = session.get(RunStepModel, producer.run_step_id)
                assert step is not None
                step.input_hash = HASH_C
            else:
                producer.prompt_version = "2.0.0"

    result = CacheSelector(factory).select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind=kind,
        failed_producer_execution_id=producer_id,
    )

    assert result.outcome == "rejected"
    assert result.reason == expected_reason
    assert result.origin_artifact_version_id is None
    with factory() as session:
        events = tuple(
            session.scalars(
                select(RunEventModel)
                .where(RunEventModel.run_id == failed_run_id)
                .order_by(RunEventModel.sequence)
            )
        )
        assert [event.event_type for event in events] == ["run.failed", "cache.rejected"]


def test_selector_rejects_expired_record_with_injected_clock(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "graph"
    )
    factory = session_factory(postgres_engine)
    expires_at = datetime.now(UTC) + timedelta(days=1)
    CacheRecordStore(factory).register(version_id, expires_at=expires_at)
    selector = CacheSelector(factory, clock=lambda _: expires_at + timedelta(seconds=1))

    result = selector.select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind="graph",
        failed_producer_execution_id=producer_id,
    )

    assert result.outcome == "rejected"
    assert result.reason == "CACHE_RECORD_EXPIRED"


@pytest.mark.parametrize(
    "origin_mutation",
    ("fixture", "cached", "failed", "failed_attempt", "no_sources"),
)
def test_cache_record_admission_rejects_non_live_or_incomplete_provenance(
    postgres_engine: Engine, origin_mutation: str
) -> None:
    _, _, origin_run_id, version_id, _ = _seed_case(
        postgres_engine, "paper_collection"
    )
    factory = session_factory(postgres_engine)
    with factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, version_id)
        run = session.get(ResearchRunModel, origin_run_id)
        assert version is not None and run is not None
        if origin_mutation in {"fixture", "cached"}:
            version.source_mode = origin_mutation
        elif origin_mutation == "failed":
            run.status = "failed"
            run.progress = 25
            run.failure_code = "UPSTREAM_FAILURE"
            run.failure_summary = "failed"
        elif origin_mutation == "failed_attempt":
            attempt = session.get(StepAttemptModel, version.step_attempt_id)
            assert attempt is not None
            attempt.status = "failed"
            attempt.error_class = "TimeoutError"
            attempt.error_code = "UPSTREAM_TIMEOUT"
            attempt.retryable = True
        else:
            version.source_snapshot_ids = []
            version.evidence_ids = []

    with pytest.raises(CacheRecordAdmissionError):
        CacheRecordStore(factory).register(
            version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
        )


def test_cache_record_admission_rejects_quality_projection_not_bound_to_version(
    postgres_engine: Engine,
) -> None:
    _, _, _, version_id, _ = _seed_case(postgres_engine, "dataset")
    factory = session_factory(postgres_engine)
    with factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, version_id)
        assert version is not None and version.quality_projection is not None
        projection = dict(version.quality_projection)
        projection["candidate_content_hash"] = HASH_C
        projection["content_hash"] = compute_canonical_payload_hash(
            {key: value for key, value in projection.items() if key != "content_hash"}
        )
        version.quality_projection = projection
        version.quality_projection_hash = projection["content_hash"]

    with pytest.raises(CacheRecordAdmissionError, match="quality projection"):
        CacheRecordStore(factory).register(
            version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
        )


def test_cache_policy_and_recoverability_fail_closed_without_audit(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "graph", current_cache_policy="disabled"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    with pytest.raises(CacheSelectionNotAllowedError, match="policy"):
        CacheSelector(factory).select_for_failed_run(
            failed_run_id,
            step_key="planning",
            artifact_kind="graph",
            failed_producer_execution_id=producer_id,
        )

    with factory() as session:
        run = session.get(ResearchRunModel, failed_run_id)
        assert run is not None and run.latest_event_sequence == 1
        assert session.scalar(
            select(func.count()).select_from(CacheSelectionAuditModel).where(
                CacheSelectionAuditModel.run_id == failed_run_id
            )
        ) == 0


def test_nonrecoverable_failure_fails_closed_without_candidate_query_or_audit(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "graph"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    with factory() as session, session.begin():
        producer = session.get(ProducerExecutionModel, producer_id)
        assert producer is not None
        attempt = session.get(StepAttemptModel, producer.step_attempt_id)
        assert attempt is not None
        attempt.retryable = False

    with pytest.raises(CacheSelectionNotAllowedError, match="recoverable"):
        CacheSelector(factory).select_for_failed_run(
            failed_run_id,
            step_key="planning",
            artifact_kind="graph",
            failed_producer_execution_id=producer_id,
        )

    with factory() as session:
        run = session.get(ResearchRunModel, failed_run_id)
        assert run is not None and run.latest_event_sequence == 1
        assert session.scalar(
            select(func.count()).select_from(CacheSelectionAuditModel).where(
                CacheSelectionAuditModel.run_id == failed_run_id
            )
        ) == 0


def test_selector_rejects_a_failed_producer_from_another_run(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, _ = _seed_case(postgres_engine, "graph")
    _, _, _, _, foreign_producer_id = _seed_case(postgres_engine, "graph")
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    with pytest.raises(CacheSelectionNotAllowedError, match="ProducerExecution"):
        CacheSelector(factory).select_for_failed_run(
            failed_run_id,
            step_key="planning",
            artifact_kind="graph",
            failed_producer_execution_id=foreign_producer_id,
        )


def test_selector_revalidates_origin_provenance_before_hit(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "reasoning_traces"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    with factory() as session, session.begin():
        version = session.get(ArtifactVersionModel, version_id)
        assert version is not None
        snapshot = session.get(SourceSnapshotModel, UUID(version.source_snapshot_ids[0]))
        assert snapshot is not None
        snapshot.content_hash = HASH_C

    result = CacheSelector(factory).select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind="reasoning_traces",
        failed_producer_execution_id=producer_id,
    )

    assert result.outcome == "rejected"
    assert result.reason == "CACHE_PROVENANCE_INVALID"


def test_concurrent_selector_is_idempotent_and_does_not_publish(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, origin_run_id, version_id, producer_id = _seed_case(
        postgres_engine, "literature_relations"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    barrier = Barrier(2)

    def select_cache():
        barrier.wait()
        return CacheSelector(factory).select_for_failed_run(
            failed_run_id,
            step_key="planning",
            artifact_kind="literature_relations",
            failed_producer_execution_id=producer_id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: select_cache(), range(2)))

    assert results[0].audit_id == results[1].audit_id
    assert {result.replayed for result in results} == {False, True}
    assert all(result.origin_run_id == origin_run_id for result in results)
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(CacheSelectionAuditModel).where(
                CacheSelectionAuditModel.run_id == failed_run_id
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(RunEventModel).where(
                RunEventModel.run_id == failed_run_id,
                RunEventModel.event_type == "cache.selected",
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(ArtifactVersionModel).where(
                ArtifactVersionModel.created_by_run_id == failed_run_id
            )
        ) == 0


def test_cache_records_are_database_immutable(postgres_engine: Engine) -> None:
    _, _, _, version_id, _ = _seed_case(postgres_engine, "paper_summary")
    factory = session_factory(postgres_engine)
    record = CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )

    with pytest.raises(ProgrammingError, match="cache records are immutable"):
        with factory() as session, session.begin():
            row = session.get(CacheRecordModel, record.id)
            assert row is not None
            row.expires_at += timedelta(days=1)
            session.flush()


def test_cache_selection_audits_are_database_immutable(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "graph"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    result = CacheSelector(factory).select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind="graph",
        failed_producer_execution_id=producer_id,
    )

    with pytest.raises(ProgrammingError, match="cache records are immutable"):
        with factory() as session, session.begin():
            row = session.get(CacheSelectionAuditModel, result.audit_id)
            assert row is not None
            row.reason = "CACHE_RECORD_NOT_FOUND"
            session.flush()


def test_cache_selection_audit_rejects_mismatched_origin_closure(
    postgres_engine: Engine,
) -> None:
    _, failed_run_id, _, version_id, producer_id = _seed_case(
        postgres_engine, "graph"
    )
    factory = session_factory(postgres_engine)
    CacheRecordStore(factory).register(
        version_id, expires_at=datetime.now(UTC) + timedelta(days=1)
    )
    result = CacheSelector(factory).select_for_failed_run(
        failed_run_id,
        step_key="planning",
        artifact_kind="graph",
        failed_producer_execution_id=producer_id,
    )

    with pytest.raises(IntegrityError, match="fk_cache_audits_record_origin_closure"):
        with factory() as session, session.begin():
            selected = session.get(CacheSelectionAuditModel, result.audit_id)
            assert selected is not None
            session.add(
                CacheSelectionAuditModel(
                    id=uuid4(),
                    project_id=selected.project_id,
                    run_id=selected.run_id,
                    run_step_id=selected.run_step_id,
                    failed_producer_execution_id=(
                        selected.failed_producer_execution_id
                    ),
                    request_hash=HASH_A,
                    selector_identity_hash=selected.selector_identity_hash,
                    outcome="selected",
                    reason="CACHE_SELECTED",
                    cache_record_id=selected.cache_record_id,
                    origin_run_id=failed_run_id,
                    origin_artifact_version_id=(
                        selected.origin_artifact_version_id
                    ),
                    live_failure_class=selected.live_failure_class,
                    live_failure_code=selected.live_failure_code,
                    event_sequence=selected.event_sequence,
                )
            )
            session.flush()
