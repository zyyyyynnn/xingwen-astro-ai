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
    ResearchRunModel,
    RunCheckpointDecisionModel,
    RunCheckpointModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
)
from app.schemas.core import (
    RepairCheckpointContext,
    RepairDecisionInput,
    RepairOutcome,
)

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


class WorkflowStoreError(RuntimeError):
    """Base class for stable workflow persistence failures."""

    code = "WORKFLOW_STORE_ERROR"


class RunNotFoundError(WorkflowStoreError):
    code = "RUN_NOT_FOUND"


class WorkflowConflictError(WorkflowStoreError):
    code = "WORKFLOW_CONFLICT"


class LeaseUnavailableError(WorkflowConflictError):
    code = "RUN_LEASE_UNAVAILABLE"


class StaleWorkflowWriteError(WorkflowConflictError):
    code = "STALE_WORKFLOW_WRITE"


class RetryBudgetExhaustedError(WorkflowConflictError):
    code = "STEP_RETRY_BUDGET_EXHAUSTED"


class CheckpointDecisionConflictError(WorkflowConflictError):
    code = "CHECKPOINT_DECISION_CONFLICT"


class CheckpointOptionInvalidError(WorkflowStoreError):
    code = "CHECKPOINT_OPTION_INVALID"


class StepNotFoundError(WorkflowStoreError):
    code = "RUN_STEP_NOT_FOUND"


class WorkflowCheckpointRequested(RuntimeError):
    """Control signal: the current attempt parked the Run for typed user input."""


@dataclass(frozen=True, slots=True)
class RepairCheckpointDecisionState:
    checkpoint_id: UUID
    context: RepairCheckpointContext
    decisions: tuple[RepairDecisionInput, ...]
    decided_at: datetime
    outcome: RepairOutcome | None


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
    activity_id: str
    activity_kind: str
    activity_phase: str
    activity_name: str
    step_key: str | None
    progress: int | None
    content: str
    details: dict[str, object]
    artifact_version_ids: tuple[str, ...]
    occurred_at: datetime


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
    latest_event_sequence: int
    failure_code: str | None
    failure_summary: str | None
    steps: tuple[StepSnapshot, ...]
    events: tuple[EventSnapshot, ...]
    next_event_cursor: int
    has_more_events: bool


