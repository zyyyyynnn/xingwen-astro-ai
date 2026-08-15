"""PostgreSQL-backed ResearchRun lifecycle store.

Every mutating operation is a short transaction. Pipeline, model, and source
calls must happen between these operations and never while a store transaction
is open.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchInputContentModel,
    ResearchInputModel,
    ResearchRunModel,
    RunCheckpointModel,
    RunDecisionModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
    WorkflowProjectDispatchModel,
)
from app.workflow.capacity import WorkflowCapacityPolicy

TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
INCOMPLETE_STEP_STATUSES = frozenset({"pending", "running", "waiting"})
RUN_STEP_STATUS_ORDER = (
    "planning",
    "fetching_data",
    "cleaning_data",
    "acquiring_observations",
    "analyzing_data",
    "training_models",
    "building_visualizations",
    "searching_papers",
    "summarizing_papers",
    "reasoning_literature",
    "building_graph",
)
_CAPACITY_ADVISORY_LOCK_ID = 8_146_273_911


class WorkflowStoreError(RuntimeError):
    """Base class for stable workflow persistence failures."""

    code = "WORKFLOW_STORE_ERROR"


class RunNotFoundError(WorkflowStoreError):
    code = "RUN_NOT_FOUND"


class WorkflowConflictError(WorkflowStoreError):
    code = "WORKFLOW_CONFLICT"


class LeaseUnavailableError(WorkflowConflictError):
    code = "RUN_LEASE_UNAVAILABLE"


class RunQueueCapacityError(WorkflowConflictError):
    code = "RUN_QUEUE_CAPACITY_EXCEEDED"

    def __init__(self, *, scope: str, retry_after_seconds: int) -> None:
        super().__init__(f"the {scope} live Run queue is at capacity")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


class WorkerCapacityUnavailableError(LeaseUnavailableError):
    code = "WORKER_CAPACITY_UNAVAILABLE"


class StaleWorkflowWriteError(WorkflowConflictError):
    code = "STALE_WORKFLOW_WRITE"


class RetryBudgetExhaustedError(WorkflowConflictError):
    code = "STEP_RETRY_BUDGET_EXHAUSTED"


class CheckpointUnavailableError(WorkflowConflictError):
    code = "RUN_CHECKPOINT_UNAVAILABLE"


class StepNotFoundError(WorkflowStoreError):
    code = "RUN_STEP_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class RunStepDefinition:
    key: str
    label: str
    enter_status: str
    success_status: str
    max_attempts: int = 1
    task_id: str | None = None
    skill_id: str | None = None
    depends_on_step_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LeaseGrant:
    run_id: UUID
    token: UUID
    generation: int
    revision: int
    expires_at: datetime
    active_attempt_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class AttemptHandle:
    run_id: UUID
    run_step_id: UUID
    attempt_id: UUID
    attempt_number: int
    run_status: str
    run_revision: int
    event_sequence: int


@dataclass(frozen=True, slots=True)
class MutationResult:
    run_id: UUID
    status: str
    revision: int
    latest_event_sequence: int


@dataclass(frozen=True, slots=True)
class AttemptSnapshot:
    id: UUID
    attempt_number: int
    status: str
    retryable: bool
    started_at: datetime
    finished_at: datetime | None
    error_class: str | None
    error_code: str | None
    upstream_request_id: str | None


@dataclass(frozen=True, slots=True)
class StepSnapshot:
    id: UUID
    position: int
    key: str
    label: str
    enter_status: str
    success_status: str
    max_attempts: int
    task_id: str | None
    skill_id: str | None
    depends_on_step_keys: tuple[str, ...]
    status: str
    progress: int
    started_at: datetime | None
    finished_at: datetime | None
    input_hash: str | None
    failure_code: str | None
    public_message: str
    attempts: tuple[AttemptSnapshot, ...]


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    sequence: int
    event_type: str
    step_key: str | None
    progress: int | None
    public_message: str
    artifact_version_ids: tuple[str, ...]
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class CheckpointSnapshot:
    id: UUID
    run_id: UUID
    step_key: str
    status: str
    code: str
    public_message: str
    required_input_types: tuple[str, ...]
    opened_at: datetime
    resolved_at: datetime | None
    resolution_run_id: UUID | None


@dataclass(frozen=True, slots=True)
class DecisionSnapshot:
    id: UUID
    parent_run_id: UUID
    child_run_id: UUID | None
    decision: str
    step_key: str
    input_ids: tuple[str, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RunSnapshot:
    id: UUID
    project_id: UUID
    contract_id: UUID
    execution_mode: str
    status: str
    progress: int
    parent_run_id: UUID | None
    derivation_kind: str
    retry_from_step: str | None
    cache_policy: str
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    revision: int
    lease_generation: int
    lease_expires_at: datetime | None
    queue_expires_at: datetime | None
    latest_event_sequence: int
    failure_code: str | None
    failure_summary: str | None
    steps: tuple[StepSnapshot, ...]
    events: tuple[EventSnapshot, ...]
    next_event_cursor: int
    has_more_events: bool


class PersistentWorkflowStore:
    """Aggregate-level transactional store for one sequential ResearchRun."""

    def __init__(
        self,
        factory: Callable[[], Session],
        *,
        capacity_policy: WorkflowCapacityPolicy | None = None,
    ) -> None:
        self._factory = factory
        self._capacity_policy = capacity_policy

    def create_run(
        self,
        *,
        project_id: UUID,
        contract_id: UUID,
        execution_mode: str,
        idempotency_key: str,
        request_hash: str,
        steps: Sequence[RunStepDefinition],
    ) -> RunSnapshot:
        self._validate_step_definitions(steps)
        run_id: UUID
        with self._factory() as session, session.begin():
            now_value = session.scalar(select(func.clock_timestamp()))
            if execution_mode == "live" and self._capacity_policy is not None:
                self._acquire_capacity_lock(session)
                existing = session.scalar(
                    select(ResearchRunModel).where(
                        ResearchRunModel.project_id == project_id,
                        ResearchRunModel.idempotency_key == idempotency_key,
                    )
                )
                if existing is not None:
                    if existing.request_hash != request_hash:
                        raise WorkflowConflictError(
                            "idempotency key was already used with a different request"
                        )
                    run_id = existing.id
                    return self.load_snapshot(run_id)
                self._expire_queued_runs_in_session(session, now=now_value, limit=100)
                self._assert_queue_capacity(session, project_id=project_id)
            candidate_run_id = uuid4()
            inserted_run_id = session.scalar(
                pg_insert(ResearchRunModel)
                .values(
                    id=candidate_run_id,
                    project_id=project_id,
                    contract_id=contract_id,
                    execution_mode=execution_mode,
                    status="queued",
                    progress=0,
                    parent_run_id=None,
                    derivation_kind="original",
                    retry_from_step=None,
                    cache_policy="disabled",
                    latest_event_sequence=1,
                    revision=1,
                    lease_generation=0,
                    queue_expires_at=(
                        now_value + self._capacity_policy.queue_timeout
                        if execution_mode == "live"
                        and self._capacity_policy is not None
                        else None
                    ),
                    steps_frozen_at=None,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                .on_conflict_do_nothing(constraint="uq_research_run_idempotency")
                .returning(ResearchRunModel.id)
            )
            if inserted_run_id is None:
                existing = session.scalar(
                    select(ResearchRunModel).where(
                        ResearchRunModel.project_id == project_id,
                        ResearchRunModel.idempotency_key == idempotency_key,
                    )
                )
                if existing is None:  # pragma: no cover - database invariant safeguard
                    raise WorkflowConflictError(
                        "idempotent Run creation lost its winner"
                    )
                if existing.request_hash != request_hash:
                    raise WorkflowConflictError(
                        "idempotency key was already used with a different request"
                    )
                run_id = existing.id
            else:
                run_id = inserted_run_id
                session.add_all(
                    [
                        RunStepModel(
                            run_id=run_id,
                            position=position,
                            key=definition.key,
                            label=definition.label,
                            enter_status=definition.enter_status,
                            success_status=definition.success_status,
                            max_attempts=definition.max_attempts,
                            task_id=definition.task_id,
                            skill_id=definition.skill_id,
                            depends_on_step_keys=list(
                                definition.depends_on_step_keys
                            ),
                            status="pending",
                            progress=0,
                            public_message="",
                        )
                        for position, definition in enumerate(steps)
                    ]
                )
                session.add(
                    RunEventModel(
                        run_id=run_id,
                        sequence=1,
                        event_type="run.queued",
                        progress=0,
                        public_message="Run queued",
                        artifact_version_ids=[],
                    )
                )
                session.flush()
                frozen = session.execute(
                    update(ResearchRunModel)
                    .where(
                        ResearchRunModel.id == run_id,
                        ResearchRunModel.steps_frozen_at.is_(None),
                    )
                    .values(steps_frozen_at=func.clock_timestamp())
                )
                if (
                    frozen.rowcount != 1
                ):  # pragma: no cover - transaction invariant safeguard
                    raise WorkflowConflictError(
                        "RunStep collection could not be frozen"
                    )
        return self.load_snapshot(run_id)

    def expire_queued_runs(self, *, limit: int = 100) -> tuple[UUID, ...]:
        """Fail queued live Runs whose durable admission deadline elapsed."""

        if not 1 <= limit <= 1000:
            raise ValueError("queue expiration limit must be between 1 and 1000")
        if self._capacity_policy is None:
            return ()
        with self._factory() as session, session.begin():
            now_value = session.scalar(select(func.clock_timestamp()))
            return self._expire_queued_runs_in_session(
                session, now=now_value, limit=limit
            )

    def release_lease(self, run_id: UUID, *, token: UUID, generation: int) -> bool:
        """Relinquish a valid lease without rewriting scientific Run state."""

        with self._factory() as session, session.begin():
            result = session.execute(
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.lease_token == token,
                    ResearchRunModel.lease_generation == generation,
                )
                .values(
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    revision=ResearchRunModel.revision + 1,
                    updated_at=func.clock_timestamp(),
                )
                .execution_options(synchronize_session=False)
            )
            return result.rowcount == 1

    def acquire_lease(
        self,
        run_id: UUID,
        *,
        owner: str,
        lease_duration: timedelta,
        expected_status: str,
        expected_revision: int,
    ) -> LeaseGrant:
        if not owner.strip():
            raise ValueError("lease owner must not be empty")
        if lease_duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        token = uuid4()
        with self._factory() as session, session.begin():
            now = func.clock_timestamp()
            run = session.get(ResearchRunModel, run_id)
            if run is None:
                raise RunNotFoundError(f"run {run_id} was not found")
            if run.execution_mode == "live" and self._capacity_policy is not None:
                self._acquire_capacity_lock(session)
                now_value = session.scalar(select(func.clock_timestamp()))
                active_global = session.scalar(
                    select(func.count())
                    .select_from(ResearchRunModel)
                    .where(
                        ResearchRunModel.execution_mode == "live",
                        ResearchRunModel.status.not_in(TERMINAL_RUN_STATUSES),
                        ResearchRunModel.lease_token.is_not(None),
                        ResearchRunModel.lease_expires_at > now_value,
                    )
                )
                active_project = session.scalar(
                    select(func.count())
                    .select_from(ResearchRunModel)
                    .where(
                        ResearchRunModel.execution_mode == "live",
                        ResearchRunModel.project_id == run.project_id,
                        ResearchRunModel.status.not_in(TERMINAL_RUN_STATUSES),
                        ResearchRunModel.lease_token.is_not(None),
                        ResearchRunModel.lease_expires_at > now_value,
                    )
                )
                if active_global >= self._capacity_policy.max_active_global:
                    raise WorkerCapacityUnavailableError(
                        "global live Run execution capacity is exhausted"
                    )
                if active_project >= self._capacity_policy.max_active_per_project:
                    raise WorkerCapacityUnavailableError(
                        "project live Run execution capacity is exhausted"
                    )
            statement = (
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.status == expected_status,
                    ResearchRunModel.revision == expected_revision,
                    ResearchRunModel.status.not_in(TERMINAL_RUN_STATUSES),
                    or_(
                        ResearchRunModel.lease_token.is_(None),
                        ResearchRunModel.lease_expires_at <= now,
                    ),
                )
                .values(
                    lease_token=token,
                    lease_owner=owner,
                    lease_generation=ResearchRunModel.lease_generation + 1,
                    lease_expires_at=now + lease_duration,
                    revision=ResearchRunModel.revision + 1,
                    updated_at=now,
                )
                .returning(
                    ResearchRunModel.lease_generation,
                    ResearchRunModel.revision,
                    ResearchRunModel.lease_expires_at,
                )
                .execution_options(synchronize_session=False)
            )
            row = session.execute(statement).one_or_none()
            if row is None:
                if session.get(ResearchRunModel, run_id) is None:
                    raise RunNotFoundError(f"run {run_id} was not found")
                raise LeaseUnavailableError(
                    "run lease is held, expired state changed, or the snapshot is stale"
                )
            run = session.get(ResearchRunModel, run_id, populate_existing=True)
            if run is None:  # pragma: no cover - update returned this identity
                raise RunNotFoundError(f"run {run_id} was not found")
            now_value = session.scalar(select(func.clock_timestamp()))
            if run.execution_mode == "live" and self._capacity_policy is not None:
                session.execute(
                    pg_insert(WorkflowProjectDispatchModel)
                    .values(
                        project_id=run.project_id,
                        last_dispatched_at=now_value,
                        dispatch_count=1,
                    )
                    .on_conflict_do_update(
                        index_elements=(WorkflowProjectDispatchModel.project_id,),
                        set_={
                            "last_dispatched_at": now_value,
                            "dispatch_count": (
                                WorkflowProjectDispatchModel.dispatch_count + 1
                            ),
                        },
                    )
                )
            self._reconcile_abandoned_attempt(run, session, now_value)
            session.flush()
            active_attempt_ids = self._active_attempt_ids(session, run_id)
            return LeaseGrant(
                run_id=run_id,
                token=token,
                generation=run.lease_generation,
                revision=run.revision,
                expires_at=run.lease_expires_at,
                active_attempt_ids=active_attempt_ids,
            )

    def heartbeat_lease(
        self,
        run_id: UUID,
        *,
        token: UUID,
        generation: int,
        lease_duration: timedelta,
        expected_status: str,
        expected_revision: int,
    ) -> LeaseGrant:
        if lease_duration <= timedelta(0):
            raise ValueError("lease duration must be positive")
        with self._factory() as session, session.begin():
            now = func.clock_timestamp()
            statement = (
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.status == expected_status,
                    ResearchRunModel.revision == expected_revision,
                    ResearchRunModel.lease_token == token,
                    ResearchRunModel.lease_generation == generation,
                    ResearchRunModel.lease_expires_at > now,
                    ResearchRunModel.status.not_in(TERMINAL_RUN_STATUSES),
                )
                .values(
                    lease_expires_at=now + lease_duration,
                    updated_at=now,
                )
                .returning(ResearchRunModel.revision, ResearchRunModel.lease_expires_at)
                .execution_options(synchronize_session=False)
            )
            row = session.execute(statement).one_or_none()
            if row is None:
                self._raise_stale_or_missing(session, run_id)
            active_attempt_ids = self._active_attempt_ids(session, run_id)
            return LeaseGrant(
                run_id=run_id,
                token=token,
                generation=generation,
                revision=row.revision,
                expires_at=row.lease_expires_at,
                active_attempt_ids=active_attempt_ids,
            )

    def begin_step(
        self,
        run_id: UUID,
        *,
        step_key: str,
        attempt_idempotency_key: str,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        public_message: str,
    ) -> AttemptHandle:
        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            self._require_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            step = session.scalar(
                select(RunStepModel)
                .where(RunStepModel.run_id == run_id, RunStepModel.key == step_key)
                .with_for_update()
            )
            if step is None:
                raise StepNotFoundError(
                    f"step {step_key!r} was not found for run {run_id}"
                )
            if step.status != "pending":
                raise WorkflowConflictError(
                    f"step {step_key!r} cannot begin from status {step.status!r}"
                )
            incomplete_dependencies = session.scalar(
                select(func.count())
                .select_from(RunStepModel)
                .where(
                    RunStepModel.run_id == run_id,
                    RunStepModel.key.in_(step.depends_on_step_keys),
                    RunStepModel.status.not_in(("completed", "skipped")),
                )
            )
            if incomplete_dependencies:
                raise WorkflowConflictError("a frozen run step dependency is incomplete")
            attempt_number = (
                session.scalar(
                    select(
                        func.coalesce(func.max(StepAttemptModel.attempt_number), 0)
                    ).where(StepAttemptModel.run_step_id == step.id)
                )
                + 1
            )
            if attempt_number > step.max_attempts:
                raise RetryBudgetExhaustedError("step retry budget is exhausted")
            earlier_executable_steps = session.scalar(
                select(func.count())
                .select_from(RunStepModel)
                .where(
                    RunStepModel.run_id == run_id,
                    RunStepModel.position < step.position,
                    RunStepModel.status != "skipped",
                )
            )
            required_run_status = (
                "queued"
                if attempt_number == 1 and not earlier_executable_steps
                else step.enter_status
            )
            if expected_status != required_run_status:
                raise WorkflowConflictError(
                    "run status does not match the frozen step transition: "
                    f"expected {required_run_status!r}, got {expected_status!r}"
                )

            now = func.clock_timestamp()
            sequence = run.latest_event_sequence + 1
            step_result = session.execute(
                update(RunStepModel)
                .where(RunStepModel.id == step.id, RunStepModel.status == "pending")
                .values(
                    status="running",
                    started_at=func.coalesce(RunStepModel.started_at, now),
                    finished_at=None,
                    failure_code=None,
                    public_message=public_message,
                )
                .execution_options(synchronize_session=False)
            )
            if step_result.rowcount != 1:
                raise StaleWorkflowWriteError(
                    "run step changed before begin_step committed"
                )
            run_result = session.execute(
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.status == expected_status,
                    ResearchRunModel.revision == expected_revision,
                    ResearchRunModel.lease_token == token,
                    ResearchRunModel.lease_generation == generation,
                    ResearchRunModel.lease_expires_at > now,
                )
                .values(
                    status=step.enter_status,
                    started_at=func.coalesce(ResearchRunModel.started_at, now),
                    revision=ResearchRunModel.revision + 1,
                    latest_event_sequence=sequence,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if run_result.rowcount != 1:
                raise StaleWorkflowWriteError("run changed before begin_step committed")
            attempt = StepAttemptModel(
                id=uuid4(),
                run_step_id=step.id,
                attempt_number=attempt_number,
                idempotency_key=attempt_idempotency_key,
                status="running",
                retryable=False,
            )
            session.add(attempt)
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                event_type="step.started",
                step_key=step.key,
                progress=run.progress,
                public_message=public_message,
            )
            return AttemptHandle(
                run_id=run_id,
                run_step_id=step.id,
                attempt_id=attempt.id,
                attempt_number=attempt_number,
                run_status=step.enter_status,
                run_revision=expected_revision + 1,
                event_sequence=sequence,
            )

    def record_retryable_failure(
        self,
        run_id: UUID,
        *,
        step_key: str,
        attempt_id: UUID,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        error_class: str,
        error_code: str,
        public_message: str,
        upstream_request_id: str | None = None,
    ) -> MutationResult:
        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            self._require_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            step, attempt = self._lock_running_attempt(
                session, run_id, step_key, attempt_id
            )
            if attempt.attempt_number >= step.max_attempts:
                raise RetryBudgetExhaustedError(
                    "retryable failure cannot be scheduled after retry budget exhaustion"
                )
            now = func.clock_timestamp()
            sequence = run.latest_event_sequence + 1
            attempt.status = "failed"
            attempt.finished_at = session.scalar(select(now))
            attempt.error_class = error_class
            attempt.error_code = error_code
            attempt.retryable = True
            attempt.upstream_request_id = upstream_request_id
            step.status = "pending"
            step.finished_at = None
            step.failure_code = error_code
            step.public_message = public_message
            self._conditional_run_update(
                session,
                run_id=run_id,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
                values={
                    "revision": ResearchRunModel.revision + 1,
                    "latest_event_sequence": sequence,
                    "updated_at": now,
                },
            )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                event_type="step.retry_scheduled",
                step_key=step.key,
                progress=run.progress,
                public_message=public_message,
            )
            return MutationResult(
                run_id=run_id,
                status=expected_status,
                revision=expected_revision + 1,
                latest_event_sequence=sequence,
            )

    def fail_run(
        self,
        run_id: UUID,
        *,
        step_key: str,
        attempt_id: UUID,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        error_class: str,
        error_code: str,
        public_message: str,
        retryable: bool = False,
        upstream_request_id: str | None = None,
    ) -> MutationResult:
        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            self._require_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            step, attempt = self._lock_running_attempt(
                session, run_id, step_key, attempt_id
            )
            now_value = session.scalar(select(func.clock_timestamp()))
            sequence = run.latest_event_sequence + 1
            attempt.status = "failed"
            attempt.finished_at = now_value
            attempt.error_class = error_class
            attempt.error_code = error_code
            attempt.retryable = retryable
            attempt.upstream_request_id = upstream_request_id
            step.status = "failed"
            step.finished_at = now_value
            step.failure_code = error_code
            step.public_message = public_message
            self._conditional_run_update(
                session,
                run_id=run_id,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
                values={
                    "status": "failed",
                    "finished_at": now_value,
                    "failure_code": error_code,
                    "failure_summary": public_message,
                    "lease_token": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "revision": ResearchRunModel.revision + 1,
                    "latest_event_sequence": sequence,
                    "updated_at": now_value,
                },
            )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                event_type="run.failed",
                step_key=step.key,
                progress=run.progress,
                public_message=public_message,
            )
            return MutationResult(run_id, "failed", expected_revision + 1, sequence)

    def request_human_input(
        self,
        run_id: UUID,
        *,
        step_key: str,
        attempt_id: UUID,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        error_class: str,
        error_code: str,
        public_message: str,
        required_input_types: tuple[str, ...],
    ) -> MutationResult:
        """Suspend one running Attempt at an audited, server-classified boundary."""

        allowed_input_types = frozenset({"pdf", "text"})
        if (
            not required_input_types
            or len(required_input_types) != len(set(required_input_types))
            or not set(required_input_types) <= allowed_input_types
        ):
            raise ValueError("checkpoint input types are outside the controlled contract")
        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            self._require_lease(
                session,
                run,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
            )
            if session.scalar(
                select(RunCheckpointModel.id).where(RunCheckpointModel.run_id == run_id)
            ) is not None:
                raise CheckpointUnavailableError("Run already has a checkpoint")
            step, attempt = self._lock_running_attempt(
                session, run_id, step_key, attempt_id
            )
            now_value = session.scalar(select(func.clock_timestamp()))
            sequence = run.latest_event_sequence + 1
            attempt.status = "failed"
            attempt.finished_at = now_value
            attempt.error_class = error_class
            attempt.error_code = error_code
            attempt.retryable = True
            step.status = "waiting"
            step.finished_at = None
            step.failure_code = error_code
            step.public_message = public_message
            checkpoint = RunCheckpointModel(
                run_id=run_id,
                project_id=run.project_id,
                step_key=step.key,
                attempt_id=attempt.id,
                status="open",
                code=error_code,
                public_message=public_message,
                required_input_types=list(required_input_types),
                opened_at=now_value,
            )
            session.add(checkpoint)
            self._conditional_run_update(
                session,
                run_id=run_id,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
                values={
                    "status": "waiting_for_input",
                    "failure_code": error_code,
                    "failure_summary": public_message,
                    "lease_token": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "revision": ResearchRunModel.revision + 1,
                    "latest_event_sequence": sequence,
                    "updated_at": now_value,
                },
            )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                event_type="step.waiting_for_input",
                step_key=step.key,
                progress=run.progress,
                public_message=public_message,
            )
            return MutationResult(
                run_id, "waiting_for_input", expected_revision + 1, sequence
            )

    def load_checkpoint(self, run_id: UUID) -> CheckpointSnapshot:
        with self._factory() as session:
            row = session.scalar(
                select(RunCheckpointModel).where(RunCheckpointModel.run_id == run_id)
            )
            if row is None:
                raise CheckpointUnavailableError("Run has no checkpoint")
            return self._checkpoint_snapshot(row)

    def decide_run(
        self,
        run_id: UUID,
        *,
        session_id: str,
        decision: str,
        step_key: str | None,
        input_ids: tuple[UUID, ...],
        idempotency_key: str,
        request_hash: str,
        expected_status: str,
        expected_revision: int,
    ) -> tuple[DecisionSnapshot, UUID]:
        """Apply one idempotent user decision and return the resulting Run id."""

        if decision not in {"resume", "retry", "cancel"}:
            raise ValueError("unsupported Run decision")
        result_run_id: UUID
        with self._factory() as session, session.begin():
            if self._capacity_policy is not None:
                self._acquire_capacity_lock(session)
            parent = self._lock_run(session, run_id)
            replay = session.scalar(
                select(RunDecisionModel).where(
                    RunDecisionModel.parent_run_id == run_id,
                    RunDecisionModel.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.request_hash != request_hash:
                    raise WorkflowConflictError(
                        "idempotency key was already used with a different decision"
                    )
                return self._decision_snapshot(replay), replay.child_run_id or run_id
            if parent.status != expected_status or parent.revision != expected_revision:
                raise StaleWorkflowWriteError("run snapshot is stale")

            checkpoint = session.scalar(
                select(RunCheckpointModel)
                .where(RunCheckpointModel.run_id == run_id)
                .with_for_update()
            )
            target_step_key: str
            if decision in {"resume", "cancel"}:
                if (
                    parent.status != "waiting_for_input"
                    or checkpoint is None
                    or checkpoint.status != "open"
                ):
                    raise CheckpointUnavailableError(
                        "resume and cancel decisions require an open checkpoint"
                    )
                target_step_key = checkpoint.step_key
            else:
                if parent.status != "failed" or step_key is None:
                    raise CheckpointUnavailableError(
                        "retry requires a failed Run and explicit failed step"
                    )
                failed_step = session.scalar(
                    select(RunStepModel)
                    .where(
                        RunStepModel.run_id == run_id,
                        RunStepModel.key == step_key,
                        RunStepModel.status == "failed",
                    )
                    .with_for_update()
                )
                if failed_step is None:
                    raise CheckpointUnavailableError(
                        "retry step is not the failed step of this Run"
                    )
                retryable = session.scalar(
                    select(StepAttemptModel.retryable)
                    .where(StepAttemptModel.run_step_id == failed_step.id)
                    .order_by(StepAttemptModel.attempt_number.desc())
                    .limit(1)
                )
                if retryable is not True:
                    raise CheckpointUnavailableError(
                        "the failed step is not classified as repairable"
                    )
                target_step_key = step_key

            if decision == "resume":
                self._validate_resume_inputs(
                    session,
                    project_id=parent.project_id,
                    session_id=session_id,
                    input_ids=input_ids,
                    required_input_types=tuple(checkpoint.required_input_types),
                )
            elif input_ids:
                raise ValueError("only resume decisions may carry input_ids")

            now_value = session.scalar(select(func.clock_timestamp()))
            child_id: UUID | None = None
            if decision != "cancel":
                if parent.execution_mode == "live" and self._capacity_policy is not None:
                    self._expire_queued_runs_in_session(
                        session, now=now_value, limit=1000
                    )
                    self._assert_queue_capacity(
                        session,
                        project_id=parent.project_id,
                        exclude_nonterminal_run_id=(
                            parent.id if decision == "resume" else None
                        ),
                    )
                child_id = uuid4()
                child = ResearchRunModel(
                    id=child_id,
                    project_id=parent.project_id,
                    contract_id=parent.contract_id,
                    execution_mode=parent.execution_mode,
                    status="queued",
                    progress=parent.progress,
                    parent_run_id=parent.id,
                    derivation_kind="retry",
                    retry_from_step=target_step_key,
                    cache_policy="disabled",
                    latest_event_sequence=1,
                    revision=1,
                    lease_generation=0,
                    queue_expires_at=(
                        now_value + self._capacity_policy.queue_timeout
                        if parent.execution_mode == "live"
                        and self._capacity_policy is not None
                        else None
                    ),
                    steps_frozen_at=None,
                    idempotency_key=f"decision:{request_hash.removeprefix('sha256:')}",
                    request_hash=request_hash,
                    created_at=now_value,
                    updated_at=now_value,
                )
                session.add(child)
                parent_steps = tuple(
                    session.scalars(
                        select(RunStepModel)
                        .where(RunStepModel.run_id == run_id)
                        .order_by(RunStepModel.position)
                    )
                )
                target = next(
                    (item for item in parent_steps if item.key == target_step_key), None
                )
                if target is None:
                    raise StepNotFoundError(
                        f"step {target_step_key!r} was not found for run {run_id}"
                    )
                session.add_all(
                    [
                        RunStepModel(
                            run_id=child_id,
                            position=item.position,
                            key=item.key,
                            label=item.label,
                            enter_status=item.enter_status,
                            success_status=item.success_status,
                            max_attempts=item.max_attempts,
                            task_id=item.task_id,
                            skill_id=item.skill_id,
                            depends_on_step_keys=list(item.depends_on_step_keys),
                            status=(
                                "skipped" if item.position < target.position else "pending"
                            ),
                            progress=(100 if item.position < target.position else 0),
                            finished_at=(
                                now_value if item.position < target.position else None
                            ),
                            public_message=(
                                f"Reused from parent Run {run_id}"
                                if item.position < target.position
                                else ""
                            ),
                        )
                        for item in parent_steps
                    ]
                )
                session.flush()
                frozen = session.execute(
                    update(ResearchRunModel)
                    .where(
                        ResearchRunModel.id == child_id,
                        ResearchRunModel.steps_frozen_at.is_(None),
                    )
                    .values(steps_frozen_at=now_value)
                    .execution_options(synchronize_session=False)
                )
                if frozen.rowcount != 1:
                    raise WorkflowConflictError(
                        "derived RunStep collection could not be frozen"
                    )
                self._add_event(
                    session,
                    run_id=child_id,
                    sequence=1,
                    event_type="run.queued",
                    step_key=target_step_key,
                    progress=parent.progress,
                    public_message=f"Derived Run queued from step {target_step_key}",
                )

            decision_row = RunDecisionModel(
                project_id=parent.project_id,
                parent_run_id=parent.id,
                child_run_id=child_id,
                decision=decision,
                step_key=target_step_key,
                input_ids=[str(value) for value in input_ids],
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                created_at=now_value,
            )
            session.add(decision_row)

            if parent.status == "waiting_for_input":
                assert checkpoint is not None
                checkpoint.status = "resolved" if child_id is not None else "cancelled"
                checkpoint.resolved_at = now_value
                checkpoint.resolution_run_id = child_id
                self._finish_replaced_parent(
                    session,
                    parent=parent,
                    now=now_value,
                    event_type=("run.superseded" if child_id is not None else "run.cancelled"),
                    public_message=(
                        f"Run superseded by derived Run {child_id}"
                        if child_id is not None
                        else "Run cancelled by user at input checkpoint"
                    ),
                )
            session.flush()
            result_run_id = child_id or parent.id
            return self._decision_snapshot(decision_row), result_run_id

    def cancel_run(
        self,
        run_id: UUID,
        *,
        expected_status: str,
        expected_revision: int,
        public_message: str = "Run cancelled",
    ) -> MutationResult:
        """Cancel a Run and fence every in-flight writer atomically."""

        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            if run.status in TERMINAL_RUN_STATUSES:
                return MutationResult(
                    run.id, run.status, run.revision, run.latest_event_sequence
                )
            if run.status != expected_status or run.revision != expected_revision:
                raise StaleWorkflowWriteError("run snapshot is stale")
            now_value = session.scalar(select(func.clock_timestamp()))
            sequence = run.latest_event_sequence + 1
            checkpoint = session.scalar(
                select(RunCheckpointModel)
                .where(
                    RunCheckpointModel.run_id == run_id,
                    RunCheckpointModel.status == "open",
                )
                .with_for_update()
            )
            if checkpoint is not None:
                checkpoint.status = "cancelled"
                checkpoint.resolved_at = now_value
            session.execute(
                update(StepAttemptModel)
                .where(
                    StepAttemptModel.status == "running",
                    StepAttemptModel.run_step_id.in_(
                        select(RunStepModel.id).where(RunStepModel.run_id == run_id)
                    ),
                )
                .values(status="cancelled", finished_at=now_value)
                .execution_options(synchronize_session=False)
            )
            session.execute(
                update(RunStepModel)
                .where(
                    RunStepModel.run_id == run_id,
                    RunStepModel.status.in_(INCOMPLETE_STEP_STATUSES),
                )
                .values(status="cancelled", finished_at=now_value)
                .execution_options(synchronize_session=False)
            )
            result = session.execute(
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.status == expected_status,
                    ResearchRunModel.revision == expected_revision,
                )
                .values(
                    status="cancelled",
                    finished_at=now_value,
                    lease_token=None,
                    lease_owner=None,
                    lease_expires_at=None,
                    revision=ResearchRunModel.revision + 1,
                    latest_event_sequence=sequence,
                    updated_at=now_value,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise StaleWorkflowWriteError(
                    "run changed before cancellation committed"
                )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                event_type="run.cancelled",
                step_key=None,
                progress=run.progress,
                public_message=public_message,
            )
            return MutationResult(run_id, "cancelled", expected_revision + 1, sequence)

    def load_snapshot(
        self, run_id: UUID, *, after_event_sequence: int = 0, event_limit: int = 100
    ) -> RunSnapshot:
        if after_event_sequence < 0:
            raise ValueError("event cursor must be nonnegative")
        if not 1 <= event_limit <= 1000:
            raise ValueError("event limit must be between 1 and 1000")
        with self._factory() as session:
            session.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            run = session.get(ResearchRunModel, run_id)
            if run is None:
                raise RunNotFoundError(f"run {run_id} was not found")
            steps = tuple(
                session.scalars(
                    select(RunStepModel)
                    .where(RunStepModel.run_id == run_id)
                    .order_by(RunStepModel.position)
                )
            )
            step_ids = [step.id for step in steps]
            attempts_by_step: dict[UUID, list[AttemptSnapshot]] = {
                step_id: [] for step_id in step_ids
            }
            if step_ids:
                attempts = session.scalars(
                    select(StepAttemptModel)
                    .where(StepAttemptModel.run_step_id.in_(step_ids))
                    .order_by(
                        StepAttemptModel.run_step_id, StepAttemptModel.attempt_number
                    )
                )
                for attempt in attempts:
                    attempts_by_step[attempt.run_step_id].append(
                        AttemptSnapshot(
                            id=attempt.id,
                            attempt_number=attempt.attempt_number,
                            status=attempt.status,
                            retryable=attempt.retryable,
                            started_at=attempt.started_at,
                            finished_at=attempt.finished_at,
                            error_class=attempt.error_class,
                            error_code=attempt.error_code,
                            upstream_request_id=attempt.upstream_request_id,
                        )
                    )
            event_rows = tuple(
                session.scalars(
                    select(RunEventModel)
                    .where(
                        RunEventModel.run_id == run_id,
                        RunEventModel.sequence > after_event_sequence,
                    )
                    .order_by(RunEventModel.sequence)
                    .limit(event_limit + 1)
                )
            )
            has_more = len(event_rows) > event_limit
            page = event_rows[:event_limit]
            events = tuple(
                EventSnapshot(
                    sequence=event.sequence,
                    event_type=event.event_type,
                    step_key=event.step_key,
                    progress=event.progress,
                    public_message=event.public_message,
                    artifact_version_ids=tuple(event.artifact_version_ids),
                    occurred_at=event.occurred_at,
                )
                for event in page
            )
            next_cursor = events[-1].sequence if events else after_event_sequence
            return RunSnapshot(
                id=run.id,
                project_id=run.project_id,
                contract_id=run.contract_id,
                execution_mode=run.execution_mode,
                status=run.status,
                progress=run.progress,
                parent_run_id=run.parent_run_id,
                derivation_kind=run.derivation_kind,
                retry_from_step=run.retry_from_step,
                cache_policy=run.cache_policy,
                started_at=run.started_at,
                finished_at=run.finished_at,
                created_at=run.created_at,
                updated_at=run.updated_at,
                revision=run.revision,
                lease_generation=run.lease_generation,
                lease_expires_at=run.lease_expires_at,
                queue_expires_at=run.queue_expires_at,
                latest_event_sequence=run.latest_event_sequence,
                failure_code=run.failure_code,
                failure_summary=run.failure_summary,
                steps=tuple(
                    StepSnapshot(
                        id=step.id,
                        position=step.position,
                        key=step.key,
                        label=step.label,
                        enter_status=step.enter_status,
                        success_status=step.success_status,
                        max_attempts=step.max_attempts,
                        task_id=step.task_id,
                        skill_id=step.skill_id,
                        depends_on_step_keys=tuple(step.depends_on_step_keys),
                        status=step.status,
                        progress=step.progress,
                        started_at=step.started_at,
                        finished_at=step.finished_at,
                        input_hash=step.input_hash,
                        failure_code=step.failure_code,
                        public_message=step.public_message,
                        attempts=tuple(attempts_by_step[step.id]),
                    )
                    for step in steps
                ),
                events=events,
                next_event_cursor=next_cursor,
                has_more_events=has_more,
            )

    @staticmethod
    def _validate_resume_inputs(
        session: Session,
        *,
        project_id: UUID,
        session_id: str,
        input_ids: tuple[UUID, ...],
        required_input_types: tuple[str, ...],
    ) -> None:
        if not input_ids or len(input_ids) != len(set(input_ids)):
            raise CheckpointUnavailableError(
                "resume requires unique supplemental Research Inputs"
            )
        now = func.clock_timestamp()
        rows = tuple(
            session.scalars(
                select(ResearchInputModel).where(
                    ResearchInputModel.id.in_(input_ids),
                    ResearchInputModel.project_id == project_id,
                    ResearchInputModel.session_id == session_id,
                    ResearchInputModel.status == "accepted",
                    or_(
                        ResearchInputModel.expires_at.is_(None),
                        ResearchInputModel.expires_at > now,
                    ),
                )
            )
        )
        if len(rows) != len(input_ids):
            raise CheckpointUnavailableError(
                "resume inputs are missing, expired, or outside the Run owner"
            )
        provided = {row.type for row in rows}
        if not provided or not provided <= set(required_input_types):
            raise CheckpointUnavailableError(
                "resume inputs do not satisfy the checkpoint input types"
            )
        contents = session.scalar(
            select(func.count())
            .select_from(ResearchInputContentModel)
            .where(
                ResearchInputContentModel.project_id == project_id,
                ResearchInputContentModel.content_hash.in_(
                    tuple(row.content_hash for row in rows)
                ),
            )
        )
        if contents != len({row.content_hash for row in rows}):
            raise CheckpointUnavailableError(
                "resume input content identities are incomplete"
            )

    @staticmethod
    def _finish_replaced_parent(
        session: Session,
        *,
        parent: ResearchRunModel,
        now: datetime,
        event_type: str,
        public_message: str,
    ) -> None:
        session.execute(
            update(RunStepModel)
            .where(
                RunStepModel.run_id == parent.id,
                RunStepModel.status.in_(INCOMPLETE_STEP_STATUSES),
            )
            .values(status="cancelled", finished_at=now)
            .execution_options(synchronize_session=False)
        )
        sequence = parent.latest_event_sequence + 1
        parent.status = "cancelled"
        parent.finished_at = now
        parent.lease_token = None
        parent.lease_owner = None
        parent.lease_expires_at = None
        parent.revision += 1
        parent.latest_event_sequence = sequence
        parent.updated_at = now
        PersistentWorkflowStore._add_event(
            session,
            run_id=parent.id,
            sequence=sequence,
            event_type=event_type,
            step_key=None,
            progress=parent.progress,
            public_message=public_message,
        )

    @staticmethod
    def _checkpoint_snapshot(row: RunCheckpointModel) -> CheckpointSnapshot:
        return CheckpointSnapshot(
            id=row.id,
            run_id=row.run_id,
            step_key=row.step_key,
            status=row.status,
            code=row.code,
            public_message=row.public_message,
            required_input_types=tuple(row.required_input_types),
            opened_at=row.opened_at,
            resolved_at=row.resolved_at,
            resolution_run_id=row.resolution_run_id,
        )

    @staticmethod
    def _decision_snapshot(row: RunDecisionModel) -> DecisionSnapshot:
        return DecisionSnapshot(
            id=row.id,
            parent_run_id=row.parent_run_id,
            child_run_id=row.child_run_id,
            decision=row.decision,
            step_key=row.step_key,
            input_ids=tuple(row.input_ids),
            created_at=row.created_at,
        )

    @staticmethod
    def _acquire_capacity_lock(session: Session) -> None:
        session.execute(select(func.pg_advisory_xact_lock(_CAPACITY_ADVISORY_LOCK_ID)))

    def _assert_queue_capacity(
        self,
        session: Session,
        *,
        project_id: UUID,
        exclude_nonterminal_run_id: UUID | None = None,
    ) -> None:
        policy = self._capacity_policy
        if policy is None:
            return
        nonterminal_filters = [
            ResearchRunModel.execution_mode == "live",
            ResearchRunModel.status.not_in(TERMINAL_RUN_STATUSES),
        ]
        if exclude_nonterminal_run_id is not None:
            nonterminal_filters.append(
                ResearchRunModel.id != exclude_nonterminal_run_id
            )
        nonterminal_global = session.scalar(
            select(func.count())
            .select_from(ResearchRunModel)
            .where(*nonterminal_filters)
        )
        nonterminal_project = session.scalar(
            select(func.count())
            .select_from(ResearchRunModel)
            .where(
                *nonterminal_filters,
                ResearchRunModel.project_id == project_id,
            )
        )
        queued_global = session.scalar(
            select(func.count())
            .select_from(ResearchRunModel)
            .where(
                ResearchRunModel.execution_mode == "live",
                ResearchRunModel.status == "queued",
            )
        )
        queued_project = session.scalar(
            select(func.count())
            .select_from(ResearchRunModel)
            .where(
                ResearchRunModel.execution_mode == "live",
                ResearchRunModel.project_id == project_id,
                ResearchRunModel.status == "queued",
            )
        )
        if nonterminal_global >= policy.max_nonterminal_global:
            raise RunQueueCapacityError(
                scope="global nonterminal",
                retry_after_seconds=policy.retry_after_seconds,
            )
        if nonterminal_project >= policy.max_nonterminal_per_project:
            raise RunQueueCapacityError(
                scope="project nonterminal",
                retry_after_seconds=policy.retry_after_seconds,
            )
        if queued_global >= policy.max_queued_global:
            raise RunQueueCapacityError(
                scope="global", retry_after_seconds=policy.retry_after_seconds
            )
        if queued_project >= policy.max_queued_per_project:
            raise RunQueueCapacityError(
                scope="project", retry_after_seconds=policy.retry_after_seconds
            )

    def _expire_queued_runs_in_session(
        self,
        session: Session,
        *,
        now: datetime,
        limit: int,
    ) -> tuple[UUID, ...]:
        expired = tuple(
            session.scalars(
                select(ResearchRunModel)
                .where(
                    ResearchRunModel.execution_mode == "live",
                    ResearchRunModel.status == "queued",
                    ResearchRunModel.queue_expires_at.is_not(None),
                    ResearchRunModel.queue_expires_at <= now,
                    or_(
                        ResearchRunModel.lease_token.is_(None),
                        ResearchRunModel.lease_expires_at <= now,
                    ),
                )
                .order_by(ResearchRunModel.queue_expires_at, ResearchRunModel.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for run in expired:
            steps = tuple(
                session.scalars(
                    select(RunStepModel)
                    .where(RunStepModel.run_id == run.id)
                    .order_by(RunStepModel.position)
                    .with_for_update()
                )
            )
            first_pending = next(
                (step for step in steps if step.status == "pending"), None
            )
            for step in steps:
                if step.status != "pending":
                    continue
                step.status = "failed" if step is first_pending else "cancelled"
                step.finished_at = now
                step.public_message = "Run exceeded the configured queue wait limit"
                if step is first_pending:
                    step.failure_code = "RUN_QUEUE_TIMEOUT"
            sequence = run.latest_event_sequence + 1
            run.status = "failed"
            run.finished_at = now
            run.failure_code = "RUN_QUEUE_TIMEOUT"
            run.failure_summary = "Run exceeded the configured queue wait limit"
            run.lease_token = None
            run.lease_owner = None
            run.lease_expires_at = None
            run.revision += 1
            run.latest_event_sequence = sequence
            run.updated_at = now
            self._add_event(
                session,
                run_id=run.id,
                sequence=sequence,
                event_type="run.failed",
                step_key=first_pending.key if first_pending is not None else None,
                progress=run.progress,
                public_message="Run exceeded the configured queue wait limit",
            )
        return tuple(run.id for run in expired)

    @staticmethod
    def _validate_step_definitions(steps: Sequence[RunStepDefinition]) -> None:
        if not steps:
            raise ValueError("a run must freeze at least one step")
        keys = [step.key for step in steps]
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("run step keys must be nonempty and unique")
        if any(step.max_attempts < 1 for step in steps):
            raise ValueError("max_attempts must be positive")
        if any((step.task_id is None) != (step.skill_id is None) for step in steps):
            raise ValueError("scientific run steps must bind task_id and skill_id together")
        if steps[0].enter_status != "planning":
            raise ValueError("frozen run step chain must start at 'planning'")
        if steps[0].depends_on_step_keys:
            raise ValueError("the first frozen run step cannot have dependencies")
        order = {
            status: position for position, status in enumerate(RUN_STEP_STATUS_ORDER)
        }
        for position, step in enumerate(steps):
            if step.enter_status not in order:
                raise ValueError(
                    "run step phase must identify a declared workflow status"
                )
            if step.task_id is None and step.key != step.enter_status:
                raise ValueError("canonical run step key must identify its phase")
            if (
                position > 0
                and order[step.enter_status] < order[steps[position - 1].enter_status]
            ):
                raise ValueError(
                    "run step phases must follow canonical order"
                )
            expected_dependencies = (steps[position - 1].key,) if position else ()
            if step.depends_on_step_keys != expected_dependencies:
                raise ValueError(
                    "run step dependencies must freeze the canonical execution chain"
                )
            expected_success_status = (
                steps[position + 1].enter_status
                if position + 1 < len(steps)
                else "completed"
            )
            if step.success_status != expected_success_status:
                raise ValueError(
                    "run step transition does not match the frozen plan: "
                    f"{step.enter_status!r} -> {step.success_status!r}"
                )

    @staticmethod
    def _lock_run(session: Session, run_id: UUID) -> ResearchRunModel:
        run = session.scalar(
            select(ResearchRunModel)
            .where(ResearchRunModel.id == run_id)
            .with_for_update()
        )
        if run is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        return run

    @staticmethod
    def _require_lease(
        session: Session,
        run: ResearchRunModel,
        *,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
    ) -> None:
        now_value = session.scalar(select(func.clock_timestamp()))
        if (
            run.status != expected_status
            or run.revision != expected_revision
            or run.lease_token != token
            or run.lease_generation != generation
            or run.lease_expires_at is None
            or run.lease_expires_at <= now_value
            or run.status in TERMINAL_RUN_STATUSES
        ):
            raise StaleWorkflowWriteError(
                "run status, revision, lease token, or lease generation is stale"
            )

    @staticmethod
    def _lock_running_attempt(
        session: Session, run_id: UUID, step_key: str, attempt_id: UUID
    ) -> tuple[RunStepModel, StepAttemptModel]:
        step = session.scalar(
            select(RunStepModel)
            .where(RunStepModel.run_id == run_id, RunStepModel.key == step_key)
            .with_for_update()
        )
        if step is None:
            raise StepNotFoundError(f"step {step_key!r} was not found for run {run_id}")
        attempt = session.scalar(
            select(StepAttemptModel)
            .where(
                StepAttemptModel.id == attempt_id,
                StepAttemptModel.run_step_id == step.id,
            )
            .with_for_update()
        )
        if attempt is None or attempt.status != "running" or step.status != "running":
            raise WorkflowConflictError("step attempt is not running")
        return step, attempt

    @staticmethod
    def _conditional_run_update(
        session: Session,
        *,
        run_id: UUID,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        values: dict[str, object],
    ) -> None:
        result = session.execute(
            update(ResearchRunModel)
            .where(
                ResearchRunModel.id == run_id,
                ResearchRunModel.status == expected_status,
                ResearchRunModel.revision == expected_revision,
                ResearchRunModel.lease_token == token,
                ResearchRunModel.lease_generation == generation,
                ResearchRunModel.lease_expires_at > func.clock_timestamp(),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise StaleWorkflowWriteError(
                "conditional run update rejected a stale writer"
            )

    @staticmethod
    def _add_event(
        session: Session,
        *,
        run_id: UUID,
        sequence: int,
        event_type: str,
        step_key: str | None,
        progress: int | None,
        public_message: str,
    ) -> None:
        session.add(
            RunEventModel(
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                step_key=step_key,
                progress=progress,
                public_message=public_message,
                artifact_version_ids=[],
            )
        )

    @staticmethod
    def _active_attempt_ids(session: Session, run_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            session.scalars(
                select(StepAttemptModel.id)
                .join(RunStepModel, StepAttemptModel.run_step_id == RunStepModel.id)
                .where(
                    RunStepModel.run_id == run_id,
                    StepAttemptModel.status == "running",
                )
                .order_by(RunStepModel.position, StepAttemptModel.attempt_number)
            )
        )

    @classmethod
    def _reconcile_abandoned_attempt(
        cls,
        run: ResearchRunModel,
        session: Session,
        now: datetime,
    ) -> None:
        rows = tuple(
            session.execute(
                select(StepAttemptModel, RunStepModel)
                .join(RunStepModel, StepAttemptModel.run_step_id == RunStepModel.id)
                .where(
                    RunStepModel.run_id == run.id,
                    StepAttemptModel.status == "running",
                )
                .order_by(RunStepModel.position, StepAttemptModel.attempt_number)
                .with_for_update()
            )
        )
        if not rows:
            return
        if len(rows) != 1 or rows[0][1].status != "running":
            raise WorkflowConflictError(
                "expired Run lease has an ambiguous running Attempt state"
            )

        attempt, step = rows[0]
        attempt.status = "failed"
        attempt.finished_at = now
        attempt.error_class = "WorkerLeaseExpired"
        attempt.error_code = "WORKER_LEASE_EXPIRED"
        attempt.retryable = attempt.attempt_number < step.max_attempts
        step.failure_code = "WORKER_LEASE_EXPIRED"
        sequence = run.latest_event_sequence + 1

        if attempt.retryable:
            step.status = "pending"
            step.finished_at = None
            step.public_message = "Worker interrupted; retry scheduled"
            event_type = "step.retry_scheduled"
        else:
            step.status = "failed"
            step.finished_at = now
            step.public_message = "Worker interrupted after retry budget exhaustion"
            run.status = "failed"
            run.finished_at = now
            run.failure_code = "WORKER_LEASE_EXPIRED"
            run.failure_summary = step.public_message
            event_type = "step.failed"

        run.revision += 1
        run.latest_event_sequence = sequence
        run.updated_at = now
        cls._add_event(
            session,
            run_id=run.id,
            sequence=sequence,
            event_type=event_type,
            step_key=step.key,
            progress=run.progress,
            public_message=step.public_message,
        )

    @staticmethod
    def _raise_stale_or_missing(session: Session, run_id: UUID) -> None:
        if session.get(ResearchRunModel, run_id) is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        raise StaleWorkflowWriteError(
            "run status, revision, lease token, or lease generation is stale"
        )
