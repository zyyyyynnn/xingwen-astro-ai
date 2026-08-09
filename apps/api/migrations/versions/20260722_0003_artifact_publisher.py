"""Add ProducerExecution audit fields required by the atomic publisher.

Revision ID: 20260722_0003
Revises: 20260722_0002
Create Date: 2026-07-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260722_0003"
down_revision = "20260722_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "producer_executions",
        sa.Column("step_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "producer_executions",
        sa.Column(
            "lease_generation", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.execute(
        """
        UPDATE producer_executions
        SET parameters_hash =
            'sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
        WHERE parameters_hash IS NULL
        """
    )
    op.alter_column("producer_executions", "parameters_hash", nullable=False)
    op.add_column(
        "producer_executions",
        sa.Column("model_provider", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "producer_executions",
        sa.Column("prompt_hash", sa.String(length=71), nullable=True),
    )
    op.add_column(
        "producer_executions",
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.execute(
        """
        WITH candidate_matches AS (
            SELECT
                producer.id AS producer_execution_id,
                attempt.id AS step_attempt_id,
                count(*) OVER (PARTITION BY producer.id) AS match_count
            FROM producer_executions AS producer
            JOIN step_attempts AS attempt
              ON attempt.run_step_id = producer.run_step_id
             AND attempt.started_at <= producer.started_at
             AND (
                    attempt.finished_at IS NULL
                    OR producer.started_at <= attempt.finished_at
                 )
             AND (
                    producer.finished_at IS NULL
                    OR attempt.finished_at IS NULL
                    OR producer.finished_at <= attempt.finished_at
                 )
        )
        UPDATE producer_executions AS producer
        SET step_attempt_id = candidate.step_attempt_id
        FROM candidate_matches AS candidate
        WHERE producer.id = candidate.producer_execution_id
          AND candidate.match_count = 1
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM producer_executions
                WHERE step_attempt_id IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Atomic Publisher cannot infer an unambiguous StepAttempt for every existing ProducerExecution';
            END IF;
        END
        $$
        """
    )
    op.alter_column("producer_executions", "step_attempt_id", nullable=False)
    op.create_foreign_key(
        "fk_producer_execution_attempt_step",
        "producer_executions",
        "step_attempts",
        ["step_attempt_id", "run_step_id"],
        ["id", "run_step_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_producer_executions_step_attempt_id",
        "producer_executions",
        ["step_attempt_id"],
    )
    op.drop_constraint(
        "ck_producer_executions_status",
        "producer_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_producer_executions_status",
        "producer_executions",
        "status IN ('running','completed','failed','rejected','cancelled')",
    )
    op.create_check_constraint(
        "ck_producer_executions_lease_generation_nonnegative",
        "producer_executions",
        "lease_generation >= 0",
    )
    op.alter_column("producer_executions", "lease_generation", server_default=None)
    op.alter_column("producer_executions", "parameters", server_default=None)


def downgrade() -> None:
    # The previous schema has no rejected terminal state. Preserve the failed
    # execution record while mapping it to the closest compatible status.
    op.execute(
        "UPDATE producer_executions SET status = 'failed' WHERE status = 'rejected'"
    )
    op.alter_column("producer_executions", "parameters_hash", nullable=True)
    op.drop_constraint(
        "ck_producer_executions_lease_generation_nonnegative",
        "producer_executions",
        type_="check",
    )
    op.drop_constraint(
        "ck_producer_executions_status",
        "producer_executions",
        type_="check",
    )
    op.create_check_constraint(
        "ck_producer_executions_status",
        "producer_executions",
        "status IN ('running','completed','failed','cancelled')",
    )
    op.drop_index(
        "ix_producer_executions_step_attempt_id",
        table_name="producer_executions",
    )
    op.drop_constraint(
        "fk_producer_execution_attempt_step",
        "producer_executions",
        type_="foreignkey",
    )
    op.drop_column("producer_executions", "parameters")
    op.drop_column("producer_executions", "prompt_hash")
    op.drop_column("producer_executions", "model_provider")
    op.drop_column("producer_executions", "lease_generation")
    op.drop_column("producer_executions", "step_attempt_id")
