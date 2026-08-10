"""Shared PostgreSQL fixture normalization for current authoring entities.

Low-level persistence tests intentionally construct Project/Contract parents
without going through the HTTP authoring use cases they are not exercising.
The production schema still requires idempotency and draft provenance.  This
pytest-only hook completes those fixture rows before flush so component tests
remain scoped while raw SQL/schema tests continue to exercise database
constraints directly.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from uuid import UUID, uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
)


def _seed_hash(kind: str, entity_id: UUID) -> str:
    return "sha256:" + hashlib.sha256(f"{kind}:{entity_id}".encode()).hexdigest()


def _ensure_identity(entity: object, *, kind: str) -> UUID:
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        entity_id = uuid4()
        setattr(entity, "id", entity_id)
    if getattr(entity, "idempotency_key", None) is None:
        setattr(entity, "idempotency_key", f"test-seed-{kind}-{entity_id}")
    if getattr(entity, "request_hash", None) is None:
        setattr(entity, "request_hash", _seed_hash(kind, entity_id))
    return entity_id


@event.listens_for(Session, "before_flush")
def _complete_current_authoring_test_seeds(
    session: Session,
    _flush_context: object,
    _instances: object,
) -> None:
    """Make direct ORM fixture parents satisfy the current authoring contract."""

    pending = tuple(session.new)
    projects: dict[UUID, ResearchProjectModel] = {}
    for entity in pending:
        if isinstance(entity, ResearchProjectModel):
            project_id = _ensure_identity(entity, kind="project")
            projects[project_id] = entity
        elif isinstance(entity, ResearchContractDraftModel):
            _ensure_identity(entity, kind="draft")

    for entity in pending:
        if not isinstance(entity, ResearchContractModel):
            continue
        contract_id = _ensure_identity(entity, kind="contract")
        if entity.content is None:
            entity.content = {}
        if entity.created_from_draft_id is not None:
            continue

        project = projects.get(entity.project_id)
        if project is None:
            with session.no_autoflush:
                project = session.get(ResearchProjectModel, entity.project_id)
        if project is None:
            raise AssertionError(
                "current Contract fixture requires an existing Project parent"
            )

        draft_id = uuid4()
        now = datetime.now(UTC)
        draft = ResearchContractDraftModel(
            id=draft_id,
            session_id=project.session_id,
            version=1,
            intent="Current authoring seed for persistence test",
            status="confirmed",
            contract=dict(entity.content),
            warnings=[],
            updated_at=now,
            expires_at=now + timedelta(hours=1),
            idempotency_key=f"test-seed-draft-{contract_id}",
            request_hash=_seed_hash("draft", draft_id),
        )
        session.add(draft)
        entity.created_from_draft_id = draft_id
