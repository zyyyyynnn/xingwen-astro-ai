"""SQLAlchemy models for the current PostgreSQL persistence contract.

Statuses remain text plus database CHECK constraints so schema evolution stays
explicit and does not depend on PostgreSQL enum lifecycle operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _uuid() -> UUID:
    return uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ResearchSessionModel(TimestampMixin, Base):
    __tablename__ = "research_sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    credential_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    csrf_hashes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    security_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quota: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active','revoked')", name="research_session_status"
        ),
        CheckConstraint(
            "security_version >= 1", name="research_session_security_version_positive"
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL AND csrf_hashes = '[]'::jsonb)",
            name="research_session_revocation_shape",
        ),
        Index("ix_research_sessions_expires_at", "expires_at"),
        Index("ix_research_sessions_status_updated", "status", "updated_at"),
    )


class ResearchProjectModel(TimestampMixin, Base):
    __tablename__ = "research_projects"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    case_key: Mapped[str] = mapped_column(String(128), nullable=False)
    active_draft_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint("id", "session_id", name="uq_research_project_id_session"),
        UniqueConstraint(
            "session_id", "idempotency_key", name="uq_research_project_idempotency"
        ),
    )


class WorkspaceSnapshotModel(Base):
    __tablename__ = "workspace_snapshots"

    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    owner_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "owner_session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_workspace_snapshot_project_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("revision >= 1", name="workspace_snapshot_revision_positive"),
    )


class ShareSnapshotModel(Base):
    __tablename__ = "share_snapshots"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    artifact_version_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    redaction_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    artifact_versions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "owner_session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_share_snapshot_project_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('active','revoked')", name="share_snapshot_status"
        ),
        CheckConstraint(
            "(status = 'active' AND revoked_at IS NULL) OR "
            "(status = 'revoked' AND revoked_at IS NOT NULL)",
            name="share_snapshot_revocation_shape",
        ),
        CheckConstraint(
            "jsonb_array_length(artifact_version_ids) >= 1",
            name="share_snapshot_has_artifact_version",
        ),
        Index(
            "ix_share_snapshots_owner_created",
            "owner_session_id",
            "project_id",
            "created_at",
            "id",
        ),
        Index("ix_share_snapshots_retention", "status", "expires_at", "revoked_at"),
    )


class ModelExecutionModel(TimestampMixin, Base):
    """Provider-neutral, pre-run assistant execution provenance."""

    __tablename__ = "model_executions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_model: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_returned_model: Mapped[str | None] = mapped_column(String(128))
    explicit_revision: Mapped[str | None] = mapped_column(String(128))
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    prompt_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str | None] = mapped_column(String(71))
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(71))
    output_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parameters_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    parameters_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(256))
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_summary: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_model_execution_id_project"),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_model_execution_project_idempotency",
        ),
        Index(
            "uq_model_execution_active_project",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('pending','running')"),
        ),
        CheckConstraint(
            "status IN ('pending','running','succeeded','failed')",
            name="model_execution_status",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="model_execution_latency_nonnegative",
        ),
        CheckConstraint(
            "status NOT IN ('pending','running') OR "
            "(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="model_execution_active_lease",
        ),
    )


class ResearchThreadEntryModel(TimestampMixin, Base):
    """The Project-owned, strictly ordered public Research Thread."""

    __tablename__ = "research_thread_entries"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    public_content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    model_execution_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("model_executions.id", ondelete="CASCADE")
    )

    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", name="uq_research_thread_entry_id_project"
        ),
        UniqueConstraint(
            "project_id", "sequence", name="uq_research_thread_entry_project_sequence"
        ),
        CheckConstraint("sequence >= 1", name="thread_entry_sequence_positive"),
        CheckConstraint(
            "kind IN ('user_message','assistant_message','assistant_reasoning',"
            "'clarification_question','clarification_answer')",
            name="thread_entry_kind",
        ),
        CheckConstraint(
            "actor IN ('user','assistant','system')",
            name="thread_entry_actor",
        ),
        Index("ix_research_thread_entries_project_sequence", "project_id", "sequence"),
    )


class ResearchContractModel(TimestampMixin, Base):
    __tablename__ = "research_contracts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_from_draft_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_contract_id_project"),
        UniqueConstraint(
            "project_id", "version", name="uq_research_contract_project_version"
        ),
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_research_contract_idempotency"
        ),
        UniqueConstraint(
            "created_from_draft_id", name="uq_research_contract_created_from_draft"
        ),
        ForeignKeyConstraint(
            ["created_from_draft_id", "project_id"],
            ["research_contract_drafts.id", "research_contract_drafts.project_id"],
            name="fk_research_contracts_draft_project",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class ResearchContractDraftModel(TimestampMixin, Base):
    """Editable Project-owned draft persisted for contract confirmation."""

    __tablename__ = "research_contract_drafts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    contract: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", name="uq_research_contract_draft_id_project"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "status IN ('draft','confirmed','expired')", name="draft_status"
        ),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_research_contract_draft_idempotency",
        ),
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_research_contract_drafts_project_session",
            ondelete="CASCADE",
        ),
    )


class ResearchRunModel(TimestampMixin, Base):
    __tablename__ = "research_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    derivation_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="original"
    )
    retry_from_step: Mapped[str | None] = mapped_column(String(128))
    cache_policy: Mapped[str] = mapped_column(
        String(64), nullable=False, default="disabled"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    latest_event_sequence: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_summary: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    steps_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_run_id_project"),
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_research_run_idempotency"
        ),
        Index(
            "uq_research_run_single_active_per_project",
            "project_id",
            unique=True,
            postgresql_where=text(
                "status NOT IN ('completed', 'failed', 'cancelled')"
            ),
        ),
        ForeignKeyConstraint(
            ["contract_id", "project_id"],
            ["research_contracts.id", "research_contracts.project_id"],
            name="fk_research_runs_contract_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["parent_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_research_runs_parent_project",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "execution_mode IN ('demo_replay', 'live')", name="execution_mode"
        ),
        CheckConstraint(
            "status IN ('queued','planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed','failed','cancelled')",
            name="status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint(
            "latest_event_sequence >= 0", name="event_sequence_nonnegative"
        ),
        CheckConstraint(
            "(lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="lease_fields_complete",
        ),
        CheckConstraint(
            "derivation_kind IN ('original','retry','revision','fork')",
            name="derivation_kind",
        ),
        CheckConstraint(
            "(derivation_kind = 'original' AND parent_run_id IS NULL) OR "
            "(derivation_kind <> 'original' AND parent_run_id IS NOT NULL)",
            name="derivation_parent",
        ),
        CheckConstraint(
            "retry_from_step IS NULL OR derivation_kind = 'retry'",
            name="retry_step_derivation",
        ),
        CheckConstraint(
            "cache_policy IN ('disabled','fallback_on_recoverable_failure')",
            name="cache_policy",
        ),
    )


class RunStepModel(TimestampMixin, Base):
    __tablename__ = "run_steps"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    enter_status: Mapped[str] = mapped_column(String(32), nullable=False)
    success_status: Mapped[str] = mapped_column(String(32), nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str | None] = mapped_column(String(71))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    public_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("id", "run_id", name="uq_run_step_id_run"),
        UniqueConstraint("run_id", "position", name="uq_run_step_position"),
        UniqueConstraint("run_id", "key", name="uq_run_step_run_key"),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        CheckConstraint(
            "enter_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input')",
            name="enter_status",
        ),
        CheckConstraint(
            "success_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed')",
            name="success_status",
        ),
        CheckConstraint(
            "status IN ('pending','running','waiting','completed','failed','cancelled','skipped')",
            name="status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
    )


class StepAttemptModel(TimestampMixin, Base):
    __tablename__ = "step_attempts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("run_steps.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    upstream_request_id: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (
        UniqueConstraint("id", "run_step_id", name="uq_step_attempt_id_step"),
        UniqueConstraint(
            "run_step_id", "attempt_number", name="uq_step_attempt_number"
        ),
        UniqueConstraint(
            "run_step_id", "idempotency_key", name="uq_step_attempt_idempotency"
        ),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')", name="status"
        ),
    )


class RunEventModel(Base):
    __tablename__ = "run_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    activity_id: Mapped[str] = mapped_column(String(256), nullable=False)
    activity_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    activity_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    activity_name: Mapped[str] = mapped_column(String(160), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(128))
    progress: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    artifact_version_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint(
            "progress IS NULL OR progress BETWEEN 0 AND 100", name="progress_range"
        ),
        CheckConstraint(
            "activity_kind IN ('reasoning','tool','observation','status',"
            "'artifact','retry','error','completion')",
            name="run_event_activity_kind",
        ),
        CheckConstraint(
            "activity_phase IN ('queued','streaming','running','completed',"
            "'failed','retrying')",
            name="run_event_activity_phase",
        ),
        Index("ix_run_events_run_occurred", "run_id", "occurred_at"),
    )


class RunCheckpointModel(TimestampMixin, Base):
    __tablename__ = "run_checkpoints"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "step_key", name="uq_run_checkpoint_run_step"),
        CheckConstraint("jsonb_array_length(options) >= 1", name="checkpoint_options"),
    )


class RunCheckpointDecisionModel(Base):
    __tablename__ = "run_checkpoint_decisions"

    checkpoint_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("run_checkpoints.id", ondelete="CASCADE"),
        primary_key=True,
    )
    selected_option: Mapped[str] = mapped_column(Text, nullable=False)
    free_text: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ResearchArtifactModel(TimestampMixin, Base):
    __tablename__ = "research_artifacts"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    logical_key: Mapped[str] = mapped_column(String(160), nullable=False)
    latest_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_artifact_id_project"),
        UniqueConstraint(
            "project_id", "logical_key", name="uq_artifact_project_logical_key"
        ),
        ForeignKeyConstraint(
            ["latest_version_id", "id"],
            ["artifact_versions.id", "artifact_versions.artifact_id"],
            name="fk_research_artifacts_latest_version_same_artifact",
            use_alter=True,
            ondelete="RESTRICT",
        ),
    )


class ProducerExecutionModel(TimestampMixin, Base):
    __tablename__ = "producer_executions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    lease_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    producer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    producer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_provider: Mapped[str | None] = mapped_column(String(128))
    requested_model: Mapped[str | None] = mapped_column(String(128))
    provider_returned_model: Mapped[str | None] = mapped_column(String(128))
    provider_request_id: Mapped[str | None] = mapped_column(String(256))
    explicit_revision: Mapped[str | None] = mapped_column(String(128))
    prompt_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    prompt_hash: Mapped[str | None] = mapped_column(String(71))
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    parameters_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(71))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("id", "run_step_id", name="uq_producer_execution_id_step"),
        UniqueConstraint(
            "run_step_id", "idempotency_key", name="uq_producer_execution_idempotency"
        ),
        ForeignKeyConstraint(
            ["run_step_id", "run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_producer_execution_step_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["step_attempt_id", "run_step_id"],
            ["step_attempts.id", "step_attempts.run_step_id"],
            name="fk_producer_execution_attempt_step",
            ondelete="CASCADE",
        ),
        Index("ix_producer_executions_step_attempt_id", "step_attempt_id"),
        CheckConstraint(
            "producer_type IN ('pipeline','model','algorithm')", name="producer_type"
        ),
        CheckConstraint(
            "status IN ('running','completed','failed','rejected','cancelled')",
            name="status",
        ),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"
        ),
    )


class ArtifactVersionModel(TimestampMixin, Base):
    __tablename__ = "artifact_versions"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    run_step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    producer_execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_key: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    producer: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    quality_projection: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )
    quality_projection_hash: Mapped[str | None] = mapped_column(
        String(71), nullable=True
    )
    supersedes_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("id", "artifact_id", name="uq_artifact_version_id_artifact"),
        UniqueConstraint("id", "project_id", name="uq_artifact_version_id_project"),
        UniqueConstraint(
            "id",
            "artifact_id",
            "project_id",
            name="uq_artifact_version_id_artifact_project",
        ),
        UniqueConstraint(
            "id",
            "created_by_run_id",
            "project_id",
            name="uq_artifact_version_id_run_project",
        ),
        UniqueConstraint(
            "artifact_id", "version_number", name="uq_artifact_version_number"
        ),
        UniqueConstraint(
            "artifact_id", "publication_key", name="uq_artifact_publication_key"
        ),
        ForeignKeyConstraint(
            ["artifact_id", "project_id"],
            ["research_artifacts.id", "research_artifacts.project_id"],
            name="fk_artifact_version_artifact_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["created_by_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_artifact_version_run_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_step_id", "created_by_run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_artifact_version_step_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["step_attempt_id", "run_step_id"],
            ["step_attempts.id", "step_attempts.run_step_id"],
            name="fk_artifact_version_attempt_step",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["producer_execution_id", "run_step_id"],
            ["producer_executions.id", "producer_executions.run_step_id"],
            name="fk_artifact_version_producer_step",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["supersedes_version_id", "artifact_id"],
            ["artifact_versions.id", "artifact_versions.artifact_id"],
            name="fk_artifact_version_supersedes_same_artifact",
            ondelete="RESTRICT",
        ),
        Index("ix_artifact_versions_created_by_run_id", "created_by_run_id"),
        Index("ix_artifact_versions_run_step_id", "run_step_id"),
        Index("ix_artifact_versions_step_attempt_id", "step_attempt_id"),
        Index("ix_artifact_versions_producer_execution_id", "producer_execution_id"),
        CheckConstraint("version_number >= 1", name="version_positive"),
        CheckConstraint(
            "source_mode IN ('fixture','live','cached')", name="source_mode"
        ),
    )


class UserFeedbackModel(TimestampMixin, Base):
    """Immutable, owner-scoped feedback bound to one baseline ArtifactVersion."""

    __tablename__ = "user_feedback"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    baseline_artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    baseline_version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    requested_change: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_user_feedback_id_project"),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_user_feedback_project_idempotency",
        ),
        ForeignKeyConstraint(
            ["project_id", "owner_session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_user_feedback_project_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["baseline_artifact_version_id", "artifact_id", "project_id"],
            [
                "artifact_versions.id",
                "artifact_versions.artifact_id",
                "artifact_versions.project_id",
            ],
            name="fk_user_feedback_baseline_version",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "baseline_version_number >= 1", name="baseline_version_positive"
        ),
        CheckConstraint(
            "target_type IN ('artifact','artifact_version','dataset_field','dataset_row',"
            "'paper','paper_summary','claim','relation','trace','graph_node','graph_edge')",
            name="target_type",
        ),
        CheckConstraint(
            "category IN ('correction','omission','evidence','quality','interpretation')",
            name="category",
        ),
        Index(
            "ix_user_feedback_project_created",
            "project_id",
            "created_at",
            "id",
        ),
        Index("ix_user_feedback_baseline", "baseline_artifact_version_id"),
    )


class RevisionPlanModel(TimestampMixin, Base):
    """Immutable affected/reusable closure proposed for one parent Run."""

    __tablename__ = "revision_plans"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    parent_run_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    recompute_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_revision_plan_id_project"),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_revision_plan_project_idempotency",
        ),
        ForeignKeyConstraint(
            ["project_id", "owner_session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_revision_plans_project_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["parent_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_revision_plans_parent_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["contract_id", "project_id"],
            ["research_contracts.id", "research_contracts.project_id"],
            name="fk_revision_plans_contract",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "parent_run_revision >= 1", name="parent_run_revision_positive"
        ),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(
            "jsonb_typeof(recompute_steps) = 'array' "
            "AND jsonb_array_length(recompute_steps) >= 2",
            name="recompute_steps_nonempty",
        ),
        Index("ix_revision_plans_parent_run", "parent_run_id"),
    )


class RevisionPlanFeedbackModel(Base):
    __tablename__ = "revision_plan_feedback"

    revision_plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    feedback_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("revision_plan_id", "feedback_id"),
        UniqueConstraint(
            "revision_plan_id", "position", name="uq_revision_plan_feedback_position"
        ),
        ForeignKeyConstraint(
            ["revision_plan_id", "project_id"],
            ["revision_plans.id", "revision_plans.project_id"],
            name="fk_revision_plan_feedback_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["feedback_id", "project_id"],
            ["user_feedback.id", "user_feedback.project_id"],
            name="fk_revision_plan_feedback_feedback",
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
    )


class RevisionPlanVersionModel(Base):
    __tablename__ = "revision_plan_versions"

    revision_plan_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        PrimaryKeyConstraint("revision_plan_id", "artifact_version_id"),
        UniqueConstraint(
            "revision_plan_id", "position", name="uq_revision_plan_version_position"
        ),
        ForeignKeyConstraint(
            ["revision_plan_id", "project_id"],
            ["revision_plans.id", "revision_plans.project_id"],
            name="fk_revision_plan_versions_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["artifact_version_id", "artifact_id", "project_id"],
            [
                "artifact_versions.id",
                "artifact_versions.artifact_id",
                "artifact_versions.project_id",
            ],
            name="fk_revision_plan_versions_artifact_version",
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 0", name="position_nonnegative"),
        CheckConstraint("version_number >= 1", name="version_positive"),
        CheckConstraint("decision IN ('recompute','reuse')", name="decision"),
        CheckConstraint(
            "(decision = 'recompute' AND step_key IS NOT NULL) OR "
            "(decision = 'reuse' AND step_key IS NULL)",
            name="decision_shape",
        ),
        Index("ix_revision_plan_versions_version", "artifact_version_id"),
    )


class RevisionPlanConfirmationModel(Base):
    """Immutable one-to-one binding from a confirmed plan to its revision Run."""

    __tablename__ = "revision_plan_confirmations"

    revision_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    owner_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_revision_confirmation_project_idempotency",
        ),
        ForeignKeyConstraint(
            ["project_id", "owner_session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_revision_confirmations_project_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["revision_plan_id", "project_id"],
            ["revision_plans.id", "revision_plans.project_id"],
            name="fk_revision_confirmations_plan",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_revision_confirmations_run",
            ondelete="CASCADE",
        ),
    )


class DatasetRowProjectionModel(Base):
    """Immutable row projection used by bounded Dataset reads."""

    __tablename__ = "dataset_row_projections"

    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("artifact_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    row_id: Mapped[str] = mapped_column(String(256), nullable=False)
    row: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("artifact_version_id", "row_id"),
        Index(
            "ix_dataset_row_projection_project_version",
            "project_id",
            "artifact_version_id",
        ),
    )


class SourceSnapshotModel(Base):
    __tablename__ = "source_snapshots"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    query: Mapped[Any] = mapped_column(JSONB, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    source_version_or_etag: Mapped[str | None] = mapped_column(String(256))
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    license_note: Mapped[str] = mapped_column(Text, nullable=False)
    cache_version: Mapped[str | None] = mapped_column(String(128))
    request_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_source_snapshot_id_project"),
        Index("ix_source_snapshots_project_retrieved", "project_id", "retrieved_at"),
    )


class EvidenceModel(TimestampMixin, Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    paper_id: Mapped[str | None] = mapped_column(String(128))
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quote_or_value: Mapped[Any | None] = mapped_column(JSONB)
    extraction_method: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    is_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_evidence_id_project"),
        ForeignKeyConstraint(
            ["artifact_version_id", "project_id"],
            ["artifact_versions.id", "artifact_versions.project_id"],
            name="fk_evidence_version_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_evidence_snapshot_project",
            ondelete="RESTRICT",
        ),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        Index("ix_evidence_artifact_version_id", "artifact_version_id"),
        Index("ix_evidence_source_snapshot_id", "source_snapshot_id"),
    )


class CacheRecordModel(Base):
    """Immutable eligibility snapshot for one reusable live ArtifactVersion."""

    __tablename__ = "cache_records"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    origin_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    origin_artifact_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    producer_identity: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    producer_identity_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    source_scope_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    evidence_requirements_hash: Mapped[str] = mapped_column(
        String(71), nullable=False
    )
    quality_constraints_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    source_snapshot_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    source_snapshot_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    quality_projection_hash: Mapped[str | None] = mapped_column(String(71))
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    record_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_cache_record_id_project"),
        UniqueConstraint(
            "id",
            "origin_run_id",
            "origin_artifact_version_id",
            "project_id",
            name="uq_cache_record_origin_closure",
        ),
        UniqueConstraint(
            "project_id", "record_hash", name="uq_cache_record_project_hash"
        ),
        ForeignKeyConstraint(
            ["origin_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_cache_records_origin_run_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["origin_artifact_version_id", "origin_run_id", "project_id"],
            [
                "artifact_versions.id",
                "artifact_versions.created_by_run_id",
                "artifact_versions.project_id",
            ],
            name="fk_cache_records_origin_version_run_project",
            ondelete="CASCADE",
        ),
        CheckConstraint("expires_at > valid_from", name="validity_window"),
        Index(
            "ix_cache_records_selector",
            "project_id",
            "artifact_kind",
            "contract_hash",
            "input_hash",
            "expires_at",
        ),
        Index(
            "ix_cache_records_origin_version", "origin_artifact_version_id"
        ),
    )


class CacheSelectionAuditModel(Base):
    """One idempotent CacheSelector decision for a failed RunStep."""

    __tablename__ = "cache_selection_audits"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    failed_producer_execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    selector_identity_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    cache_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    origin_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    origin_artifact_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    live_failure_class: Mapped[str] = mapped_column(String(128), nullable=False)
    live_failure_code: Mapped[str] = mapped_column(String(128), nullable=False)
    event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("run_step_id", "request_hash", name="uq_cache_audit_request"),
        ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_cache_audits_run_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_step_id", "run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_cache_audits_step_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "event_sequence"],
            ["run_events.run_id", "run_events.sequence"],
            name="fk_cache_audits_event_sequence",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["failed_producer_execution_id", "run_step_id"],
            ["producer_executions.id", "producer_executions.run_step_id"],
            name="fk_cache_audits_failed_producer_step",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            [
                "cache_record_id",
                "origin_run_id",
                "origin_artifact_version_id",
                "project_id",
            ],
            [
                "cache_records.id",
                "cache_records.origin_run_id",
                "cache_records.origin_artifact_version_id",
                "cache_records.project_id",
            ],
            name="fk_cache_audits_record_origin_closure",
            ondelete="RESTRICT",
        ),
        CheckConstraint("outcome IN ('selected','rejected')", name="outcome"),
        CheckConstraint("event_sequence >= 1", name="event_sequence_positive"),
        CheckConstraint(
            "(outcome = 'selected' AND reason = 'CACHE_SELECTED' "
            "AND cache_record_id IS NOT NULL AND origin_run_id IS NOT NULL "
            "AND origin_artifact_version_id IS NOT NULL) OR "
            "(outcome = 'rejected' AND reason <> 'CACHE_SELECTED' "
            "AND cache_record_id IS NULL AND origin_run_id IS NULL "
            "AND origin_artifact_version_id IS NULL)",
            name="decision_shape",
        ),
        Index("ix_cache_audits_run_created", "run_id", "created_at"),
    )


class ResearchInputModel(Base):
    """Immutable provenance reference for one ingested Research Input.

    Content facts (``storage_ref``, ``mime_type``, ``size_bytes``) live solely
    in :class:`ResearchInputContentModel`, referenced through the composite FK
    ``(project_id, content_hash)``. This table records who ingested which
    content identity from which source and when.

    ``expires_at`` is the soft-delete marker: deletion expires the reference,
    never the content blob.
    """

    __tablename__ = "research_inputs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_input_id_project"),
        ForeignKeyConstraint(
            ["project_id", "content_hash"],
            [
                "research_input_contents.project_id",
                "research_input_contents.content_hash",
            ],
            name="fk_research_input_content",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_research_input_snapshot_project",
            ondelete="RESTRICT",
        ),
        Index("ix_research_inputs_session_project", "session_id", "project_id"),
        Index("ix_research_inputs_session_content", "session_id", "content_hash"),
        CheckConstraint(
            "type IN ('url','pdf','csv','json','image','text')", name="input_type"
        ),
        CheckConstraint(
            "source_type IN ('upload','url_fetch','text')", name="source_type"
        ),
        CheckConstraint(
            "status IN ('accepted','unsupported_processing','failed_ingestion')",
            name="input_status",
        ),
    )


class ResearchInputContentModel(Base):
    """Immutable content identity for ingested Research Input bytes.

    A ``(project_id, content_hash)`` pair identifies one blob with one storage
    reference, MIME type and size. Source facts do not belong on this table.
    """

    __tablename__ = "research_input_contents"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    )
    content_hash: Mapped[str] = mapped_column(
        String(71), nullable=False, primary_key=True
    )
    storage_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "size_bytes >= 0", name="ck_research_input_content_size_nonneg"
        ),
    )


class ResearchInputBindingModel(Base):
    """One active binding from an immutable Research Input to a Draft or Run."""

    __tablename__ = "research_input_bindings"

    input_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    contract_draft_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_research_input_binding_input_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["contract_draft_id", "project_id"],
            ["research_contract_drafts.id", "research_contract_drafts.project_id"],
            name="fk_research_input_binding_draft_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_research_input_binding_run_project",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(contract_draft_id IS NULL) <> (run_id IS NULL)",
            name="binding_target_xor",
        ),
    )


class ResearchInputIdempotencyModel(Base):
    """HTTP request identity for Research Input creation.

    Content deduplication belongs to ``research_input_contents`` under the
    ``(project_id, content_hash)`` key. Request idempotency belongs here under
    ``(session_id, project_id, idempotency_key)``. Distinct ingestion requests
    may therefore reference the same immutable content without being collapsed
    into one provenance event.
    """

    __tablename__ = "research_input_idempotency"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_research_input_idempotency_input_project",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending','completed')",
            name="idempotency_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND input_id IS NULL"
            " AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)"
            " OR (status = 'completed' AND input_id IS NOT NULL"
            " AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="idempotency_status_lease",
        ),
        Index(
            "ix_research_input_idempotency_input",
            "input_id",
        ),
    )


class PaperCandidateInputBindingModel(Base):
    """Immutable provenance bridge from a selected paper to a ResearchInput."""

    __tablename__ = "paper_candidate_input_bindings"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    paper_collection_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    canonical_paper_id: Mapped[str] = mapped_column(String(256), nullable=False)
    candidate_source_snapshot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    candidate_evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    source_collection_status: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_reason: Mapped[str | None] = mapped_column(String(64))
    access_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True)
    )
    access_evidence_hash: Mapped[str | None] = mapped_column(String(71))
    research_input_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    research_input_content_hash: Mapped[str | None] = mapped_column(String(71))
    identity_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    producer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "id", "project_id", name="uq_paper_candidate_input_binding_id_project"
        ),
        UniqueConstraint(
            "project_id",
            "identity_hash",
            name="uq_paper_candidate_input_binding_identity",
        ),
        UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_paper_candidate_input_binding_idempotency",
        ),
        ForeignKeyConstraint(
            ["paper_collection_version_id", "project_id"],
            ["artifact_versions.id", "artifact_versions.project_id"],
            name="fk_paper_candidate_input_binding_version_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["candidate_source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_paper_candidate_input_binding_snapshot_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["candidate_evidence_id", "project_id"],
            ["evidence.id", "evidence.project_id"],
            name="fk_paper_candidate_input_binding_evidence_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["research_input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_paper_candidate_input_binding_input_project",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "mode IN ('open_access_url','existing_research_input','metadata_only')",
            name="mode",
        ),
        CheckConstraint(
            "outcome IN ('accepted','metadata_only')", name="outcome"
        ),
        CheckConstraint(
            "source_collection_status IN ('completed','partial')",
            name="source_collection_status",
        ),
        CheckConstraint(
            "(outcome = 'accepted' AND mode <> 'metadata_only'"
            " AND metadata_reason IS NULL"
            " AND access_evidence IS NOT NULL AND access_evidence_hash IS NOT NULL"
            " AND research_input_id IS NOT NULL"
            " AND research_input_content_hash IS NOT NULL)"
            " OR (outcome = 'metadata_only' AND mode = 'metadata_only'"
            " AND metadata_reason IS NOT NULL"
            " AND access_evidence IS NULL AND access_evidence_hash IS NULL"
            " AND research_input_id IS NULL"
            " AND research_input_content_hash IS NULL)",
            name="outcome_shape",
        ),
        Index(
            "ix_paper_candidate_input_bindings_candidate",
            "project_id",
            "paper_collection_version_id",
            "candidate_id",
        ),
        Index(
            "ix_paper_candidate_input_bindings_input", "research_input_id"
        ),
    )


class PaperCandidateInputIdempotencyModel(Base):
    """Lease-bound request identity for the PaperCandidate input bridge."""

    __tablename__ = "paper_candidate_input_idempotency"

    session_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("research_projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    binding_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    lease_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["binding_id", "project_id"],
            [
                "paper_candidate_input_bindings.id",
                "paper_candidate_input_bindings.project_id",
            ],
            name="fk_paper_candidate_input_idempotency_binding_project",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('pending','completed')",
            name="paper_candidate_input_idempotency_status",
        ),
        CheckConstraint(
            "(status = 'pending' AND binding_id IS NULL"
            " AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)"
            " OR (status = 'completed' AND binding_id IS NOT NULL"
            " AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="paper_candidate_input_idempotency_status_lease",
        ),
        Index("ix_paper_candidate_input_idempotency_binding", "binding_id"),
    )


class DocumentParseModel(Base):
    """Immutable internal persistence record for a Canonical document parse.

    The large Canonical payload lives behind ``payload_storage_ref`` in the
    existing content-addressed storage.  This table keeps only identity,
    ownership and provenance metadata; it is deliberately not an
    ``ArtifactVersion`` and has no public API representation.
    """

    __tablename__ = "document_parses"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    research_input_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    producer_execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    candidate_parse_id: Mapped[str] = mapped_column(String(256), nullable=False)
    identity_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    parse_input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    canonical_output_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    payload_content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    payload_semantic_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    payload_storage_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    parser_profile_id: Mapped[str] = mapped_column(String(256), nullable=False)
    parser_profile_version: Mapped[str] = mapped_column(String(128), nullable=False)
    native_engine: Mapped[str] = mapped_column(String(256), nullable=False)
    native_engine_version: Mapped[str] = mapped_column(String(128), nullable=False)
    visual_engine: Mapped[str | None] = mapped_column(String(256))
    visual_engine_version: Mapped[str | None] = mapped_column(String(128))
    visual_model_id: Mapped[str | None] = mapped_column(String(256))
    visual_model_revision: Mapped[str | None] = mapped_column(String(256))
    config_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    overall_quality: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_document_parse_id_project"),
        UniqueConstraint(
            "id",
            "project_id",
            "source_snapshot_id",
            name="uq_document_parse_id_project_snapshot",
        ),
        UniqueConstraint("project_id", "identity_hash", name="uq_document_parse_identity"),
        ForeignKeyConstraint(
            ["research_input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_document_parse_input_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_document_parse_snapshot_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["created_by_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_document_parse_run_project",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["run_step_id", "created_by_run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_document_parse_step_run",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["producer_execution_id", "run_step_id"],
            ["producer_executions.id", "producer_executions.run_step_id"],
            name="fk_document_parse_producer_step",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "overall_quality IN ('accepted','partial','unsupported')",
            name="quality",
        ),
        CheckConstraint(
            "(visual_engine IS NULL AND visual_engine_version IS NULL) OR "
            "(visual_engine IS NOT NULL AND visual_engine_version IS NOT NULL)",
            name="visual_engine_complete",
        ),
        CheckConstraint(
            "(visual_model_id IS NULL AND visual_model_revision IS NULL) OR "
            "(visual_model_id IS NOT NULL AND visual_model_revision IS NOT NULL)",
            name="visual_model_complete",
        ),
        Index("ix_document_parses_input", "project_id", "research_input_id"),
        Index("ix_document_parses_snapshot", "source_snapshot_id"),
        Index("ix_document_parses_producer", "producer_execution_id"),
    )


class DocumentParseLocatorModel(Base):
    """Immutable, parse-pinned Canonical Evidence locator."""

    __tablename__ = "document_parse_locators"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    document_parse_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    locator_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint(
            "document_parse_id", "locator_hash", name="uq_document_parse_locator_hash"
        ),
        ForeignKeyConstraint(
            ["document_parse_id", "project_id", "source_snapshot_id"],
            [
                "document_parses.id",
                "document_parses.project_id",
                "document_parses.source_snapshot_id",
            ],
            name="fk_document_parse_locator_parse_project",
            ondelete="CASCADE",
        ),
        Index("ix_document_parse_locators_project", "project_id"),
        Index("ix_document_parse_locators_snapshot", "source_snapshot_id"),
    )
