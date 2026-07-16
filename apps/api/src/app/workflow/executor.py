"""Sequential, state-checked ResearchTask workflow executor."""

from __future__ import annotations

from collections.abc import Sequence

from app.schemas.enums import StepStatus, TaskStatus

from .state_machine import require_transition
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
            await self._hooks.set_step_status(
                context.task_id,
                step.key,
                StepStatus.running,
                message=step.label,
            )

            try:
                produced = await step.run(context)
                artifacts = dict(produced or {})
                if artifacts:
                    context.artifacts.update(artifacts)
                    await self._hooks.record_artifacts(
                        context.task_id,
                        step.key,
                        artifacts,
                    )

                require_transition(step.enter_status, step.success_status)
                await self._hooks.set_task_status(
                    context.task_id,
                    expected=step.enter_status,
                    target=step.success_status,
                )
                await self._hooks.set_step_status(
                    context.task_id,
                    step.key,
                    StepStatus.completed,
                )
                current = step.success_status
            except Exception as exc:
                await self._fail(context.task_id, step, exc)
                raise WorkflowExecutionError(context.task_id, step.key, exc) from exc

        return current

    async def _fail(
        self,
        task_id: str,
        step: WorkflowStep,
        cause: Exception,
    ) -> None:
        message = f"{type(cause).__name__}: {cause}"
        await self._hooks.set_step_status(
            task_id,
            step.key,
            StepStatus.failed,
            message=message,
        )

        if step.enter_status is not TaskStatus.failed:
            require_transition(step.enter_status, TaskStatus.failed)
            await self._hooks.set_task_status(
                task_id,
                expected=step.enter_status,
                target=TaskStatus.failed,
            )
