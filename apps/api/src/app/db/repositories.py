"""Minimal repositories and Unit of Work for workflow persistence.

Workflow transitions and publication transactions remain in their owning
boundaries; this module only supplies transaction and persistence primitives.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
)

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    def get(self, entity_id: UUID) -> ModelT | None:
        return self.session.get(self.model, entity_id)


class UnitOfWork:
    def __init__(self, factory: Callable[[], Session]) -> None:
        self.factory = factory

    def __enter__(self) -> UnitOfWork:
        self.session = self.factory()
        self.runs = Repository(self.session, ResearchRunModel)
        self.steps = Repository(self.session, RunStepModel)
        self.attempts = Repository(self.session, StepAttemptModel)
        self.events = Repository(self.session, RunEventModel)
        self.versions = Repository(self.session, ArtifactVersionModel)
        self.producer_executions = Repository(self.session, ProducerExecutionModel)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.session.rollback()
        self.session.close()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
