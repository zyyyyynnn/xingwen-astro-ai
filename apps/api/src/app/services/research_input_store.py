"""Research Input persistence adapters (B-19).

Three identities, three ports, never conflated:

* content identity -- ``ResearchInputContentModel`` / ``research_input_contents``,
  keyed by ``(project_id, content_hash)``. One immutable blob, no source facts.
* ingestion identity -- ``ResearchInputModel`` / ``research_inputs``, an
  immutable provenance reference. No ``(session, project, content_hash)`` unique
  constraint, so the same bytes ingested by upload / URL / text stay distinct.
* request identity -- ``ResearchInputIdempotencyModel`` / ``research_input_idempotency``,
  keyed by ``(session_id, project_id, Idempotency-Key)``.

MIME/filename policy lives in ``app.services.research_input_policy`` and is
injected by the application service; this module only persists.
"""

from __future__ import annotations

import base64
import dataclasses
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchContractDraftModel,
    ResearchInputBindingModel,
    ResearchInputContentModel,
    ResearchInputIdempotencyModel,
    ResearchInputModel,
    ResearchProjectModel,
    ResearchRunModel,
    SourceSnapshotModel,
)
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.research_input import (
    FILE_INPUT_TYPES,
    RESEARCH_INPUT_NOT_FOUND,
    TEXT_SOURCE_TYPE,
    UPLOAD_SOURCE_TYPE,
    URL_FETCH_SOURCE_TYPE,
    ResearchInputCreate,
    ResearchInputDetail,
    ResearchInputRef,
    ResearchInputStatus,
    ResearchInputType,
)
from app.security import SecurityProblem

#: Reservation states for the request-identity mapping.
IDEMPOTENCY_PENDING = "pending"
IDEMPOTENCY_COMPLETED = "completed"

#: Default lease window when none is injected (tests override via clock).
DEFAULT_LEASE_TTL = timedelta(seconds=300)


@dataclass(frozen=True, slots=True)
class ResearchInputRecord:
    """Store-internal record; ``storage_ref`` and ``url`` never leave it raw."""

    id: str
    session_id: str
    project_id: str
    type: ResearchInputType
    source_type: str
    content_hash: str
    storage_ref: str
    filename: str | None
    mime_type: str | None
    size_bytes: int
    status: ResearchInputStatus
    source_snapshot_id: str | None
    url: str | None
    created_at: datetime
    expires_at: datetime | None

    def to_ref(self) -> ResearchInputRef:
        return ResearchInputRef(
            id=self.id,
            type=self.type,
            source_type=self.source_type,
            content_hash=self.content_hash,
            filename=self.filename,
            mime_type=self.mime_type,
            size_bytes=self.size_bytes,
            created_at=_utc(self.created_at),
            source_snapshot_id=self.source_snapshot_id,
            status=self.status,
        )

    def to_detail(self) -> ResearchInputDetail:
        return ResearchInputDetail(
            **self.to_ref().model_dump(),
            project_id=self.project_id,
            url=self.url,
        )


@dataclass(frozen=True, slots=True)
class PreparedInput:
    """Validated ingestion facts produced by the application service."""

    content_hash: str
    storage_ref: str
    size_bytes: int
    mime_type: str | None
    filename: str | None
    source_snapshot: SourceSnapshotRecord | None


@dataclass(frozen=True, slots=True)
class IdempotencyReservation:
    """Outcome of resolving one ``Idempotency-Key`` against stored requests.

    ``replayed_input_id`` is set when a completed mapping already exists for
    this exact request, in which case the caller returns the existing resource
    without repeating any side effect (notably: without re-fetching a URL).

    ``reserved`` is ``True`` when this caller now owns a ``pending``
    reservation it must either commit (with its ``lease_token``) or release.
    """

    replayed_input_id: str | None
    reserved: bool
    lease_token: str | None = None
    lease_expires_at: datetime | None = None


