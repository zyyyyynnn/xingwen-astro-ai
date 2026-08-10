"""Strict builders for direct persistence seeds at the authoring boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.db.models import (
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchProjectModel,
)


def _seed_hash(kind: str, entity_id: UUID) -> str:
    return "sha256:" + hashlib.sha256(f"{kind}:{entity_id}".encode()).hexdigest()


def build_research_project(
    *,
    project_id: UUID,
    session_id: str,
    name: str,
    case_key: str,
    revision: int = 1,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> ResearchProjectModel:
    """Build one complete Project without inferring ownership from session state."""

    values: dict[str, object] = {
        "id": project_id,
        "session_id": session_id,
        "name": name,
        "case_key": case_key,
        "revision": revision,
        "idempotency_key": f"test-project-{project_id}",
        "request_hash": _seed_hash("project", project_id),
    }
    if created_at is not None:
        values["created_at"] = created_at
    if updated_at is not None:
        values["updated_at"] = updated_at
    return ResearchProjectModel(**values)


def build_contract_draft(
    project: ResearchProjectModel,
    *,
    draft_id: UUID | None = None,
    intent: str = "Persistence test authoring seed",
    status: str = "confirmed",
    content: dict[str, object] | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> ResearchContractDraftModel:
    """Build one Draft with explicit Project and Session ownership."""

    identity = draft_id or uuid4()
    now = created_at or datetime.now(UTC)
    return ResearchContractDraftModel(
        id=identity,
        project_id=project.id,
        session_id=project.session_id,
        version=1,
        intent=intent,
        status=status,
        contract=dict(content or {}),
        warnings=[],
        created_at=now,
        updated_at=updated_at or now,
        expires_at=expires_at or now + timedelta(hours=1),
        idempotency_key=f"test-draft-{identity}",
        request_hash=_seed_hash("draft", identity),
    )


def build_research_contract(
    project: ResearchProjectModel,
    draft: ResearchContractDraftModel,
    *,
    contract_id: UUID,
    content_hash: str,
    content: dict[str, object] | None = None,
    created_at: datetime | None = None,
) -> ResearchContractModel:
    """Build one Contract whose lineage is explicitly bound to its Project Draft."""

    if draft.project_id != project.id or draft.session_id != project.session_id:
        raise ValueError("Contract seed Draft must belong to the supplied Project")
    values: dict[str, object] = {
        "id": contract_id,
        "project_id": project.id,
        "version": 1,
        "content_hash": content_hash,
        "content": dict(content or {}),
        "created_from_draft_id": draft.id,
        "idempotency_key": f"test-contract-{contract_id}",
        "request_hash": _seed_hash("contract", contract_id),
    }
    if created_at is not None:
        values["created_at"] = created_at
    return ResearchContractModel(**values)


def persist_authoring_models(
    session: Session,
    *,
    project: ResearchProjectModel,
    draft: ResearchContractDraftModel | None = None,
    contract: ResearchContractModel | None = None,
) -> None:
    """Persist fully built authoring models in their database dependency order."""

    if contract is not None and draft is None:
        raise ValueError("Contract persistence requires its explicit Draft")
    session.add(project)
    session.flush((project,))
    if draft is not None:
        if draft.project_id != project.id or draft.session_id != project.session_id:
            raise ValueError("Draft persistence requires its explicit owning Project")
        session.add(draft)
        session.flush((draft,))
    if contract is not None:
        if contract.project_id != project.id or contract.created_from_draft_id != draft.id:
            raise ValueError("Contract persistence requires matching Project and Draft lineage")
        session.add(contract)
        session.flush((contract,))
