"""establish workflow PostgreSQL persistence baseline

Revision ID: 20260721_0001
Revises: None
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("case_key", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_research_projects_revision_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_research_projects"),
    )
    op.create_index("ix_research_projects_session_id", "research_projects", ["session_id"])
    op.create_table(
        "research_contracts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_research_contracts_version_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], name="fk_research_contracts_project_id_research_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_research_contracts"),
        sa.UniqueConstraint("id", "project_id", name="uq_research_contract_id_project"),
        sa.UniqueConstraint("project_id", "version", name="uq_research_contract_project_version"),
    )
    op.create_table(
        "research_runs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("contract_id", _uuid(), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("parent_run_id", _uuid(), nullable=True),
        sa.Column("derivation_kind", sa.String(32), nullable=False),
        sa.Column("retry_from_step", sa.String(128), nullable=True),
        sa.Column("cache_policy", sa.String(64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("latest_event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("execution_mode IN ('demo_replay', 'live')", name="ck_research_runs_execution_mode"),
        sa.CheckConstraint("status IN ('queued','planning','fetching_data','cleaning_data','searching_papers','summarizing_papers','reasoning_literature','building_graph','waiting_for_input','completed','failed','cancelled')", name="ck_research_runs_status"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_research_runs_progress_range"),
        sa.CheckConstraint("revision >= 1", name="ck_research_runs_revision_positive"),
        sa.CheckConstraint("latest_event_sequence >= 0", name="ck_research_runs_event_sequence_nonnegative"),
        sa.CheckConstraint("derivation_kind IN ('original','retry','revision','fork')", name="ck_research_runs_derivation_kind"),
        sa.CheckConstraint("(derivation_kind = 'original' AND parent_run_id IS NULL) OR (derivation_kind <> 'original' AND parent_run_id IS NOT NULL)", name="ck_research_runs_derivation_parent"),
        sa.ForeignKeyConstraint(["contract_id", "project_id"], ["research_contracts.id", "research_contracts.project_id"], name="fk_research_runs_contract_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_run_id", "project_id"], ["research_runs.id", "research_runs.project_id"], name="fk_research_runs_parent_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], name="fk_research_runs_project_id_research_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_research_runs"),
        sa.UniqueConstraint("id", "project_id", name="uq_research_run_id_project"),
        sa.UniqueConstraint("project_id", "idempotency_key", name="uq_research_run_idempotency"),
    )
    op.create_table(
        "run_steps",
        sa.Column("id", _uuid(), nullable=False), sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False), sa.Column("label", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_hash", sa.String(71), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True), sa.Column("public_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('pending','running','waiting','completed','failed','cancelled','skipped')", name="ck_run_steps_status"),
        sa.CheckConstraint("progress BETWEEN 0 AND 100", name="ck_run_steps_progress_range"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name="fk_run_steps_run_id_research_runs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps"),
        sa.UniqueConstraint("id", "run_id", name="uq_run_step_id_run"),
        sa.UniqueConstraint("run_id", "key", name="uq_run_step_run_key"),
    )
    op.create_table(
        "step_attempts",
        sa.Column("id", _uuid(), nullable=False), sa.Column("run_step_id", _uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), sa.Column("error_class", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True), sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("upstream_request_id", sa.String(256), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("attempt_number >= 1", name="ck_step_attempts_attempt_number_positive"),
        sa.CheckConstraint("status IN ('running','completed','failed','cancelled')", name="ck_step_attempts_status"),
        sa.ForeignKeyConstraint(["run_step_id"], ["run_steps.id"], name="fk_step_attempts_run_step_id_run_steps", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_step_attempts"),
        sa.UniqueConstraint("id", "run_step_id", name="uq_step_attempt_id_step"),
        sa.UniqueConstraint("run_step_id", "attempt_number", name="uq_step_attempt_number"),
        sa.UniqueConstraint("run_step_id", "idempotency_key", name="uq_step_attempt_idempotency"),
    )
    op.create_table(
        "run_events",
        sa.Column("id", _uuid(), nullable=False), sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False), sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=True), sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("public_message", sa.Text(), nullable=False), sa.Column("artifact_version_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_run_events_sequence_positive"),
        sa.CheckConstraint("progress IS NULL OR progress BETWEEN 0 AND 100", name="ck_run_events_progress_range"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name="fk_run_events_run_id_research_runs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_run_events"), sa.UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
    )
    op.create_index("ix_run_events_run_occurred", "run_events", ["run_id", "occurred_at"])
    op.create_table(
        "research_artifacts",
        sa.Column("id", _uuid(), nullable=False), sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("logical_key", sa.String(160), nullable=False), sa.Column("latest_version_id", _uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], name="fk_research_artifacts_project_id_research_projects", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_research_artifacts"),
        sa.UniqueConstraint("id", "project_id", name="uq_research_artifact_id_project"),
        sa.UniqueConstraint("project_id", "logical_key", name="uq_artifact_project_logical_key"),
    )
    op.create_table(
        "producer_executions",
        sa.Column("id", _uuid(), nullable=False), sa.Column("run_id", _uuid(), nullable=False), sa.Column("run_step_id", _uuid(), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=False), sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("producer_type", sa.String(32), nullable=False), sa.Column("producer_name", sa.String(128), nullable=False),
        sa.Column("producer_version", sa.String(64), nullable=False), sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("prompt_name", sa.String(128), nullable=True), sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("parameters_hash", sa.String(71), nullable=True), sa.Column("input_hash", sa.String(71), nullable=False),
        sa.Column("output_hash", sa.String(71), nullable=True), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True), sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("producer_type IN ('pipeline','model','algorithm')", name="ck_producer_executions_producer_type"),
        sa.CheckConstraint("status IN ('running','completed','failed','cancelled')", name="ck_producer_executions_status"),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_producer_executions_latency_nonnegative"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], name="fk_producer_executions_run_id_research_runs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_step_id", "run_id"], ["run_steps.id", "run_steps.run_id"], name="fk_producer_execution_step_run", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_producer_executions"),
        sa.UniqueConstraint("id", "run_step_id", name="uq_producer_execution_id_step"),
        sa.UniqueConstraint("run_step_id", "idempotency_key", name="uq_producer_execution_idempotency"),
    )
    op.create_table(
        "artifact_versions",
        sa.Column("id", _uuid(), nullable=False), sa.Column("artifact_id", _uuid(), nullable=False), sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("created_by_run_id", _uuid(), nullable=False), sa.Column("run_step_id", _uuid(), nullable=False), sa.Column("step_attempt_id", _uuid(), nullable=False), sa.Column("producer_execution_id", _uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("publication_key", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False), sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False), sa.Column("input_hash", sa.String(71), nullable=False),
        sa.Column("source_mode", sa.String(16), nullable=False), sa.Column("producer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_snapshot_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False), sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supersedes_version_id", _uuid(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("version_number >= 1", name="ck_artifact_versions_version_positive"),
        sa.CheckConstraint("source_mode IN ('fixture','live','cached')", name="ck_artifact_versions_source_mode"),
        sa.ForeignKeyConstraint(["artifact_id", "project_id"], ["research_artifacts.id", "research_artifacts.project_id"], name="fk_artifact_version_artifact_project", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_run_id", "project_id"], ["research_runs.id", "research_runs.project_id"], name="fk_artifact_version_run_project", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], name="fk_artifact_versions_project_id_research_projects", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_step_id", "created_by_run_id"], ["run_steps.id", "run_steps.run_id"], name="fk_artifact_version_step_run", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["step_attempt_id", "run_step_id"], ["step_attempts.id", "step_attempts.run_step_id"], name="fk_artifact_version_attempt_step", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["producer_execution_id", "run_step_id"], ["producer_executions.id", "producer_executions.run_step_id"], name="fk_artifact_version_producer_step", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_version_id", "artifact_id"], ["artifact_versions.id", "artifact_versions.artifact_id"], name="fk_artifact_version_supersedes_same_artifact", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_artifact_versions"),
        sa.UniqueConstraint("id", "artifact_id", name="uq_artifact_version_id_artifact"),
        sa.UniqueConstraint("artifact_id", "version_number", name="uq_artifact_version_number"),
        sa.UniqueConstraint("artifact_id", "publication_key", name="uq_artifact_publication_key"),
    )
    op.create_index("ix_artifact_versions_created_by_run_id", "artifact_versions", ["created_by_run_id"])
    op.create_index("ix_artifact_versions_run_step_id", "artifact_versions", ["run_step_id"])
    op.create_index("ix_artifact_versions_step_attempt_id", "artifact_versions", ["step_attempt_id"])
    op.create_index("ix_artifact_versions_producer_execution_id", "artifact_versions", ["producer_execution_id"])
    op.create_foreign_key("fk_research_artifacts_latest_version_same_artifact", "research_artifacts", "artifact_versions", ["latest_version_id", "id"], ["id", "artifact_id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_research_artifacts_latest_version_same_artifact", "research_artifacts", type_="foreignkey")
    op.drop_table("artifact_versions")
    op.drop_table("producer_executions")
    op.drop_table("research_artifacts")
    op.drop_index("ix_run_events_run_occurred", table_name="run_events")
    op.drop_table("run_events")
    op.drop_table("step_attempts")
    op.drop_table("run_steps")
    op.drop_table("research_runs")
    op.drop_table("research_contracts")
    op.drop_index("ix_research_projects_session_id", table_name="research_projects")
    op.drop_table("research_projects")
