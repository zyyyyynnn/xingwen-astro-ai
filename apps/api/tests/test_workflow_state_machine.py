"""Tests for the workflow transition contract."""

from __future__ import annotations

import pytest

from app.schemas.enums import TaskStatus
from app.workflow.state_machine import (
    InvalidTaskTransition,
    can_transition,
    next_statuses,
    require_transition,
)


def test_happy_path_declares_the_complete_research_flow() -> None:
    path = [
        TaskStatus.pending,
        TaskStatus.planning,
        TaskStatus.fetching_data,
        TaskStatus.cleaning_data,
        TaskStatus.searching_papers,
        TaskStatus.summarizing_papers,
        TaskStatus.reasoning_literature,
        TaskStatus.building_graph,
        TaskStatus.completed,
    ]

    assert all(can_transition(current, target) for current, target in zip(path, path[1:]))


def test_completed_task_can_enter_local_revision() -> None:
    require_transition(TaskStatus.completed, TaskStatus.revising)
    require_transition(TaskStatus.revising, TaskStatus.completed)


def test_failed_is_terminal() -> None:
    assert next_statuses(TaskStatus.failed) == frozenset()


def test_skipping_a_pipeline_stage_is_rejected() -> None:
    with pytest.raises(InvalidTaskTransition):
        require_transition(TaskStatus.planning, TaskStatus.searching_papers)
