"""PostgreSQL-backed integration tests for the B-19 research input store.

Gate: requires TEST_DATABASE_URL naming a database whose name contains "test"
(never touches a production database). Schema is rebuilt from Alembic on each
module run.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine

from app.db.models import (
    ResearchContractDraftModel,
    ResearchContractModel,
    ResearchInputModel,
    ResearchProjectModel,
    ResearchRunModel,
    SourceSnapshotModel,
)
from app.db.session import create_engine_from_url, session_factory
from app.main import create_app
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.research_input import ResearchInputCreate
from app.security import SecurityProblem
from app.services.research_input_store import (
    PersistentResearchInputStore,
    PreparedInput,
)
from app.services.content_storage import sha256_content_hash

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not configured"
)
NOW = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
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
def store_context(postgres_engine: Engine) -> dict[str, object]:
    factory = session_factory(postgres_engine)
    app = create_app()
    app.state.research_input_store = PersistentResearchInputStore(factory)
    owner, owner_credential, _ = app.state.session_service.create(now=NOW)
    other, other_credential, _ = app.state.session_service.create(now=NOW)
    ids = {
        name: UUID(int=index)
        for index, name in enumerate(
            (
                "project",
                "other_project",
                "contract",
                "run",
                "snapshot",
                "input",
                "input_two",
            ),
            start=1,
        )
    }
    with factory() as session, session.begin():
        session.add_all(
            [
                ResearchProjectModel(
                    id=ids["project"],
                    session_id=owner.id,
                    name="B-19 inputs",
                    case_key="exoplanet_host_star",
                    revision=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                ResearchProjectModel(
                    id=ids["other_project"],
                    session_id=other.id,
                    name="other session",
                    case_key="exoplanet_host_star",
                    revision=1,
                    created_at=NOW,
                    updated_at=NOW,
                ),
            ]
        )
    with factory() as session, session.begin():
        session.add_all(
            [
                ResearchContractModel(
                    id=ids["contract"],
                    project_id=ids["project"],
                    version=1,
                    content_hash="sha256:" + "0" * 64,
                    content={},
                    idempotency_key="test-contract-1",
                    created_at=NOW,
                ),
                ResearchContractDraftModel(
                    id=ids["contract"],
                    session_id=owner.id,
                    version=1,
                    intent="seed draft",
                    status="draft",
                    contract={},
                    warnings=[],
                    expires_at=NOW,
                ),
            ]
        )
    with factory() as session, session.begin():
        session.add_all(
            [
                ResearchRunModel(
                    id=ids["run"],
                    project_id=ids["project"],
                    contract_id=ids["contract"],
                    execution_mode="live",
                    derivation_kind="original",
                    status="completed",
                    cache_policy="none",
                    idempotency_key="test-run-1",
                    request_hash="sha256:" + "1" * 64,
                    created_at=NOW,
                ),
                SourceSnapshotModel(
                    id=ids["snapshot"],
                    project_id=ids["project"],
                    source_id="url_example.com",
                    source_type="url_fetch",
                    retrieved_at=NOW,
                    query="https://example.com/data.csv",
                    query_hash="sha256:" + "2" * 64,
                    content_hash="sha256:" + "3" * 64,
                    license_note="fetched",
                    cache_version=None,
                    request_metadata={},
                ),
            ]
        )
    return {
        "app": app,
        "factory": factory,
        "owner": owner,
        "other": other,
        "ids": ids,
    }


def _prepared(
    *,
    content: bytes = b"persisted payload",
    source: SourceSnapshotRecord | None = None,
) -> PreparedInput:
    return PreparedInput(
        content_hash=sha256_content_hash(content),
        storage_ref="aa/bb",
        size_bytes=len(content),
        mime_type="text/plain",
        filename="notes.txt",
        source_snapshot=source,
    )


def _create(
    store: PersistentResearchInputStore,
    ctx: dict[str, object],
    *,
    project_key: str = "project",
    content: bytes = b"persisted payload",
    source: SourceSnapshotRecord | None = None,
) -> object:
    return store.create(
        session_id=ctx["owner"].id,
        project_id=str(ctx["ids"][project_key]),
        payload=ResearchInputCreate(type="text", text_content="persisted payload"),
        prepared=_prepared(content=content, source=source),
    )


def _store(ctx: dict[str, object]) -> PersistentResearchInputStore:
    return PersistentResearchInputStore(ctx["factory"])  # type: ignore[arg-type]


def test_persistent_store_round_trips_and_scopes_to_session(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    factory = ctx["factory"]
    store = _store(ctx)

    created = _create(store, ctx)
    assert UUID(created.id)  # raw UUID string, matching the house id style

    fetched = store.get(session_id=ctx["owner"].id, input_id=created.id)
    assert fetched is not None
    assert fetched.content_hash.startswith("sha256:")
    assert fetched.filename == "notes.txt"
    assert fetched.status.value == "accepted"

    foreign = store.get(session_id=ctx["other"].id, input_id=created.id)
    assert foreign is None

    row = ctx["ids"]["project"]
    with factory() as session:  # type: ignore[attr-defined]
        persisted = session.get(ResearchInputModel, UUID(created.id))
    assert persisted is not None
    assert persisted.project_id == row
    assert persisted.session_id == ctx["owner"].id


def test_persistent_store_replays_identical_content_within_session(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    first = _create(store, ctx, content=b"replay me")
    second = _create(store, ctx, content=b"replay me")
    assert second.id == first.id


def test_persistent_store_hides_foreign_project(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    with pytest.raises(SecurityProblem) as exc:
        store.create(
            session_id=ctx["owner"].id,
            project_id=str(ctx["ids"]["other_project"]),
            payload=ResearchInputCreate(type="text", text_content="sneak"),
            prepared=_prepared(content=b"sneak"),
        )
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_persistent_store_soft_delete_and_resurrection(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    created = _create(store, ctx, content=b"delete me")
    store.delete(session_id=ctx["owner"].id, input_id=created.id)
    assert store.get(session_id=ctx["owner"].id, input_id=created.id) is None

    resurrected = _create(store, ctx, content=b"delete me")
    assert resurrected.id == created.id
    assert store.get(session_id=ctx["owner"].id, input_id=created.id) is not None


def test_persistent_store_binds_only_owned_targets(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    created = _create(store, ctx, content=b"bind me")

    store.bind_to_contract(
        session_id=ctx["owner"].id,
        input_id=created.id,
        project_id=str(ctx["ids"]["project"]),
        contract_draft_id=str(ctx["ids"]["contract"]),
    )
    store.bind_to_run(
        session_id=ctx["owner"].id,
        input_id=created.id,
        project_id=str(ctx["ids"]["project"]),
        run_id=str(ctx["ids"]["run"]),
    )

    with pytest.raises(SecurityProblem) as exc:
        store.bind_to_run(
            session_id=ctx["other"].id,
            input_id=created.id,
            project_id=str(ctx["ids"]["project"]),
            run_id=str(ctx["ids"]["run"]),
        )
    assert exc.value.code == "RESEARCH_INPUT_NOT_FOUND"


def test_persistent_store_keeps_snapshot_provenance_for_url_inputs(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    snapshot = SourceSnapshotRecord(
        snapshot_id="snap_1a2b3c4d5e6f",
        source_id="url_example.com",
        source_type="url_fetch",
        retrieved_at=NOW,
        query="https://example.com/data.csv",
        query_hash="sha256:" + "3" * 64,
        content_hash="sha256:" + "4" * 64,
        license_note="fetched",
        request_metadata={"status_code": 200},
    )
    created = _create(store, ctx, content=b"url payload", source=snapshot)
    assert created.source_snapshot_id is not None
    detail = store.get(session_id=ctx["owner"].id, input_id=created.id)
    assert detail is not None
    assert detail.url == "https://example.com/data.csv"
