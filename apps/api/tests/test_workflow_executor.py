"""Tests for state-safe workflow execution ordering."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from app.schemas.enums import StepStatus, TaskStatus
from app.workflow import (
    WorkflowContext,
    WorkflowExecutionError,
    WorkflowExecutor,
    WorkflowStep,
)


class MemoryHooks:
    def __init__(self, *, fail_completed_step_write: bool = False) -> None:
        self.status = TaskStatus.pending
        self.fail_completed_step_write = fail_completed_step_write
        self.transitions: list[tuple[TaskStatus, TaskStatus]] = []
        self.step_events: list[tuple[str, StepStatus]] = []
        self.artifacts: dict[str, Any] = {}

    async def get_task_status(self, task_id: str) -> TaskStatus:
        return self.status

    async def set_task_status(
        self,
        task_id: str,
        *,
        expected: TaskStatus,
        target: TaskStatus,
    ) -> None:
        if self.status != expected:
            raise RuntimeError(f"stale task state: expected={expected} actual={self.status}")
        self.transitions.append((expected, target))
        self.status = target

    async def set_step_status(
        self,
        task_id: str,
        step_key: str,
        status: StepStatus,
        *,
        message: str = "",
    ) -> None:
        if self.fail_completed_step_write and status == StepStatus.completed:
            raise RuntimeError("step persistence unavailable")
        self.step_events.append((step_key, status))

    async def record_artifacts(
        self,
        task_id: str,
        step_key: str,
        artifacts: Mapping[str, Any],
    ) -> None:
        self.artifacts.update(artifacts)


async def run_planning(context: WorkflowContext) -> Mapping[str, Any]:
    return {"plan": {"goal": context.goal}}


def planning_step() -> WorkflowStep:
    return WorkflowStep(
        key="planning",
        label="生成任务计划",
        enter_status=TaskStatus.planning,
        success_status=TaskStatus.fetching_data,
        run=run_planning,
    )


def workflow_context() -> WorkflowContext:
    return WorkflowContext(
        task_id="task_test",
        goal="整合系外行星与宿主恒星参数",
        case_key="exoplanet_host_star",
    )


def test_executor_advances_only_after_step_result_is_persisted() -> None:
    hooks = MemoryHooks()
    executor = WorkflowExecutor(hooks)

    status = asyncio.run(executor.execute(workflow_context(), [planning_step()]))

    assert status == TaskStatus.fetching_data
    assert hooks.status == TaskStatus.fetching_data
    assert hooks.transitions == [
        (TaskStatus.pending, TaskStatus.planning),
        (TaskStatus.planning, TaskStatus.fetching_data),
    ]
    assert hooks.step_events[-1] == ("planning", StepStatus.completed)
    assert "plan" in hooks.artifacts


def test_step_completion_write_failure_does_not_leave_task_advanced() -> None:
    hooks = MemoryHooks(fail_completed_step_write=True)
    executor = WorkflowExecutor(hooks)

    with pytest.raises(WorkflowExecutionError) as captured:
        asyncio.run(executor.execute(workflow_context(), [planning_step()]))

    assert hooks.status == TaskStatus.failed
    assert hooks.transitions == [
        (TaskStatus.pending, TaskStatus.planning),
        (TaskStatus.planning, TaskStatus.failed),
    ]
    assert ("planning", StepStatus.failed) in hooks.step_events
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert "step persistence unavailable" in str(captured.value.__cause__)
