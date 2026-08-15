"""PostgreSQL coverage for the database-backed graph Evidence restriction port."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine, select

from app.db.models import EvidenceModel
from app.db.session import create_engine_from_url
from app.services.graph_inputs import (
    ArtifactVersionGraphInputReadAdapter,
    DatabaseEvidenceRestrictionReadAdapter,
)
from app.schemas.graph_artifact import GraphRejectionReason
from services.graph_pipeline import (
    GraphInputIntegrityError,
)
from test_artifact_publisher_postgres import _active_publication


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "localhost:15432" in TEST_DATABASE_URL, (
        "refusing a non-dedicated graph-inputs PostgreSQL endpoint"
    )
    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine_from_url(TEST_DATABASE_URL)
    yield engine
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(scope="module")
def evidence_context(postgres_engine: Engine) -> dict[str, object]:
    active = _active_publication(postgres_engine)
    foreign = _active_publication(postgres_engine)
    with active.factory() as session:
        own_rows = tuple(
            session.scalars(
                select(EvidenceModel)
                .where(EvidenceModel.project_id == active.project.id)
                .order_by(EvidenceModel.id)
            )
        )
    with foreign.factory() as session:
        foreign_rows = tuple(
            session.scalars(
                select(EvidenceModel)
                .where(EvidenceModel.project_id == foreign.project.id)
                .order_by(EvidenceModel.id)
            )
        )
    assert own_rows
    assert foreign_rows
    return {
        "active": active,
        "foreign": foreign,
        "own_ids": tuple(str(row.id) for row in own_rows),
        "foreign_ids": tuple(str(row.id) for row in foreign_rows),
    }


def _restriction_adapter(evidence_context: dict[str, object]):
    active = evidence_context["active"]
    return DatabaseEvidenceRestrictionReadAdapter(active.factory)  # type: ignore[union-attr]


def _graph_adapter(restrictions: DatabaseEvidenceRestrictionReadAdapter):
    return ArtifactVersionGraphInputReadAdapter(
        artifacts=object(),  # type: ignore[arg-type]
        session_id="owner",
        evidence_restrictions=restrictions,
    )


def test_database_restrictions_close_requested_project_and_exclude_foreign_rows(
    evidence_context: dict[str, object],
) -> None:
    active = evidence_context["active"]
    own_ids = evidence_context["own_ids"]
    foreign_ids = evidence_context["foreign_ids"]
    assert isinstance(own_ids, tuple)
    assert isinstance(foreign_ids, tuple)

    facts = _restriction_adapter(evidence_context).read_restrictions(
        project_id=str(active.project.id),  # type: ignore[union-attr]
        evidence_ids=own_ids + foreign_ids,
    )

    assert {fact.evidence_id for fact in facts} == set(own_ids)
    assert all(
        fact.project_id == str(active.project.id)  # type: ignore[union-attr]
        for fact in facts
    )
    assert not set(foreign_ids) & {fact.evidence_id for fact in facts}


def test_graph_adapter_rejects_missing_database_restriction_fact(
    evidence_context: dict[str, object],
) -> None:
    active = evidence_context["active"]
    own_ids = evidence_context["own_ids"]
    assert isinstance(own_ids, tuple) and own_ids
    missing_id = str(UUID(int=0))
    graph_adapter = _graph_adapter(_restriction_adapter(evidence_context))

    with pytest.raises(GraphInputIntegrityError) as captured:
        graph_adapter._restriction_facts(  # noqa: SLF001
            project_id=str(active.project.id),  # type: ignore[union-attr]
            evidence_ids=(own_ids[0], missing_id),
        )

    assert captured.value.reason is GraphRejectionReason.evidence_inconsistent
    assert captured.value.path == "input_versions.evidence.restrictions"


def test_graph_adapter_rejects_foreign_database_restriction_fact(
    evidence_context: dict[str, object],
) -> None:
    active = evidence_context["active"]
    own_ids = evidence_context["own_ids"]
    foreign_ids = evidence_context["foreign_ids"]
    assert isinstance(own_ids, tuple) and own_ids
    assert isinstance(foreign_ids, tuple) and foreign_ids
    graph_adapter = _graph_adapter(_restriction_adapter(evidence_context))

    with pytest.raises(GraphInputIntegrityError) as captured:
        graph_adapter._restriction_facts(  # noqa: SLF001
            project_id=str(active.project.id),  # type: ignore[union-attr]
            evidence_ids=(own_ids[0], foreign_ids[0]),
        )

    assert captured.value.reason is GraphRejectionReason.evidence_inconsistent
    assert captured.value.path == "input_versions.evidence.restrictions"
