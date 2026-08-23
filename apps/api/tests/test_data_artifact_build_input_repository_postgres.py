"""PostgreSQL coverage for immutable Data Artifact build-input replay."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from app.db.models import DataArtifactBuildInputRecordModel
from app.db.session import create_engine_from_url, session_factory
from app.services.data_artifact_build_inputs import (
    DataArtifactBuildInputReplayError,
    DataArtifactBuildInputRepository,
)
from authoring_test_support import build_research_project, persist_authoring_models
from data_artifact_test_support import build_input
from db_bootstrap import reset_current_schema


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)


def test_build_input_record_is_unique_replayable_and_tamper_evident() -> None:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower()
    reset_current_schema(TEST_DATABASE_URL)
    engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    project = build_research_project(
        project_id=uuid4(),
        session_id="data-build-input-replay-owner",
        name="Data build input replay",
        case_key="exoplanet_host_star",
    )
    input_value = build_input("star.tic_id")

    try:
        with factory() as session, session.begin():
            persist_authoring_models(session, project=project)

        repository = DataArtifactBuildInputRepository(factory)
        repository.put(project_id=project.id, input_value=input_value)
        repository.put(project_id=project.id, input_value=input_value)

        replayed = repository.get(
            project_id=project.id,
            input_hash=input_value.input_hash,
        )
        assert replayed == input_value

        with pytest.raises(DatabaseError, match="immutable"):
            with factory() as session, session.begin():
                row = session.get(
                    DataArtifactBuildInputRecordModel,
                    (project.id, input_value.input_hash),
                )
                assert row is not None
                row.payload = {**row.payload, "producer_version": "9.9.9"}

        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE data_artifact_build_inputs "
                    "DISABLE TRIGGER trg_data_artifact_build_inputs_immutable"
                )
            )
            connection.execute(
                text(
                    "UPDATE data_artifact_build_inputs "
                    "SET payload = jsonb_set("
                    "payload, '{producer_version}', to_jsonb('9.9.9'::text)) "
                    "WHERE project_id = :project_id AND input_hash = :input_hash"
                ),
                {"project_id": project.id, "input_hash": input_value.input_hash},
            )
            connection.execute(
                text(
                    "ALTER TABLE data_artifact_build_inputs "
                    "ENABLE TRIGGER trg_data_artifact_build_inputs_immutable"
                )
            )

        with pytest.raises(
            DataArtifactBuildInputReplayError,
            match="DATA_ARTIFACT_BUILD_INPUT_NOT_REPLAYABLE",
        ):
            repository.get(
                project_id=project.id,
                input_hash=input_value.input_hash,
            )
    finally:
        engine.dispose()
        reset_current_schema(TEST_DATABASE_URL)
