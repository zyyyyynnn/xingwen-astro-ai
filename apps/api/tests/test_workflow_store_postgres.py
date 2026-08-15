"""PostgreSQL concurrency and recovery contract tests for the workflow store.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
These tests exercise PostgreSQL row locks and database time and therefore do
not substitute SQLite when PostgreSQL is unavailable.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import asyncio
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ResearchContractModel,
    ResearchInputContentModel,
    ResearchInputModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunStepModel,
    WorkflowProjectDispatchModel,
    WorkflowWorkerModel,
)
from app.db.repositories import UnitOfWork
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import (
    build_contract_draft,
    build_research_contract,
    build_research_project,
    persist_authoring_models,
)
from app.workflow.store import (
    CheckpointUnavailableError,
    LeaseGrant,
    LeaseUnavailableError,
    PersistentWorkflowStore,
    RunSnapshot,
    RunQueueCapacityError,
    RunStepDefinition,
    StaleWorkflowWriteError,
    WorkflowConflictError,
    WorkerCapacityUnavailableError,
)
from app.workflow.capacity import PersistentWorkerRegistry, WorkflowCapacityPolicy
from app.workflow.research_run_worker import ResearchRunWorker
from app.workflow.persistent_executor import (
    FailureDecision,
    HumanCheckpointRequirement,
    PersistentWorkflowExecutionError,
    PersistentWorkflowExecutor,
)
from app.workflow.publisher import ArtifactPublisher

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
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


def _step_definitions(*, max_attempts: int = 2) -> tuple[RunStepDefinition, ...]:
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
            key=enter_status,
            label=enter_status.replace("_", " ").title(),
            enter_status=enter_status,
            success_status=success_status,
            max_attempts=max_attempts if position == 0 else 1,
            depends_on_step_keys=(transitions[position - 1][0],) if position else (),
        )
        for position, (enter_status, success_status) in enumerate(transitions)
    )


def _seed_project(
    engine: Engine,
) -> tuple[PersistentWorkflowStore, ResearchProjectModel, ResearchContractModel]:
    factory = session_factory(engine)
    project = build_research_project(
        project_id=uuid4(),
        session_id=f"session-{uuid4()}",
        name="Workflow Store Test",
        case_key="exoplanet_host_star",
    )
    draft = build_contract_draft(project)
    contract = build_research_contract(
        project,
        draft,
        contract_id=uuid4(),
        content_hash="sha256:" + "a" * 64,
    )
    with UnitOfWork(factory) as uow:
        persist_authoring_models(
            uow.session, project=project, draft=draft, contract=contract
        )
        uow.commit()
    store = PersistentWorkflowStore(factory)
    return store, project, contract


def _create_run(
    engine: Engine, *, max_attempts: int = 2
) -> tuple[PersistentWorkflowStore, RunSnapshot]:
    store, project, contract = _seed_project(engine)
    snapshot = store.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=f"run-{uuid4()}",
        request_hash="sha256:" + "b" * 64,
        steps=_step_definitions(max_attempts=max_attempts),
    )
    return store, snapshot


def _capacity_policy(
    *,
    queued_global: int = 4,
    queued_project: int = 2,
    active_global: int = 2,
    active_project: int = 1,
    nonterminal_global: int | None = None,
    nonterminal_project: int | None = None,
) -> WorkflowCapacityPolicy:
    return WorkflowCapacityPolicy(
        max_queued_global=queued_global,
        max_queued_per_project=queued_project,
        max_nonterminal_global=nonterminal_global or max(queued_global, 8),
        max_nonterminal_per_project=nonterminal_project or max(queued_project, 4),
        max_active_global=active_global,
        max_active_per_project=active_project,
        worker_capacity=min(2, active_global),
        queue_timeout=timedelta(minutes=5),
        retry_after_seconds=7,
    )


def _clear_capacity_test_state(engine: Engine) -> None:
    factory = session_factory(engine)
    with factory() as session, session.begin():
        session.execute(delete(WorkflowWorkerModel))
        session.execute(delete(ResearchProjectModel))


def _open_checkpoint(
    store: PersistentWorkflowStore, snapshot: RunSnapshot
) -> RunSnapshot:
    lease = store.acquire_lease(
        snapshot.id,
        owner="checkpoint-test",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"checkpoint-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    store.request_human_input(
        snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=attempt.run_revision,
        error_class="DocumentPipelineInputError",
        error_code="DOCUMENT_INPUT_REQUIRED",
        public_message="请补充 PDF、Markdown 或纯文本文档后继续研究。",
        required_input_types=("pdf", "text"),
    )
    return store.load_snapshot(snapshot.id)


def test_concurrent_lease_acquisition_has_one_winner(postgres_engine: Engine) -> None:
    store, snapshot = _create_run(postgres_engine)
    barrier = Barrier(2)

    def acquire(owner: str) -> LeaseGrant | LeaseUnavailableError:
        barrier.wait()
        try:
            return store.acquire_lease(
                snapshot.id,
                owner=owner,
                lease_duration=timedelta(seconds=30),
                expected_status="queued",
                expected_revision=1,
            )
        except LeaseUnavailableError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(acquire, ("executor-a", "executor-b")))

    assert sum(isinstance(item, LeaseGrant) for item in outcomes) == 1
    assert sum(isinstance(item, LeaseUnavailableError) for item in outcomes) == 1
    winner = next(item for item in outcomes if isinstance(item, LeaseGrant))
    heartbeat = store.heartbeat_lease(
        snapshot.id,
        token=winner.token,
        generation=winner.generation,
        lease_duration=timedelta(seconds=60),
        expected_status="queued",
        expected_revision=winner.revision,
    )
    assert heartbeat.token == winner.token
    assert heartbeat.generation == winner.generation
    assert heartbeat.revision == winner.revision
    assert heartbeat.expires_at > winner.expires_at


def test_concurrent_create_run_is_idempotent_and_rejects_conflicting_request(
    postgres_engine: Engine,
) -> None:
    store, project, contract = _seed_project(postgres_engine)
    barrier = Barrier(2)
    idempotency_key = f"concurrent-run-{uuid4()}"
    request_hash = "sha256:" + "f" * 64

    def create() -> RunSnapshot:
        barrier.wait()
        return store.create_run(
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            steps=_step_definitions(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        snapshots = list(executor.map(lambda _: create(), range(2)))

    assert snapshots[0].id == snapshots[1].id
    assert len(snapshots[0].steps) == 7
    assert snapshots[0].latest_event_sequence == 1
    with pytest.raises(
        WorkflowConflictError,
        match="idempotency key was already used with a different request",
    ):
        store.create_run(
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            idempotency_key=idempotency_key,
            request_hash="sha256:" + "e" * 64,
            steps=_step_definitions(),
        )


def test_invalid_transition_chain_is_rejected_before_database_write(
    postgres_engine: Engine,
) -> None:
    store, project, contract = _seed_project(postgres_engine)

    with pytest.raises(ValueError, match="must follow canonical order"):
        store.create_run(
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            idempotency_key=f"invalid-chain-{uuid4()}",
            request_hash="sha256:" + "c" * 64,
            steps=(
                RunStepDefinition(
                    key="planning",
                    label="Planning",
                    enter_status="planning",
                    success_status="cleaning_data",
                ),
                RunStepDefinition(
                    key="cleaning_data",
                    label="Cleaning data",
                    enter_status="cleaning_data",
                    success_status="fetching_data",
                    depends_on_step_keys=("planning",),
                ),
                RunStepDefinition(
                    key="fetching_data",
                    label="Fetching data",
                    enter_status="fetching_data",
                    success_status="completed",
                    depends_on_step_keys=("cleaning_data",),
                ),
            ),
        )


def test_run_step_definitions_are_database_frozen_after_create(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    factory = session_factory(postgres_engine)

    with pytest.raises(IntegrityError, match="RunStep collection is frozen"):
        with factory() as session, session.begin():
            session.add(
                RunStepModel(
                    run_id=snapshot.id,
                    position=7,
                    key="extra",
                    label="Extra",
                    enter_status="building_graph",
                    success_status="completed",
                    max_attempts=1,
                    status="pending",
                    progress=0,
                )
            )
            session.flush()

    with pytest.raises(IntegrityError, match="RunStep definition is frozen"):
        with factory() as session, session.begin():
            step = session.scalar(
                select(RunStepModel).where(
                    RunStepModel.run_id == snapshot.id,
                    RunStepModel.position == 0,
                )
            )
            assert step is not None
            step.label = "Changed"
            session.flush()

    with pytest.raises(IntegrityError, match="RunStep collection is frozen"):
        with factory() as session, session.begin():
            step = session.scalar(
                select(RunStepModel).where(
                    RunStepModel.run_id == snapshot.id,
                    RunStepModel.position == 0,
                )
            )
            assert step is not None
            session.delete(step)
            session.flush()


def test_begin_step_is_atomic_and_freezes_order(postgres_engine: Engine) -> None:
    store, snapshot = _create_run(postgres_engine)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )

    with pytest.raises(
        WorkflowConflictError, match="frozen run step dependency is incomplete"
    ):
        store.begin_step(
            snapshot.id,
            step_key="fetching_data",
            attempt_idempotency_key="attempt-out-of-order",
            token=lease.token,
            generation=lease.generation,
            expected_status="queued",
            expected_revision=lease.revision,
            public_message="Fetching",
        )

    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-1",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    current = store.load_snapshot(snapshot.id)

    assert current.status == "planning"
    assert current.revision == attempt.run_revision
    assert current.latest_event_sequence == attempt.event_sequence
    assert current.steps[0].status == "running"
    assert current.steps[0].attempts[0].status == "running"
    assert [step.key for step in current.steps[:2]] == ["planning", "fetching_data"]
    assert len(current.steps) == 7


def test_heartbeat_does_not_invalidate_in_flight_attempt(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=2)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-before-heartbeat",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )

    renewed = store.heartbeat_lease(
        snapshot.id,
        token=lease.token,
        generation=lease.generation,
        lease_duration=timedelta(seconds=60),
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
    )
    recovered = store.record_retryable_failure(
        snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=renewed.token,
        generation=renewed.generation,
        expected_status=attempt.run_status,
        expected_revision=attempt.run_revision,
        error_class="TimeoutError",
        error_code="UPSTREAM_TIMEOUT",
        public_message="Retry after heartbeat",
    )

    assert renewed.revision == attempt.run_revision
    assert recovered.revision == attempt.run_revision + 1
    assert store.load_snapshot(snapshot.id).steps[0].status == "pending"


def test_executor_cancellation_durably_schedules_a_retry(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=2)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    executor: PersistentWorkflowExecutor[object, object] = PersistentWorkflowExecutor(
        store
    )

    async def exercise() -> None:
        started = asyncio.Event()

        async def runner(_attempt: object) -> object:
            started.set()
            await asyncio.Future()
            return object()

        async def commit_success(*_args: object) -> object:
            raise AssertionError("cancelled execution must not commit")

        task = asyncio.create_task(
            executor.execute_step(
                run_id=snapshot.id,
                step_key="planning",
                attempt_idempotency_key="cancelled-attempt",
                lease=lease,
                expected_status="queued",
                expected_revision=lease.revision,
                public_message="Planning",
                runner=runner,
                commit_success=commit_success,
                classify_failure=lambda _exc: FailureDecision(
                    error_code="UNUSED",
                    public_message="unused",
                    retryable=False,
                ),
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    recovered = store.load_snapshot(snapshot.id)
    assert recovered.steps[0].status == "pending"
    assert recovered.steps[0].attempts[0].status == "failed"
    assert recovered.steps[0].attempts[0].retryable is True
    assert (
        recovered.steps[0].attempts[0].error_code
        == "WORKER_EXECUTION_INTERRUPTED"
    )


def test_expired_lease_takeover_fences_old_executor_and_retries_abandoned_attempt(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    first = store.acquire_lease(
        snapshot.id,
        owner="executor-old",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-before-crash",
        token=first.token,
        generation=first.generation,
        expected_status="queued",
        expected_revision=first.revision,
        public_message="Planning",
    )
    factory = session_factory(postgres_engine)
    with factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == snapshot.id)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )

    takeover = store.acquire_lease(
        snapshot.id,
        owner="executor-new",
        lease_duration=timedelta(seconds=30),
        expected_status="planning",
        expected_revision=attempt.run_revision,
    )

    assert takeover.generation == first.generation + 1
    assert takeover.active_attempt_ids == ()
    recovered = store.load_snapshot(snapshot.id)
    assert recovered.status == "planning"
    assert recovered.steps[0].status == "pending"
    assert recovered.steps[0].failure_code == "WORKER_LEASE_EXPIRED"
    assert recovered.steps[0].attempts[0].status == "failed"
    assert recovered.steps[0].attempts[0].retryable is True
    assert recovered.events[-1].event_type == "step.retry_scheduled"
    with pytest.raises(StaleWorkflowWriteError):
        store.record_retryable_failure(
            snapshot.id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            token=first.token,
            generation=first.generation,
            expected_status="planning",
            expected_revision=takeover.revision,
            error_class="TimeoutError",
            error_code="UPSTREAM_TIMEOUT",
            public_message="Retrying after recovery",
        )

    replacement = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-after-crash",
        token=takeover.token,
        generation=takeover.generation,
        expected_status="planning",
        expected_revision=takeover.revision,
        public_message="Planning after recovery",
    )
    assert replacement.attempt_number == 2


def test_expired_attempt_exhaustion_fails_the_run_during_takeover(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=1)
    first = store.acquire_lease(
        snapshot.id,
        owner="executor-old",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="only-attempt",
        token=first.token,
        generation=first.generation,
        expected_status="queued",
        expected_revision=first.revision,
        public_message="Planning",
    )
    factory = session_factory(postgres_engine)
    with factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == snapshot.id)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )

    takeover = store.acquire_lease(
        snapshot.id,
        owner="executor-new",
        lease_duration=timedelta(seconds=30),
        expected_status="planning",
        expected_revision=attempt.run_revision,
    )

    assert takeover.active_attempt_ids == ()
    failed = store.load_snapshot(snapshot.id)
    assert failed.status == "failed"
    assert failed.failure_code == "WORKER_LEASE_EXPIRED"
    assert failed.steps[0].status == "failed"
    assert failed.steps[0].attempts[0].retryable is False


def test_retry_attempts_are_append_only_and_exhaustion_fails_atomically(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=2)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    first = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-1",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    retry = store.record_retryable_failure(
        snapshot.id,
        step_key="planning",
        attempt_id=first.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=first.run_revision,
        error_class="TimeoutError",
        error_code="UPSTREAM_TIMEOUT",
        public_message="Retry scheduled",
        upstream_request_id="upstream-1",
    )
    second = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-2",
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=retry.revision,
        public_message="Planning retry",
    )
    failed = store.fail_run(
        snapshot.id,
        step_key="planning",
        attempt_id=second.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=second.run_revision,
        error_class="TimeoutError",
        error_code="UPSTREAM_TIMEOUT",
        public_message="Retry budget exhausted",
        retryable=True,
        upstream_request_id="upstream-2",
    )
    current = store.load_snapshot(snapshot.id)

    assert failed.status == current.status == "failed"
    assert current.steps[0].status == "failed"
    assert [item.attempt_number for item in current.steps[0].attempts] == [1, 2]
    assert [item.status for item in current.steps[0].attempts] == ["failed", "failed"]
    assert current.lease_expires_at is None


def test_persistent_executor_records_adapter_failure_after_begin_transaction(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=2)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    executor: PersistentWorkflowExecutor[object, object] = PersistentWorkflowExecutor(
        store
    )
    factory = session_factory(postgres_engine)

    async def runner(_: object) -> object:
        # A separate transaction can observe the durable begin_step state, proving
        # the adapter is not called inside the Store's mutation transaction.
        with factory() as session:
            status = session.scalar(
                select(ResearchRunModel.status).where(
                    ResearchRunModel.id == snapshot.id
                )
            )
        assert status == "planning"
        raise TimeoutError("source timed out")

    async def commit_success(*_: object) -> object:  # pragma: no cover - failure path
        raise AssertionError("success committer must not run")

    with pytest.raises(PersistentWorkflowExecutionError):
        asyncio.run(
            executor.execute_step(
                run_id=snapshot.id,
                step_key="planning",
                attempt_idempotency_key="executor-attempt-1",
                lease=lease,
                expected_status="queued",
                expected_revision=lease.revision,
                public_message="Planning",
                runner=runner,
                commit_success=commit_success,
                classify_failure=lambda _: FailureDecision(
                    error_code="UPSTREAM_TIMEOUT",
                    public_message="Retry scheduled",
                    retryable=True,
                ),
            )
        )

    current = store.load_snapshot(snapshot.id)
    assert current.status == "planning"
    assert current.steps[0].status == "pending"
    assert current.steps[0].attempts[0].status == "failed"
    assert current.steps[0].attempts[0].retryable is True


def test_persistent_executor_opens_audited_human_checkpoint(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    executor: PersistentWorkflowExecutor[object, object] = PersistentWorkflowExecutor(
        store
    )

    async def runner(_: object) -> object:
        raise ValueError("document input missing")

    async def commit_success(*_: object) -> object:  # pragma: no cover - failure path
        raise AssertionError("success committer must not run")

    requirement = HumanCheckpointRequirement(
        error_code="DOCUMENT_INPUT_REQUIRED",
        public_message="请补充 PDF、Markdown 或纯文本文档后继续研究。",
        required_input_types=("pdf", "text"),
    )
    with pytest.raises(PersistentWorkflowExecutionError):
        asyncio.run(
            executor.execute_step(
                run_id=snapshot.id,
                step_key="planning",
                attempt_idempotency_key="checkpoint-attempt-1",
                lease=lease,
                expected_status="queued",
                expected_revision=lease.revision,
                public_message="Planning",
                runner=runner,
                commit_success=commit_success,
                classify_failure=lambda _: FailureDecision(
                    error_code=requirement.error_code,
                    public_message=requirement.public_message,
                    retryable=False,
                    checkpoint=requirement,
                ),
            )
        )

    current = store.load_snapshot(snapshot.id)
    checkpoint = store.load_checkpoint(snapshot.id)
    assert current.status == "waiting_for_input"
    assert current.lease_expires_at is None
    assert current.steps[0].status == "waiting"
    assert current.steps[0].attempts[0].status == "failed"
    assert checkpoint.status == "open"
    assert checkpoint.step_key == "planning"
    assert checkpoint.required_input_types == ("pdf", "text")
    assert current.events[-1].event_type == "step.waiting_for_input"


def test_resume_decision_is_atomic_idempotent_and_derives_one_run(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    waiting = _open_checkpoint(store, snapshot)
    factory = session_factory(postgres_engine)
    with factory() as session:
        parent = session.get(ResearchRunModel, snapshot.id)
        assert parent is not None
        session_id = session.scalar(
            select(ResearchProjectModel.session_id).where(
                ResearchProjectModel.id == parent.project_id
            )
        )
        project_id = parent.project_id
    assert session_id is not None
    input_id = uuid4()
    content_hash = "sha256:" + "c" * 64
    with factory() as session, session.begin():
        session.add(
            ResearchInputContentModel(
                project_id=project_id,
                content_hash=content_hash,
                storage_ref=f"research-inputs/{content_hash}",
                mime_type="application/pdf",
                size_bytes=4,
            )
        )
        session.add(
            ResearchInputModel(
                id=input_id,
                session_id=session_id,
                project_id=project_id,
                type="pdf",
                source_type="upload",
                content_hash=content_hash,
                filename="repair.pdf",
                status="accepted",
            )
        )

    barrier = Barrier(2)

    def decide() -> tuple[object, object]:
        barrier.wait()
        return store.decide_run(
            snapshot.id,
            session_id=session_id,
            decision="resume",
            step_key=None,
            input_ids=(input_id,),
            idempotency_key="resume-once",
            request_hash="sha256:" + "d" * 64,
            expected_status="waiting_for_input",
            expected_revision=waiting.revision,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: decide(), range(2)))

    first_decision, first_child_id = results[0]
    second_decision, second_child_id = results[1]
    assert first_decision.id == second_decision.id  # type: ignore[attr-defined]
    assert first_child_id == second_child_id
    parent = store.load_snapshot(snapshot.id)
    child = store.load_snapshot(first_child_id)  # type: ignore[arg-type]
    checkpoint = store.load_checkpoint(snapshot.id)
    assert parent.status == "cancelled"
    assert parent.events[-1].event_type == "run.superseded"
    assert checkpoint.status == "resolved"
    assert checkpoint.resolution_run_id == child.id
    assert child.parent_run_id == parent.id
    assert child.derivation_kind == "retry"
    assert child.retry_from_step == "planning"
    assert child.steps[0].status == "pending"
    assert child.events[0].step_key == "planning"

    with pytest.raises(WorkflowConflictError, match="different decision"):
        store.decide_run(
            snapshot.id,
            session_id=session_id,
            decision="resume",
            step_key=None,
            input_ids=(input_id,),
            idempotency_key="resume-once",
            request_hash="sha256:" + "e" * 64,
            expected_status="cancelled",
            expected_revision=parent.revision,
        )


def test_resume_rejects_unowned_input_without_mutating_checkpoint(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    waiting = _open_checkpoint(store, snapshot)
    with pytest.raises(CheckpointUnavailableError, match="outside the Run owner"):
        store.decide_run(
            snapshot.id,
            session_id="not-the-owner",
            decision="resume",
            step_key=None,
            input_ids=(uuid4(),),
            idempotency_key="resume-unowned",
            request_hash="sha256:" + "f" * 64,
            expected_status="waiting_for_input",
            expected_revision=waiting.revision,
        )
    assert store.load_snapshot(snapshot.id).status == "waiting_for_input"
    assert store.load_checkpoint(snapshot.id).status == "open"


def test_checkpoint_cancel_decision_is_terminal_and_creates_no_child(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    waiting = _open_checkpoint(store, snapshot)
    with session_factory(postgres_engine)() as session:
        session_id = session.scalar(
            select(ResearchProjectModel.session_id).where(
                ResearchProjectModel.id == waiting.project_id
            )
        )
    assert session_id is not None
    decision, result_run_id = store.decide_run(
        waiting.id,
        session_id=session_id,
        decision="cancel",
        step_key=None,
        input_ids=(),
        idempotency_key="cancel-checkpoint",
        request_hash="sha256:" + "0" * 64,
        expected_status="waiting_for_input",
        expected_revision=waiting.revision,
    )
    terminal = store.load_snapshot(result_run_id)
    checkpoint = store.load_checkpoint(waiting.id)
    assert decision.child_run_id is None
    assert result_run_id == waiting.id
    assert terminal.status == "cancelled"
    assert terminal.events[-1].event_type == "run.cancelled"
    assert checkpoint.status == "cancelled"
    assert checkpoint.resolution_run_id is None


@pytest.mark.parametrize("retryable", [True, False])
def test_retry_decision_requires_a_repairable_failed_attempt(
    postgres_engine: Engine, retryable: bool
) -> None:
    store, snapshot = _create_run(postgres_engine, max_attempts=1)
    lease = store.acquire_lease(
        snapshot.id,
        owner="retry-test",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key=f"retry-failure-{uuid4()}",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    store.fail_run(
        snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=attempt.run_revision,
        error_class="TimeoutError" if retryable else "ValueError",
        error_code="UPSTREAM_TIMEOUT" if retryable else "CONTRACT_INVALID",
        public_message="Failed",
        retryable=retryable,
    )
    failed = store.load_snapshot(snapshot.id)
    with session_factory(postgres_engine)() as session:
        session_id = session.scalar(
            select(ResearchProjectModel.session_id).where(
                ResearchProjectModel.id == failed.project_id
            )
        )
    assert session_id is not None

    if not retryable:
        with pytest.raises(CheckpointUnavailableError, match="not classified"):
            store.decide_run(
                failed.id,
                session_id=session_id,
                decision="retry",
                step_key="planning",
                input_ids=(),
                idempotency_key="retry-nonrepairable",
                request_hash="sha256:" + "1" * 64,
                expected_status="failed",
                expected_revision=failed.revision,
            )
        assert store.load_snapshot(failed.id).status == "failed"
        return

    decision, child_id = store.decide_run(
        failed.id,
        session_id=session_id,
        decision="retry",
        step_key="planning",
        input_ids=(),
        idempotency_key="retry-repairable",
        request_hash="sha256:" + "2" * 64,
        expected_status="failed",
        expected_revision=failed.revision,
    )
    child = store.load_snapshot(child_id)
    assert decision.decision == "retry"
    assert child.parent_run_id == failed.id
    assert child.retry_from_step == "planning"
    assert store.load_snapshot(failed.id).status == "failed"


def test_retry_child_starts_at_exact_failed_step_after_skipped_prefix(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    lease = store.acquire_lease(
        snapshot.id,
        owner="suffix-retry-test",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    planning = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="suffix-planning",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    published = ArtifactPublisher(session_factory(postgres_engine)).publish_step_outputs(
        snapshot.id,
        step_key="planning",
        attempt_id=planning.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=planning.run_status,
        expected_revision=planning.run_revision,
        publications=(),
        public_message="Planning complete",
    )
    fetching = store.begin_step(
        snapshot.id,
        step_key="fetching_data",
        attempt_idempotency_key="suffix-fetching",
        token=lease.token,
        generation=lease.generation,
        expected_status=published.status,
        expected_revision=published.revision,
        public_message="Fetching",
    )
    store.fail_run(
        snapshot.id,
        step_key="fetching_data",
        attempt_id=fetching.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status=fetching.run_status,
        expected_revision=fetching.run_revision,
        error_class="TimeoutError",
        error_code="UPSTREAM_TIMEOUT",
        public_message="Fetching failed",
        retryable=True,
    )
    failed = store.load_snapshot(snapshot.id)
    with session_factory(postgres_engine)() as session:
        session_id = session.scalar(
            select(ResearchProjectModel.session_id).where(
                ResearchProjectModel.id == failed.project_id
            )
        )
    assert session_id is not None
    _, child_id = store.decide_run(
        failed.id,
        session_id=session_id,
        decision="retry",
        step_key="fetching_data",
        input_ids=(),
        idempotency_key="suffix-retry",
        request_hash="sha256:" + "3" * 64,
        expected_status="failed",
        expected_revision=failed.revision,
    )
    child = store.load_snapshot(child_id)
    assert child.steps[0].status == "skipped"
    assert child.steps[1].status == "pending"
    child_lease = store.acquire_lease(
        child.id,
        owner="suffix-child",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=child.revision,
    )
    restarted = store.begin_step(
        child.id,
        step_key="fetching_data",
        attempt_idempotency_key="suffix-child-fetching",
        token=child_lease.token,
        generation=child_lease.generation,
        expected_status="queued",
        expected_revision=child_lease.revision,
        public_message="Retrying fetching",
    )
    assert restarted.run_status == "fetching_data"


def test_failed_run_rejects_late_results_and_snapshot_cursor_recovers(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-1",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    failed = store.fail_run(
        snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=lease.token,
        generation=lease.generation,
        expected_status="planning",
        expected_revision=attempt.run_revision,
        error_class="PipelineError",
        error_code="PIPELINE_FAILED",
        public_message="Pipeline failed",
    )
    with pytest.raises(StaleWorkflowWriteError):
        store.fail_run(
            snapshot.id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status="planning",
            expected_revision=failed.revision,
            error_class="LateResult",
            error_code="LATE_RESULT",
            public_message="Late result",
        )

    first_page = store.load_snapshot(snapshot.id, event_limit=1)
    second_page = store.load_snapshot(
        snapshot.id, after_event_sequence=first_page.next_event_cursor, event_limit=10
    )
    current = store.load_snapshot(snapshot.id)

    assert current.status == "failed"
    assert current.steps[0].status == "failed"
    assert current.steps[0].attempts[0].status == "failed"
    assert first_page.has_more_events is True
    assert [event.sequence for event in first_page.events + second_page.events] == list(
        range(1, current.latest_event_sequence + 1)
    )


def test_cancellation_rejects_late_results_and_snapshot_cursor_recovers(
    postgres_engine: Engine,
) -> None:
    store, snapshot = _create_run(postgres_engine)
    lease = store.acquire_lease(
        snapshot.id,
        owner="executor",
        lease_duration=timedelta(seconds=30),
        expected_status="queued",
        expected_revision=snapshot.revision,
    )
    attempt = store.begin_step(
        snapshot.id,
        step_key="planning",
        attempt_idempotency_key="attempt-1",
        token=lease.token,
        generation=lease.generation,
        expected_status="queued",
        expected_revision=lease.revision,
        public_message="Planning",
    )
    cancelled = store.cancel_run(
        snapshot.id,
        expected_status="planning",
        expected_revision=attempt.run_revision,
    )
    with pytest.raises(StaleWorkflowWriteError):
        store.fail_run(
            snapshot.id,
            step_key="planning",
            attempt_id=attempt.attempt_id,
            token=lease.token,
            generation=lease.generation,
            expected_status="planning",
            expected_revision=cancelled.revision,
            error_class="LateResult",
            error_code="LATE_RESULT",
            public_message="Late result",
        )

    first_page = store.load_snapshot(snapshot.id, event_limit=1)
    second_page = store.load_snapshot(
        snapshot.id, after_event_sequence=first_page.next_event_cursor, event_limit=10
    )
    current = store.load_snapshot(snapshot.id)

    assert current.status == "cancelled"
    assert current.steps[0].status == "cancelled"
    assert current.steps[0].attempts[0].status == "cancelled"
    assert first_page.has_more_events is True
    assert [event.sequence for event in first_page.events + second_page.events] == list(
        range(1, current.latest_event_sequence + 1)
    )
    repeated = store.cancel_run(
        snapshot.id,
        expected_status="cancelled",
        expected_revision=cancelled.revision,
    )
    assert repeated == cancelled


def test_live_queue_admission_is_atomic_and_idempotent(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    factory = session_factory(postgres_engine)
    _, project, contract = _seed_project(postgres_engine)
    store = PersistentWorkflowStore(
        factory,
        capacity_policy=_capacity_policy(queued_global=1, queued_project=1),
    )
    barrier = Barrier(2)

    def create(key: str) -> tuple[str, RunSnapshot | RunQueueCapacityError]:
        barrier.wait()
        try:
            result: RunSnapshot | RunQueueCapacityError = store.create_run(
                project_id=project.id,
                contract_id=contract.id,
                execution_mode="live",
                idempotency_key=key,
                request_hash=f"sha256:{key[-1] * 64}",
                steps=_step_definitions(),
            )
        except RunQueueCapacityError as exc:
            result = exc
        return key, result

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(create, ("run-a", "run-b")))

    accepted_key, accepted = next(
        item for item in results if isinstance(item[1], RunSnapshot)
    )
    _, rejected = next(
        item for item in results if isinstance(item[1], RunQueueCapacityError)
    )
    assert isinstance(accepted, RunSnapshot)
    assert isinstance(rejected, RunQueueCapacityError)
    assert rejected.scope == "global"
    assert rejected.retry_after_seconds == 7
    replay = store.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key=accepted_key,
        request_hash=(
            "sha256:" + "a" * 64
            if accepted_key == "run-a"
            else "sha256:" + "b" * 64
        ),
        steps=_step_definitions(),
    )
    assert replay.id == accepted.id


def test_active_capacity_is_enforced_across_concurrent_workers(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    factory = session_factory(postgres_engine)
    _, first_project, first_contract = _seed_project(postgres_engine)
    _, second_project, second_contract = _seed_project(postgres_engine)
    store = PersistentWorkflowStore(
        factory,
        capacity_policy=_capacity_policy(active_global=1, active_project=1),
    )
    first = store.create_run(
        project_id=first_project.id,
        contract_id=first_contract.id,
        execution_mode="live",
        idempotency_key="active-a",
        request_hash="sha256:" + "a" * 64,
        steps=_step_definitions(),
    )
    second = store.create_run(
        project_id=second_project.id,
        contract_id=second_contract.id,
        execution_mode="live",
        idempotency_key="active-b",
        request_hash="sha256:" + "b" * 64,
        steps=_step_definitions(),
    )
    barrier = Barrier(2)

    def acquire(snapshot: RunSnapshot) -> LeaseGrant | WorkerCapacityUnavailableError:
        barrier.wait()
        try:
            return store.acquire_lease(
                snapshot.id,
                owner=f"worker-{snapshot.id}",
                lease_duration=timedelta(seconds=30),
                expected_status="queued",
                expected_revision=snapshot.revision,
            )
        except WorkerCapacityUnavailableError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(acquire, (first, second)))

    assert sum(isinstance(item, LeaseGrant) for item in results) == 1
    assert sum(isinstance(item, WorkerCapacityUnavailableError) for item in results) == 1
    with factory() as session:
        dispatches = tuple(session.scalars(select(WorkflowProjectDispatchModel)))
    assert len(dispatches) == 1
    assert dispatches[0].dispatch_count == 1


def test_live_nonterminal_capacity_includes_waiting_runs(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    factory = session_factory(postgres_engine)
    _, project, contract = _seed_project(postgres_engine)
    store = PersistentWorkflowStore(
        factory,
        capacity_policy=_capacity_policy(
            queued_global=1,
            queued_project=1,
            active_global=1,
            active_project=1,
            nonterminal_global=1,
            nonterminal_project=1,
        ),
    )
    waiting = store.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key="waiting-run",
        request_hash="sha256:" + "e" * 64,
        steps=_step_definitions(),
    )
    _open_checkpoint(store, waiting)

    with pytest.raises(RunQueueCapacityError) as captured:
        store.create_run(
            project_id=project.id,
            contract_id=contract.id,
            execution_mode="live",
            idempotency_key="after-waiting",
            request_hash="sha256:" + "f" * 64,
            steps=_step_definitions(),
        )

    assert captured.value.scope == "global nonterminal"


def test_fair_selection_offers_one_oldest_run_per_project(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    factory = session_factory(postgres_engine)
    _, first_project, first_contract = _seed_project(postgres_engine)
    _, second_project, second_contract = _seed_project(postgres_engine)
    policy = _capacity_policy(active_global=2, active_project=2)
    store = PersistentWorkflowStore(factory, capacity_policy=policy)
    first = store.create_run(
        project_id=first_project.id,
        contract_id=first_contract.id,
        execution_mode="live",
        idempotency_key="fair-a-1",
        request_hash="sha256:" + "a" * 64,
        steps=_step_definitions(),
    )
    store.create_run(
        project_id=first_project.id,
        contract_id=first_contract.id,
        execution_mode="live",
        idempotency_key="fair-a-2",
        request_hash="sha256:" + "b" * 64,
        steps=_step_definitions(),
    )
    second = store.create_run(
        project_id=second_project.id,
        contract_id=second_contract.id,
        execution_mode="live",
        idempotency_key="fair-b-1",
        request_hash="sha256:" + "c" * 64,
        steps=_step_definitions(),
    )
    worker = object.__new__(ResearchRunWorker)
    worker._session_factory = factory
    worker._capacity_policy = policy

    offered = worker._runnable_run_ids(2)

    assert set(offered) == {first.id, second.id}


def test_queue_timeout_persists_stable_terminal_failure(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    factory = session_factory(postgres_engine)
    _, project, contract = _seed_project(postgres_engine)
    store = PersistentWorkflowStore(factory, capacity_policy=_capacity_policy())
    snapshot = store.create_run(
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        idempotency_key="queue-timeout",
        request_hash="sha256:" + "d" * 64,
        steps=_step_definitions(),
    )
    with factory() as session, session.begin():
        session.execute(
            update(ResearchRunModel)
            .where(ResearchRunModel.id == snapshot.id)
            .values(queue_expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    assert store.expire_queued_runs() == (snapshot.id,)
    expired = store.load_snapshot(snapshot.id)
    assert expired.status == "failed"
    assert expired.failure_code == "RUN_QUEUE_TIMEOUT"
    assert expired.steps[0].status == "failed"
    assert all(step.status == "cancelled" for step in expired.steps[1:])
    assert expired.events[-1].event_type == "run.failed"


def test_worker_lifecycle_is_persistent_and_auditable(
    postgres_engine: Engine,
) -> None:
    _clear_capacity_test_state(postgres_engine)
    registry = PersistentWorkerRegistry(session_factory(postgres_engine))

    accepting = registry.register("worker-audit", configured_capacity=2)
    draining = registry.request_drain("worker-audit")
    stopped = registry.mark_stopped("worker-audit")

    assert accepting.state == "accepting"
    assert draining.state == "draining"
    assert draining.drain_requested_at is not None
    assert stopped.state == "stopped"
    assert stopped.stopped_at is not None
