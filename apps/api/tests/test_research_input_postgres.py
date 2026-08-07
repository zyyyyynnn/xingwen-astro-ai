"""PostgreSQL-backed integration tests for the B-19 research input store.

Gate: requires TEST_DATABASE_URL naming a database whose name contains "test"
(never touches a production database). Schema is rebuilt from Alembic on each
module run.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
import threading
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError

from app.db.models import (
    ResearchContractDraftModel,
    ResearchInputBindingModel,
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
    IdempotencyReservation,
    PersistentIdempotencyRepository,
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
    idempotency_key: str | None = None,
) -> object:
    idem = PersistentIdempotencyRepository(ctx["factory"])
    session_id = ctx["owner"].id
    project_id = str(ctx["ids"][project_key])
    request_hash = sha256_content_hash(content)
    key = idempotency_key or f"pg-create-{uuid4().hex}"
    reservation = idem.resolve(
        session_id=session_id,
        project_id=project_id,
        idempotency_key=key,
        request_hash=request_hash,
    )
    if reservation.replayed_input_id is not None:
        replayed = store.get(session_id=session_id, input_id=reservation.replayed_input_id)
        if replayed is not None:
            return replayed
    return store.commit_ingestion(
        session_id=session_id,
        project_id=project_id,
        payload=ResearchInputCreate(type="text", text_content="persisted payload"),
        prepared=_prepared(content=content, source=source),
        idempotency_key=key,
        lease_token=reservation.lease_token,
        request_hash=request_hash,
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
    key = "pg-replay-shared"
    first = _create(store, ctx, content=b"replay me", idempotency_key=key)
    second = _create(store, ctx, content=b"replay me", idempotency_key=key)
    assert second.id == first.id


def test_persistent_store_hides_foreign_project(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    idem = PersistentIdempotencyRepository(ctx["factory"])
    session_id = ctx["owner"].id
    project_id = str(ctx["ids"]["other_project"])
    content = b"sneak"
    res = idem.resolve(
        session_id=session_id,
        project_id=project_id,
        idempotency_key="pg-foreign",
        request_hash=sha256_content_hash(content),
    )
    with pytest.raises(SecurityProblem) as exc:
        _store(ctx).commit_ingestion(
            session_id=session_id,
            project_id=project_id,
            payload=ResearchInputCreate(type="text", text_content="sneak"),
            prepared=_prepared(content=content),
            idempotency_key="pg-foreign",
            lease_token=res.lease_token,
            request_hash=sha256_content_hash(content),
        )
    assert exc.value.code == "PROJECT_NOT_FOUND"


def test_persistent_store_soft_delete_and_resurrection(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    store = _store(ctx)
    created = _create(store, ctx, content=b"delete me", idempotency_key="pg-del-1")
    store.delete(session_id=ctx["owner"].id, input_id=created.id)
    assert store.get(session_id=ctx["owner"].id, input_id=created.id) is None

    # A new ingestion under a new key creates a NEW input; the expired one is
    # never resurrected or mutated (no resurrection in the new model).
    fresh = _create(store, ctx, content=b"delete me", idempotency_key="pg-del-2")
    assert fresh.id != created.id
    assert fresh.content_hash == created.content_hash
    assert store.get(session_id=ctx["owner"].id, input_id=fresh.id) is not None


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


def test_persistent_store_binding_target_xor_constraint(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    factory = ctx["factory"]
    with factory() as session, session.begin():
        from app.db.models import ResearchInputBindingModel
        from sqlalchemy.exc import IntegrityError

        bad_binding = ResearchInputBindingModel(
            input_id=UUID(int=999),
            project_id=ctx["ids"]["project"],
            contract_draft_id=ctx["ids"]["contract"],
            run_id=ctx["ids"]["run"],
        )
        session.add(bad_binding)
        with pytest.raises(IntegrityError):
            session.flush()


# ---- referential invariants ------------------------------------------------
#
# These assert that the *database* refuses inconsistent rows, so the guarantees
# do not depend on application code remembering to check.


def test_dangling_contract_draft_id_is_rejected(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    factory = ctx["factory"]
    store = _store(ctx)
    created = _create(store, ctx, content=b"fk draft probe")

    with factory() as session, session.begin():
        binding = ResearchInputBindingModel(
            input_id=UUID(created.id),
            project_id=ctx["ids"]["project"],
            contract_draft_id=UUID(int=987654),  # no such draft
            run_id=None,
        )
        session.add(binding)
        with pytest.raises(IntegrityError):
            session.flush()


def test_binding_run_must_belong_to_the_same_project(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    factory = ctx["factory"]
    store = _store(ctx)
    created = _create(store, ctx, content=b"fk run probe")

    with factory() as session, session.begin():
        binding = ResearchInputBindingModel(
            input_id=UUID(created.id),
            project_id=ctx["ids"]["other_project"],
            contract_draft_id=None,
            run_id=ctx["ids"]["run"],
        )
        session.add(binding)
        with pytest.raises(IntegrityError):
            session.flush()


def test_binding_input_must_belong_to_the_same_project(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    factory = ctx["factory"]
    store = _store(ctx)
    created = _create(store, ctx, content=b"fk input probe")

    with factory() as session, session.begin():
        binding = ResearchInputBindingModel(
            input_id=UUID(created.id),
            project_id=ctx["ids"]["other_project"],
            contract_draft_id=None,
            run_id=None,
        )
        session.add(binding)
        with pytest.raises(IntegrityError):
            session.flush()


def test_snapshot_project_pair_is_enforced(
    store_context: dict[str, object],
) -> None:
    """A research input cannot point at a snapshot from another project."""

    ctx = store_context
    factory = ctx["factory"]
    with factory() as session, session.begin():
        foreign_snapshot = SourceSnapshotModel(
            project_id=ctx["ids"]["other_project"],
            source_id="url_foreign",
            source_type="url_fetch",
            retrieved_at=NOW,
            query="https://example.com/foreign.csv",
            query_hash="sha256:" + "7" * 64,
            content_hash="sha256:" + "8" * 64,
            license_note="fetched",
            request_metadata={"status_code": 200},
        )
        session.add(foreign_snapshot)
        session.flush()
        foreign_snapshot_id = foreign_snapshot.id

    # Create the required content row for the FK before testing the snapshot FK.
    from app.db.models import ResearchInputContentModel

    with factory() as session, session.begin():
        session.add(
            ResearchInputContentModel(
                project_id=ctx["ids"]["project"],
                content_hash="sha256:" + "9" * 64,
                storage_ref="99/" + "9" * 64,
                mime_type="text/csv",
                size_bytes=8,
                created_at=NOW,
            )
        )

    with factory() as session, session.begin():
        row = ResearchInputModel(
            session_id=ctx["owner"].id,
            project_id=ctx["ids"]["project"],
            type="url",
            source_type="url_fetch",
            content_hash="sha256:" + "9" * 64,
            filename=None,
            status="accepted",
            source_snapshot_id=foreign_snapshot_id,
            created_at=NOW,
            expires_at=None,
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            session.flush()


# ---- request idempotency persistence ---------------------------------------


def test_idempotency_mapping_is_separate_from_content_dedup(
    store_context: dict[str, object],
) -> None:
    """Each key completes to its own ingestion; one key may not span two requests.

    Distinct keys create distinct Research Input rows (ingestion identity) that
    share the same content blob (content identity), and a key replayed with the
    identical request returns the same input -- while reusing it with a
    different request body is a deterministic 409.
    """

    ctx = store_context
    repo = PersistentIdempotencyRepository(ctx["factory"])
    store = _store(ctx)
    project_id = str(ctx["ids"]["project"])
    session_id = ctx["owner"].id

    created = _create(
        store, ctx, content=b"idem shared payload", idempotency_key="pg-key-A"
    )

    replay = repo.resolve(
        session_id=session_id,
        project_id=project_id,
        idempotency_key="pg-key-A",
        request_hash=sha256_content_hash(b"idem shared payload"),
    )
    assert replay.replayed_input_id == created.id

    # A different key for the same content is independently valid: it creates a
    # second ingestion but deduplicates onto the same content blob.
    second = _create(
        store, ctx, content=b"idem shared payload", idempotency_key="pg-key-B"
    )
    assert second.id != created.id
    assert second.content_hash == created.content_hash
    assert (
        repo.resolve(
            session_id=session_id,
            project_id=project_id,
            idempotency_key="pg-key-B",
            request_hash=sha256_content_hash(b"idem shared payload"),
        ).replayed_input_id
        == second.id
    )

    # Reusing key A with a different request is a deterministic conflict.
    with pytest.raises(SecurityProblem) as exc:
        repo.resolve(
            session_id=session_id,
            project_id=project_id,
            idempotency_key="pg-key-A",
            request_hash="sha256:" + "c" * 64,
        )
    assert exc.value.status == 409
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


def test_released_reservation_is_retryable(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    repo = PersistentIdempotencyRepository(ctx["factory"])
    project_id = str(ctx["ids"]["project"])
    session_id = ctx["owner"].id

    reserved = repo.resolve(
        session_id=session_id,
        project_id=project_id,
        idempotency_key="pg-key-release",
        request_hash="sha256:" + "d" * 64,
    )
    assert reserved.reserved is True
    repo.release(
        session_id=session_id,
        project_id=project_id,
        idempotency_key="pg-key-release",
        lease_token=reserved.lease_token,
    )

    again = repo.resolve(
        session_id=session_id,
        project_id=project_id,
        idempotency_key="pg-key-release",
        request_hash="sha256:" + "d" * 64,
    )
    assert again.reserved is True


def test_concurrent_same_key_same_request_yields_one_reservation(
    store_context: dict[str, object],
) -> None:
    """Exactly one caller may reserve; no raw IntegrityError escapes as a 500."""

    ctx = store_context
    repo = PersistentIdempotencyRepository(ctx["factory"])
    project_id = str(ctx["ids"]["project"])
    session_id = ctx["owner"].id
    request_hash = "sha256:" + "e" * 64
    barrier = threading.Barrier(6)
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt() -> None:
        barrier.wait()
        try:
            result = repo.resolve(
                session_id=session_id,
                project_id=project_id,
                idempotency_key="pg-key-race",
                request_hash=request_hash,
            )
        except SecurityProblem as problem:
            result = problem
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reservations = [
        item for item in outcomes if isinstance(item, IdempotencyReservation)
    ]
    problems = [item for item in outcomes if isinstance(item, SecurityProblem)]
    assert len(reservations) == 1
    assert reservations[0].reserved is True
    # Every loser is a deterministic 409, never a raw database error.
    assert len(problems) == 5
    assert all(problem.status == 409 for problem in problems)


def test_concurrent_same_key_different_request_is_deterministic(
    store_context: dict[str, object],
) -> None:
    ctx = store_context
    repo = PersistentIdempotencyRepository(ctx["factory"])
    project_id = str(ctx["ids"]["project"])
    session_id = ctx["owner"].id
    barrier = threading.Barrier(4)
    outcomes: list[object] = []
    lock = threading.Lock()

    def attempt(index: int) -> None:
        barrier.wait()
        try:
            result = repo.resolve(
                session_id=session_id,
                project_id=project_id,
                idempotency_key="pg-key-divergent",
                request_hash=f"sha256:{index:064d}",
            )
        except SecurityProblem as problem:
            result = problem
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reservations = [
        item for item in outcomes if isinstance(item, IdempotencyReservation)
    ]
    problems = [item for item in outcomes if isinstance(item, SecurityProblem)]
    assert len(reservations) == 1
    assert len(problems) == 3
    assert all(problem.status == 409 for problem in problems)
