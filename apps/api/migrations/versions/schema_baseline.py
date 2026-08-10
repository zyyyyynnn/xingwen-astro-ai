"""Create the current PostgreSQL schema directly.

This repository has no deployed production database requiring an in-place
upgrade path. Git retains development migration history; the active tree keeps
one baseline describing the current write/read contracts.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "schema_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "research_projects",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("case_key", sa.String(128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_research_projects_revision_positive"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_projects"),
        sa.UniqueConstraint("id", "session_id", name="uq_research_project_id_session"),
        sa.UniqueConstraint(
            "session_id",
            "idempotency_key",
            name="uq_research_project_idempotency",
        ),
    )
    op.create_index(
        "ix_research_projects_session_id", "research_projects", ["session_id"]
    )

    op.create_table(
        "research_contract_drafts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("contract", _jsonb(), nullable=False),
        sa.Column("warnings", _jsonb(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_research_contract_drafts_version_positive"
        ),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','expired')",
            name="ck_research_contract_drafts_draft_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_contract_drafts"),
        sa.ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["research_projects.id", "research_projects.session_id"],
            name="fk_research_contract_drafts_project_session",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_research_contract_draft_id_project"
        ),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_research_contract_draft_idempotency",
        ),
    )
    op.create_index(
        "ix_research_contract_drafts_session_id",
        "research_contract_drafts",
        ["session_id"],
    )

    op.create_table(
        "research_contracts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("content", _jsonb(), nullable=False),
        sa.Column("created_from_draft_id", _uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_research_contracts_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            name="fk_research_contracts_project_id_research_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_from_draft_id", "project_id"],
            ["research_contract_drafts.id", "research_contract_drafts.project_id"],
            name="fk_research_contracts_draft_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_contracts"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_research_contract_id_project"
        ),
        sa.UniqueConstraint(
            "project_id", "version", name="uq_research_contract_project_version"
        ),
        sa.UniqueConstraint(
            "project_id",
            "idempotency_key",
            name="uq_research_contract_idempotency",
        ),
        sa.UniqueConstraint(
            "created_from_draft_id", name="uq_research_contract_created_from_draft"
        ),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("latest_event_sequence", sa.BigInteger(), nullable=False),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("failure_summary", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("lease_token", _uuid(), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("steps_frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "execution_mode IN ('demo_replay', 'live')",
            name="ck_research_runs_execution_mode",
        ),
        sa.CheckConstraint(
            "status IN ('queued','planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed','failed','cancelled')",
            name="ck_research_runs_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_research_runs_progress_range"
        ),
        sa.CheckConstraint(
            "revision >= 1", name="ck_research_runs_revision_positive"
        ),
        sa.CheckConstraint(
            "latest_event_sequence >= 0",
            name="ck_research_runs_event_sequence_nonnegative",
        ),
        sa.CheckConstraint(
            "lease_generation >= 0",
            name="ck_research_runs_lease_generation_nonnegative",
        ),
        sa.CheckConstraint(
            "(lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
            name="ck_research_runs_lease_fields_complete",
        ),
        sa.CheckConstraint(
            "derivation_kind IN ('original','retry','revision','fork')",
            name="ck_research_runs_derivation_kind",
        ),
        sa.CheckConstraint(
            "(derivation_kind = 'original' AND parent_run_id IS NULL) OR "
            "(derivation_kind <> 'original' AND parent_run_id IS NOT NULL)",
            name="ck_research_runs_derivation_parent",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id", "project_id"],
            ["research_contracts.id", "research_contracts.project_id"],
            name="fk_research_runs_contract_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_research_runs_parent_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            name="fk_research_runs_project_id_research_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_runs"),
        sa.UniqueConstraint("id", "project_id", name="uq_research_run_id_project"),
        sa.UniqueConstraint(
            "project_id", "idempotency_key", name="uq_research_run_idempotency"
        ),
    )

    op.create_table(
        "run_steps",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("enter_status", sa.String(32), nullable=False),
        sa.Column("success_status", sa.String(32), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_hash", sa.String(71), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("public_message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "position >= 0", name="ck_run_steps_position_nonnegative"
        ),
        sa.CheckConstraint(
            "max_attempts >= 1", name="ck_run_steps_max_attempts_positive"
        ),
        sa.CheckConstraint(
            "enter_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input')",
            name="ck_run_steps_enter_status",
        ),
        sa.CheckConstraint(
            "success_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
            "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
            "'completed')",
            name="ck_run_steps_success_status",
        ),
        sa.CheckConstraint(
            "(enter_status = 'planning' AND success_status = 'fetching_data') OR "
            "(enter_status = 'fetching_data' AND success_status = 'cleaning_data') OR "
            "(enter_status = 'cleaning_data' AND success_status = 'searching_papers') OR "
            "(enter_status = 'searching_papers' AND success_status = 'summarizing_papers') OR "
            "(enter_status = 'summarizing_papers' AND success_status = 'reasoning_literature') OR "
            "(enter_status = 'reasoning_literature' AND success_status = 'building_graph') OR "
            "(enter_status = 'building_graph' AND success_status = 'completed')",
            name="ck_run_steps_canonical_transition",
        ),
        sa.CheckConstraint(
            "status IN ('pending','running','waiting','completed','failed','cancelled','skipped')",
            name="ck_run_steps_status",
        ),
        sa.CheckConstraint(
            "progress BETWEEN 0 AND 100", name="ck_run_steps_progress_range"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name="fk_run_steps_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_steps"),
        sa.UniqueConstraint("id", "run_id", name="uq_run_step_id_run"),
        sa.UniqueConstraint("run_id", "position", name="uq_run_step_position"),
        sa.UniqueConstraint("run_id", "key", name="uq_run_step_run_key"),
    )

    op.create_table(
        "step_attempts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_step_id", _uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_class", sa.String(128), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("upstream_request_id", sa.String(256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "attempt_number >= 1", name="ck_step_attempts_attempt_number_positive"
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="ck_step_attempts_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id"],
            ["run_steps.id"],
            name="fk_step_attempts_run_step_id_run_steps",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_step_attempts"),
        sa.UniqueConstraint("id", "run_step_id", name="uq_step_attempt_id_step"),
        sa.UniqueConstraint(
            "run_step_id", "attempt_number", name="uq_step_attempt_number"
        ),
        sa.UniqueConstraint(
            "run_step_id", "idempotency_key", name="uq_step_attempt_idempotency"
        ),
    )

    op.create_table(
        "run_events",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("public_message", sa.Text(), nullable=False),
        sa.Column("artifact_version_ids", _jsonb(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "sequence >= 1", name="ck_run_events_sequence_positive"
        ),
        sa.CheckConstraint(
            "progress IS NULL OR progress BETWEEN 0 AND 100",
            name="ck_run_events_progress_range",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name="fk_run_events_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_run_events"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),
    )
    op.create_index(
        "ix_run_events_run_occurred", "run_events", ["run_id", "occurred_at"]
    )

    op.create_table(
        "research_artifacts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("logical_key", sa.String(160), nullable=False),
        sa.Column("latest_version_id", _uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            name="fk_research_artifacts_project_id_research_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_research_artifacts"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_research_artifact_id_project"
        ),
        sa.UniqueConstraint(
            "project_id", "logical_key", name="uq_artifact_project_logical_key"
        ),
    )

    op.create_table(
        "producer_executions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("run_id", _uuid(), nullable=False),
        sa.Column("run_step_id", _uuid(), nullable=False),
        sa.Column("step_attempt_id", _uuid(), nullable=False),
        sa.Column("step_key", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("lease_generation", sa.BigInteger(), nullable=False),
        sa.Column("producer_type", sa.String(32), nullable=False),
        sa.Column("producer_name", sa.String(128), nullable=False),
        sa.Column("producer_version", sa.String(64), nullable=False),
        sa.Column("model_provider", sa.String(128), nullable=True),
        sa.Column("model_name", sa.String(128), nullable=True),
        sa.Column("prompt_name", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("prompt_hash", sa.String(71), nullable=True),
        sa.Column("parameters", _jsonb(), nullable=False),
        sa.Column("parameters_hash", sa.String(71), nullable=False),
        sa.Column("input_hash", sa.String(71), nullable=False),
        sa.Column("output_hash", sa.String(71), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_usage", _jsonb(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "producer_type IN ('pipeline','model','algorithm')",
            name="ck_producer_executions_producer_type",
        ),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','rejected','cancelled')",
            name="ck_producer_executions_status",
        ),
        sa.CheckConstraint(
            "lease_generation >= 0",
            name="ck_producer_executions_lease_generation_nonnegative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_producer_executions_latency_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.id"],
            name="fk_producer_executions_run_id_research_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id", "run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_producer_execution_step_run",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["step_attempt_id", "run_step_id"],
            ["step_attempts.id", "step_attempts.run_step_id"],
            name="fk_producer_execution_attempt_step",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_producer_executions"),
        sa.UniqueConstraint(
            "id", "run_step_id", name="uq_producer_execution_id_step"
        ),
        sa.UniqueConstraint(
            "run_step_id",
            "idempotency_key",
            name="uq_producer_execution_idempotency",
        ),
    )
    op.create_index(
        "ix_producer_executions_step_attempt_id",
        "producer_executions",
        ["step_attempt_id"],
    )

    op.create_table(
        "artifact_versions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("artifact_id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("created_by_run_id", _uuid(), nullable=False),
        sa.Column("run_step_id", _uuid(), nullable=False),
        sa.Column("step_attempt_id", _uuid(), nullable=False),
        sa.Column("producer_execution_id", _uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("publication_key", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(32), nullable=False),
        sa.Column("content", _jsonb(), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("input_hash", sa.String(71), nullable=False),
        sa.Column("source_mode", sa.String(16), nullable=False),
        sa.Column("producer", _jsonb(), nullable=False),
        sa.Column("source_snapshot_ids", _jsonb(), nullable=False),
        sa.Column("evidence_ids", _jsonb(), nullable=False),
        sa.Column("quality_projection", _jsonb(), nullable=True),
        sa.Column("quality_projection_hash", sa.String(71), nullable=True),
        sa.Column("supersedes_version_id", _uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_number >= 1", name="ck_artifact_versions_version_positive"
        ),
        sa.CheckConstraint(
            "source_mode IN ('fixture','live','cached')",
            name="ck_artifact_versions_source_mode",
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id", "project_id"],
            ["research_artifacts.id", "research_artifacts.project_id"],
            name="fk_artifact_version_artifact_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_artifact_version_run_project",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["research_projects.id"],
            name="fk_artifact_versions_project_id_research_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_step_id", "created_by_run_id"],
            ["run_steps.id", "run_steps.run_id"],
            name="fk_artifact_version_step_run",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["step_attempt_id", "run_step_id"],
            ["step_attempts.id", "step_attempts.run_step_id"],
            name="fk_artifact_version_attempt_step",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["producer_execution_id", "run_step_id"],
            ["producer_executions.id", "producer_executions.run_step_id"],
            name="fk_artifact_version_producer_step",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id", "artifact_id"],
            ["artifact_versions.id", "artifact_versions.artifact_id"],
            name="fk_artifact_version_supersedes_same_artifact",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_artifact_versions"),
        sa.UniqueConstraint(
            "id", "artifact_id", name="uq_artifact_version_id_artifact"
        ),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_artifact_version_id_project"
        ),
        sa.UniqueConstraint(
            "artifact_id", "version_number", name="uq_artifact_version_number"
        ),
        sa.UniqueConstraint(
            "artifact_id", "publication_key", name="uq_artifact_publication_key"
        ),
    )
    op.create_index(
        "ix_artifact_versions_created_by_run_id",
        "artifact_versions",
        ["created_by_run_id"],
    )
    op.create_index(
        "ix_artifact_versions_run_step_id", "artifact_versions", ["run_step_id"]
    )
    op.create_index(
        "ix_artifact_versions_step_attempt_id",
        "artifact_versions",
        ["step_attempt_id"],
    )
    op.create_index(
        "ix_artifact_versions_producer_execution_id",
        "artifact_versions",
        ["producer_execution_id"],
    )
    op.create_foreign_key(
        "fk_research_artifacts_latest_version_same_artifact",
        "research_artifacts",
        "artifact_versions",
        ["latest_version_id", "id"],
        ["id", "artifact_id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "dataset_row_projections",
        sa.Column("artifact_version_id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("row_id", sa.String(256), nullable=False),
        sa.Column("row", _jsonb(), nullable=False),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"],
            ["artifact_versions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("artifact_version_id", "row_id"),
    )
    op.create_index(
        "ix_dataset_row_projection_project_version",
        "dataset_row_projections",
        ["project_id", "artifact_version_id"],
    )

    op.create_table(
        "source_snapshots",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("query", _jsonb(), nullable=False),
        sa.Column("query_hash", sa.String(71), nullable=False),
        sa.Column("source_version_or_etag", sa.String(256), nullable=True),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("cache_version", sa.String(128), nullable=True),
        sa.Column("request_metadata", _jsonb(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_source_snapshot_id_project"
        ),
    )
    op.create_index(
        "ix_source_snapshots_project_retrieved",
        "source_snapshots",
        ["project_id", "retrieved_at"],
    )

    op.create_table(
        "evidence",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("artifact_version_id", _uuid(), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(128), nullable=False),
        sa.Column("evidence_type", sa.String(64), nullable=False),
        sa.Column("source_snapshot_id", _uuid(), nullable=False),
        sa.Column("paper_id", sa.String(128), nullable=True),
        sa.Column("locator", _jsonb(), nullable=False),
        sa.Column("quote_or_value", _jsonb(), nullable=True),
        sa.Column("extraction_method", sa.String(128), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("is_restricted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_evidence_confidence_range"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id", "project_id"],
            ["artifact_versions.id", "artifact_versions.project_id"],
            name="fk_evidence_version_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_evidence_snapshot_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "project_id", name="uq_evidence_id_project"),
    )
    op.create_index(
        "ix_evidence_artifact_version_id", "evidence", ["artifact_version_id"]
    )
    op.create_index(
        "ix_evidence_source_snapshot_id", "evidence", ["source_snapshot_id"]
    )

    op.create_table(
        "research_input_contents",
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("storage_ref", sa.String(160), nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("project_id", "content_hash"),
        sa.CheckConstraint(
            "size_bytes >= 0", name="ck_research_input_content_size_nonneg"
        ),
    )

    op.create_table(
        "research_inputs",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(71), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_snapshot_id", _uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "content_hash"],
            ["research_input_contents.project_id", "research_input_contents.content_hash"],
            name="fk_research_input_content",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_research_input_snapshot_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "project_id", name="uq_research_input_id_project"
        ),
        sa.CheckConstraint(
            "type IN ('url','pdf','csv','json','image','text')",
            name="ck_research_inputs_input_type",
        ),
        sa.CheckConstraint(
            "source_type IN ('upload','url_fetch','text')",
            name="ck_research_inputs_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('accepted','unsupported_processing','failed_ingestion')",
            name="ck_research_inputs_input_status",
        ),
    )
    op.create_index(
        "ix_research_inputs_session_project",
        "research_inputs",
        ["session_id", "project_id"],
    )
    op.create_index(
        "ix_research_inputs_session_content",
        "research_inputs",
        ["session_id", "content_hash"],
    )

    op.create_table(
        "research_input_idempotency",
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(71), nullable=False),
        sa.Column("input_id", _uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_research_input_idempotency_input_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "session_id",
            "project_id",
            "idempotency_key",
            name="pk_research_input_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed')",
            name="ck_research_input_idempotency_status",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND input_id IS NULL"
            " AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)"
            " OR (status = 'completed' AND input_id IS NOT NULL"
            " AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_research_input_idempotency_status_lease",
        ),
    )
    op.create_index(
        "ix_research_input_idempotency_input",
        "research_input_idempotency",
        ["input_id"],
    )

    op.create_table(
        "research_input_bindings",
        sa.Column("input_id", _uuid(), nullable=False),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("contract_draft_id", _uuid(), nullable=True),
        sa.Column("run_id", _uuid(), nullable=True),
        sa.Column(
            "bound_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["input_id", "project_id"],
            ["research_inputs.id", "research_inputs.project_id"],
            name="fk_research_input_binding_input_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["research_projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["contract_draft_id", "project_id"],
            ["research_contract_drafts.id", "research_contract_drafts.project_id"],
            name="fk_research_input_binding_draft_project",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "project_id"],
            ["research_runs.id", "research_runs.project_id"],
            name="fk_research_input_binding_run_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("input_id"),
        sa.CheckConstraint(
            "(contract_draft_id IS NULL) <> (run_id IS NULL)",
            name="ck_research_input_bindings_binding_target_xor",
        ),
    )

    op.execute(
        """
        CREATE FUNCTION enforce_frozen_run_steps() RETURNS trigger AS $$
        DECLARE
            frozen_at timestamptz;
            target_run_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                target_run_id := NEW.run_id;
            ELSE
                target_run_id := OLD.run_id;
            END IF;

            SELECT steps_frozen_at INTO frozen_at
            FROM research_runs
            WHERE id = target_run_id;

            IF frozen_at IS NULL THEN
                IF TG_OP = 'DELETE' THEN
                    RETURN OLD;
                END IF;
                RETURN NEW;
            END IF;

            IF TG_OP = 'INSERT' OR TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'RunStep collection is frozen for run %', target_run_id
                    USING ERRCODE = '23514';
            END IF;

            IF ROW(
                NEW.run_id, NEW.position, NEW.key, NEW.label,
                NEW.enter_status, NEW.success_status, NEW.max_attempts
            ) IS DISTINCT FROM ROW(
                OLD.run_id, OLD.position, OLD.key, OLD.label,
                OLD.enter_status, OLD.success_status, OLD.max_attempts
            ) THEN
                RAISE EXCEPTION 'RunStep definition is frozen for run %', target_run_id
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_run_steps_frozen
        BEFORE INSERT OR UPDATE OR DELETE ON run_steps
        FOR EACH ROW EXECUTE FUNCTION enforce_frozen_run_steps();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_run_steps_frozen ON run_steps")
    op.execute("DROP FUNCTION IF EXISTS enforce_frozen_run_steps()")
    op.drop_table("research_input_bindings")
    op.drop_index(
        "ix_research_input_idempotency_input",
        table_name="research_input_idempotency",
    )
    op.drop_table("research_input_idempotency")
    op.drop_index("ix_research_inputs_session_content", table_name="research_inputs")
    op.drop_index("ix_research_inputs_session_project", table_name="research_inputs")
    op.drop_table("research_inputs")
    op.drop_table("research_input_contents")
    op.drop_index("ix_evidence_source_snapshot_id", table_name="evidence")
    op.drop_index("ix_evidence_artifact_version_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(
        "ix_source_snapshots_project_retrieved", table_name="source_snapshots"
    )
    op.drop_table("source_snapshots")
    op.drop_index(
        "ix_dataset_row_projection_project_version",
        table_name="dataset_row_projections",
    )
    op.drop_table("dataset_row_projections")
    op.drop_constraint(
        "fk_research_artifacts_latest_version_same_artifact",
        "research_artifacts",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_artifact_versions_producer_execution_id",
        table_name="artifact_versions",
    )
    op.drop_index(
        "ix_artifact_versions_step_attempt_id", table_name="artifact_versions"
    )
    op.drop_index("ix_artifact_versions_run_step_id", table_name="artifact_versions")
    op.drop_index(
        "ix_artifact_versions_created_by_run_id", table_name="artifact_versions"
    )
    op.drop_table("artifact_versions")
    op.drop_index(
        "ix_producer_executions_step_attempt_id",
        table_name="producer_executions",
    )
    op.drop_table("producer_executions")
    op.drop_table("research_artifacts")
    op.drop_index("ix_run_events_run_occurred", table_name="run_events")
    op.drop_table("run_events")
    op.drop_table("step_attempts")
    op.drop_table("run_steps")
    op.drop_table("research_runs")
    op.drop_table("research_contracts")
    op.drop_index(
        "ix_research_contract_drafts_session_id",
        table_name="research_contract_drafts",
    )
    op.drop_table("research_contract_drafts")
    op.drop_index("ix_research_projects_session_id", table_name="research_projects")
    op.drop_table("research_projects")
