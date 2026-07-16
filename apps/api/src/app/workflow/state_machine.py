"""Explicit ResearchTask state transition rules."""

from __future__ import annotations

from collections.abc import Mapping

from app.schemas.enums import TaskStatus


ALLOWED_TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.pending: frozenset({TaskStatus.planning, TaskStatus.failed}),
    TaskStatus.planning: frozenset({TaskStatus.fetching_data, TaskStatus.failed}),
    TaskStatus.fetching_data: frozenset({TaskStatus.cleaning_data, TaskStatus.failed}),
    TaskStatus.cleaning_data: frozenset({TaskStatus.searching_papers, TaskStatus.failed}),
    TaskStatus.searching_papers: frozenset(
        {TaskStatus.summarizing_papers, TaskStatus.failed}
    ),
    TaskStatus.summarizing_papers: frozenset(
        {TaskStatus.reasoning_literature, TaskStatus.failed}
    ),
    TaskStatus.reasoning_literature: frozenset(
        {TaskStatus.building_graph, TaskStatus.failed}
    ),
    TaskStatus.building_graph: frozenset({TaskStatus.completed, TaskStatus.failed}),
    TaskStatus.completed: frozenset({TaskStatus.revising}),
    TaskStatus.revising: frozenset({TaskStatus.completed, TaskStatus.failed}),
    TaskStatus.failed: frozenset(),
}


class InvalidTaskTransition(ValueError):
    """Raised when a workflow attempts an undeclared task transition."""

    def __init__(self, current: TaskStatus, target: TaskStatus) -> None:
        allowed = ", ".join(sorted(status.value for status in next_statuses(current)))
        detail = allowed or "<none>"
        super().__init__(
            f"invalid task transition: {current.value} -> {target.value}; "
            f"allowed targets: {detail}"
        )
        self.current = current
        self.target = target


def next_statuses(current: TaskStatus) -> frozenset[TaskStatus]:
    """Return the declared next states for ``current``."""

    return ALLOWED_TRANSITIONS[current]


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    """Return whether ``current`` may move directly to ``target``."""

    return target in next_statuses(current)


def require_transition(current: TaskStatus, target: TaskStatus) -> None:
    """Validate a direct transition or raise ``InvalidTaskTransition``."""

    if not can_transition(current, target):
        raise InvalidTaskTransition(current, target)
