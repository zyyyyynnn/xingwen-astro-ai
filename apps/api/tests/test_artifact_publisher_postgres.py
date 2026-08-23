"""PostgreSQL transaction, fencing, and concurrency tests for Atomic Publisher.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import timedelta
import os
from threading import Barrier
from uuid import UUID, uuid4

import pytest

from db_bootstrap import reset_current_schema
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from artifact_publication_test_support import (
    build_reference_dataset_candidate,
    publish_reference_dataset,
)
from app.workflow.publisher import (
    ArtifactPublication,
    ArtifactPublisher,
    ProducerExecutionConflictError,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    PublicationConflictError,
    PublicationResult,
    StalePublicationError,
    admit_artifact_candidate,
)
from app.schemas.core import ArtifactKind, ExportArtifactContent
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
HASH_A = "sha256:" + "a" * 64


def _accept(_: object) -> None:
    return None


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


def _steps() -> tuple[RunStepDefinition, ...]:
    transitions = (
        ("planning", "fetching_data"),
        ("fetching_data", "cleaning_data"),
        ("cleaning_data", "searching_papers"),
        ("searching_papers", "summarizing_papers"),
        ("summarizing_papers", "reasoning_literature"),
        ("reasoning_literature", "building_graph"),
        ("building_graph", "completed"),
    )
    return tuple(
        RunStepDefinition(
            key=enter,
            label=enter.replace("_", " ").title(),
            enter_status=enter,
            success_status=success,
            max_attempts=2,
        )
        for enter, success in transitions
    )


def _seed_project(
    factory: Callable[[], Session],
) -> tuple[ResearchProjectModel, ResearchContractModel]:
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Atomic Publisher integration",
        case_key="exoplanet_host_star",
    )
    draft = build_contract_draft(project)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=HASH_A,
    )
    with factory() as session, session.begin():
        persist_authoring_models(
            session, project=project, draft=draft, contract=contract
        )
    return project, contract


def _create_artifact(
    factory: Callable[[], Session],
    *,
    project_id: UUID,
    logical_key: str,
    kind: str = "export",
) -> ResearchArtifactModel:
    artifact = ResearchArtifactModel(
        id=uuid4(),
        project_id=project_id,
        kind=kind,
        title=logical_key,
        logical_key=logical_key,
    )
    with factory() as session, session.begin():
        session.add(artifact)
    return artifact


def _admit(*, reference_version_id: UUID, export_format: str = "json"):
    return admit_artifact_candidate(
        ExportArtifactContent(
            kind=ArtifactKind.export,
            format=export_format,
            artifact_version_ids=(str(reference_version_id),),
        ),
        schema_version="2.0.0",
        source_snapshot_ids=(),
        evidence_ids=(),
        evidence_validator=_accept,
        domain_validator=_accept,
        quality_validator=_accept,
    )


def _seed_reference_version(
    *,
    factory: Callable[[], Session],
    project: ResearchProjectModel,
) -> UUID:
    return publish_reference_dataset(
        factory=factory,
        project=project,
    )


@dataclass(frozen=True, slots=True)
class ActivePublication:
    factory: Callable[[], Session]
    workflow: PersistentWorkflowStore
    ledger: ProducerExecutionStore
    publisher: ArtifactPublisher
    project: ResearchProjectModel
    contract: ResearchContractModel
    artifact: ResearchArtifactModel
    run_id: UUID
    token: UUID
    generation: int
    attempt_id: UUID
    run_status: str
    run_revision: int
    reference_version_id: UUID
    execution_id: UUID
    publication: ArtifactPublication


def _active_publication(
    engine: Engine,
    *,
    project: ResearchProjectModel | None = None,
    contract: ResearchContractModel | None = None,
    artifact: ResearchArtifactModel | None = None,
    revision: int = 1,
    publication_key: str | None = None,
    finish_status: str = "completed",
) -> ActivePublication:
    factory = session_factory(engine)
    if project is None or contract is None:
        project, contract = _seed_project(factory)
    reference_version_id = _seed_reference_version(
        factory=factory,
        project=project,
    )
    workflow = PersistentWorkflowStore(factory)
    snapshot = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=_steps(),
    )
    lease = workflow.acquire_lease(
        snapshot.id,
        owner=f"publisher-{uuid4()}",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = workflow.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    if artifact is None:
        artifact = _create_artifact(
            factory,
            project_id=project.id,
            logical_key=f"artifact-{uuid4()}",
        )
    ledger = ProducerExecutionStore(factory)
    candidate = _admit(reference_version_id=reference_version_id)
    request = ProducerExecutionRequest(
        run_id=snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        idempotency_key=f"producer-{uuid4()}",
        producer_type="pipeline",
        producer_name="fixture-data-port",
        producer_version="1.0.0",
        input_hash="sha256:" + "c" * 64,
        parameters={"page_size": 20, "strict": True},
    )
    execution = ledger.start_producer_execution(
        request,
        token=lease.token,
        generation=lease.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    ledger.finish_producer_execution(
        execution.id,
        status=finish_status,
        output_hash=candidate.content_hash,
        token_usage={"records": 1},
        latency_ms=12,
        error_code=(None if finish_status == "completed" else "CANDIDATE_REJECTED"),
    )
    return ActivePublication(
        factory=factory,
        workflow=workflow,
        ledger=ledger,
        publisher=ArtifactPublisher(factory),
        project=project,
        contract=contract,
        artifact=artifact,
        run_id=snapshot.id,
        token=lease.token,
        generation=lease.generation,
        attempt_id=attempt.attempt_id,
        run_status=attempt.run_status,
        run_revision=attempt.run_revision,
        reference_version_id=reference_version_id,
        execution_id=execution.id,
        publication=ArtifactPublication(
            artifact_id=artifact.id,
            publication_key=publication_key or f"publication-{uuid4()}",
            producer_execution_id=execution.id,
            candidate=candidate,
            source_mode="fixture",
        ),
    )


def _publish(active: ActivePublication) -> PublicationResult:
    return active.publisher.publish_step_outputs(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        publications=(active.publication,),
        public_message="Planning artifacts published",
    )


def test_producer_execution_is_idempotent_auditable_and_secret_free(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    with active.factory() as session:
        execution = session.get(ProducerExecutionModel, active.execution_id)
        assert execution is not None
        assert execution.step_attempt_id == active.attempt_id
        assert execution.status == "completed"
        assert execution.parameters == {"page_size": 20, "strict": True}
        assert execution.parameters_hash.startswith("sha256:")
        assert execution.output_hash == active.publication.candidate.content_hash
        assert execution.error_code is None
        assert "api_key" not in repr(execution.__dict__)

    request = ProducerExecutionRequest(
        run_id=active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        idempotency_key="conflicting-key",
        producer_type="pipeline",
        producer_name="fixture-data-port",
        producer_version="1.0.0",
        input_hash="sha256:" + "c" * 64,
        parameters={"page_size": 20},
    )
    first = active.ledger.start_producer_execution(
        request,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    replay = active.ledger.start_producer_execution(
        request,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    assert replay.id == first.id
    with pytest.raises(ProducerExecutionConflictError):
        active.ledger.start_producer_execution(
            replace(request, parameters={"page_size": 100}),
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision,
        )


def _assert_publication_not_started(active: ActivePublication) -> None:
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        assert artifact is not None and artifact.latest_version_id is None
        assert run is not None and run.status == active.run_status
        assert step is not None and step.status == "running"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(
                    RunEventModel.run_id == active.run_id,
                    RunEventModel.step_key == "planning",
                    RunEventModel.activity_phase == "completed",
                    RunEventModel.activity_kind.in_(("artifact", "tool")),
                )
            )
            == 0
        )


@pytest.mark.parametrize("status", ("failed", "rejected"))
def test_failed_and_rejected_executions_are_retained_without_versions(
    postgres_engine: Engine, status: str
) -> None:
    active = _active_publication(postgres_engine, finish_status=status)
    with pytest.raises(PublicationAdmissionError):
        _publish(active)
    with active.factory() as session:
        execution = session.get(ProducerExecutionModel, active.execution_id)
        assert execution is not None and execution.status == status
        assert execution.error_code == "CANDIDATE_REJECTED"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )
        assert (
            session.get(ResearchArtifactModel, active.artifact.id).latest_version_id
            is None
        )


def test_publication_is_atomic_and_idempotent_with_a_stable_conflict(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    first = _publish(active)
    replay = _publish(active)
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.versions == first.versions
    with active.factory() as session:
        version = session.get(ArtifactVersionModel, first.versions[0].id)
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        attempt = session.get(StepAttemptModel, active.attempt_id)
        event = session.scalar(
            select(RunEventModel).where(
                RunEventModel.run_id == active.run_id,
                RunEventModel.step_key == "planning",
                RunEventModel.activity_phase == "completed",
                RunEventModel.activity_kind.in_(("artifact", "tool")),
            )
        )
        assert version is not None and version.version_number == 1
        assert artifact is not None and artifact.latest_version_id == version.id
        assert run is not None and run.status == "fetching_data"
        assert step is not None and step.status == "completed"
        assert attempt is not None and attempt.status == "completed"
        assert event is not None and event.artifact_version_ids == [str(version.id)]

    changed = replace(
        active.publication,
        candidate=_admit(
            reference_version_id=active.reference_version_id,
            export_format="csv",
        ),
    )
    with pytest.raises(PublicationConflictError):
        active.publisher.publish_step_outputs(
            active.run_id,
            step_key="planning",
            attempt_id=active.attempt_id,
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision,
            publications=(changed,),
            public_message="Conflicting replay",
        )


def test_export_publication_rejects_a_dangling_artifact_reference(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    invalid = replace(
        active,
        publication=replace(
            active.publication,
            candidate=_admit(reference_version_id=uuid4()),
        ),
    )

    with pytest.raises(
        PublicationAdmissionError,
        match="must resolve within the Run Project",
    ):
        _publish(invalid)
    _assert_publication_not_started(active)


def test_export_publication_rejects_a_cross_project_artifact_reference(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    other_project = _active_publication(postgres_engine)
    invalid = replace(
        active,
        publication=replace(
            active.publication,
            candidate=_admit(reference_version_id=other_project.reference_version_id),
        ),
    )

    with pytest.raises(
        PublicationAdmissionError,
        match="must resolve within the Run Project",
    ):
        _publish(invalid)
    _assert_publication_not_started(active)


def test_publication_rejects_a_candidate_for_the_wrong_artifact_kind(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"dataset-{uuid4()}",
        kind="dataset",
    )
    active = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
    )

    with pytest.raises(
        PublicationAdmissionError,
        match="must match its ResearchArtifact kind",
    ):
        _publish(active)
    _assert_publication_not_started(active)


def test_publication_rejects_a_dataset_candidate_for_an_export_artifact(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    invalid = replace(
        active,
        publication=replace(
            active.publication,
            candidate=build_reference_dataset_candidate(run_id=active.run_id),
        ),
    )

    with pytest.raises(
        PublicationAdmissionError,
        match="must match its ResearchArtifact kind",
    ):
        _publish(invalid)
    _assert_publication_not_started(active)


def test_dataset_without_persisted_provenance_rolls_back_publication(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"dataset-missing-provenance-{uuid4()}",
        kind="dataset",
    )
    active = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
    )
    candidate = build_reference_dataset_candidate(run_id=active.run_id)
    with factory() as session, session.begin():
        execution = session.get(ProducerExecutionModel, active.execution_id)
        assert execution is not None
        execution.input_hash = candidate.content["input_hash"]
        execution.output_hash = candidate.content_hash
    invalid = replace(
        active,
        publication=replace(active.publication, candidate=candidate),
    )

    with pytest.raises(
        PublicationAdmissionError,
        match="persisted Data Artifact SourceSnapshot binding was not found",
    ):
        _publish(invalid)

    _assert_publication_not_started(active)


def test_publication_rejects_dataset_with_mismatched_producer_input_hash(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"dataset-input-hash-mismatch-{uuid4()}",
        kind="dataset",
    )
    active = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
    )
    candidate = build_reference_dataset_candidate(run_id=active.run_id)
    with factory() as session, session.begin():
        execution = session.get(ProducerExecutionModel, active.execution_id)
        assert execution is not None
        execution.output_hash = candidate.content_hash
    invalid = replace(
        active,
        publication=replace(active.publication, candidate=candidate),
    )

    with pytest.raises(PublicationAdmissionError, match="input_hash"):
        _publish(invalid)

    _assert_publication_not_started(active)


class _FailingPublisher(ArtifactPublisher):
    def _before_commit(self, session: Session) -> None:
        raise RuntimeError("injected transaction failure")


def test_any_publication_write_failure_rolls_back_the_entire_snapshot(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    publisher = _FailingPublisher(active.factory)
    with pytest.raises(RuntimeError, match="injected"):
        publisher.publish_step_outputs(
            active.run_id,
            step_key="planning",
            attempt_id=active.attempt_id,
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision,
            publications=(active.publication,),
            public_message="Must roll back",
        )
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        attempt = session.get(StepAttemptModel, active.attempt_id)
        assert artifact is not None and artifact.latest_version_id is None
        assert run is not None and run.status == "planning"
        assert step is not None and step.status == "running"
        assert attempt is not None and attempt.status == "running"
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(
                    RunEventModel.run_id == active.run_id,
                    RunEventModel.step_key == "planning",
                    RunEventModel.activity_phase == "completed",
                    RunEventModel.activity_kind.in_(("artifact", "tool")),
                )
            )
            == 0
        )


def test_failed_run_rejects_late_output_without_updating_latest(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    active.workflow.fail_run(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        error_class="PipelineError",
        error_code="PIPELINE_FAILED",
        public_message="Pipeline failed",
    )
    with pytest.raises(StalePublicationError):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None and artifact.latest_version_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )


def test_cancelled_run_rejects_late_output_without_updating_latest(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    active.workflow.cancel_run(
        active.run_id,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    with pytest.raises(StalePublicationError):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None and artifact.latest_version_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )


def test_expired_lease_rejects_publication_without_updating_latest(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    with active.factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == active.run_id)
            .values(
                lease_expires_at=func.clock_timestamp() - text("INTERVAL '1 second'")
            )
        )
    with pytest.raises(StalePublicationError):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None and artifact.latest_version_id is None


def test_stale_revision_and_generation_reject_publication_without_updates(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    for revision, generation in (
        (active.run_revision - 1, active.generation),
        (active.run_revision, active.generation + 1),
    ):
        with pytest.raises(StalePublicationError):
            active.publisher.publish_step_outputs(
                active.run_id,
                step_key="planning",
                attempt_id=active.attempt_id,
                token=active.token,
                generation=generation,
                expected_status=active.run_status,
                expected_revision=revision,
                publications=(active.publication,),
                public_message="Stale publication",
            )
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        assert artifact is not None and artifact.latest_version_id is None
        assert run is not None and run.revision == active.run_revision


@pytest.mark.parametrize("terminal_status", ("failed", "completed"))
def test_terminal_run_rejects_new_publication_without_updating_latest(
    postgres_engine: Engine,
    terminal_status: str,
) -> None:
    active = _active_publication(postgres_engine)
    with active.factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == active.run_id)
            .values(
                status=terminal_status,
                progress=100 if terminal_status == "completed" else 0,
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                finished_at=func.clock_timestamp(),
            )
        )
    with pytest.raises(StalePublicationError):
        _publish(active)
    with active.factory() as session:
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        assert artifact is not None and artifact.latest_version_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(ArtifactVersionModel)
                .where(ArtifactVersionModel.artifact_id == active.artifact.id)
            )
            == 0
        )


def test_new_version_must_supersede_the_locked_latest_version(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"revision-artifact-{uuid4()}",
    )
    original = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
        revision=1,
        publication_key="original",
    )
    version_one = _publish(original).versions[0]
    with factory() as session, session.begin():
        orig_run = session.get(ResearchRunModel, original.run_id)
        if orig_run is not None:
            orig_run.status = "completed"
    revision = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
        revision=2,
        publication_key="revision",
    )
    with pytest.raises(PublicationConflictError, match="supersedes"):
        _publish(revision)

    revision_publication = replace(
        revision.publication,
        supersedes_version_id=version_one.id,
    )
    result = revision.publisher.publish_step_outputs(
        revision.run_id,
        step_key="planning",
        attempt_id=revision.attempt_id,
        token=revision.token,
        generation=revision.generation,
        expected_status=revision.run_status,
        expected_revision=revision.run_revision,
        publications=(revision_publication,),
        public_message="Revision published",
    )
    assert result.versions[0].version_number == 2
    assert result.versions[0].supersedes_version_id == version_one.id
    assert result.versions[0].source_mode == "fixture"
    with factory() as session:
        stored = session.get(ArtifactVersionModel, result.versions[0].id)
        latest = session.get(ResearchArtifactModel, artifact.id)
        assert stored is not None and stored.supersedes_version_id == version_one.id
        assert latest is not None and latest.latest_version_id == stored.id


def test_revision_bundle_rejects_one_stale_target_atomically(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifacts = {
        kind: _create_artifact(
            factory,
            project_id=project.id,
            logical_key=f"revision-{kind}-{uuid4()}",
        )
        for kind in ("dataset", "field_dictionary", "source_collection")
    }
    baseline_ids: dict[str, UUID] = {}
    for kind, artifact in artifacts.items():
        original = _active_publication(
            postgres_engine,
            project=project,
            contract=contract,
            artifact=artifact,
            publication_key=f"{kind}-initial",
        )
        baseline_ids[kind] = _publish(original).versions[0].id
        with factory() as session, session.begin():
            run = session.get(ResearchRunModel, original.run_id)
            assert run is not None
            run.status = "completed"

    revision = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifacts["dataset"],
        publication_key="dataset-revision",
    )
    publications = [
        replace(
            revision.publication,
            supersedes_version_id=baseline_ids["dataset"],
        )
    ]
    for index, kind in enumerate(("field_dictionary", "source_collection"), start=1):
        candidate = _admit(
            reference_version_id=revision.reference_version_id,
            export_format="csv" if index == 1 else "json",
        )
        execution = revision.ledger.start_producer_execution(
            ProducerExecutionRequest(
                run_id=revision.run_id,
                step_key="planning",
                attempt_id=revision.attempt_id,
                idempotency_key=f"revision-{kind}-{uuid4()}",
                producer_type="algorithm",
                producer_name="fixture-data-revision",
                producer_version="1.0.0",
                input_hash="sha256:" + f"{index + 3:x}" * 64,
                parameters={"kind": kind},
            ),
            token=revision.token,
            generation=revision.generation,
            expected_status=revision.run_status,
            expected_revision=revision.run_revision,
        )
        revision.ledger.finish_producer_execution(
            execution.id,
            status="completed",
            output_hash=candidate.content_hash,
        )
        publications.append(
            ArtifactPublication(
                artifact_id=artifacts[kind].id,
                publication_key=f"{kind}-revision",
                producer_execution_id=execution.id,
                candidate=candidate,
                source_mode="fixture",
                supersedes_version_id=baseline_ids[kind],
            )
        )

    with factory() as session, session.begin():
        baseline = session.get(
            ArtifactVersionModel,
            baseline_ids["field_dictionary"],
        )
        assert baseline is not None
        concurrent = ArtifactVersionModel(
            id=uuid4(),
            artifact_id=baseline.artifact_id,
            project_id=baseline.project_id,
            created_by_run_id=baseline.created_by_run_id,
            run_step_id=baseline.run_step_id,
            step_attempt_id=baseline.step_attempt_id,
            producer_execution_id=baseline.producer_execution_id,
            version_number=2,
            publication_key="field-dictionary-concurrent",
            schema_version=baseline.schema_version,
            content=dict(baseline.content),
            content_hash=baseline.content_hash,
            input_hash=baseline.input_hash,
            source_mode=baseline.source_mode,
            producer=dict(baseline.producer),
            source_snapshot_ids=list(baseline.source_snapshot_ids),
            evidence_ids=list(baseline.evidence_ids),
            quality_projection=baseline.quality_projection,
            quality_projection_hash=baseline.quality_projection_hash,
            supersedes_version_id=baseline.id,
        )
        session.add(concurrent)
        session.flush()
        artifact = session.get(ResearchArtifactModel, baseline.artifact_id)
        assert artifact is not None
        artifact.latest_version_id = concurrent.id
        concurrent_id = concurrent.id

    with pytest.raises(PublicationConflictError, match="supersedes"):
        revision.publisher.publish_step_outputs(
            revision.run_id,
            step_key="planning",
            attempt_id=revision.attempt_id,
            token=revision.token,
            generation=revision.generation,
            expected_status=revision.run_status,
            expected_revision=revision.run_revision,
            publications=tuple(publications),
            public_message="Revision bundle published",
        )

    expected_latest = {
        "dataset": baseline_ids["dataset"],
        "field_dictionary": concurrent_id,
        "source_collection": baseline_ids["source_collection"],
    }
    with factory() as session:
        assert {
            kind: session.get(ResearchArtifactModel, artifact.id).latest_version_id
            for kind, artifact in artifacts.items()
        } == expected_latest
        assert session.scalar(
            select(func.count())
            .select_from(ArtifactVersionModel)
            .where(ArtifactVersionModel.created_by_run_id == revision.run_id)
        ) == 0


def test_dataset_crossmatch_evidence_persists_both_source_sides(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, _ = _seed_project(factory)
    version_id = publish_reference_dataset(factory=factory, project=project)

    with factory() as session:
        evidence = session.scalar(
            select(EvidenceModel).where(
                EvidenceModel.artifact_version_id == version_id,
                EvidenceModel.evidence_type == "crossmatch_decision",
            )
        )
        assert evidence is not None
        provenance = evidence.locator["source_provenance"]
        assert set(provenance) == {"left", "right"}
        assert provenance["left"]["pipeline_source_snapshot_id"]
        assert provenance["right"]["pipeline_source_snapshot_id"]
        assert provenance["left"]["persisted_source_snapshot_id"]
        assert provenance["right"]["persisted_source_snapshot_id"]
        assert (
            provenance["left"]["persisted_source_snapshot_id"]
            != provenance["right"]["persisted_source_snapshot_id"]
        )
        crossmatch = evidence.locator["crossmatch_evidence"]
        assert crossmatch["left_locators"]
        assert crossmatch["right_locators"]
        assert evidence.source_snapshot_id == UUID(
            provenance["left"]["persisted_source_snapshot_id"]
        )


def test_concurrent_publishers_never_allocate_duplicate_version_numbers(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"shared-artifact-{uuid4()}",
    )
    first = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
        revision=1,
        publication_key="concurrent-a",
    )
    candidate_2 = _admit(reference_version_id=first.reference_version_id)
    execution_2 = first.ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=first.run_id,
            step_key="planning",
            attempt_id=first.attempt_id,
            idempotency_key=f"producer-2-{uuid4()}",
            producer_type="pipeline",
            producer_name="fixture-data-port",
            producer_version="1.0.0",
            input_hash="sha256:" + "c" * 64,
            parameters={"page_size": 20, "strict": True},
        ),
        token=first.token,
        generation=first.generation,
        expected_status=first.run_status,
        expected_revision=first.run_revision,
    )
    first.ledger.finish_producer_execution(
        execution_2.id,
        status="completed",
        output_hash=candidate_2.content_hash,
        token_usage={"records": 1},
        latency_ms=12,
    )
    second = replace(
        first,
        execution_id=execution_2.id,
        publication=ArtifactPublication(
            artifact_id=artifact.id,
            publication_key="concurrent-b",
            producer_execution_id=execution_2.id,
            candidate=candidate_2,
            source_mode="fixture",
        ),
    )
    barrier = Barrier(2)

    def publish(active: ActivePublication) -> PublicationResult | Exception:
        barrier.wait()
        try:
            return _publish(active)
        except Exception as exc:  # noqa: BLE001 - concurrent outcome is asserted below
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(publish, (first, second)))
    assert sum(isinstance(item, PublicationResult) for item in outcomes) == 1
    assert sum(isinstance(item, PublicationConflictError) for item in outcomes) == 1
    with factory() as session:
        numbers = tuple(
            session.scalars(
                select(ArtifactVersionModel.version_number)
                .where(ArtifactVersionModel.artifact_id == artifact.id)
                .order_by(ArtifactVersionModel.version_number)
            )
        )
        assert numbers == (1,)


def test_last_step_atomically_completes_run_and_releases_lease(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    project, contract = _seed_project(factory)
    reference_version_id = _seed_reference_version(
        factory=factory,
        project=project,
    )
    workflow = PersistentWorkflowStore(factory)
    ledger = ProducerExecutionStore(factory)
    publisher = ArtifactPublisher(factory)
    snapshot = workflow.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"run-{uuid4()}",
        request_hash="sha256:" + "d" * 64,
        steps=_steps(),
    )
    lease = workflow.acquire_lease(
        snapshot.id,
        owner="final-step-executor",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    status = "queued"
    revision = lease.revision
    published_ids: list[UUID] = []
    for position, definition in enumerate(_steps()):
        attempt = workflow.begin_step(
            snapshot.id,
            step_key=definition.key,
            attempt_idempotency_key=f"attempt-{position}-{uuid4()}",
            token=lease.token,
            generation=lease.generation,
            expected_status=status,
            expected_revision=revision,
            public_message=f"Starting {definition.key}",
        )
        artifact = _create_artifact(
            factory,
            project_id=project.id,
            logical_key=f"step-{position}-{uuid4()}",
        )
        candidate = _admit(reference_version_id=reference_version_id)
        execution = ledger.start_producer_execution(
            ProducerExecutionRequest(
                run_id=snapshot.id,
                step_key=definition.key,
                attempt_id=attempt.attempt_id,
                idempotency_key=f"producer-{position}-{uuid4()}",
                producer_type="algorithm",
                producer_name="fixture-stage",
                producer_version="1.0.0",
                input_hash="sha256:" + f"{position + 1:x}" * 64,
                parameters={"stage": position},
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )
        ledger.finish_producer_execution(
            execution.id,
            status="completed",
            output_hash=candidate.content_hash,
            latency_ms=position,
        )
        result = publisher.publish_step_outputs(
            snapshot.id,
            step_key=definition.key,
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
            publications=(
                ArtifactPublication(
                    artifact_id=artifact.id,
                    publication_key=f"publication-{position}",
                    producer_execution_id=execution.id,
                    candidate=candidate,
                    source_mode="fixture",
                ),
            ),
            public_message=f"Completed {definition.key}",
        )
        status = result.status
        revision = result.revision
        published_ids.extend(version.id for version in result.versions)

    with factory() as session:
        run = session.get(ResearchRunModel, snapshot.id)
        assert run is not None
        assert run.status == "completed"
        assert run.progress == 100
        assert run.finished_at is not None
        assert run.lease_token is None
        assert run.lease_owner is None
        assert run.lease_expires_at is None
        assert session.scalar(
            select(func.count())
            .select_from(ArtifactVersionModel)
            .where(ArtifactVersionModel.id.in_(published_ids))
        ) == len(_steps())
        completed = session.scalar(
            select(RunEventModel).where(
                RunEventModel.run_id == snapshot.id,
                RunEventModel.activity_kind == "completion",
                RunEventModel.activity_phase == "completed",
            )
        )
        assert completed is not None and completed.progress == 100
