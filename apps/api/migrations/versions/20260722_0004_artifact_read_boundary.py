"""Add Evidence and SourceSnapshot persistence for the Artifact read boundary.

Revision ID: 20260722_0004
Revises: 20260722_0003
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260722_0004"
down_revision = "20260722_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_artifact_version_id_project",
        "artifact_versions",
        ["id", "project_id"],
    )
    op.create_table(
        "source_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "query", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("query_hash", sa.String(length=71), nullable=False),
        sa.Column("source_version_or_etag", sa.String(length=256), nullable=True),
        sa.Column("content_hash", sa.String(length=71), nullable=False),
        sa.Column("license_note", sa.Text(), nullable=False),
        sa.Column("cache_version", sa.String(length=128), nullable=True),
        sa.Column(
            "request_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
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
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", sa.String(length=128), nullable=True),
        sa.Column("locator", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quote_or_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_method", sa.String(length=128), nullable=False),
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


def downgrade() -> None:
    op.drop_index("ix_evidence_source_snapshot_id", table_name="evidence")
    op.drop_index("ix_evidence_artifact_version_id", table_name="evidence")
    op.drop_table("evidence")
    op.drop_index(
        "ix_source_snapshots_project_retrieved", table_name="source_snapshots"
    )
    op.drop_table("source_snapshots")
    op.drop_constraint(
        "uq_artifact_version_id_project", "artifact_versions", type_="unique"
    )