class ResearchInputRepository(Protocol):
    """Ownership-scoped persistence boundary for ingested inputs."""

    def require_owned_project(self, *, session_id: str, project_id: str) -> str:
        """Return the canonical project id, or raise a hidden 404.

        All failure shapes (malformed id, missing project, foreign project)
        are identical so the existence of a project is never leaked.
        """

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
        """Atomically ensure content, insert the input, complete the lease."""

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        """Return the record only when owned by ``session_id`` and not expired."""

    def list(
        self, *, session_id: str, project_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[ResearchInputRef, ...], str | None, bool]:
        """Session- and project-scoped listing with a stable keyset cursor."""

    def delete(self, *, session_id: str, input_id: str) -> None:
        """Soft-delete by expiring the reference; content blobs are never removed."""

    def bind_to_contract(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        contract_draft_id: str,
    ) -> None:
        """Bind an owned input reference to an owned ContractDraft."""

    def bind_to_run(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        run_id: str,
    ) -> None:
        """Bind an owned input reference to a Run inside the same project."""


class ResearchInputIdempotencyRepository(Protocol):
    """Request-identity mapping, independent of content identity."""

    def resolve(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        """Replay, conflict (409) or reserve this key for the current request."""

    def release(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
    ) -> None:
        """Drop a pending reservation only if the lease token still matches."""


# ---- in-memory adapters ----------------------------------------------------


class InMemoryResearchInputStore:
    """Process-local adapter for unit/security tests and the no-DB runtime.

    Mirrors the Postgres adapter's contract exactly, including content/ingestion
    separation and lease-bound idempotency.
    """

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._contents: dict[tuple[str, str], tuple[str, str, int]] = {}
        self._records: dict[str, ResearchInputRecord] = {}
        self._projects: dict[str, str] = {}
        self._drafts: dict[str, str] = {}
        self._runs: dict[str, str] = {}
        self._bindings: dict[str, tuple[str | None, str | None]] = {}
        self._idempotency: InMemoryIdempotencyRepository | None = None
        self._lock = threading.RLock()

    def bind_idempotency(self, repo: InMemoryIdempotencyRepository) -> None:
        """Pair with the in-memory idempotency repository so a committed
        ingestion atomically completes its reservation (no real transaction
        exists in-process, but the two adapters share a single lock order)."""

        self._idempotency = repo

    def register_project(self, *, project_id: str, owner_session_id: str) -> None:
        self._projects[project_id] = owner_session_id

    def register_contract_draft(self, *, draft_id: str, owner_session_id: str) -> None:
        self._drafts[draft_id] = owner_session_id

    def register_run(self, *, run_id: str, project_id: str) -> None:
        self._runs[run_id] = project_id

    def require_owned_project(self, *, session_id: str, project_id: str) -> str:
        if self._projects.get(project_id) != session_id:
            raise _not_found("PROJECT_NOT_FOUND")
        return project_id

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
        with self._lock:
            self.require_owned_project(session_id=session_id, project_id=project_id)
            _ensure_content_memory(
                self._contents,
                project_id=project_id,
                content_hash=prepared.content_hash,
                storage_ref=prepared.storage_ref,
                mime_type=prepared.mime_type or "",
                size_bytes=prepared.size_bytes,
            )
            now = datetime.now(UTC)
            record = ResearchInputRecord(
                id=f"input_{secrets.token_urlsafe(18)}",
                session_id=session_id,
                project_id=project_id,
                type=payload.type,
                source_type=_source_type_for(payload),
                content_hash=prepared.content_hash,
                storage_ref=prepared.storage_ref,
                filename=prepared.filename,
                mime_type=prepared.mime_type,
                size_bytes=prepared.size_bytes,
                status=ResearchInputStatus.accepted,
                source_snapshot_id=(
                    prepared.source_snapshot.snapshot_id
                    if prepared.source_snapshot is not None
                    else None
                ),
                url=_snapshot_url(prepared.source_snapshot),
                created_at=now,
                expires_at=None,
            )
            self._records[record.id] = record
            if self._idempotency is not None:
                self._idempotency.complete_reservation(
                    session_id, project_id, idempotency_key, lease_token, record.id
                )
            return record

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        with self._lock:
            record = self._records.get(input_id)
            if record is None or record.session_id != session_id:
                return None
            if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
                return None
            return record

    def list(
        self, *, session_id: str, project_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[ResearchInputRef, ...], str | None, bool]:
        with self._lock:
            now = datetime.now(UTC)
            records = sorted(
                (
                    record
                    for record in self._records.values()
                    if record.session_id == session_id
                    and record.project_id == project_id
                    and (record.expires_at is None or record.expires_at > now)
                ),
                key=lambda item: (item.created_at, item.id),
                reverse=True,
            )
        start = _memory_cursor_start(records, cursor)
        selected = records[start : start + limit]
        has_more = start + len(selected) < len(records)
        next_cursor = _encode_cursor(selected[-1].id) if selected and has_more else None
        return (
            tuple(record.to_ref() for record in selected),
            next_cursor,
            has_more,
        )

    def delete(self, *, session_id: str, input_id: str) -> None:
        with self._lock:
            record = self.get(session_id=session_id, input_id=input_id)
            if record is None:
                raise _not_found(RESEARCH_INPUT_NOT_FOUND)
            self._records[input_id] = dataclasses.replace(
                record, expires_at=datetime.now(UTC)
            )

    def bind_to_contract(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        contract_draft_id: str,
    ) -> None:
        with self._lock:
            record = self._require_owned_input(session_id, input_id, project_id)
            if self._drafts.get(contract_draft_id) != session_id:
                raise _not_found("RESOURCE_NOT_FOUND")
            self._bindings[record.id] = (contract_draft_id, None)

    def bind_to_run(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        run_id: str,
    ) -> None:
        with self._lock:
            record = self._require_owned_input(session_id, input_id, project_id)
            if self._runs.get(run_id) != project_id:
                raise _not_found("RESOURCE_NOT_FOUND")
            self._bindings[record.id] = (None, run_id)

    def _require_owned_input(
        self, session_id: str, input_id: str, project_id: str
    ) -> ResearchInputRecord:
        record = self.get(session_id=session_id, input_id=input_id)
        if record is None or record.project_id != project_id:
            raise _not_found(RESEARCH_INPUT_NOT_FOUND)
        return record


class InMemoryIdempotencyRepository:
    """Process-local request-identity mapping with lease ownership.

    The lock is required: two concurrent requests carrying the same key must
    not both reserve and fetch. A stale pending reservation (lease expired) may
    be reclaimed by a later caller, who receives a NEW token so the original
    worker can no longer release or complete it.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = DEFAULT_LEASE_TTL,
    ) -> None:
        # entry: (request_hash, status, input_id, lease_token, lease_expires_at)
        self._entries: dict[
            tuple[str, str, str], tuple[str, str, str | None, str | None, datetime | None]
        ] = {}
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_ttl = lease_ttl
        self._lock = threading.RLock()

    def _new_token(self) -> str:
        return secrets.token_urlsafe(24)

    def resolve(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        key = (session_id, project_id, idempotency_key)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                token = self._new_token()
                self._entries[key] = (
                    request_hash,
                    IDEMPOTENCY_PENDING,
                    None,
                    token,
                    now + self._lease_ttl,
                )
                return IdempotencyReservation(
                    replayed_input_id=None,
                    reserved=True,
                    lease_token=token,
                    lease_expires_at=now + self._lease_ttl,
                )
            stored_hash, status, input_id, token, expires_at = entry
            if stored_hash != request_hash:
                raise _idempotency_conflict()
            if status == IDEMPOTENCY_COMPLETED:
                return IdempotencyReservation(
                    replayed_input_id=input_id,
                    reserved=False,
                )
            # pending path
            if expires_at is not None and expires_at > now:
                # A valid in-flight reservation for the identical request: the
                # second caller must not duplicate the side effect.
                raise _idempotency_in_progress()
            # Stale lease -> reclaim with a fresh token.
            new_token = self._new_token()
            new_expiry = now + self._lease_ttl
            self._entries[key] = (
                stored_hash,
                IDEMPOTENCY_PENDING,
                None,
                new_token,
                new_expiry,
            )
            return IdempotencyReservation(
                replayed_input_id=None,
                reserved=True,
                lease_token=new_token,
                lease_expires_at=new_expiry,
            )

    def release(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
    ) -> None:
        key = (session_id, project_id, idempotency_key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            _hash, status, _input_id, token, _expires = entry
            if status != IDEMPOTENCY_PENDING:
                return
            if token != lease_token:
                raise _idempotency_reservation_lost()
            del self._entries[key]

    def complete_reservation(
        self,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
        input_id: str,
    ) -> None:
        """Atomically complete the reservation this worker's lease owns."""
        key = (session_id, project_id, idempotency_key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                # No outstanding reservation (e.g. committed directly, or the
                # key was already released): nothing to reconcile.
                return
            _hash, status, _old_input, token, _expires = entry
            if status != IDEMPOTENCY_PENDING or token != lease_token:
                raise _idempotency_reservation_lost()
            self._entries[key] = (_hash, IDEMPOTENCY_COMPLETED, input_id, None, None)


# ---- PostgreSQL adapters ---------------------------------------------------


class PersistentResearchInputStore:
    """PostgreSQL-backed adapter sharing the same ownership semantics."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def require_owned_project(self, *, session_id: str, project_id: str) -> str:
        pid = _uuid_or_none(project_id)
        if pid is None:
            raise _not_found("PROJECT_NOT_FOUND")
        with self._factory() as session:
            project = session.get(ResearchProjectModel, pid)
            if project is None or project.session_id != session_id:
                raise _not_found("PROJECT_NOT_FOUND")
            return str(project.id)

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
        pid = _uuid_or_none(project_id)
        with self._factory() as session, session.begin():
            project = session.get(ResearchProjectModel, pid)
            if project is None or project.session_id != session_id:
                raise _not_found("PROJECT_NOT_FOUND")

            # 1. ensure content identity (race-safe upsert keyed by hash).
            _ensure_content_row(
                session,
                project_id=project.id,
                content_hash=prepared.content_hash,
                storage_ref=prepared.storage_ref,
                mime_type=prepared.mime_type or "",
                size_bytes=prepared.size_bytes,
            )

            # 2. insert the immutable ingestion reference.
            source_snapshot_id = _persist_snapshot(
                session, project_id=str(project.id), source=prepared.source_snapshot
            )
            row = ResearchInputModel(
                session_id=session_id,
                project_id=project.id,
                type=payload.type.value,
                source_type=_source_type_for(payload),
                content_hash=prepared.content_hash,
                storage_ref=prepared.storage_ref,
                filename=prepared.filename,
                mime_type=prepared.mime_type,
                size_bytes=prepared.size_bytes,
                status=ResearchInputStatus.accepted.value,
                source_snapshot_id=source_snapshot_id,
                created_at=datetime.now(UTC),
                expires_at=None,
            )
            session.add(row)
            session.flush()

            # 3. atomically complete the lease: token + request must match.
            idem = session.get(
                ResearchInputIdempotencyModel,
                (session_id, project.id, idempotency_key),
                with_for_update=True,
            )
            if idem is None:
                raise _conflict_unresolved()
            if idem.status != IDEMPOTENCY_PENDING:
                raise _idempotency_conflict()
            if idem.request_hash != request_hash:
                raise _idempotency_conflict()
            if idem.lease_token != lease_token:
                raise _idempotency_reservation_lost()
            idem.input_id = row.id
            idem.status = IDEMPOTENCY_COMPLETED
            idem.lease_token = None
            idem.lease_expires_at = None
            idem.updated_at = datetime.now(UTC)

            return _record(
                row,
                content=(
                    prepared.storage_ref,
                    prepared.mime_type,
                    prepared.size_bytes,
                ),
                url=_snapshot_url(prepared.source_snapshot),
            )

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        iid = _uuid_or_none(input_id)
        if iid is None:
            return None
        with self._factory() as session:
            row = session.get(ResearchInputModel, iid)
            if row is None or row.session_id != session_id:
                return None
            if _is_expired(row):
                return None
            return _record(row, session=session)

    def list(
        self, *, session_id: str, project_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[ResearchInputRef, ...], str | None, bool]:
        pid = _uuid_or_none(project_id)
        with self._factory() as session:
            query = select(ResearchInputModel).where(
                ResearchInputModel.session_id == session_id,
                ResearchInputModel.project_id == pid,
                ResearchInputModel.expires_at.is_(None),
            )
            if cursor is not None:
                anchor_id = _decode_cursor(cursor)
                anchor = session.get(ResearchInputModel, _uuid_or_none(anchor_id))
                if anchor is None or anchor.session_id != session_id:
                    raise _invalid_cursor()
                query = query.where(
                    (ResearchInputModel.created_at < anchor.created_at)
                    | (
                        (ResearchInputModel.created_at == anchor.created_at)
                        & (ResearchInputModel.id < anchor.id)
                    )
                )
            rows = (
                session.scalars(
                    query.order_by(
                        ResearchInputModel.created_at.desc(),
                        ResearchInputModel.id.desc(),
                    ).limit(limit + 1)
                )
            ).all()
            has_more = len(rows) > limit
            selected = rows[:limit]
            next_cursor = (
                _encode_cursor(str(selected[-1].id)) if selected and has_more else None
            )
            return (
                tuple(_record(row, session=session).to_ref() for row in selected),
                next_cursor,
                has_more,
            )

    def delete(self, *, session_id: str, input_id: str) -> None:
        iid = _uuid_or_none(input_id)
        with self._factory() as session, session.begin():
            row = session.get(ResearchInputModel, iid)
            if row is None or row.session_id != session_id:
                raise _not_found(RESEARCH_INPUT_NOT_FOUND)
            if row.expires_at is not None and row.expires_at <= datetime.now(UTC):
                return
            row.expires_at = datetime.now(UTC)

    def bind_to_contract(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        contract_draft_id: str,
    ) -> None:
        with self._factory() as session, session.begin():
            record = self._require_owned_input(session, session_id, input_id, project_id)
            draft_id = _uuid_or_none(contract_draft_id)
            draft = (
                session.get(ResearchContractDraftModel, draft_id)
                if draft_id is not None
                else None
            )
            if draft is None or draft.session_id != session_id:
                raise _not_found("RESOURCE_NOT_FOUND")
            _upsert_binding(session, record.id, project_id, contract_draft_id, None)

    def bind_to_run(
        self,
        *,
        session_id: str,
        input_id: str,
        project_id: str,
        run_id: str,
    ) -> None:
        with self._factory() as session, session.begin():
            record = self._require_owned_input(session, session_id, input_id, project_id)
            rid = _uuid_or_none(run_id)
            run = session.get(ResearchRunModel, rid) if rid is not None else None
            if run is None or run.project_id != _uuid_or_none(project_id):
                raise _not_found("RESOURCE_NOT_FOUND")
            _upsert_binding(session, record.id, project_id, None, run_id)

    @staticmethod
    def _require_owned_input(
        session: Session, session_id: str, input_id: str, project_id: str
    ) -> ResearchInputModel:
        iid = _uuid_or_none(input_id)
        row = session.get(ResearchInputModel, iid)
        if row is None or row.session_id != session_id:
            raise _not_found(RESEARCH_INPUT_NOT_FOUND)
        if str(row.project_id) != project_id:
            raise _not_found(RESEARCH_INPUT_NOT_FOUND)
        if _is_expired(row):
            raise _not_found(RESEARCH_INPUT_NOT_FOUND)
        return row


class PersistentIdempotencyRepository:
    """PostgreSQL request-identity mapping with lease ownership.

    Reservation is an ``INSERT`` against the ``(session_id, project_id,
    idempotency_key)`` primary key. Concurrency is decided by the database: the
    loser of the insert race reads the existing row and either replays it,
    conflicts on a different request hash, or reclaims a stale lease. A pending
    reservation is never left dangling as a persistent unrecoverable state.
    """

    def __init__(
        self,
        factory: Callable[[], Session],
        *,
        clock: Callable[[], datetime] | None = None,
        lease_ttl: timedelta = DEFAULT_LEASE_TTL,
    ) -> None:
        self._factory = factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lease_ttl = lease_ttl

    def _new_token(self) -> str:
        return secrets.token_urlsafe(24)

    def resolve(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        request_hash: str,
    ) -> IdempotencyReservation:
        pid = _uuid_or_none(project_id)
        now = self._clock()
        with self._factory() as session, session.begin():
            existing = session.get(
                ResearchInputIdempotencyModel, (session_id, pid, idempotency_key)
            )
            if existing is not None:
                return _reservation_from_row(existing, request_hash, now=now)

            token = self._new_token()
            row = ResearchInputIdempotencyModel(
                session_id=session_id,
                project_id=pid,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                input_id=None,
                status=IDEMPOTENCY_PENDING,
                lease_token=token,
                lease_expires_at=now + self._lease_ttl,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
            else:
                return IdempotencyReservation(
                    replayed_input_id=None,
                    reserved=True,
                    lease_token=token,
                    lease_expires_at=now + self._lease_ttl,
                )

        # Lost the insert race: the winner's row is authoritative.
        with self._factory() as session, session.begin():
            winner = session.get(
                ResearchInputIdempotencyModel, (session_id, pid, idempotency_key)
            )
            if winner is None:
                raise _conflict_unresolved()
            return _reservation_from_row(winner, request_hash, now=now)

    def release(
        self,
        *,
        session_id: str,
        project_id: str,
        idempotency_key: str,
        lease_token: str,
    ) -> None:
        pid = _uuid_or_none(project_id)
        with self._factory() as session, session.begin():
            row = session.get(
                ResearchInputIdempotencyModel,
                (session_id, pid, idempotency_key),
                with_for_update=True,
            )
            if row is None:
                return
            if row.status == IDEMPOTENCY_PENDING and row.lease_token == lease_token:
                session.delete(row)


# ---- state-machine helpers -------------------------------------------------


def _reservation_from_row(
    row: ResearchInputIdempotencyModel, request_hash: str, *, now: datetime
) -> IdempotencyReservation:
    if row.request_hash != request_hash:
        raise _idempotency_conflict()
    if row.status == IDEMPOTENCY_COMPLETED and row.input_id is not None:
        return IdempotencyReservation(
            replayed_input_id=str(row.input_id), reserved=False
        )
    # pending: decide in-progress vs reclaimable by lease expiry.
    if row.lease_expires_at is not None and row.lease_expires_at > now:
        raise _idempotency_in_progress()
    # Stale lease: reclaim with a fresh token.
    new_token = secrets.token_urlsafe(24)
    new_expiry = now + DEFAULT_LEASE_TTL
    row.lease_token = new_token
    row.lease_expires_at = new_expiry
    row.updated_at = now
    return IdempotencyReservation(
        replayed_input_id=None,
        reserved=True,
        lease_token=new_token,
        lease_expires_at=new_expiry,
    )


def _ensure_content_memory(
    contents: dict[tuple[str, str], tuple[str, str, int]],
    *,
    project_id: str,
    content_hash: str,
    storage_ref: str,
    mime_type: str,
    size_bytes: int,
) -> None:
    key = (project_id, content_hash)
    existing = contents.get(key)
    if existing is not None:
        _assert_content_consistent(existing, storage_ref, mime_type, size_bytes)
        return
    contents[key] = (storage_ref, mime_type, size_bytes)


def _ensure_content_row(
    session: Session,
    *,
    project_id: UUID,
    content_hash: str,
    storage_ref: str,
    mime_type: str,
    size_bytes: int,
) -> None:
    existing = session.get(
        ResearchInputContentModel, (project_id, content_hash)
    )
    if existing is not None:
        _assert_content_consistent(
            (existing.storage_ref, existing.mime_type, existing.size_bytes),
            storage_ref,
            mime_type,
            size_bytes,
        )
        return
    row = ResearchInputContentModel(
        project_id=project_id,
        content_hash=content_hash,
        storage_ref=storage_ref,
        mime_type=mime_type,
        size_bytes=size_bytes,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        # Another worker won the upsert race; re-read the winner.
        session.rollback()
        winner = session.get(
            ResearchInputContentModel, (project_id, content_hash)
        )
        if winner is None:
            raise _conflict_unresolved() from None
        _assert_content_consistent(
            (winner.storage_ref, winner.mime_type, winner.size_bytes),
            storage_ref,
            mime_type,
            size_bytes,
        )


def _assert_content_consistent(
    existing: tuple[str, str, int],
    storage_ref: str,
    mime_type: str,
    size_bytes: int,
) -> None:
    ex_ref, ex_mime, ex_size = existing
    if ex_ref != storage_ref or ex_size != size_bytes or ex_mime != mime_type:
        raise SecurityProblem(
            status=500,
            code="CONTENT_INTEGRITY_CONFLICT",
            title="Content integrity conflict",
            detail="An existing content row with the same hash has different bytes",
        )


# ---- value helpers ---------------------------------------------------------


def _source_type_for(payload: ResearchInputCreate) -> str:
    if payload.type is ResearchInputType.url:
        return URL_FETCH_SOURCE_TYPE
    if payload.type is ResearchInputType.text:
        return TEXT_SOURCE_TYPE
    return UPLOAD_SOURCE_TYPE


def _snapshot_url(source: SourceSnapshotRecord | None) -> str | None:
    if source is None:
        return None
    query = source.query
    return query if isinstance(query, str) else str(query)


def _persist_snapshot(
    session: Session, *, project_id: str, source: SourceSnapshotRecord | None
) -> UUID | None:
    if source is None:
        return None
    snapshot = SourceSnapshotModel(
        project_id=_uuid_or_none(project_id),
        source_id=source.source_id,
        source_type=source.source_type,
        retrieved_at=source.retrieved_at,
        query=source.query,
        query_hash=source.query_hash,
        source_version_or_etag=source.source_version_or_etag,
        content_hash=source.content_hash,
        license_note=source.license_note,
        cache_version=source.cache_version,
        request_metadata=source.request_metadata,
    )
    session.add(snapshot)
    session.flush()
    return snapshot.id


def _record(
    row: ResearchInputModel,
    *,
    session: Session | None = None,
    content: tuple[str, str | None, int] | None = None,
    url: str | None = None,
) -> ResearchInputRecord:
    if content is not None:
        storage_ref, mime_type, size_bytes = content
    elif session is not None:
        content_row = session.get(
            ResearchInputContentModel, (row.project_id, row.content_hash)
        )
        storage_ref = content_row.storage_ref if content_row is not None else row.storage_ref
        mime_type = (
            content_row.mime_type
            if content_row is not None and content_row.mime_type
            else row.mime_type
        )
        size_bytes = (
            content_row.size_bytes if content_row is not None else row.size_bytes
        )
    else:
        storage_ref, mime_type, size_bytes = (
            row.storage_ref,
            row.mime_type,
            row.size_bytes,
        )
    if url is None:
        url = (
            _snapshot_query_url(session, row)
            if session is not None
            else None
        )
    return ResearchInputRecord(
        id=str(row.id),
        session_id=row.session_id,
        project_id=str(row.project_id),
        type=ResearchInputType(row.type),
        source_type=row.source_type,
        content_hash=row.content_hash,
        storage_ref=storage_ref,
        filename=row.filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        status=ResearchInputStatus(row.status),
        source_snapshot_id=(
            str(row.source_snapshot_id) if row.source_snapshot_id is not None else None
        ),
        url=url,
        created_at=_utc(row.created_at),
        expires_at=_utc(row.expires_at) if row.expires_at is not None else None,
    )


def _snapshot_query_url(session: Session, row: ResearchInputModel) -> str | None:
    if row.source_snapshot_id is None:
        return None
    snapshot = session.get(SourceSnapshotModel, row.source_snapshot_id)
    if snapshot is None or not isinstance(snapshot.query, str):
        return None
    return snapshot.query


def _upsert_binding(
    session: Session,
    input_id: UUID,
    project_id: str,
    contract_draft_id: str | None,
    run_id: str | None,
) -> None:
    binding = session.get(ResearchInputBindingModel, input_id)
    if binding is None:
        binding = ResearchInputBindingModel(
            input_id=input_id,
            project_id=_uuid_or_none(project_id),
            contract_draft_id=(
                _uuid_or_none(contract_draft_id) if contract_draft_id is not None else None
            ),
            run_id=_uuid_or_none(run_id) if run_id is not None else None,
            bound_at=datetime.now(UTC),
        )
        session.add(binding)
    else:
        binding.contract_draft_id = (
            _uuid_or_none(contract_draft_id) if contract_draft_id is not None else None
        )
        binding.run_id = _uuid_or_none(run_id) if run_id is not None else None
        binding.bound_at = datetime.now(UTC)


def _is_expired(row: ResearchInputModel) -> bool:
    return row.expires_at is not None and row.expires_at <= datetime.now(UTC)


def _idempotency_conflict() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_CONFLICT",
        title="Idempotency key reuse conflict",
        detail="The Idempotency-Key header was reused with a different request body",
    )


def _idempotency_in_progress() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_IN_PROGRESS",
        title="Idempotent request in progress",
        detail="An identical request with this Idempotency-Key is still being processed",
    )


def _idempotency_reservation_lost() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_RESERVATION_LOST",
        title="Idempotency reservation lost",
        detail="The reservation lease was reclaimed by another request",
    )


def _conflict_unresolved() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_CONFLICT",
        title="Concurrent request conflict",
        detail="A concurrent request for this resource could not be resolved",
    )


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404, code=code, title="Resource not found", detail="Resource not found"
    )


def _invalid_cursor() -> SecurityProblem:
    return SecurityProblem(
        status=400,
        code="INVALID_CURSOR",
        title="Invalid cursor",
        detail="The pagination cursor is invalid for this collection",
    )


def _encode_cursor(value: str) -> str:
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str) -> str:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise _invalid_cursor() from None
    if not decoded:
        raise _invalid_cursor()
    return decoded


def _memory_cursor_start(records: list[ResearchInputRecord], cursor: str | None) -> int:
    if cursor is None:
        return 0
    anchor_id = _decode_cursor(cursor)
    for index, record in enumerate(records):
        if record.id == anchor_id:
            return index + 1
    raise _invalid_cursor()


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "DEFAULT_LEASE_TTL",
    "FILE_INPUT_TYPES",
    "IDEMPOTENCY_COMPLETED",
    "IDEMPOTENCY_PENDING",
    "IdempotencyReservation",
    "InMemoryIdempotencyRepository",
    "InMemoryResearchInputStore",
    "PersistentIdempotencyRepository",
    "PersistentResearchInputStore",
    "PreparedInput",
    "ResearchInputIdempotencyRepository",
    "ResearchInputRecord",
    "ResearchInputRepository",
]
