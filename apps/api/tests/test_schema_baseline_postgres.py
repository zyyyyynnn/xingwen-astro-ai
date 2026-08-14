"""Fresh-PostgreSQL invariants for the sole active schema baseline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.db.session import create_engine_from_url


API_ROOT = Path(__file__).parents[1]
EXPECTED_TABLES = frozenset(
    {
        "alembic_version",
        "artifact_versions",
        "cache_records",
        "cache_selection_audits",
        "dataset_row_projections",
        "document_parse_locators",
        "document_parses",
        "evidence",
        "model_executions",
        "paper_candidate_input_bindings",
        "paper_candidate_input_idempotency",
        "producer_executions",
        "research_artifacts",
        "research_contract_drafts",
        "research_contracts",
        "research_input_bindings",
        "research_input_contents",
        "research_input_idempotency",
        "research_inputs",
        "research_projects",
        "research_runs",
        "research_sessions",
        "research_thread_entries",
        "run_events",
        "run_steps",
        "source_snapshots",
        "step_attempts",
        "share_snapshots",
        "workspace_snapshots",
        "user_feedback",
        "revision_plans",
        "revision_plan_feedback",
        "revision_plan_versions",
        "revision_plan_confirmations",
    }
)
CURRENT_REQUIRED_COLUMNS = {
    "research_sessions": frozenset(
        {"credential_hash", "csrf_hashes", "security_version", "quota"}
    ),
    "research_projects": frozenset({"description", "idempotency_key", "request_hash"}),
    "research_contract_drafts": frozenset({"idempotency_key", "request_hash"}),
    "research_contracts": frozenset(
        {
            "content",
            "created_from_draft_id",
            "idempotency_key",
            "request_hash",
        }
    ),
    "model_executions": frozenset(
        {
            "prompt_snapshot",
            "input_snapshot",
            "parameters_snapshot",
        }
    ),
    "workspace_snapshots": frozenset(
        {"owner_session_id", "payload", "revision", "updated_at"}
    ),
    "share_snapshots": frozenset(
        {
            "owner_session_id",
            "token_hash",
            "artifact_version_ids",
            "evidence_ids",
            "artifact_versions",
            "evidence",
        }
    ),
    "user_feedback": frozenset(
        {
            "owner_session_id",
            "baseline_artifact_version_id",
            "feedback_hash",
            "idempotency_key",
            "request_hash",
        }
    ),
    "revision_plans": frozenset(
        {
            "owner_session_id",
            "parent_run_id",
            "parent_run_revision",
            "recompute_steps",
            "plan_hash",
        }
    ),
    "revision_plan_confirmations": frozenset(
        {"owner_session_id", "run_id", "idempotency_key", "request_hash"}
    ),
    "cache_records": frozenset(
        {
            "origin_run_id",
            "origin_artifact_version_id",
            "contract_hash",
            "input_hash",
            "producer_identity_hash",
            "source_snapshot_ids",
            "source_snapshot_hash",
            "evidence_ids",
            "expires_at",
        }
    ),
    "cache_selection_audits": frozenset(
        {
            "run_id",
            "run_step_id",
            "failed_producer_execution_id",
            "request_hash",
            "outcome",
            "reason",
            "live_failure_class",
            "live_failure_code",
            "event_sequence",
        }
    ),
}


def test_migration_directory_has_one_current_root_and_head() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_bases() == ["schema_baseline"]
    assert scripts.get_heads() == ["schema_baseline"]


def test_fresh_postgres_matches_current_schema_contract() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if "test" not in database_url.lower():
        pytest.fail("TEST_DATABASE_URL must identify an isolated test database")

    engine = create_engine_from_url(database_url)
    try:
        inspector = inspect(engine)
        assert frozenset(inspector.get_table_names()) == EXPECTED_TABLES

        for table, required_columns in CURRENT_REQUIRED_COLUMNS.items():
            columns = {
                column["name"]: column for column in inspector.get_columns(table)
            }
            assert required_columns <= columns.keys()
            assert all(columns[name]["nullable"] is False for name in required_columns)
    finally:
        engine.dispose()
