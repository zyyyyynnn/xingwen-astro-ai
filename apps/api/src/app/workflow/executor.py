"""Sequential, state-checked ResearchTask workflow executor."""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.enums import StepStatus, TaskStatus

from .state_machine import can_transition, require_transition
from .types import WorkflowContext, WorkflowHooks, WorkflowStep


class WorkflowExecutionError(RuntimeError):
    """Wrap a step failure with task and step context."""

    def __init__(self, task_id: str, step_key: str, cause: Exception) -> None:
        super().__init__(f"workflow step failed: task={task_id} step={step_key}")
        self.task_id = task_id
        self.step_key = step_key
        self.__cause__ = cause


class WorkflowExecutor:
    """Execute ordered steps without embedding pipeline business logic."""

    def __init__(self, hooks: WorkflowHooks) -> None:
        self._hooks = hooks

    async def execute(
        self,
        context: WorkflowContext,
        steps: Sequence[WorkflowStep],
    ) -> TaskStatus:
        current = await self._hooks.get_task_status(context.task_id)

        for step in steps:
            require_transition(current, step.enter_status)
            await self._hooks.set_task_status(
                context.task_id,
                expected=current,
                target=step.enter_status,
            )
            current = step.enter_status

            try:
                await self._hooks.set_step_status(
                    context.task_id,
                    step.key,
                    StepStatus.running,
                    message=step.label,
                )

                produced = await step.run(context)
                artifacts = dict(produced or {})
                if artifacts:
                    await self._hooks.record_artifacts(
                        context.task_id,
                        step.key,
                        artifacts,
                    )
                    context.artifacts.update(artifacts)

                require_transition(current, step.success_status)
                # Persist the step result before advancing the task. After the task
                # transition succeeds there are no further awaited writes that can
                # leave a completed task paired with an incomplete step record.
                await self._hooks.set_step_status(
                    context.task_id,
                    step.key,
                    StepStatus.completed,
                )
                await self._hooks.set_task_status(
                    context.task_id,
                    expected=current,
                    target=step.success_status,
                )
                current = step.success_status
            except Exception as exc:
                await self._fail(context.task_id, step, current, exc)
                raise WorkflowExecutionError(context.task_id, step.key, exc) from exc

        return current

    async def _fail(
        self,
        task_id: str,
        step: WorkflowStep,
        current: TaskStatus,
        cause: Exception,
    ) -> None:
        """Best-effort failure bookkeeping without masking the root exception."""

        bookkeeping_errors: list[Exception] = []
        message = f"{type(cause).__name__}: {cause}"

        try:
            await self._hooks.set_step_status(
                task_id,
                step.key,
                StepStatus.failed,
                message=message,
            )
        except Exception as error:  # pragma: no cover - adapter-specific safeguard
            bookkeeping_errors.append(error)

        if can_transition(current, TaskStatus.failed):
            try:
                await self._hooks.set_task_status(
                    task_id,
                    expected=current,
                    target=TaskStatus.failed,
                )
            except Exception as error:  # pragma: no cover - adapter-specific safeguard
                bookkeeping_errors.append(error)

        for error in bookkeeping_errors:
            cause.add_note(
                "workflow failure bookkeeping also failed: "
                f"{type(error).__name__}: {error}"
            )
