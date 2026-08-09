"""Public authoring chain idempotent-replay identity.

Revision ID: 20260728_0006
Revises: 20260722_0005
Create Date: 2026-07-28

`createResearchProject` and `createResearchContractDraft` reuse the existing
Idempotency-Key replay-or-409 convention from contract confirm and run create,
which requires persisting the key and the canonical request hash. Both column
additions are nullable so pre-existing rows (seeded before the public
authoring chain existed) remain valid; PostgreSQL unique constraints ignore
NULL keys.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260728_0006"
down_revision = "20260722_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "research_projects",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "research_projects",
        sa.Column("request_hash", sa.String(length=71), nullable=True),
    )
    op.create_unique_constraint(
        "uq_research_project_idempotency",
        "research_projects",
        ["session_id", "idempotency_key"],
    )
    op.add_column(
        "research_contract_drafts",
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "research_contract_drafts",
        sa.Column("request_hash", sa.String(length=71), nullable=True),
    )
    op.create_unique_constraint(
        "uq_research_contract_draft_idempotency",
        "research_contract_drafts",
        ["session_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_research_contract_draft_idempotency",
        "research_contract_drafts",
        type_="unique",
    )
    op.drop_column("research_contract_drafts", "request_hash")
    op.drop_column("research_contract_drafts", "idempotency_key")
    op.drop_constraint(
        "uq_research_project_idempotency",
        "research_projects",
        type_="unique",
    )
    op.drop_column("research_projects", "request_hash")
    op.drop_column("research_projects", "idempotency_key")
