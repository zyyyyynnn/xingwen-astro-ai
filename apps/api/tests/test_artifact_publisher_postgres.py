"""PostgreSQL transaction, fencing, and concurrency tests for Atomic Publisher.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import timedelta
import os
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
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
from app.schemas.core import (
    ArtifactKind,
    ExportArtifactContent,
    ResearchContractInput,
    ScientificSkillId,
    compute_research_contract_content_hash,
)
from app.schemas.scientific_skills import VisualizationArtifactContent
from app.services.artifacts import ArtifactReadService
from app.services.scientific_artifacts import ScientificArtifactReadService
from app.workflow.scientific_publication import ScientificStepPublisher
from app.workflow.store import PersistentWorkflowStore, RunStepDefinition
from services.scientific_skills.demo_fixture import build_scientific_fixture_document
from services.scientific_skills.execution import ScientificStepOutput


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
HASH_A = "sha256:" + "a" * 64


def _accept(_: object) -> None:
    return None


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
            depends_on_step_keys=(transitions[position - 1][0],) if position else (),
        )
        for position, (enter, success) in enumerate(transitions)
    )


def _seed_project(
    factory: Callable[[], Session],
    *,
    contract_input: ResearchContractInput | None = None,
) -> tuple[ResearchProjectModel, ResearchContractModel]:
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Atomic Publisher integration",
        case_key="exoplanet_host_star",
    )
    contract_content = (
        contract_input.model_dump(mode="json") if contract_input is not None else None
    )
    draft = build_contract_draft(project, content=contract_content)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash=(
            compute_research_contract_content_hash(contract_input)
            if contract_input is not None
            else HASH_A
        ),
        content=contract_content,
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
    reference_version_id = _seed_reference_version(
        factory=factory,
        project=project,
    )
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


def test_function_call_execution_replays_one_safe_audit_record(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    request = ProducerExecutionRequest(
        run_id=active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        idempotency_key="research-step-agent:1",
        producer_type="model",
        producer_name="research_step_agent",
        producer_version="1.0.0",
        model_provider="qwen",
        model_name="qwen-plus-test",
        prompt_name="research_step_agent",
        prompt_version="1.0.0",
        prompt_hash="sha256:" + "d" * 64,
        input_hash="sha256:" + "e" * 64,
        parameters={"temperature": 0.2, "top_p": 0.8},
        authorized_tool_name="confirm_research_plan",
        authorized_skill_id=None,
        registry_revision="sha256:" + "f" * 64,
    )
    started = active.ledger.start_producer_execution(
        request,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    assert started.replayed is False

    completed = active.ledger.finish_producer_execution(
        started.id,
        status="completed",
        output_hash="sha256:" + "1" * 64,
        token_usage={"prompt_tokens": 10, "completion_tokens": 3},
        latency_ms=9,
        provider_request_id="provider-request-1",
        tool_call_id="tool-call-1",
        validated_arguments_hash="sha256:" + "2" * 64,
        public_message="已核对冻结研究协议并确认当前唯一受控工具。",
    )
    terminal_replay = active.ledger.finish_producer_execution(
        started.id,
        status="completed",
        output_hash="sha256:" + "1" * 64,
        token_usage={"prompt_tokens": 10, "completion_tokens": 3},
        latency_ms=9,
        provider_request_id="provider-request-1",
        tool_call_id="tool-call-1",
        validated_arguments_hash="sha256:" + "2" * 64,
        public_message="已核对冻结研究协议并确认当前唯一受控工具。",
    )
    replay = active.ledger.start_producer_execution(
        request,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )

    assert completed.status == "completed"
    assert terminal_replay.id == started.id
    assert terminal_replay.replayed is True
    assert replay.id == started.id
    assert replay.replayed is True
    assert replay.provider_request_id == "provider-request-1"
    assert replay.tool_call_id == "tool-call-1"
    assert replay.authorized_tool_name == "confirm_research_plan"
    assert replay.authorized_skill_id is None
    assert replay.registry_revision == "sha256:" + "f" * 64
    assert replay.validated_arguments_hash == "sha256:" + "2" * 64
    assert replay.rejected_arguments_hash is None
    assert replay.public_message.startswith("已核对")
    assert replay.error_hash is None
    with pytest.raises(ProducerExecutionConflictError):
        active.ledger.finish_producer_execution(
            started.id,
            status="completed",
            output_hash="sha256:" + "1" * 64,
            token_usage={"prompt_tokens": 10, "completion_tokens": 3},
            latency_ms=9,
            provider_request_id="different-provider-request",
            tool_call_id="tool-call-1",
            validated_arguments_hash="sha256:" + "2" * 64,
            public_message="已核对冻结研究协议并确认当前唯一受控工具。",
        )

    rejected_started = active.ledger.start_producer_execution(
        replace(request, idempotency_key="research-step-agent:2"),
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    rejected = active.ledger.finish_producer_execution(
        rejected_started.id,
        status="rejected",
        output_hash="sha256:" + "3" * 64,
        token_usage={"prompt_tokens": 8, "completion_tokens": 2},
        latency_ms=11,
        error_code="AGENT_ARGUMENTS_INVALID",
        provider_request_id="provider-request-2",
        tool_call_id="tool-call-2",
        rejected_arguments_hash="sha256:" + "4" * 64,
        error_hash="sha256:" + "5" * 64,
    )
    rejected_replay = active.ledger.finish_producer_execution(
        rejected_started.id,
        status="rejected",
        output_hash="sha256:" + "3" * 64,
        token_usage={"prompt_tokens": 8, "completion_tokens": 2},
        latency_ms=11,
        error_code="AGENT_ARGUMENTS_INVALID",
        provider_request_id="provider-request-2",
        tool_call_id="tool-call-2",
        rejected_arguments_hash="sha256:" + "4" * 64,
        error_hash="sha256:" + "5" * 64,
    )
    assert rejected.replayed is False
    assert rejected_replay.replayed is True
    assert rejected_replay.rejected_arguments_hash == "sha256:" + "4" * 64
    assert rejected_replay.validated_arguments_hash is None
    with pytest.raises(ProducerExecutionConflictError):
        active.ledger.finish_producer_execution(
            rejected_started.id,
            status="rejected",
            output_hash="sha256:" + "3" * 64,
            token_usage={"prompt_tokens": 8, "completion_tokens": 2},
            latency_ms=11,
            error_code="AGENT_ARGUMENTS_INVALID",
            provider_request_id="provider-request-2",
            tool_call_id="tool-call-2",
            rejected_arguments_hash="sha256:" + "6" * 64,
            error_hash="sha256:" + "5" * 64,
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
                    RunEventModel.event_type == "step.completed",
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
                RunEventModel.event_type == "step.completed",
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


def test_intermediate_publication_is_replayable_then_final_publish_completes_attempt(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    with active.factory() as session:
        event_count_before = session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(RunEventModel.run_id == active.run_id)
        )
    intermediate = active.publisher.publish_intermediate_outputs(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        publications=(active.publication,),
    )
    assert intermediate.replayed is False
    assert intermediate.status == active.run_status
    assert intermediate.revision == active.run_revision

    with active.factory() as session:
        version = session.get(ArtifactVersionModel, intermediate.versions[0].id)
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        attempt = session.get(StepAttemptModel, active.attempt_id)
        assert version is not None and version.version_number == 1
        assert artifact is not None and artifact.latest_version_id == version.id
        assert run is not None and run.status == active.run_status
        assert run.revision == active.run_revision
        assert step is not None and step.status == "running"
        assert attempt is not None and attempt.status == "running"
        assert (
            session.scalar(
                select(func.count())
                .select_from(RunEventModel)
                .where(RunEventModel.run_id == active.run_id)
            )
            == event_count_before
        )

    replay = active.publisher.publish_intermediate_outputs(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        publications=(active.publication,),
    )
    assert replay.replayed is True
    assert replay.versions == intermediate.versions
    assert replay.status == intermediate.status
    assert replay.revision == intermediate.revision

    final_request = ProducerExecutionRequest(
        run_id=active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        idempotency_key=f"final-producer-{uuid4()}",
        producer_type="pipeline",
        producer_name="fixture-data-port",
        producer_version="1.0.0",
        input_hash="sha256:" + "d" * 64,
        parameters={"page_size": 20, "strict": True},
    )
    final_execution = active.ledger.start_producer_execution(
        final_request,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
    )
    active.ledger.finish_producer_execution(
        final_execution.id,
        status="completed",
        output_hash=active.publication.candidate.content_hash,
        token_usage={"records": 1},
        latency_ms=12,
    )
    final_publication = replace(
        active.publication,
        publication_key=f"final-{uuid4()}",
        producer_execution_id=final_execution.id,
        supersedes_version_id=intermediate.versions[0].id,
    )
    final = active.publisher.publish_step_outputs(
        active.run_id,
        step_key="planning",
        attempt_id=active.attempt_id,
        token=active.token,
        generation=active.generation,
        expected_status=active.run_status,
        expected_revision=active.run_revision,
        publications=(final_publication,),
        public_message="Planning artifacts published",
    )
    assert final.replayed is False
    assert final.status == "fetching_data"
    assert final.revision == active.run_revision + 1

    with active.factory() as session:
        final_version = session.get(ArtifactVersionModel, final.versions[0].id)
        artifact = session.get(ResearchArtifactModel, active.artifact.id)
        run = session.get(ResearchRunModel, active.run_id)
        step = session.scalar(
            select(RunStepModel).where(
                RunStepModel.run_id == active.run_id,
                RunStepModel.key == "planning",
            )
        )
        attempt = session.get(StepAttemptModel, active.attempt_id)
        step_events = session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(
                RunEventModel.run_id == active.run_id,
                RunEventModel.event_type == "step.completed",
            )
        )
        run_events = session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(
                RunEventModel.run_id == active.run_id,
                RunEventModel.event_type == "run.completed",
            )
        )
        assert final_version is not None and final_version.version_number == 2
        assert final_version.supersedes_version_id == intermediate.versions[0].id
        assert artifact is not None and artifact.latest_version_id == final_version.id
        assert run is not None and run.status == "fetching_data"
        assert run.revision == active.run_revision + 1
        assert step is not None and step.status == "completed"
        assert attempt is not None and attempt.status == "completed"
        assert step_events == 1
        assert run_events == 0


def test_intermediate_publication_requires_active_fence(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    with pytest.raises(StalePublicationError):
        active.publisher.publish_intermediate_outputs(
            active.run_id,
            step_key="planning",
            attempt_id=active.attempt_id,
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision - 1,
            publications=(active.publication,),
        )

    with active.factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == active.run_id)
            .values(
                lease_expires_at=func.clock_timestamp() - text("INTERVAL '1 second'")
            )
        )
    with pytest.raises(StalePublicationError):
        active.publisher.publish_intermediate_outputs(
            active.run_id,
            step_key="planning",
            attempt_id=active.attempt_id,
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision,
            publications=(active.publication,),
        )
    _assert_publication_not_started(active)


def test_intermediate_publication_rolls_back_without_completion_or_events(
    postgres_engine: Engine,
) -> None:
    active = _active_publication(postgres_engine)
    with active.factory() as session:
        event_count_before = session.scalar(
            select(func.count())
            .select_from(RunEventModel)
            .where(RunEventModel.run_id == active.run_id)
        )
    publisher = _FailingPublisher(active.factory)
    with pytest.raises(RuntimeError, match="injected"):
        publisher.publish_intermediate_outputs(
            active.run_id,
            step_key="planning",
            attempt_id=active.attempt_id,
            token=active.token,
            generation=active.generation,
            expected_status=active.run_status,
            expected_revision=active.run_revision,
            publications=(active.publication,),
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
        assert run is not None and run.status == active.run_status
        assert run.revision == active.run_revision
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
                .where(RunEventModel.run_id == active.run_id)
            )
            == event_count_before
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
                    RunEventModel.event_type == "step.completed",
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
    second = _active_publication(
        postgres_engine,
        project=project,
        contract=contract,
        artifact=artifact,
        revision=2,
        publication_key="concurrent-b",
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
        reference_version_id = _seed_reference_version(
            factory=factory,
            project=project,
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
                RunEventModel.event_type == "run.completed",
            )
        )
        assert completed is not None and completed.progress == 100


def test_scientific_step_publishes_and_reads_one_current_artifact_closure(
    postgres_engine: Engine,
) -> None:
    factory = session_factory(postgres_engine)
    contract = ResearchContractInput.model_validate(
        {
            "research_goal": "Render a bounded WorldWide Telescope scene",
            "target_objects": ["host_star"],
            "data_requirements": {},
            "requested_fields": ["star.ra", "star.dec"],
            "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
            "paper_search_scope": {},
            "scientific_tasks": [
                {
                    "task_id": "task.wwt",
                    "skill_id": "wwt_scene",
                    "parameters": {
                        "view": {
                            "kind": "coordinates",
                            "center": {"ra_hours": 10.25, "dec_degrees": -12.4},
                            "field_of_view_degrees": 4,
                        },
                        "text_alternative": (
                            "A four-degree WWT field centered on the target star."
                        ),
                    },
                    "input_refs": [],
                }
            ],
            "output_requirements": ["visualization"],
            "evidence_requirements": {},
            "quality_constraints": {},
        }
    )
    project, persisted_contract = _seed_project(factory, contract_input=contract)
    workflow = PersistentWorkflowStore(factory)
    snapshot = workflow.create_run(
        project_id=project.id,
        contract_id=persisted_contract.id,
        execution_mode="demo_replay",
        idempotency_key=f"scientific-run-{uuid4()}",
        request_hash="sha256:" + "9" * 64,
        steps=(
            RunStepDefinition(
                key="planning",
                label="Planning",
                enter_status="planning",
                success_status="building_visualizations",
                max_attempts=2,
            ),
            RunStepDefinition(
                key="scientific.wwt",
                label="Building scientific visualizations",
                enter_status="building_visualizations",
                success_status="completed",
                max_attempts=2,
                task_id="task.wwt",
                skill_id="wwt_scene",
                depends_on_step_keys=("planning",),
            ),
        ),
    )
    lease = workflow.acquire_lease(
        snapshot.id,
        owner="scientific-publisher-test",
        lease_duration=timedelta(minutes=5),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    planning_attempt = workflow.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"planning-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning scientific work",
    )
    planning_artifact = _create_artifact(
        factory,
        project_id=project.id,
        logical_key=f"scientific-plan-{uuid4()}",
    )
    reference_version_id = _seed_reference_version(factory=factory, project=project)
    planning_candidate = _admit(reference_version_id=reference_version_id)
    ledger = ProducerExecutionStore(factory)
    planning_execution = ledger.start_producer_execution(
        ProducerExecutionRequest(
            run_id=snapshot.id,
            step_key="planning",
            attempt_id=planning_attempt.attempt_id,
            idempotency_key=f"scientific-planning-{uuid4()}",
            producer_type="pipeline",
            producer_name="fixture-planner",
            producer_version="1.0.0",
            input_hash="sha256:" + "8" * 64,
            parameters={"mode": "fixture"},
        ),
        token=lease.token,
        generation=lease.generation,
        expected_status=planning_attempt.run_status,
        expected_revision=planning_attempt.run_revision,
    )
    ledger.finish_producer_execution(
        planning_execution.id,
        status="completed",
        output_hash=planning_candidate.content_hash,
        latency_ms=1,
    )
    planning_result = ArtifactPublisher(factory).publish_step_outputs(
        snapshot.id,
        step_key="planning",
        attempt_id=planning_attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=planning_attempt.run_status,
        expected_revision=planning_attempt.run_revision,
        publications=(
            ArtifactPublication(
                artifact_id=planning_artifact.id,
                publication_key=f"scientific-planning-publication-{uuid4()}",
                producer_execution_id=planning_execution.id,
                candidate=planning_candidate,
                source_mode="fixture",
            ),
        ),
        public_message="Scientific planning completed",
    )
    attempt = workflow.begin_step(
        snapshot.id,
        step_key="scientific.wwt",
        attempt_idempotency_key=f"scientific-attempt-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status=planning_result.status,
        expected_revision=planning_result.revision,
        public_message="Building scientific visualizations",
    )
    fixture_entry = next(
        item
        for item in build_scientific_fixture_document()["entries"]
        if item["read"]["content"].get("spec", {}).get("mode") == "wwt_scene"
    )
    candidate = VisualizationArtifactContent.model_validate(
        fixture_entry["read"]["content"]
    )
    published = ScientificStepPublisher(factory).publish(
        attempt=attempt,
        lease=lease,
        step_key="scientific.wwt",
        contract=contract,
        output=ScientificStepOutput(
            task_id="task.wwt",
            skill_id=ScientificSkillId.wwt_scene,
            artifact_candidates=(candidate,),
        ),
        source_mode="fixture",
        public_message="Scientific visualization published",
    )

    assert published.status == "completed"
    assert len(published.versions) == 1
    read = ScientificArtifactReadService(
        ArtifactReadService(factory)
    ).get_scientific_artifact(
        version_id=str(published.versions[0].id),
        session_id=project.session_id,
    )
    assert read.content == candidate
    assert read.producer_execution.producer.name == "scientific_artifact_assembler"
    with factory() as session:
        assert (
            session.scalar(
                select(func.count(ArtifactVersionModel.id)).where(
                    ArtifactVersionModel.id == published.versions[0].id
                )
            )
            == 1
        )
