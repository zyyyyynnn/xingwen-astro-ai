"""PostgreSQL concurrency and recovery tests for research-input persistence."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, select

from app.db.models import (
    ResearchInputContentModel,
    ResearchInputIdempotencyModel,
    ResearchInputModel,
    ResearchProjectModel,
)
from app.db.session import create_engine_from_url, session_factory
from authoring_test_support import build_research_project
from app.schemas.research_input import ResearchInputCreate
from app.security import SecurityProblem
from app.services.content_storage import sha256_content_hash
from app.services.research_input_store import (
    IdempotencyReservation,
    PersistentIdempotencyRepository,
    PersistentResearchInputStore,
    PreparedInput,
)

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not configured",
)


@dataclass
class MutableClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def _alembic_config(url: str) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(root / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="module")
def database() -> tuple[Engine, object, UUID, str]:
    assert TEST_DATABASE_URL is not None
    assert "test" in TEST_DATABASE_URL.rsplit("/", 1)[-1].lower(), (
        "refusing non-test database"
    )

    config = _alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine_from_url(TEST_DATABASE_URL)
    factory = session_factory(engine)
    project_id = uuid4()
    session_id = "research_input-concurrency-session"
    now = datetime(2026, 8, 7, 11, 0, tzinfo=UTC)

    with factory() as session, session.begin():
        session.add(
            build_research_project(
                project_id=project_id,
                session_id=session_id,
                name="Research Input Ingestion concurrency",
                case_key="exoplanet_host_star",
                created_at=now,
                updated_at=now,
            )
        )

    yield engine, factory, project_id, session_id

    engine.dispose()
    # Leave the shared CI test database at head for whichever module runs next.
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def _prepared(content: bytes) -> PreparedInput:
    content_hash = sha256_content_hash(content)
    hex_value = content_hash.removeprefix("sha256:")
    return PreparedInput(
        content_hash=content_hash,
        storage_ref=f"{hex_value[:2]}/{hex_value}",
        size_bytes=len(content),
        mime_type="text/plain",
        filename="notes.txt",
        source_snapshot=None,
    )


def test_persistent_stale_reclaim_uses_injected_lease_ttl(
    database: tuple[Engine, object, UUID, str],
) -> None:
    _engine, factory, project_id, session_id = database
    clock = MutableClock(datetime(2026, 8, 7, 11, 0, tzinfo=UTC))
    ttl = timedelta(seconds=17)
    repo = PersistentIdempotencyRepository(
        factory,  # type: ignore[arg-type]
        clock=clock,
        lease_ttl=ttl,
    )
    key = f"ttl-{uuid4().hex}"

    first = repo.resolve(
        session_id=session_id,
        project_id=str(project_id),
        idempotency_key=key,
        request_hash="sha256:" + "1" * 64,
    )
    assert first.lease_expires_at == clock.now + ttl

    clock.now += ttl + timedelta(seconds=1)
    reclaimed = repo.resolve(
        session_id=session_id,
        project_id=str(project_id),
        idempotency_key=key,
        request_hash="sha256:" + "1" * 64,
    )
    assert reclaimed.reserved is True
    assert reclaimed.lease_token != first.lease_token
    assert reclaimed.lease_expires_at == clock.now + ttl


def test_persistent_stale_reclaim_is_single_winner(
    database: tuple[Engine, object, UUID, str],
) -> None:
    _engine, factory, project_id, session_id = database
    clock = MutableClock(datetime(2026, 8, 7, 11, 15, tzinfo=UTC))
    ttl = timedelta(seconds=5)
    repo = PersistentIdempotencyRepository(
        factory,  # type: ignore[arg-type]
        clock=clock,
        lease_ttl=ttl,
    )
    key = f"reclaim-{uuid4().hex}"
    request_hash = "sha256:" + "2" * 64

    original = repo.resolve(
        session_id=session_id,
        project_id=str(project_id),
        idempotency_key=key,
        request_hash=request_hash,
    )
    assert original.reserved is True
    clock.now += ttl + timedelta(seconds=1)

    barrier = threading.Barrier(6)
    outcomes: list[object] = []
    outcomes_lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            result: object = repo.resolve(
                session_id=session_id,
                project_id=str(project_id),
                idempotency_key=key,
                request_hash=request_hash,
            )
        except SecurityProblem as exc:
            result = exc
        with outcomes_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)

    winners = [item for item in outcomes if isinstance(item, IdempotencyReservation)]
    losers = [item for item in outcomes if isinstance(item, SecurityProblem)]
    assert len(winners) == 1
    assert winners[0].reserved is True
    assert len(losers) == 5
    assert all(item.code == "IDEMPOTENCY_IN_PROGRESS" for item in losers)


def test_concurrent_same_content_commits_share_one_content_row(
    database: tuple[Engine, object, UUID, str],
) -> None:
    _engine, factory, project_id, session_id = database
    idem = PersistentIdempotencyRepository(factory)  # type: ignore[arg-type]
    store = PersistentResearchInputStore(factory)  # type: ignore[arg-type]
    content = b"same bytes committed concurrently"
    prepared = _prepared(content)
    request_hash = prepared.content_hash
    keys = [f"content-a-{uuid4().hex}", f"content-b-{uuid4().hex}"]

    reservations = [
        idem.resolve(
            session_id=session_id,
            project_id=str(project_id),
            idempotency_key=key,
            request_hash=request_hash,
        )
        for key in keys
    ]
    assert all(item.lease_token is not None for item in reservations)

    barrier = threading.Barrier(2)
    outcomes: list[object] = []
    outcomes_lock = threading.Lock()

    def commit(index: int) -> None:
        barrier.wait()
        try:
            result: object = store.commit_ingestion(
                session_id=session_id,
                project_id=str(project_id),
                payload=ResearchInputCreate(
                    type="text",
                    text_content=content.decode(),
                ),
                prepared=prepared,
                idempotency_key=keys[index],
                lease_token=reservations[index].lease_token or "",
                request_hash=request_hash,
            )
        except Exception as exc:  # pragma: no cover - asserted below
            result = exc
        with outcomes_lock:
            outcomes.append(result)

    threads = [threading.Thread(target=commit, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert len(outcomes) == 2
    assert all(not isinstance(item, Exception) for item in outcomes)

    input_ids = {item.id for item in outcomes}  # type: ignore[union-attr]
    assert len(input_ids) == 2

    with factory() as session:  # type: ignore[operator]
        content_count = session.scalar(
            select(func.count())
            .select_from(ResearchInputContentModel)
            .where(
                ResearchInputContentModel.project_id == project_id,
                ResearchInputContentModel.content_hash == prepared.content_hash,
            )
        )
        input_count = session.scalar(
            select(func.count())
            .select_from(ResearchInputModel)
            .where(
                ResearchInputModel.project_id == project_id,
                ResearchInputModel.content_hash == prepared.content_hash,
            )
        )
        completed_count = session.scalar(
            select(func.count())
            .select_from(ResearchInputIdempotencyModel)
            .where(
                ResearchInputIdempotencyModel.project_id == project_id,
                ResearchInputIdempotencyModel.idempotency_key.in_(keys),
                ResearchInputIdempotencyModel.status == "completed",
            )
        )

    assert content_count == 1
    assert input_count == 2
    assert completed_count == 2
