"""SQLAlchemy models for the #76 workflow persistence baseline.

Statuses remain text plus database CHECK constraints so migrations are explicit
and do not depend on PostgreSQL enum lifecycle operations.
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
    ForeignKey,
    Index,
    Integer,
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
    description: Mapped[str | None] = mapped_column(Text)
    case_key: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (CheckConstraint("revision >= 1", name="revision_positive"),)


class ResearchContractModel(TimestampMixin, Base):
    __tablename__ = "research_contracts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_research_contract_project_version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )


class ResearchRunModel(TimestampMixin, Base):
    __tablename__ = "research_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    contract_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_contracts.id", ondelete="RESTRICT"), nullable=False
    )
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parent_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="RESTRICT")
    )
    derivation_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="original")
    retry_from_step: Mapped[str | None] = mapped_column(String(128))
    cache_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    latest_event_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    failure_summary: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(71), nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key", name="uq_research_run_idempotency"),
        CheckConstraint("execution_mode IN ('demo_replay', 'live')", name="execution_mode"),
        CheckConstraint(
            "status IN ('queued','planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed','failed','cancelled')",
            name="status",
        ),
        CheckConstraint("progress BETWEEN 0 AND 100", name="progress_range"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint("latest_event_sequence >= 0", name="event_sequence_nonnegative"),
        CheckConstraint(
            "derivation_kind IN ('original','retry','revision','fork')", name="derivation_kind"
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
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str | None] = mapped_column(String(71))
    failure_code: Mapped[str | None] = mapped_column(String(128))
    public_message: Mapped[str] = mapped_column(Text, nullable=False, default="")

    __table_args__ = (
        UniqueConstraint("run_id", "key", name="uq_run_step_run_key"),
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
    latest_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            "artifact_versions.id",
            name="fk_research_artifacts_latest_version_id_artifact_versions",
            use_alter=True,
            ondelete="SET NULL",
        ),
    )

    __table_args__ = (
        UniqueConstraint("project_id", "logical_key", name="uq_artifact_project_logical_key"),
    )


class ProducerExecutionModel(TimestampMixin, Base):
    __tablename__ = "producer_executions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False
    )
    run_step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("run_steps.id", ondelete="CASCADE"), nullable=False
    )
    step_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    producer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    producer_name: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    parameters_hash: Mapped[str | None] = mapped_column(String(71))
    input_hash: Mapped[str] = mapped_column(String(71), nullable=False)
    output_hash: Mapped[str | None] = mapped_column(String(71))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(128))

    __table_args__ = (
        UniqueConstraint("run_step_id", "idempotency_key", name="uq_producer_execution_idempotency"),
        CheckConstraint("producer_type IN ('pipeline','model','algorithm')", name="producer_type"),
        CheckConstraint("status IN ('running','completed','failed','cancelled')", name="status"),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_nonnegative"),
    )


class ArtifactVersionModel(TimestampMixin, Base):
    __tablename__ = "artifact_versions"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=_uuid)
    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    created_by_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("research_runs.id", ondelete="RESTRICT"), nullable=False
    )
    run_step_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("run_steps.id", ondelete="RESTRICT"), nullable=False
    )
    step_attempt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("step_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    producer_execution_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("producer_executions.id", ondelete="RESTRICT"),
        nullable=False,
    )
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
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifact_versions.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint("artifact_id", "version_number", name="uq_artifact_version_number"),
        UniqueConstraint("artifact_id", "publication_key", name="uq_artifact_publication_key"),
        CheckConstraint("version_number >= 1", name="version_positive"),
        CheckConstraint("source_mode IN ('fixture','live','cached')", name="source_mode"),
    )
