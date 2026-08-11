"""PostgreSQL concurrency and recovery contract tests for the workflow store.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
These tests exercise PostgreSQL row locks and database time and therefore do
not substitute SQLite when PostgreSQL is unavailable.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import asyncio
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunStepModel,
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
    LeaseGrant,
    LeaseUnavailableError,
    PersistentWorkflowStore,
    RunSnapshot,
    RunStepDefinition,
    StaleWorkflowWriteError,
    WorkflowConflictError,
)
from app.workflow.persistent_executor import (
    FailureDecision,
    PersistentWorkflowExecutionError,
    PersistentWorkflowExecutor,
)

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

    with pytest.raises(ValueError, match="not declared by WORKFLOW_DESIGN.md"):
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
                    success_status="completed",
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
        WorkflowConflictError, match="previous frozen run step is incomplete"
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


def test_expired_lease_takeover_fences_old_executor_and_reports_active_attempt(
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
    assert takeover.active_attempt_ids == (attempt.attempt_id,)
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

    recovered = store.record_retryable_failure(
        snapshot.id,
        step_key="planning",
        attempt_id=attempt.attempt_id,
        token=takeover.token,
        generation=takeover.generation,
        expected_status="planning",
        expected_revision=takeover.revision,
        error_class="ExecutorCrash",
        error_code="LEASE_EXPIRED",
        public_message="Recovered expired attempt",
    )
    assert recovered.status == "planning"


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
