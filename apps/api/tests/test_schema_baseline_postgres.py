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
        "research_thread_entries",
        "run_events",
        "run_steps",
        "source_snapshots",
        "step_attempts",
    }
)
CURRENT_REQUIRED_COLUMNS = {
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
