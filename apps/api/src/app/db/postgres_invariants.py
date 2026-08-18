"""PostgreSQL invariants that are part of the current schema contract.

Tables, keys and checks are declared by ``app.db.models``.  PostgreSQL
triggers live here because they are behavioural invariants rather than schema
shape, and keeping them next to the schema bootstrap avoids a second history
that can drift from the current models.
"""

from __future__ import annotations

from sqlalchemy import Connection, text


def _replace_trigger(
    connection: Connection,
    *,
    name: str,
    table: str,
    events: str,
    function: str,
) -> None:
    connection.execute(text(f"DROP TRIGGER IF EXISTS {name} ON {table}"))
    connection.execute(
        text(
            f"CREATE TRIGGER {name} {events} ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function}()"
        )
    )


def install_postgres_invariants(connection: Connection) -> None:
    """Install the current PostgreSQL trigger invariants idempotently."""

    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION reject_revision_record_update()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'feedback and revision records are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in (
        "user_feedback",
        "revision_plans",
        "revision_plan_feedback",
        "revision_plan_versions",
        "revision_plan_confirmations",
    ):
        _replace_trigger(
            connection,
            name=f"trg_{table}_immutable",
            table=table,
            events="BEFORE UPDATE",
            function="reject_revision_record_update",
        )

    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION reject_paper_candidate_input_binding_update()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'paper candidate input bindings are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    _replace_trigger(
        connection,
        name="trg_paper_candidate_input_bindings_immutable",
        table="paper_candidate_input_bindings",
        events="BEFORE UPDATE",
        function="reject_paper_candidate_input_binding_update",
    )

    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION reject_document_parse_update()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'document parse records are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in ("document_parses", "document_parse_locators"):
        _replace_trigger(
            connection,
            name=f"trg_{table}_immutable",
            table=table,
            events="BEFORE UPDATE",
            function="reject_document_parse_update",
        )

    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION reject_cache_record_update()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'cache records are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table in ("cache_records", "cache_selection_audits"):
        _replace_trigger(
            connection,
            name=f"trg_{table}_immutable",
            table=table,
            events="BEFORE UPDATE",
            function="reject_cache_record_update",
        )

    connection.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION enforce_frozen_run_steps()
            RETURNS trigger AS $$
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
            $$ LANGUAGE plpgsql
            """
        )
    )
    connection.execute(text("DROP TRIGGER IF EXISTS trg_run_steps_frozen ON run_steps"))
    connection.execute(
        text(
            """
            CREATE TRIGGER trg_run_steps_frozen
            BEFORE INSERT OR UPDATE OR DELETE ON run_steps
            FOR EACH ROW EXECUTE FUNCTION enforce_frozen_run_steps()
            """
        )
    )
