
"""PostgreSQL migration and repository integration tests.

Set TEST_DATABASE_URL to an isolated database whose name contains ``test``.
The suite intentionally skips when PostgreSQL is unavailable rather than
silently testing PostgreSQL-specific models against SQLite.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models import (
    ArtifactVersionModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchContractModel,
    ResearchProjectModel,
    ResearchRunModel,
    RunEventModel,
    RunStepModel,
    StepAttemptModel,
)
from app.db.repositories import UnitOfWork
from app.db.session import create_engine_from_url, session_factory

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured")


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), "refusing non-test database"
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def _seed_run(engine: Engine) -> tuple[ResearchRunModel, RunStepModel]:
    factory = session_factory(engine)
    project = ResearchProjectModel(
        id=uuid4(),
        session_id="session-test", name="Test", case_key="exoplanet_host_star", revision=1
    )
    contract = ResearchContractModel(
        id=uuid4(), project_id=project.id, version=1, content_hash="sha256:" + "a" * 64
    )
    run = ResearchRunModel(
        id=uuid4(),
        project_id=project.id,
        contract_id=contract.id,
        execution_mode="live",
        status="queued",
        progress=0,
        derivation_kind="original",
        cache_policy="disabled",
        latest_event_sequence=0,
        revision=1,
        idempotency_key="run-key",
        request_hash="sha256:" + "b" * 64,
    )
    step = RunStepModel(
        id=uuid4(), run_id=run.id, position=0, key="planning", label="Planning",
        enter_status="planning", success_status="fetching_data", max_attempts=2,
        status="pending", progress=0
    )
    with UnitOfWork(factory) as uow:
        uow.session.add(project)
        uow.session.flush()
        uow.session.add(contract)
        uow.session.flush()
        uow.session.add(run)
        uow.session.flush()
        uow.session.add(step)
        uow.commit()
    return run, step


def test_upgrade_schema_matches_reviewed_metadata(postgres_engine: Engine) -> None:
    tables = set(inspect(postgres_engine).get_table_names())
    assert set(Base.metadata.tables) <= tables
    with postgres_engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []


def test_repository_create_read_unique_conflict_and_rollback(postgres_engine: Engine) -> None:
    run, step = _seed_run(postgres_engine)
    factory = session_factory(postgres_engine)
    with UnitOfWork(factory) as uow:
        assert uow.runs.get(run.id) is not None
        uow.steps.add(
            RunStepModel(
                run_id=run.id, position=1, key="planning", label="Duplicate",
                enter_status="planning", success_status="fetching_data", max_attempts=1,
                status="pending", progress=0
            )
        )
        with pytest.raises(IntegrityError):
            uow.commit()
        uow.rollback()
        event = uow.events.add(
            RunEventModel(
                run_id=run.id,
                sequence=1,
                event_type="run.queued",
                public_message="Queued",
                artifact_version_ids=[],
                occurred_at=datetime.now(UTC),
            )
        )
        uow.commit()
        assert uow.events.get(event.id) is not None


def test_database_rejects_all_version_and_sequence_duplicates(postgres_engine: Engine) -> None:
    run, step = _seed_run(postgres_engine)
    factory = session_factory(postgres_engine)

    duplicates = [
        (
            RunEventModel(
                id=uuid4(), run_id=run.id, sequence=1, event_type="run.queued",
                public_message="First", artifact_version_ids=[], occurred_at=datetime.now(UTC)
            ),
            RunEventModel(
                id=uuid4(), run_id=run.id, sequence=1, event_type="run.queued",
                public_message="Duplicate", artifact_version_ids=[], occurred_at=datetime.now(UTC)
            ),
        ),
        (
            StepAttemptModel(
                id=uuid4(), run_step_id=step.id, attempt_number=1,
                idempotency_key="attempt-a", status="running", retryable=False
            ),
            StepAttemptModel(
                id=uuid4(), run_step_id=step.id, attempt_number=1,
                idempotency_key="attempt-b", status="running", retryable=False
            ),
        ),
    ]
    for first, duplicate in duplicates:
        with UnitOfWork(factory) as uow:
            uow.session.add(first)
            uow.commit()
            uow.session.add(duplicate)
            with pytest.raises(IntegrityError):
                uow.commit()
            uow.rollback()

    with UnitOfWork(factory) as uow:
        artifact = ResearchArtifactModel(
            id=uuid4(), project_id=run.project_id, kind="dataset",
            title="Dataset", logical_key="dataset.primary"
        )
        publication_attempt = StepAttemptModel(
            id=uuid4(), run_step_id=step.id, attempt_number=2,
            idempotency_key="attempt-publication", status="completed", retryable=False
        )
        execution = ProducerExecutionModel(
            id=uuid4(),
            run_id=run.id,
            run_step_id=step.id,
            step_attempt_id=publication_attempt.id,
            step_key=step.key,
            idempotency_key="producer-1",
            lease_generation=1,
            producer_type="pipeline",
            producer_name="data",
            producer_version="1.0.0",
            parameters={},
            parameters_hash="sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
            input_hash="sha256:" + "c" * 64,
            output_hash="sha256:" + "d" * 64,
            status="completed",
            started_at=datetime.now(UTC),
        )
        uow.session.add_all([artifact, publication_attempt])
        uow.session.flush()
        uow.session.add(execution)
        uow.commit()
        common = {
            "artifact_id": artifact.id,
            "project_id": run.project_id,
            "created_by_run_id": run.id,
            "run_step_id": step.id,
            "step_attempt_id": publication_attempt.id,
            "producer_execution_id": execution.id,
            "version_number": 1,
            "schema_version": "2.0.0",
            "content": {"kind": "dataset", "field_ids": ["planet.toi_id"], "rows": []},
            "content_hash": "sha256:" + "d" * 64,
            "input_hash": "sha256:" + "c" * 64,
            "source_mode": "live",
            "producer": {"type": "pipeline", "name": "data", "version": "1.0.0"},
            "source_snapshot_ids": [],
            "evidence_ids": [],
        }
        uow.versions.add(ArtifactVersionModel(id=uuid4(), publication_key="publish-1", **common))
        uow.commit()
        uow.versions.add(ArtifactVersionModel(id=uuid4(), publication_key="publish-2", **common))
        with pytest.raises(IntegrityError):
            uow.commit()
        uow.rollback()


def test_database_rejects_foreign_key_failure(postgres_engine: Engine) -> None:
    factory = session_factory(postgres_engine)
    with UnitOfWork(factory) as uow:
        uow.events.add(
            RunEventModel(
                run_id=uuid4(),
                sequence=1,
                event_type="run.queued",
                public_message="Invalid",
                artifact_version_ids=[],
                occurred_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            uow.commit()
        uow.rollback()


def test_database_rejects_cross_project_contract_reference(postgres_engine: Engine) -> None:
    original_run, _ = _seed_run(postgres_engine)
    factory = session_factory(postgres_engine)
    other_project = ResearchProjectModel(
        id=uuid4(), session_id="session-other", name="Other",
        case_key="exoplanet_host_star", revision=1
    )
    invalid_run = ResearchRunModel(
        id=uuid4(), project_id=other_project.id, contract_id=original_run.contract_id,
        execution_mode="live", status="queued", progress=0, derivation_kind="original",
        cache_policy="disabled", latest_event_sequence=0, revision=1,
        idempotency_key="cross-project", request_hash="sha256:" + "e" * 64
    )
    with UnitOfWork(factory) as uow:
        uow.session.add(other_project)
        uow.session.flush()
        uow.runs.add(invalid_run)
        with pytest.raises(IntegrityError):
            uow.commit()
        uow.rollback()
