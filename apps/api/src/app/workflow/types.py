"""Workflow contracts shared by the executor and step adapters."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas.enums import StepStatus, TaskStatus


@dataclass(slots=True)
class WorkflowContext:
    """Mutable execution context scoped to one ResearchTask."""

    task_id: str
    goal: str
    case_key: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


StepRunner = Callable[[WorkflowContext], Awaitable[Mapping[str, Any] | None]]


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """One declared transition plus its executable adapter."""

    key: str
    label: str
    enter_status: TaskStatus
    success_status: TaskStatus
    run: StepRunner


class WorkflowHooks(Protocol):
    """Persistence/observability boundary used by ``WorkflowExecutor``.

    The executor depends on this boundary and remains independent from SQLAlchemy.
    """

    async def get_task_status(self, task_id: str) -> TaskStatus: ...

    async def set_task_status(
        self,
        task_id: str,
        *,
        expected: TaskStatus,
        target: TaskStatus,
    ) -> None: ...

    async def set_step_status(
        self,
        task_id: str,
        step_key: str,
        status: StepStatus,
        *,
        message: str = "",
    ) -> None: ...

    async def record_artifacts(
        self,
        task_id: str,
        step_key: str,
        artifacts: Mapping[str, Any],
    ) -> None: ...
