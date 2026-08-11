"""Lease-fenced execution boundary for the persistent workflow.

The executor owns orchestration around one frozen step. External adapters and
the Publisher success committer run after ``begin_step`` has closed its transaction.
The success committer remains an injected port so the executor does not publish
an ArtifactVersion or advance a successful Step outside the Publisher's atomic boundary.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from .store import (
    AttemptHandle,
    LeaseGrant,
    PersistentWorkflowStore,
    RetryBudgetExhaustedError,
)

StepResultT = TypeVar("StepResultT")
CommitResultT = TypeVar("CommitResultT")


@dataclass(frozen=True, slots=True)
class FailureDecision:
    error_code: str
    public_message: str
    retryable: bool
    upstream_request_id: str | None = None


class PersistentWorkflowExecutionError(RuntimeError):
    """Wrap an adapter failure after durable workflow bookkeeping."""

    def __init__(self, run_id: UUID, step_key: str, cause: Exception) -> None:
        super().__init__(f"persistent workflow step failed: run={run_id} step={step_key}")
        self.run_id = run_id
        self.step_key = step_key
        self.__cause__ = cause


class PersistentWorkflowExecutor(Generic[StepResultT, CommitResultT]):
    """Execute one lease-fenced Step without holding a database transaction."""

    def __init__(self, store: PersistentWorkflowStore) -> None:
        self.store = store

    async def execute_step(
        self,
        *,
        run_id: UUID,
        step_key: str,
        attempt_idempotency_key: str,
        lease: LeaseGrant,
        expected_status: str,
        expected_revision: int,
        public_message: str,
        runner: Callable[[AttemptHandle], Awaitable[StepResultT]],
        commit_success: Callable[
            [AttemptHandle, LeaseGrant, StepResultT], Awaitable[CommitResultT]
        ],
        classify_failure: Callable[[Exception], FailureDecision],
    ) -> CommitResultT:
        attempt = self.store.begin_step(
            run_id,
            step_key=step_key,
            attempt_idempotency_key=attempt_idempotency_key,
            token=lease.token,
            generation=lease.generation,
            expected_status=expected_status,
            expected_revision=expected_revision,
            public_message=public_message,
        )

        try:
            result = await runner(attempt)
        except Exception as cause:
            self._record_failure(
                cause=cause,
                run_id=run_id,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                classify_failure=classify_failure,
            )
            raise PersistentWorkflowExecutionError(run_id, step_key, cause) from cause

        # The Publisher supplies this port and owns the atomic Step/Run/Event/Version commit.
        # A committer failure is not rewritten here because it may need transaction
        # reconciliation before the Attempt can safely be marked failed.
        return await commit_success(attempt, lease, result)

    def _record_failure(
        self,
        *,
        cause: Exception,
        run_id: UUID,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        classify_failure: Callable[[Exception], FailureDecision],
    ) -> None:
        decision = classify_failure(cause)
        error_class = type(cause).__name__
        try:
            if decision.retryable:
                try:
                    self.store.record_retryable_failure(
                        run_id,
                        step_key=step_key,
                        attempt_id=attempt.attempt_id,
                        token=lease.token,
                        generation=lease.generation,
                        expected_status=attempt.run_status,
                        expected_revision=attempt.run_revision,
                        error_class=error_class,
                        error_code=decision.error_code,
                        public_message=decision.public_message,
                        upstream_request_id=decision.upstream_request_id,
                    )
                    return
                except RetryBudgetExhaustedError:
                    pass
            self.store.fail_run(
                run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                token=lease.token,
                generation=lease.generation,
                expected_status=attempt.run_status,
                expected_revision=attempt.run_revision,
                error_class=error_class,
                error_code=decision.error_code,
                public_message=decision.public_message,
                retryable=decision.retryable,
                upstream_request_id=decision.upstream_request_id,
            )
        except Exception as bookkeeping_error:
            cause.add_note(
                "persistent workflow failure bookkeeping also failed: "
                f"{type(bookkeeping_error).__name__}: {bookkeeping_error}"
            )
