"""Add ResearchContractDraft persistence and full frozen contract content.

Revision ID: 20260722_0005
Revises: 20260722_0004
Create Date: 2026-07-22

Adds the session-scoped ``research_contract_drafts`` table and the columns that
let an immutable ``research_contracts`` row recover its full frozen
``ResearchContractInput`` payload (not only ``content_hash``). Both column
additions are nullable so pre-existing workflow rows remain valid.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260722_0005"
down_revision = "20260722_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_contracts",
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "research_contracts",
        sa.Column(
            "created_from_draft_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
    )
    op.add_column(
        "research_contracts",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "research_contracts",
        sa.Column("request_hash", sa.String(length=71), nullable=True),
    )
    op.create_table(
        "research_contract_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "status IN ('draft','confirmed','expired')", name="draft_status"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_research_contract_drafts_session_id",
        "research_contract_drafts",
        ["session_id"],
    )
    op.create_unique_constraint(
        "uq_research_contract_idempotency",
        "research_contracts",
        ["project_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_research_contract_created_from_draft",
        "research_contracts",
        ["created_from_draft_id"],
    )
    op.create_foreign_key(
        "fk_research_contracts_created_from_draft",
        "research_contracts",
        "research_contract_drafts",
        ["created_from_draft_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_contracts_created_from_draft",
        "research_contracts",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_research_contract_created_from_draft",
        "research_contracts",
        type_="unique",
    )
    op.drop_constraint(
        "uq_research_contract_idempotency",
        "research_contracts",
        type_="unique",
    )
    op.drop_index(
        "ix_research_contract_drafts_session_id",
        table_name="research_contract_drafts",
    )
    op.drop_table("research_contract_drafts")
    op.drop_column("research_contracts", "request_hash")
    op.drop_column("research_contracts", "idempotency_key")
    op.drop_column("research_contracts", "created_from_draft_id")
    op.drop_column("research_contracts", "content")
