"""Durable admission, worker lifecycle, and dispatch-capacity policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import ResearchRunModel, WorkflowWorkerModel


@dataclass(frozen=True, slots=True)
class WorkflowCapacityPolicy:
    """One bounded policy shared by Run admission and every worker process."""

    max_queued_global: int
    max_queued_per_project: int
    max_nonterminal_global: int
    max_nonterminal_per_project: int
    max_active_global: int
    max_active_per_project: int
    worker_capacity: int
    queue_timeout: timedelta
    retry_after_seconds: int

    def __post_init__(self) -> None:
        integer_limits = (
            self.max_queued_global,
            self.max_queued_per_project,
            self.max_nonterminal_global,
            self.max_nonterminal_per_project,
            self.max_active_global,
            self.max_active_per_project,
            self.worker_capacity,
            self.retry_after_seconds,
        )
        if any(value < 1 for value in integer_limits):
            raise ValueError("workflow capacity limits must be positive")
        if self.max_queued_per_project > self.max_queued_global:
            raise ValueError("project queue capacity must not exceed global capacity")
        if self.max_nonterminal_per_project > self.max_nonterminal_global:
            raise ValueError(
                "project nonterminal capacity must not exceed global capacity"
            )
        if self.max_queued_global > self.max_nonterminal_global:
            raise ValueError("global queue capacity must not exceed nonterminal capacity")
        if self.max_queued_per_project > self.max_nonterminal_per_project:
            raise ValueError(
                "project queue capacity must not exceed nonterminal capacity"
            )
        if self.max_active_global > self.max_nonterminal_global:
            raise ValueError("global active capacity must not exceed nonterminal capacity")
        if self.max_active_per_project > self.max_nonterminal_per_project:
            raise ValueError(
                "project active capacity must not exceed nonterminal capacity"
            )
        if self.max_active_per_project > self.max_active_global:
            raise ValueError("project active capacity must not exceed global capacity")
        if self.worker_capacity > self.max_active_global:
            raise ValueError("worker capacity must not exceed global active capacity")
        if self.queue_timeout <= timedelta(0):
            raise ValueError("workflow queue timeout must be positive")


@dataclass(frozen=True, slots=True)
class WorkerSnapshot:
    worker_id: str
    state: str
    configured_capacity: int
    active_run_count: int
    started_at: datetime
    heartbeat_at: datetime
    drain_requested_at: datetime | None
    stopped_at: datetime | None


class PersistentWorkerRegistry:
    """Persist worker lifecycle so drain state is process-independent and auditable."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def register(self, worker_id: str, *, configured_capacity: int) -> WorkerSnapshot:
        if not worker_id.strip() or len(worker_id) > 128:
            raise ValueError("worker_id must contain 1 to 128 characters")
        if configured_capacity < 1:
            raise ValueError("configured_capacity must be positive")
        with self._factory() as session, session.begin():
            now = session.scalar(select(func.clock_timestamp()))
            session.execute(
                pg_insert(WorkflowWorkerModel)
                .values(
                    worker_id=worker_id,
                    state="accepting",
                    configured_capacity=configured_capacity,
                    started_at=now,
                    heartbeat_at=now,
                    drain_requested_at=None,
                    stopped_at=None,
                )
                .on_conflict_do_update(
                    index_elements=(WorkflowWorkerModel.worker_id,),
                    set_={
                        "state": "accepting",
                        "configured_capacity": configured_capacity,
                        "started_at": now,
                        "heartbeat_at": now,
                        "drain_requested_at": None,
                        "stopped_at": None,
                    },
                )
            )
        return self.load(worker_id)

    def heartbeat(self, worker_id: str) -> WorkerSnapshot:
        with self._factory() as session, session.begin():
            result = session.execute(
                update(WorkflowWorkerModel)
                .where(
                    WorkflowWorkerModel.worker_id == worker_id,
                    WorkflowWorkerModel.state.in_(("accepting", "draining")),
                )
                .values(heartbeat_at=func.clock_timestamp())
            )
            if result.rowcount != 1:
                raise RuntimeError(f"workflow worker {worker_id!r} is not active")
        return self.load(worker_id)

    def request_drain(self, worker_id: str) -> WorkerSnapshot:
        with self._factory() as session, session.begin():
            now = session.scalar(select(func.clock_timestamp()))
            result = session.execute(
                update(WorkflowWorkerModel)
                .where(
                    WorkflowWorkerModel.worker_id == worker_id,
                    WorkflowWorkerModel.state == "accepting",
                )
                .values(
                    state="draining",
                    drain_requested_at=now,
                    heartbeat_at=now,
                )
            )
            if result.rowcount == 0:
                row = session.get(WorkflowWorkerModel, worker_id)
                if row is None:
                    raise RuntimeError(f"workflow worker {worker_id!r} is not registered")
        return self.load(worker_id)

    def mark_stopped(self, worker_id: str) -> WorkerSnapshot:
        with self._factory() as session, session.begin():
            now = session.scalar(select(func.clock_timestamp()))
            result = session.execute(
                update(WorkflowWorkerModel)
                .where(WorkflowWorkerModel.worker_id == worker_id)
                .values(state="stopped", heartbeat_at=now, stopped_at=now)
            )
            if result.rowcount != 1:
                raise RuntimeError(f"workflow worker {worker_id!r} is not registered")
        return self.load(worker_id)

    def load(self, worker_id: str) -> WorkerSnapshot:
        with self._factory() as session:
            row = session.get(WorkflowWorkerModel, worker_id)
            if row is None:
                raise RuntimeError(f"workflow worker {worker_id!r} is not registered")
            now = session.scalar(select(func.clock_timestamp()))
            active_run_count = session.scalar(
                select(func.count())
                .select_from(ResearchRunModel)
                .where(
                    ResearchRunModel.execution_mode == "live",
                    ResearchRunModel.lease_owner == worker_id,
                    ResearchRunModel.lease_expires_at > now,
                )
            )
            return WorkerSnapshot(
                worker_id=row.worker_id,
                state=row.state,
                configured_capacity=row.configured_capacity,
                active_run_count=active_run_count,
                started_at=row.started_at,
                heartbeat_at=row.heartbeat_at,
                drain_requested_at=row.drain_requested_at,
                stopped_at=row.stopped_at,
            )


__all__ = [
    "PersistentWorkerRegistry",
    "WorkerSnapshot",
    "WorkflowCapacityPolicy",
]
