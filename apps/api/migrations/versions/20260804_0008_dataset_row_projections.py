"""Persist version-pinned Dataset row projections for bounded reads."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260804_0008"
down_revision = "20260804_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_row_projections",
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_id", sa.String(length=256), nullable=False),
        sa.Column("row", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["artifact_version_id"], ["artifact_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["research_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("artifact_version_id", "row_id"),
    )
    op.create_index(
        "ix_dataset_row_projection_project_version",
        "dataset_row_projections",
        ["project_id", "artifact_version_id"],
    )
    op.execute(
        """
        INSERT INTO dataset_row_projections (artifact_version_id, project_id, row_id, row)
        SELECT av.id, av.project_id, row->>'row_id', row
        FROM artifact_versions AS av
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(av.content->'rows', '[]'::jsonb)) AS row
        WHERE av.content->>'kind' = 'dataset'
          AND jsonb_typeof(row) = 'object'
          AND NULLIF(row->>'row_id', '') IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_row_projection_project_version", table_name="dataset_row_projections")
    op.drop_table("dataset_row_projections")
