"""The single writer for the Project-owned public Research Thread.

Every Thread entry — user messages, assistant messages, assistant reasoning,
clarification questions and answers — is appended through this module so the
strict per-Project sequence and the ``assistant_reasoning`` /
``assistant_message`` boundary stay consistent across the Research turn service
and the ResearchRun worker. No other module may construct a
``ResearchThreadEntryModel`` directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ResearchThreadEntryModel
from app.schemas.core import ResearchThreadEntryKind


def append_thread_entry(
    session: Session,
    *,
    project_id: UUID,
    kind: ResearchThreadEntryKind,
    actor: str,
    public_content: str,
    structured_payload: dict[str, Any] | None = None,
    model_execution_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> ResearchThreadEntryModel:
    """Append one entry at the next strict Project sequence inside a transaction."""

    if idempotency_key is not None:
        existing = next(
            (
                entry
                for entry in session.scalars(
                    select(ResearchThreadEntryModel).where(
                        ResearchThreadEntryModel.project_id == project_id,
                        ResearchThreadEntryModel.kind == kind.value,
                    )
                )
                if entry.structured_payload.get("assistant_milestone_key")
                == idempotency_key
            ),
            None,
        )
        if existing is not None:
            return existing

    payload = dict(structured_payload or {})
    if idempotency_key is not None:
        payload["assistant_milestone_key"] = idempotency_key

    next_sequence = (
        session.scalar(
            select(func.coalesce(func.max(ResearchThreadEntryModel.sequence), 0)).where(
                ResearchThreadEntryModel.project_id == project_id
            )
        )
        or 0
    ) + 1
    row = ResearchThreadEntryModel(
        project_id=project_id,
        sequence=next_sequence,
        kind=kind.value,
        actor=actor,
        public_content=public_content,
        structured_payload=payload,
        model_execution_id=model_execution_id,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def append_assistant_message(
    session: Session,
    *,
    project_id: UUID,
    public_content: str,
    structured_payload: dict[str, Any] | None = None,
    model_execution_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> ResearchThreadEntryModel:
    """Append the assistant's public narrative message for a completed step."""

    return append_thread_entry(
        session,
        project_id=project_id,
        kind=ResearchThreadEntryKind.assistant_message,
        actor="assistant",
        public_content=public_content,
        structured_payload=structured_payload,
        model_execution_id=model_execution_id,
        idempotency_key=idempotency_key,
    )


__all__ = ["append_assistant_message", "append_thread_entry"]
