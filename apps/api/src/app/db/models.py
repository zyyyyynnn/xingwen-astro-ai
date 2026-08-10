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
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ResearchProjectModel(TimestampMixin, Base):
    __tablename__ = "research_projects"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    case_key: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
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


class ResearchContractModel(TimestampMixin, Base):
    __tablename__ = "research_contracts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
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
        UniqueConstraint("project_id", "version", name="uq_research_contract_project_version"),
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    contract: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_contract_draft_id_project"),
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    derivation_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="original")
    retry_from_step: Mapped[str | None] = mapped_column(String(128))
    cache_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="disabled")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    latest_event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
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
        UniqueConstraint("project_id", "idempotency_key", name="uq_research_run_idempotency"),
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
        CheckConstraint("execution_mode IN ('demo_replay', 'live')", name="execution_mode"),
        CheckConstraint(
            "status IN ('queued','planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed','failed','cancelled')",
            name="status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint("latest_event_sequence >= 0", name="event_sequence_nonnegative"),
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
    )


class RunStepModel(TimestampMixin, Base):
    __tablename__ = "run_steps"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
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
            "(enter_status = 'planning' AND success_status = 'fetching_data') OR "
            "(enter_status = 'fetching_data' AND success_status = 'cleaning_data') OR "
            "(enter_status = 'cleaning_data' AND success_status = 'searching_papers') OR "
            "(enter_status = 'searching_papers' AND success_status = 'summarizing_papers') OR "
            "(enter_status = 'summarizing_papers' AND success_status = 'reasoning_literature') OR "
            "(enter_status = 'reasoning_literature' AND success_status = 'building_graph') OR "
            "(enter_status = 'building_graph' AND success_status = 'completed')",
            name="canonical_transition",
        ),
        CheckConstraint(
            "status IN ('pending','running','waiting','completed','failed','cancelled','skipped')",
            name="status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
    )


class StepAttemptModel(TimestampMixin, Base):
    __tablename__ = "step_attempts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    run_step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(128))
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    upstream_request_id: Mapped[str | None] = mapped_column(String(256))

    __table_args__ = (
        UniqueConstraint("id", "run_step_id", name="uq_step_attempt_id_step"),
        UniqueConstraint("run_step_id", "attempt_number", name="uq_step_attempt_number"),
        UniqueConstraint("run_step_id", "idempotency_key", name="uq_step_attempt_idempotency"),
        CheckConstraint("attempt_number >= 1", name="attempt_number_positive"),
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')", name="status"
        ),
    )


class RunEventModel(Base):
    __tablename__ = "run_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(128))
    progress: Mapped[int | None] = mapped_column(Integer)
    public_message: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_version_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
        CheckConstraint("sequence >= 1", name="sequence_positive"),
        CheckConstraint("progress IS NULL OR progress BETWEEN 0 AND 100", name="progress_range"),
        Index("ix_run_events_run_occurred", "run_id", "occurred_at"),
    )


class ResearchArtifactModel(TimestampMixin, Base):
    __tablename__ = "research_artifacts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    logical_key: Mapped[str] = mapped_column(String(160), nullable=False)
    latest_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_artifact_id_project"),
        UniqueConstraint("project_id", "logical_key", name="uq_artifact_project_logical_key"),
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
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
    model_name: Mapped[str | None] = mapped_column(String(128))
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
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("id", "run_step_id", name="uq_producer_execution_id_step"),
        UniqueConstraint("run_step_id", "idempotency_key", name="uq_producer_execution_idempotency"),
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
        CheckConstraint("producer_type IN ('pipeline','model','algorithm')", name="producer_type"),
        CheckConstraint(
            "status IN ('running','completed','failed','rejected','cancelled')",
            name="status",
        ),
        CheckConstraint("lease_generation >= 0", name="lease_generation_nonnegative"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
    )


class ArtifactVersionModel(TimestampMixin, Base):
    __tablename__ = "artifact_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    created_by_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_step_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    step_attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    producer_execution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_key: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    source_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    producer: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_snapshot_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    quality_projection: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    quality_projection_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    supersedes_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))

    __table_args__ = (
        UniqueConstraint("id", "artifact_id", name="uq_artifact_version_id_artifact"),
        UniqueConstraint("id", "project_id", name="uq_artifact_version_id_project"),
        UniqueConstraint("artifact_id", "version_number", name="uq_artifact_version_number"),
        UniqueConstraint("artifact_id", "publication_key", name="uq_artifact_publication_key"),
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
        CheckConstraint("source_mode IN ('fixture','live','cached')", name="source_mode"),
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    artifact_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_snapshot_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
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

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_snapshot_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        UniqueConstraint("id", "project_id", name="uq_research_input_id_project"),
        ForeignKeyConstraint(
            ["project_id", "content_hash"],
            ["research_input_contents.project_id", "research_input_contents.content_hash"],
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
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False, primary_key=True)
    storage_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_research_input_content_size_nonneg"),
    )


class ResearchInputBindingModel(Base):
    """One active binding from an immutable Research Input to a Draft or Run."""

    __tablename__ = "research_input_bindings"

    input_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    contract_draft_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
    )
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    bound_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
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
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
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
