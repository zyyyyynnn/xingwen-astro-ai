"""add workflow lease and frozen step execution metadata

Revision ID: 20260722_0002
Revises: 20260721_0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0002"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "research_runs", sa.Column("lease_owner", sa.String(128), nullable=True)
    )
    op.add_column(
        "research_runs",
        sa.Column(
            "lease_generation", sa.BigInteger(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "research_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "research_runs",
        sa.Column("steps_frozen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_research_runs_lease_generation_nonnegative",
        "research_runs",
        "lease_generation >= 0",
    )
    op.create_check_constraint(
        "ck_research_runs_lease_fields_complete",
        "research_runs",
        "(lease_token IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) OR "
        "(lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
    )
    op.alter_column("research_runs", "lease_generation", server_default=None)

    op.add_column("run_steps", sa.Column("position", sa.Integer(), nullable=True))
    op.add_column("run_steps", sa.Column("enter_status", sa.String(32), nullable=True))
    op.add_column(
        "run_steps", sa.Column("success_status", sa.String(32), nullable=True)
    )
    op.add_column(
        "run_steps",
        sa.Column("max_attempts", sa.Integer(), server_default="1", nullable=False),
    )
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, row_number() OVER (
                    PARTITION BY run_id ORDER BY created_at, id
                ) - 1 AS position
                FROM run_steps
            )
            UPDATE run_steps
            SET position = ordered.position,
                enter_status = CASE key
                    WHEN 'planning' THEN 'planning'
                    WHEN 'fetching_data' THEN 'fetching_data'
                    WHEN 'cleaning_data' THEN 'cleaning_data'
                    WHEN 'searching_papers' THEN 'searching_papers'
                    WHEN 'summarizing_papers' THEN 'summarizing_papers'
                    WHEN 'reasoning_literature' THEN 'reasoning_literature'
                    WHEN 'building_graph' THEN 'building_graph'
                    ELSE 'planning'
                END,
                success_status = CASE key
                    WHEN 'planning' THEN 'fetching_data'
                    WHEN 'fetching_data' THEN 'cleaning_data'
                    WHEN 'cleaning_data' THEN 'searching_papers'
                    WHEN 'searching_papers' THEN 'summarizing_papers'
                    WHEN 'summarizing_papers' THEN 'reasoning_literature'
                    WHEN 'reasoning_literature' THEN 'building_graph'
                    WHEN 'building_graph' THEN 'completed'
                    ELSE 'fetching_data'
                END
            FROM ordered
            WHERE run_steps.id = ordered.id
            """
        )
    )
    op.alter_column("run_steps", "position", nullable=False)
    op.alter_column("run_steps", "enter_status", nullable=False)
    op.alter_column("run_steps", "success_status", nullable=False)
    op.alter_column("run_steps", "max_attempts", server_default=None)
    op.create_unique_constraint(
        "uq_run_step_position", "run_steps", ["run_id", "position"]
    )
    op.create_check_constraint(
        "ck_run_steps_position_nonnegative", "run_steps", "position >= 0"
    )
    op.create_check_constraint(
        "ck_run_steps_max_attempts_positive", "run_steps", "max_attempts >= 1"
    )
    op.create_check_constraint(
        "ck_run_steps_enter_status",
        "run_steps",
        "enter_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
        "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input')",
    )
    op.create_check_constraint(
        "ck_run_steps_success_status",
        "run_steps",
        "success_status IN ('planning','fetching_data','cleaning_data','searching_papers',"
        "'summarizing_papers','reasoning_literature','building_graph','waiting_for_input',"
        "'completed')",
    )
    op.create_check_constraint(
        op.f("ck_run_steps_canonical_transition"),
        "run_steps",
        "(enter_status = 'planning' AND success_status = 'fetching_data') OR "
        "(enter_status = 'fetching_data' AND success_status = 'cleaning_data') OR "
        "(enter_status = 'cleaning_data' AND success_status = 'searching_papers') OR "
        "(enter_status = 'searching_papers' AND success_status = 'summarizing_papers') OR "
        "(enter_status = 'summarizing_papers' AND success_status = 'reasoning_literature') OR "
        "(enter_status = 'reasoning_literature' AND success_status = 'building_graph') OR "
        "(enter_status = 'building_graph' AND success_status = 'completed')",
    )
    op.execute(
        sa.text(
            "UPDATE research_runs SET steps_frozen_at = CURRENT_TIMESTAMP "
            "WHERE steps_frozen_at IS NULL"
        )
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
    op.drop_constraint(
        op.f("ck_run_steps_canonical_transition"), "run_steps", type_="check"
    )
    op.drop_constraint("ck_run_steps_success_status", "run_steps", type_="check")
    op.drop_constraint("ck_run_steps_enter_status", "run_steps", type_="check")
    op.drop_constraint("ck_run_steps_max_attempts_positive", "run_steps", type_="check")
    op.drop_constraint("ck_run_steps_position_nonnegative", "run_steps", type_="check")
    op.drop_constraint("uq_run_step_position", "run_steps", type_="unique")
    op.drop_column("run_steps", "max_attempts")
    op.drop_column("run_steps", "success_status")
    op.drop_column("run_steps", "enter_status")
    op.drop_column("run_steps", "position")

    op.drop_constraint(
        "ck_research_runs_lease_fields_complete", "research_runs", type_="check"
    )
    op.drop_constraint(
        "ck_research_runs_lease_generation_nonnegative", "research_runs", type_="check"
    )
    op.drop_column("research_runs", "lease_expires_at")
    op.drop_column("research_runs", "steps_frozen_at")
    op.drop_column("research_runs", "lease_generation")
    op.drop_column("research_runs", "lease_owner")
    op.drop_column("research_runs", "lease_token")
