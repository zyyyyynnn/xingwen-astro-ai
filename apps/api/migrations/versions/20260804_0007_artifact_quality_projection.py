"""Persist the immutable data quality projection with each ArtifactVersion."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260804_0007"
down_revision = "20260728_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "artifact_versions",
        sa.Column("quality_projection", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "artifact_versions",
        sa.Column("quality_projection_hash", sa.String(length=71), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("artifact_versions", "quality_projection_hash")
    op.drop_column("artifact_versions", "quality_projection")
