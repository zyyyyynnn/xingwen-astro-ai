"""Concurrency invariants for the coordinated Research Input Ingestion in-memory runtime."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.research_input import ResearchInputCreate
from app.security import SecurityProblem
from app.services.content_storage import sha256_content_hash
from app.services.research_input_memory_runtime import InMemoryResearchInputRuntime
from app.services.research_input_store import PreparedInput


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _prepared(*, content: bytes, storage_ref: str) -> PreparedInput:
    return PreparedInput(
        content_hash=sha256_content_hash(content),
        storage_ref=storage_ref,
        size_bytes=len(content),
        mime_type="text/plain",
        filename="notes.txt",
        source_snapshot=None,
    )


def test_reclaimed_old_token_commit_has_zero_mutation() -> None:
    """A worker that lost its lease cannot leave ghost content or input state."""

    clock = MutableClock(datetime(2026, 8, 7, 10, 0, tzinfo=UTC))
    runtime = InMemoryResearchInputRuntime(
        clock=clock,
        lease_ttl=timedelta(seconds=1),
    )
    runtime.register_project(project_id="proj_01", owner_session_id="session_a")

    old = runtime.resolve(
        session_id="session_a",
        project_id="proj_01",
        idempotency_key="lease-key",
        request_hash="request-a",
    )
    assert old.lease_token is not None

    clock.now += timedelta(seconds=2)
    reclaimed = runtime.resolve(
        session_id="session_a",
        project_id="proj_01",
        idempotency_key="lease-key",
        request_hash="request-a",
    )
    assert reclaimed.lease_token is not None
    assert reclaimed.lease_token != old.lease_token

    content = b"atomic payload"
    with pytest.raises(SecurityProblem) as exc:
        runtime.commit_ingestion(
            session_id="session_a",
            project_id="proj_01",
            payload=ResearchInputCreate(type="text", text_content=content.decode()),
            prepared=_prepared(content=content, storage_ref="old/ghost"),
            idempotency_key="lease-key",
            lease_token=old.lease_token,
            request_hash="request-a",
        )
    assert exc.value.code == "IDEMPOTENCY_RESERVATION_LOST"

    # Use a deliberately different storage_ref for the same hash. If the
    # losing commit had mutated the content map before failing, consistency
    # validation would reject this legitimate winner.
    created = runtime.commit_ingestion(
        session_id="session_a",
        project_id="proj_01",
        payload=ResearchInputCreate(type="text", text_content=content.decode()),
        prepared=_prepared(content=content, storage_ref="winner/content"),
        idempotency_key="lease-key",
        lease_token=reclaimed.lease_token,
        request_hash="request-a",
    )

    refs, _, _ = runtime.list(
        session_id="session_a",
        project_id="proj_01",
        cursor=None,
        limit=20,
    )
    assert [ref.id for ref in refs] == [created.id]


def test_reclaimer_cannot_enter_validate_to_commit_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The coordinator serializes stale reclaim against the commit critical section."""

    clock = MutableClock(datetime(2026, 8, 7, 10, 0, tzinfo=UTC))
    runtime = InMemoryResearchInputRuntime(
        clock=clock,
        lease_ttl=timedelta(seconds=1),
    )
    runtime.register_project(project_id="proj_01", owner_session_id="session_a")
    reservation = runtime.resolve(
        session_id="session_a",
        project_id="proj_01",
        idempotency_key="race-key",
        request_hash="request-race",
    )
    assert reservation.lease_token is not None

    # Make the lease stale. The old worker then enters commit first. We pause it
    # immediately after token validation; a concurrent reclaimer attempts
    # resolve during precisely the historical race window.
    clock.now += timedelta(seconds=2)
    validated = threading.Event()
    allow_commit = threading.Event()
    reclaimer_started = threading.Event()
    outcomes: dict[str, object] = {}

    original_validate = runtime._idempotency.validate_lease  # noqa: SLF001

    def paused_validate(*args: object, **kwargs: object) -> None:
        original_validate(*args, **kwargs)
        validated.set()
        assert allow_commit.wait(timeout=5)

    monkeypatch.setattr(runtime._idempotency, "validate_lease", paused_validate)  # noqa: SLF001

    content = b"race payload"

    def old_worker() -> None:
        try:
            outcomes["commit"] = runtime.commit_ingestion(
                session_id="session_a",
                project_id="proj_01",
                payload=ResearchInputCreate(type="text", text_content=content.decode()),
                prepared=_prepared(content=content, storage_ref="race/content"),
                idempotency_key="race-key",
                lease_token=reservation.lease_token or "",
                request_hash="request-race",
            )
        except Exception as exc:  # pragma: no cover - asserted below
            outcomes["commit"] = exc

    def reclaimer() -> None:
        reclaimer_started.set()
        try:
            outcomes["reclaim"] = runtime.resolve(
                session_id="session_a",
                project_id="proj_01",
                idempotency_key="race-key",
                request_hash="request-race",
            )
        except Exception as exc:  # pragma: no cover - asserted below
            outcomes["reclaim"] = exc

    commit_thread = threading.Thread(target=old_worker)
    reclaim_thread = threading.Thread(target=reclaimer)
    commit_thread.start()
    assert validated.wait(timeout=5)
    reclaim_thread.start()
    assert reclaimer_started.wait(timeout=5)

    # If resolve and commit used independent coordination, the reclaimer could
    # change the lease while commit is paused. The runtime-level lock keeps it
    # outside until the old worker has atomically completed.
    allow_commit.set()
    commit_thread.join(timeout=5)
    reclaim_thread.join(timeout=5)
    assert not commit_thread.is_alive()
    assert not reclaim_thread.is_alive()

    committed = outcomes["commit"]
    replay = outcomes["reclaim"]
    assert not isinstance(committed, Exception)
    assert not isinstance(replay, Exception)
    assert replay.replayed_input_id == committed.id  # type: ignore[union-attr]

    refs, _, _ = runtime.list(
        session_id="session_a",
        project_id="proj_01",
        cursor=None,
        limit=20,
    )
    assert [ref.id for ref in refs] == [committed.id]  # type: ignore[union-attr]
