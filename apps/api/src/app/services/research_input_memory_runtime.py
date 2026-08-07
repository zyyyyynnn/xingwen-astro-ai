"""Atomic in-memory Research Input runtime composition (B-19).

The production PostgreSQL path gets transaction atomicity from the database.
The no-database/test runtime has two independent adapters instead:
``InMemoryResearchInputStore`` for ingestion/content state and
``InMemoryIdempotencyRepository`` for request identity.  Their individual
locks are intentionally implementation details and cannot by themselves make
``validate lease -> mutate input/content -> complete reservation`` atomic.

This coordinator is the supported in-memory runtime boundary.  It implements
both ports and serializes the cross-adapter state transitions with one explicit
transaction lock while leaving each adapter responsible for its own data.
Long-running URL fetches are *not* performed under this lock: the application
service reserves first, releases the call, performs I/O, then enters the atomic
commit section here.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from app.schemas.research_input import ResearchInputCreate
from app.services.research_input_store import (
    DEFAULT_LEASE_TTL,
    IdempotencyReservation,
    InMemoryIdempotencyRepository,
    InMemoryResearchInputStore,
    PreparedInput,
    ResearchInputRecord,
)


class InMemoryResearchInputRuntime:
    """Coordinated in-memory implementation of both B-19 persistence ports.

    ``resolve`` / ``release`` and ``commit_ingestion`` use the same coordinator
    lock.  Therefore a stale-lease reclaimer cannot slip between the store's
    token validation and its state mutation.  A losing worker observes
    ``IDEMPOTENCY_RESERVATION_LOST`` before any ghost content/input is created.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = DEFAULT_LEASE_TTL,
    ) -> None:
        self._transaction_lock = threading.RLock()
        self._store = InMemoryResearchInputStore(clock=clock)
        self._idempotency = InMemoryIdempotencyRepository(
            clock=clock,
            lease_ttl=lease_ttl,
        )
        self._store.bind_idempotency(self._idempotency)

    # ---- test/bootstrap authority -----------------------------------------

    def register_project(self, *, project_id: str, owner_session_id: str) -> None:
        with self._transaction_lock:
            self._store.register_project(
                project_id=project_id,
                owner_session_id=owner_session_id,
            )

    def register_contract_draft(
        self, *, draft_id: str, owner_session_id: str
    ) -> None:
        with self._transaction_lock:
            self._store.register_contract_draft(
                draft_id=draft_id,
                owner_session_id=owner_session_id,
            )

    def register_run(self, *, run_id: str, project_id: str) -> None:
        with self._transaction_lock:
            self._store.register_run(run_id=run_id, project_id=project_id)

    # ---- ResearchInputRepository ------------------------------------------

    def require_owned_project(self, *, session_id: str, project_id: str) -> str:
        with self._transaction_lock:
            return self._store.require_owned_project(
                session_id=session_id,
                project_id=project_id,
            )

    def commit_ingestion(
        self,
        *,
        session_id: str,
        project_id: str,
        payload: ResearchInputCreate,
        prepared: PreparedInput,
        idempotency_key: str,
        lease_token: str,
        request_hash: str,
    ) -> ResearchInputRecord:
        """Atomically validate the active lease, mutate state and complete it."""

        with self._transaction_lock:
            return self._store.commit_ingestion(
                session_id=session_id,
                project_id=project_id,
                payload=payload,
                prepared=prepared,
                idempotency_key=idempotency_key,
                lease_token=lease_token,
                request_hash=request_hash,
            )

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        return self._store.get(session_id=session_id, input_id=input_id)

    def list(
        self,
        *,
        session_id: str,
        project_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[object, ...], str | None, bool]:
        # The concrete tuple elements are ResearchInputRef; keeping delegation
        # here avoids duplicating the DTO import solely for an adapter wrapper.
        return self._store.list(
            session_id=session_id,
            project_id=project_id,
            cursor=cursor,
            limit=limit,
        )

    def delete(self, *, session_id: str, input_id: str) -> None:
        with self._transaction_lock:
            self._store.delete(session_id=session_id, input_id=input_id)

    def bind_to_contract(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        contract_draft_id: str,
    ) -> None:
        with self._transaction_lock:
            self._store.bind_to_contract(
                session_id=session_id,
                input_id=input_id,
                project_id=project_id,
                contract_draft_id=contract_draft_id,
            )

    def bind_to_run(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        run_id: str,
    ) -> None:
        with self._transaction_lock:
            self._store.bind_to_run(
                session_id=session_id,
                input_id=input_id,
                project_id=project_id,
                run_id=run_id,
            )

    # ---- ResearchInputIdempotencyRepository -------------------------------

    def resolve(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        with self._transaction_lock:
            return self._idempotency.resolve(
                session_id=session_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )

    def release(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
    ) -> None:
        with self._transaction_lock:
            self._idempotency.release(
                session_id=session_id,
                project_id=project_id,
                idempotency_key=idempotency_key,
                lease_token=lease_token,
            )


__all__ = ["InMemoryResearchInputRuntime"]
