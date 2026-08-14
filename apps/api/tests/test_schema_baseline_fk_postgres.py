"""Database-level immutability guard for the current ArtifactVersion pointer."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import inspect

from app.db.session import create_engine_from_url


def test_latest_artifact_version_foreign_key_restricts_deletion() -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if "test" not in database_url.lower():
        pytest.fail("TEST_DATABASE_URL must identify an isolated test database")

    engine = create_engine_from_url(database_url)
    try:
        foreign_keys = inspect(engine).get_foreign_keys("research_artifacts")
        latest_version_fk = next(
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key["name"]
            == "fk_research_artifacts_latest_version_same_artifact"
        )
        assert latest_version_fk["referred_table"] == "artifact_versions"
        assert latest_version_fk["constrained_columns"] == ["latest_version_id", "id"]
        assert latest_version_fk["referred_columns"] == ["id", "artifact_id"]
        assert latest_version_fk["options"].get("ondelete") == "RESTRICT"
    finally:
        engine.dispose()


@pytest.mark.parametrize("table", ("workspace_snapshots", "share_snapshots"))
def test_snapshot_foreign_keys_bind_project_and_session_owner(table: str) -> None:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    if "test" not in database_url.lower():
        pytest.fail("TEST_DATABASE_URL must identify an isolated test database")

    engine = create_engine_from_url(database_url)
    try:
        foreign_keys = inspect(engine).get_foreign_keys(table)
        owner_fk = next(
            foreign_key
            for foreign_key in foreign_keys
            if foreign_key["referred_table"] == "research_projects"
        )
        assert owner_fk["constrained_columns"] == [
            "project_id",
            "owner_session_id",
        ]
        assert owner_fk["referred_columns"] == ["id", "session_id"]
        assert owner_fk["options"].get("ondelete") == "CASCADE"
    finally:
        engine.dispose()