class PersistentWorkflowStore:
    """Aggregate-level transactional store for one sequential ResearchRun."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def create_run(
        self,
        *,
        project_id: UUID,
        contract_id: UUID,
        execution_mode: str,
        idempotency_key: str,
        request_hash: str,
        steps: Sequence[RunStepDefinition],
        cache_policy: str = "disabled",
    ) -> RunSnapshot:
        with self._factory() as session, session.begin():
            run_id = self.create_run_in_session(
                session,
                project_id=project_id,
                contract_id=contract_id,
                execution_mode=execution_mode,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                steps=steps,
                cache_policy=cache_policy,
            )
        return self.load_snapshot(run_id)

    def create_run_in_session(
        self,
        session: Session,
        *,
        project_id: UUID,
        contract_id: UUID,
        execution_mode: str,
        idempotency_key: str,
        request_hash: str,
        steps: Sequence[RunStepDefinition],
        parent_run_id: UUID | None = None,
        derivation_kind: str = "original",
        retry_from_step: str | None = None,
        cache_policy: str = "disabled",
        queued_message: str = "Run queued",
    ) -> UUID:
        """Create one frozen Run aggregate inside an existing transaction."""

        self._validate_step_definitions(steps)
        if cache_policy not in {"disabled", "fallback_on_recoverable_failure"}:
            raise ValueError("cache_policy is not supported")
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
                parent_run_id=parent_run_id,
                derivation_kind=derivation_kind,
                retry_from_step=retry_from_step,
                cache_policy=cache_policy,
                latest_event_sequence=1,
                revision=1,
                lease_generation=0,
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
                raise WorkflowConflictError("idempotent Run creation lost its winner")
            if (
                existing.request_hash != request_hash
                or existing.execution_mode != execution_mode
                or existing.contract_id != contract_id
                or existing.parent_run_id != parent_run_id
                or existing.derivation_kind != derivation_kind
                or existing.retry_from_step != retry_from_step
                or existing.cache_policy != cache_policy
            ):
                raise WorkflowConflictError(
                    "idempotency key was already used with a different request"
                )
            return existing.id

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
                    status="pending",
                    progress=0,
                    public_message="",
                    task_id=definition.task_id,
                    skill_id=definition.skill_id,
                    depends_on_step_keys=list(definition.depends_on_step_keys),
                )
                for position, definition in enumerate(steps)
            ]
        )
        session.add(
            RunEventModel(
                run_id=run_id,
                sequence=1,
                activity_id=f"run:{run_id}",
                activity_kind="status",
                activity_phase="queued",
                activity_name="研究任务",
                step_key=None,
                progress=0,
                content=queued_message,
                details={},
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
        if frozen.rowcount != 1:  # pragma: no cover - transaction invariant safeguard
            raise WorkflowConflictError("RunStep collection could not be frozen")
        return run_id

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
            active_attempt_ids = tuple(
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
            return LeaseGrant(
                run_id=run_id,
                token=token,
                generation=row.lease_generation,
                revision=row.revision,
                expires_at=row.lease_expires_at,
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
            incomplete_predecessors = session.scalar(
                select(func.count())
                .select_from(RunStepModel)
                .where(
                    RunStepModel.run_id == run_id,
                    RunStepModel.position < step.position,
                    RunStepModel.status != "completed",
                )
            )
            if incomplete_predecessors:
                raise WorkflowConflictError("a previous frozen run step is incomplete")
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
            required_run_status = (
                "queued"
                if step.position == 0 and attempt_number == 1
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
                activity_id=f"{attempt.id}:step",
                activity_kind="status",
                activity_phase="running",
                activity_name=step.label,
                step_key=step.key,
                progress=run.progress,
                content=public_message,
                details={},
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

    def append_activity_event(
        self,
        run_id: UUID,
        *,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        activity_id: str,
        activity_kind: str,
        activity_phase: str,
        activity_name: str,
        content: str,
        step_key: str | None = None,
        progress: int | None = None,
        details: dict[str, object] | None = None,
        artifact_version_ids: Sequence[str] = (),
    ) -> MutationResult:
        """Append a streaming Activity event without advancing the run revision.

        Activity events are presentation appends emitted while a step attempt is
        running. The active worker keeps one revision for the whole attempt, so
        only the event cursor moves here; command-level mutations own revision.
        """

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
            sequence = run.latest_event_sequence + 1
            self._conditional_run_update(
                session,
                run_id=run_id,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
                values={
                    "latest_event_sequence": sequence,
                    "updated_at": func.clock_timestamp(),
                },
            )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                activity_id=activity_id,
                activity_kind=activity_kind,
                activity_phase=activity_phase,
                activity_name=activity_name,
                step_key=step_key,
                progress=progress,
                content=content,
                details=details,
                artifact_version_ids=artifact_version_ids,
            )
            return MutationResult(run_id, expected_status, expected_revision, sequence)

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
        failure_activity_id: str | None = None,
        failure_activity_kind: str | None = None,
        failure_activity_name: str | None = None,
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
                activity_id=failure_activity_id or f"{attempt.id}:retry",
                activity_kind="retry",
                activity_phase="retrying",
                activity_name=failure_activity_name or step.label,
                step_key=step.key,
                progress=run.progress,
                content=public_message,
                details={"error_code": error_code},
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
        failure_activity_id: str | None = None,
        failure_activity_kind: str | None = None,
        failure_activity_name: str | None = None,
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
                activity_id=failure_activity_id or f"{attempt.id}:failure",
                activity_kind=failure_activity_kind or "error",
                activity_phase="failed",
                activity_name=failure_activity_name or step.label,
                step_key=step.key,
                progress=run.progress,
                content=public_message,
                details={"error_code": error_code, "error_class": error_class},
            )
            return MutationResult(run_id, "failed", expected_revision + 1, sequence)

    def cancel_run(
        self,
        run_id: UUID,
        *,
        expected_status: str,
        expected_revision: int,
        public_message: str = "Run cancelled",
    ) -> MutationResult:
        """Cancel a Run with one conditional write; idempotent on terminal Runs."""

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
                activity_id=f"run:{run_id}",
                activity_kind="status",
                activity_phase="completed",
                activity_name="研究任务",
                step_key=None,
                progress=run.progress,
                content=public_message,
                details={"run_status": "cancelled"},
            )
            return MutationResult(run_id, "cancelled", expected_revision + 1, sequence)

    def request_checkpoint(
        self,
        run_id: UUID,
        *,
        step_key: str,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
        attempt_id: UUID,
        question: str,
        options: Sequence[str],
        kind: str = "choice",
        repair_context: RepairCheckpointContext | None = None,
    ) -> MutationResult:
        """Persist a human-input checkpoint and park the Run at waiting_for_input."""

        if kind not in {"choice", "scientific_repair"}:
            raise ValueError("unsupported checkpoint kind")
        if (kind == "scientific_repair") != (repair_context is not None):
            raise ValueError("scientific repair checkpoint requires typed context")
        context_payload = (
            repair_context.model_dump(mode="json")
            if repair_context is not None
            else None
        )
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
            checkpoint = session.scalar(
                select(RunCheckpointModel).where(
                    RunCheckpointModel.run_id == run_id,
                    RunCheckpointModel.step_key == step_key,
                )
            )
            if checkpoint is None:
                checkpoint = RunCheckpointModel(
                    run_id=run_id,
                    step_key=step_key,
                    question=question,
                    options=list(options),
                    kind=kind,
                    repair_context=context_payload,
                )
                session.add(checkpoint)
                session.flush()
            elif (
                checkpoint.question != question
                or checkpoint.options != list(options)
                or checkpoint.kind != kind
                or checkpoint.repair_context != context_payload
            ):
                raise WorkflowConflictError(
                    "checkpoint identity was reused with different immutable context"
                )
            attempt = session.scalar(
                select(StepAttemptModel)
                .where(
                    StepAttemptModel.id == attempt_id,
                    StepAttemptModel.run_step_id == step.id,
                )
                .with_for_update()
            )
            if attempt is None or attempt.status != "running":
                raise WorkflowConflictError(
                    "checkpoint requires the active running StepAttempt"
                )
            step.status = "waiting"
            now_value = session.scalar(select(func.clock_timestamp()))
            attempt.status = "completed"
            attempt.finished_at = now_value
            sequence = run.latest_event_sequence + 1
            self._conditional_run_update(
                session,
                run_id=run_id,
                token=token,
                generation=generation,
                expected_status=expected_status,
                expected_revision=expected_revision,
                values={
                    "status": "waiting_for_input",
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
                activity_id=f"checkpoint:{checkpoint.id}",
                activity_kind="status",
                activity_phase="running",
                activity_name="等待用户决定",
                step_key=step_key,
                progress=run.progress,
                content=question,
                details={
                    "checkpoint_id": str(checkpoint.id),
                    "checkpoint_kind": kind,
                },
            )
            return MutationResult(
                run_id, "waiting_for_input", expected_revision + 1, sequence
            )

    def submit_checkpoint_decision(
        self,
        run_id: UUID,
        *,
        checkpoint_id: UUID,
        selected_option: str | None,
        free_text: str | None,
        repair_decisions: Sequence[dict[str, object]] = (),
        expected_status: str,
        expected_revision: int,
    ) -> MutationResult:
        """Record an immutable decision and resume the same Run for execution."""

        with self._factory() as session, session.begin():
            run = self._lock_run(session, run_id)
            checkpoint = session.scalar(
                select(RunCheckpointModel)
                .where(
                    RunCheckpointModel.id == checkpoint_id,
                    RunCheckpointModel.run_id == run_id,
                )
                .with_for_update()
            )
            if checkpoint is None:
                raise RunNotFoundError(
                    f"checkpoint {checkpoint_id} was not found for run {run_id}"
                )
            parsed_repairs = tuple(
                RepairDecisionInput.model_validate(item) for item in repair_decisions
            )
            if checkpoint.kind == "scientific_repair":
                context = RepairCheckpointContext.model_validate(
                    checkpoint.repair_context
                )
                expected_defects = {item.defect_id for item in context.defects}
                decided_defects = {item.defect_id for item in parsed_repairs}
                if (
                    selected_option is not None
                    or decided_defects != expected_defects
                    or any(
                        item.action not in context.rule_set.allowed_actions
                        for item in parsed_repairs
                    )
                ):
                    raise CheckpointOptionInvalidError(
                        "repair decisions must exactly cover the authorized defects"
                    )
            elif selected_option is None or parsed_repairs:
                raise CheckpointOptionInvalidError(
                    "choice checkpoint requires exactly one selected option"
                )
            repair_payload = [item.model_dump(mode="json") for item in parsed_repairs]
            existing = session.get(RunCheckpointDecisionModel, checkpoint_id)
            if existing is not None:
                raise CheckpointDecisionConflictError(
                    "checkpoint decision already recorded"
                )
            if (
                checkpoint.kind == "choice"
                and selected_option not in checkpoint.options
            ):
                raise CheckpointOptionInvalidError(
                    "selected option is not part of the checkpoint"
                )
            if run.status != expected_status or run.revision != expected_revision:
                raise StaleWorkflowWriteError("run snapshot is stale")
            if run.status != "waiting_for_input":
                raise StaleWorkflowWriteError("run is not waiting for input")
            session.add(
                RunCheckpointDecisionModel(
                    checkpoint_id=checkpoint_id,
                    selected_option=selected_option,
                    free_text=free_text,
                    repair_decisions=repair_payload,
                )
            )
            step = session.scalar(
                select(RunStepModel)
                .where(
                    RunStepModel.run_id == run_id,
                    RunStepModel.key == checkpoint.step_key,
                )
                .with_for_update()
            )
            if step is None or step.status != "waiting":
                raise WorkflowConflictError(
                    "checkpoint step is not waiting for a decision"
                )
            step.status = "pending"
            step.started_at = None
            resume_status = step.enter_status
            now_value = session.scalar(select(func.clock_timestamp()))
            sequence = run.latest_event_sequence + 1
            result = session.execute(
                update(ResearchRunModel)
                .where(
                    ResearchRunModel.id == run_id,
                    ResearchRunModel.status == expected_status,
                    ResearchRunModel.revision == expected_revision,
                )
                .values(
                    status=resume_status,
                    revision=ResearchRunModel.revision + 1,
                    latest_event_sequence=sequence,
                    updated_at=now_value,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                raise StaleWorkflowWriteError(
                    "run changed before the decision committed"
                )
            self._add_event(
                session,
                run_id=run_id,
                sequence=sequence,
                activity_id=f"checkpoint:{checkpoint_id}",
                activity_kind="status",
                activity_phase="completed",
                activity_name="等待用户决定",
                step_key=checkpoint.step_key,
                progress=run.progress,
                content=(
                    f"用户已作出选择：{selected_option}"
                    if selected_option is not None
                    else f"用户已提交 {len(parsed_repairs)} 项科学修复决定"
                ),
                details={
                    "checkpoint_id": str(checkpoint_id),
                    "selected_option": selected_option,
                    "repair_decision_count": len(parsed_repairs),
                },
            )
            return MutationResult(
                run_id, resume_status, expected_revision + 1, sequence
            )

    def repair_checkpoint_decision(
        self, run_id: UUID, *, step_key: str
    ) -> RepairCheckpointDecisionState | None:
        with self._factory() as session:
            checkpoint = session.scalar(
                select(RunCheckpointModel).where(
                    RunCheckpointModel.run_id == run_id,
                    RunCheckpointModel.step_key == step_key,
                    RunCheckpointModel.kind == "scientific_repair",
                )
            )
            if checkpoint is None:
                return None
            decision = session.get(RunCheckpointDecisionModel, checkpoint.id)
            if decision is None:
                return None
            context = RepairCheckpointContext.model_validate(checkpoint.repair_context)
            decisions = tuple(
                RepairDecisionInput.model_validate(item)
                for item in decision.repair_decisions
            )
            outcome = (
                RepairOutcome.model_validate(decision.repair_outcome)
                if decision.repair_outcome is not None
                else None
            )
            return RepairCheckpointDecisionState(
                checkpoint_id=checkpoint.id,
                context=context,
                decisions=decisions,
                decided_at=decision.decided_at,
                outcome=outcome,
            )

    def complete_repair_checkpoint(
        self,
        run_id: UUID,
        *,
        step_key: str,
        checkpoint_id: UUID,
        outcome: RepairOutcome,
        token: UUID,
        generation: int,
        expected_status: str,
        expected_revision: int,
    ) -> None:
        payload = outcome.model_dump(mode="json")
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
            checkpoint = session.scalar(
                select(RunCheckpointModel).where(
                    RunCheckpointModel.id == checkpoint_id,
                    RunCheckpointModel.run_id == run_id,
                    RunCheckpointModel.step_key == step_key,
                    RunCheckpointModel.kind == "scientific_repair",
                )
            )
            decision = session.get(RunCheckpointDecisionModel, checkpoint_id)
            if checkpoint is None or decision is None:
                raise RunNotFoundError("scientific repair checkpoint was not found")
            if decision.repair_outcome is not None:
                if decision.repair_outcome == payload:
                    return
                raise CheckpointDecisionConflictError(
                    "scientific repair outcome already recorded"
                )
            decision.repair_outcome = payload

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
                    activity_id=event.activity_id,
                    activity_kind=event.activity_kind,
                    activity_phase=event.activity_phase,
                    activity_name=event.activity_name,
                    step_key=event.step_key,
                    progress=event.progress,
                    content=event.content,
                    details=dict(event.details),
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
    def _validate_step_definitions(steps: Sequence[RunStepDefinition]) -> None:
        if not steps:
            raise ValueError("a run must freeze at least one step")
        keys = [step.key for step in steps]
        if any(not key.strip() for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("run step keys must be nonempty and unique")
        if any(step.max_attempts < 1 for step in steps):
            raise ValueError("max_attempts must be positive")
        if steps[0].enter_status != "planning":
            raise ValueError("frozen run step chain must start at 'planning'")
        order = {
            status: position for position, status in enumerate(RUN_STEP_STATUS_ORDER)
        }
        for position, step in enumerate(steps):
            if step.enter_status not in order:
                raise ValueError("run step must enter a declared workflow status")
            if step.skill_id is None:
                if step.key != step.enter_status or step.task_id is not None:
                    raise ValueError(
                        "canonical run step key must identify its workflow status"
                    )
            elif not step.key.startswith("scientific.") or step.task_id is None:
                raise ValueError(
                    "scientific run step must preserve its task and skill identity"
                )
            if (
                position > 0
                and order[step.enter_status] < order[steps[position - 1].enter_status]
            ):
                raise ValueError("run step statuses must follow canonical order")
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
        activity_id: str,
        activity_kind: str,
        activity_phase: str,
        activity_name: str,
        step_key: str | None,
        progress: int | None,
        content: str,
        details: dict[str, object] | None = None,
        artifact_version_ids: Sequence[str] = (),
    ) -> None:
        session.add(
            RunEventModel(
                run_id=run_id,
                sequence=sequence,
                activity_id=activity_id,
                activity_kind=activity_kind,
                activity_phase=activity_phase,
                activity_name=activity_name,
                step_key=step_key,
                progress=progress,
                content=content,
                details=dict(details or {}),
                artifact_version_ids=list(artifact_version_ids),
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

    @staticmethod
    def _raise_stale_or_missing(session: Session, run_id: UUID) -> None:
        if session.get(ResearchRunModel, run_id) is None:
            raise RunNotFoundError(f"run {run_id} was not found")
        raise StaleWorkflowWriteError(
            "run status, revision, lease token, or lease generation is stale"
        )
