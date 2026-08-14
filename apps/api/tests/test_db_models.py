
"""Static contract tests for the PostgreSQL workflow model baseline."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.base import Base
from app.db import models  # noqa: F401


def _unique_columns(table_name: str) -> set[tuple[str, ...]]:
    table = Base.metadata.tables[table_name]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_workflow_tables_and_unique_invariants_are_declared() -> None:
    assert {
        "research_runs",
        "run_steps",
        "step_attempts",
        "run_events",
        "research_artifacts",
        "artifact_versions",
        "producer_executions",
        "user_feedback",
        "revision_plans",
        "revision_plan_feedback",
        "revision_plan_versions",
        "revision_plan_confirmations",
        "cache_records",
        "cache_selection_audits",
    } <= set(Base.metadata.tables)
    assert ("project_id", "idempotency_key") in _unique_columns("research_runs")
    assert ("run_id", "key") in _unique_columns("run_steps")
    assert ("run_id", "position") in _unique_columns("run_steps")
    assert ("run_step_id", "attempt_number") in _unique_columns("step_attempts")
    assert ("run_id", "sequence") in _unique_columns("run_events")
    assert ("artifact_id", "version_number") in _unique_columns("artifact_versions")
    assert ("id", "artifact_id", "project_id") in _unique_columns("artifact_versions")
    assert ("project_id", "idempotency_key") in _unique_columns("user_feedback")
    assert ("project_id", "idempotency_key") in _unique_columns("revision_plans")
    assert ("revision_plan_id", "position") in _unique_columns("revision_plan_feedback")
    assert ("revision_plan_id", "position") in _unique_columns("revision_plan_versions")
    assert ("run_step_id", "idempotency_key") in _unique_columns("producer_executions")
    assert ("project_id", "record_hash") in _unique_columns("cache_records")
    assert ("run_step_id", "request_hash") in _unique_columns(
        "cache_selection_audits"
    )


def test_document_parse_internal_tables_and_identity_are_declared() -> None:
    assert {"document_parses", "document_parse_locators"} <= set(
        Base.metadata.tables
    )
    assert ("project_id", "identity_hash") in _unique_columns("document_parses")
    assert ("document_parse_id", "locator_hash") in _unique_columns(
        "document_parse_locators"
    )
    assert "content" not in Base.metadata.tables["document_parses"].columns
    assert "payload_storage_ref" in Base.metadata.tables["document_parses"].columns


def test_models_compile_to_postgresql_uuid_jsonb_and_timestamptz() -> None:
    dialect = postgresql.dialect()
    version_sql = str(CreateTable(Base.metadata.tables["artifact_versions"]).compile(dialect=dialect))
    run_sql = str(CreateTable(Base.metadata.tables["research_runs"]).compile(dialect=dialect))
    assert "UUID" in version_sql
    assert "JSONB" in version_sql
    assert "TIMESTAMP WITH TIME ZONE" in version_sql
    assert "ck_artifact_versions_source_mode" in version_sql
    assert "ck_research_runs_status" in run_sql
    assert "lease_generation" in run_sql
    assert "lease_expires_at" in run_sql
    assert "steps_frozen_at" in run_sql
    step_sql = str(
        CreateTable(Base.metadata.tables["run_steps"]).compile(dialect=dialect)
    )
    assert "ck_run_steps_enter_status" in step_sql
    assert "ck_run_steps_success_status" in step_sql
    assert "ck_run_steps_status" in step_sql
    assert "ck_run_steps_canonical_transition" not in step_sql


def test_every_stable_text_state_has_a_database_check_constraint() -> None:
    for table_name in (
        "research_runs",
        "run_steps",
        "step_attempts",
        "producer_executions",
        "artifact_versions",
        "cache_selection_audits",
    ):
        constraints = Base.metadata.tables[table_name].constraints
        assert any(isinstance(item, CheckConstraint) for item in constraints), table_name


def test_artifact_version_reverse_lookup_paths_are_indexed() -> None:
    indexes = {
        tuple(column.name for column in index.columns)
        for index in Base.metadata.tables["artifact_versions"].indexes
    }
    assert {
        ("created_by_run_id",),
        ("run_step_id",),
        ("step_attempt_id",),
        ("producer_execution_id",),
    } <= indexes
