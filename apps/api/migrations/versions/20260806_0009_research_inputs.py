"""Research Input ingestion tables (#176, B-19).

Revision ID: 20260806_0009
Revises: 20260804_0008
Create Date: 2026-08-06

`research_inputs` stores immutable content *references* (content hash, storage
ref, metadata) ownership-scoped by the anonymous session; the bytes themselves
live in the content-addressed local store and are never owned by a table.
`expires_at` doubles as the soft-delete marker.

`research_input_idempotency` keeps HTTP request identity separate from content
identity: content dedup is `(session_id, project_id, content_hash)` on
`research_inputs`, while replay of a specific HTTP request is
`(session_id, project_id, idempotency_key)` here. Several keys may therefore
resolve to the same immutable input, and a `pending` reservation lets a URL
replay be decided before any network fetch is issued.

`research_input_bindings` records one active binding from an input reference to
a ContractDraft or Run so composer-bound inputs keep provenance without copying
binary content into public DTOs.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260806_0009"
down_revision = "20260804_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("storage_ref", sa.String(length=160), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=127), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["source_snapshot_id", "project_id"],
            ["source_snapshots.id", "source_snapshots.project_id"],
            name="fk_research_input_snapshot_project",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "project_id",
            "content_hash",
            name="uq_research_input_session_project_content",
        ),
        sa.UniqueConstraint("id", "project_id", name="uq_research_input_id_project"),
        sa.CheckConstraint(
            "type IN ('url','pdf','csv','json','image','text')", name="ck_research_inputs_input_type"
        ),
        sa.CheckConstraint(
            "source_type IN ('upload','url_fetch','text')",
            name="ck_research_inputs_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('accepted','unsupported_processing','failed_ingestion')",
            name="ck_research_inputs_input_status",
        ),
        sa.CheckConstraint("size_bytes >= 0", name="ck_research_inputs_size_nonnegative"),
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
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=71), nullable=False),
        sa.Column("input_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
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
            "(status = 'pending' AND input_id IS NULL)"
            " OR (status = 'completed' AND input_id IS NOT NULL)",
            name="ck_research_input_idempotency_status_input",
        ),
    )
    op.create_index(
        "ix_research_input_idempotency_input",
        "research_input_idempotency",
        ["input_id"],
    )

    op.create_table(
        "research_input_bindings",
        sa.Column("input_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_draft_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            ["contract_draft_id"],
            ["research_contract_drafts.id"],
            name="fk_research_input_binding_contract_draft",
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


def downgrade() -> None:
    op.drop_table("research_input_bindings")
    op.drop_index(
        "ix_research_input_idempotency_input",
        table_name="research_input_idempotency",
    )
    op.drop_table("research_input_idempotency")
    op.drop_index("ix_research_inputs_session_content", table_name="research_inputs")
    op.drop_index("ix_research_inputs_session_project", table_name="research_inputs")
    op.drop_table("research_inputs")

