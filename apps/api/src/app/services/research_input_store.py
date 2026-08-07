"""Research Input persistence port and ingestion domain logic (B-19).

Ownership-scoped records live behind the :class:`ResearchInputStore` Protocol
with in-memory (tests/process-local) and PostgreSQL adapters. This module also
owns the MIME sniffing and filename sanitization rules: the transport layer
never trusts client headers, so every uploaded byte is classified from magic
bytes before it may enter the immutable content store.
"""

from __future__ import annotations

import base64
import dataclasses
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ResearchContractDraftModel,
    ResearchInputBindingModel,
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

_MAX_FILENAME_LENGTH = 255

#: MIME prefixes accepted per declared ResearchInputType.
_TYPE_MIME_FAMILIES: dict[ResearchInputType, tuple[str, ...]] = {
    ResearchInputType.url: (
        "application/pdf",
        "text/csv",
        "application/json",
        "image/",
        "text/plain",
    ),
    ResearchInputType.pdf: ("application/pdf",),
    ResearchInputType.csv: ("text/csv",),
    ResearchInputType.json: ("application/json",),
    ResearchInputType.image: ("image/",),
    ResearchInputType.text: ("text/plain",),
}


_FILENAME_EXTENSION_MIME: dict[str, tuple[str, ...]] = {
    "pdf": ("application/pdf",),
    "csv": ("text/csv",),
    "json": ("application/json",),
    "png": ("image/png",),
    "jpg": ("image/jpeg",),
    "jpeg": ("image/jpeg",),
    "gif": ("image/gif",),
    "webp": ("image/webp",),
    "txt": ("text/plain",),
}

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_ANY_CHARACTER_BUT_SEPARATORS = re.compile(r"[^/\\]+$")


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
    """Validated ingestion facts produced by the transport and frozen by the store."""

    content_hash: str
    storage_ref: str
    size_bytes: int
    mime_type: str | None
    filename: str | None
    source_snapshot: SourceSnapshotRecord | None


class ResearchInputStore(Protocol):
    """Ownership-scoped persistence boundary for ingested inputs."""

    def create(
        self,
        *,
        session_id: str,
        project_id: str,
        payload: ResearchInputCreate,
        prepared: PreparedInput,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> ResearchInputRecord:
        """Ingest one input; replay by ``(session_id, project_id, content_hash)`` is reused."""

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


class InMemoryResearchInputStore:
    """Process-local adapter for unit/security tests and the no-DB runtime."""

    def __init__(self) -> None:
        self._records: dict[str, ResearchInputRecord] = {}
        self._projects: dict[str, str] = {}
        self._drafts: dict[str, str] = {}
        self._runs: dict[str, str] = {}
        self._bindings: dict[str, tuple[str, str | None, str | None]] = {}
        self._idempotency: dict[tuple[str, str, str], tuple[ResearchInputRecord, str]] = {}

    def register_project(self, *, project_id: str, owner_session_id: str) -> None:
        self._projects[project_id] = owner_session_id

    def register_contract_draft(self, *, draft_id: str, owner_session_id: str) -> None:
        self._drafts[draft_id] = owner_session_id

    def register_run(self, *, run_id: str, project_id: str) -> None:
        self._runs[run_id] = project_id

    def create(
        self,
        *,
        session_id: str,
        project_id: str,
        payload: ResearchInputCreate,
        prepared: PreparedInput,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> ResearchInputRecord:
        if self._projects.get(project_id) != session_id:
            raise _not_found("PROJECT_NOT_FOUND")

        if idempotency_key is not None and request_hash is not None:
            idem_key = (session_id, project_id, idempotency_key)
            if idem_key in self._idempotency:
                saved_record, saved_hash = self._idempotency[idem_key]
                if saved_hash != request_hash:
                    raise _idempotency_conflict()
                return saved_record

        existing = next(
            (
                record
                for record in self._records.values()
                if record.session_id == session_id
                and record.project_id == project_id
                and record.content_hash == prepared.content_hash
            ),
            None,
        )
        now = datetime.now(UTC)
        if existing is not None:
            if existing.expires_at is not None and existing.expires_at <= now:
                resurrected = dataclasses.replace(
                    existing,
                    type=payload.type,
                    source_type=_source_type_for(payload),
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
                    expires_at=None,
                )
                self._records[existing.id] = resurrected
                if idempotency_key is not None and request_hash is not None:
                    self._idempotency[(session_id, project_id, idempotency_key)] = (
                        resurrected,
                        request_hash,
                    )
                return resurrected
            if idempotency_key is not None and request_hash is not None:
                self._idempotency[(session_id, project_id, idempotency_key)] = (
                    existing,
                    request_hash,
                )
            return existing

        source_type = _source_type_for(payload)
        record = ResearchInputRecord(
            id=f"input_{secrets.token_urlsafe(18)}",
            session_id=session_id,
            project_id=project_id,
            type=payload.type,
            source_type=source_type,
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
        if idempotency_key is not None and request_hash is not None:
            self._idempotency[(session_id, project_id, idempotency_key)] = (
                record,
                request_hash,
            )
        return record

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        record = self._records.get(input_id)
        if record is None or record.session_id != session_id:
            return None
        if record.expires_at is not None and record.expires_at <= datetime.now(UTC):
            return None
        return record

    def list(
        self, *, session_id: str, project_id: str, cursor: str | None, limit: int
    ) -> tuple[tuple[ResearchInputRef, ...], str | None, bool]:
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
        next_cursor = (
            _encode_cursor(selected[-1].id) if selected and has_more else None
        )
        return (
            tuple(record.to_ref() for record in selected),
            next_cursor,
            has_more,
        )

    def delete(self, *, session_id: str, input_id: str) -> None:
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


class PersistentResearchInputStore:
    """PostgreSQL-backed adapter sharing the same ownership semantics."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def create(
        self,
        *,
        session_id: str,
        project_id: str,
        payload: ResearchInputCreate,
        prepared: PreparedInput,
        idempotency_key: str | None = None,
        request_hash: str | None = None,
    ) -> ResearchInputRecord:
        pid = _uuid_or_none(project_id)
        with self._factory() as session, session.begin():
            project = session.get(ResearchProjectModel, pid)
            if project is None or project.session_id != session_id:
                raise _not_found("PROJECT_NOT_FOUND")

            if idempotency_key is not None and request_hash is not None:
                replay = session.scalar(
                    select(ResearchInputModel).where(
                        ResearchInputModel.session_id == session_id,
                        ResearchInputModel.project_id == project.id,
                        ResearchInputModel.idempotency_key == idempotency_key,
                    )
                )
                if replay is not None:
                    if replay.request_hash != request_hash:
                        raise _idempotency_conflict()
                    return _record(replay, url=_snapshot_query_url(session, replay))

            existing = session.scalar(
                select(ResearchInputModel).where(
                    ResearchInputModel.session_id == session_id,
                    ResearchInputModel.project_id == project.id,
                    ResearchInputModel.content_hash == prepared.content_hash,
                )
            )
            now = datetime.now(UTC)
            if existing is not None:
                if existing.expires_at is not None and existing.expires_at <= now:
                    _resurrect(session, existing, payload, prepared)
                    session.flush()
                if idempotency_key is not None and request_hash is not None:
                    existing.idempotency_key = idempotency_key
                    existing.request_hash = request_hash
                    session.flush()
                return _record(existing, url=_snapshot_query_url(session, existing))

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
                created_at=now,
                expires_at=None,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
            session.add(row)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                with self._factory() as replay_session, replay_session.begin():
                    replay = replay_session.scalar(
                        select(ResearchInputModel).where(
                            ResearchInputModel.session_id == session_id,
                            ResearchInputModel.project_id == project.id,
                            ResearchInputModel.content_hash == prepared.content_hash,
                        )
                    )
                if replay is None:
                    raise
                return _record(
                    replay, url=_snapshot_query_url(replay_session, replay)
                )
            return _record(row, url=_snapshot_url(prepared.source_snapshot))


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
            return _record(row, url=_snapshot_query_url(session, row))

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
                _encode_cursor(str(selected[-1].id))
                if selected and has_more
                else None
            )
            return (
                tuple(_record(row).to_ref() for row in selected),
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
            run = (
                session.get(ResearchRunModel, rid) if rid is not None else None
            )
            if (
                run is None
                or run.project_id != _uuid_or_none(project_id)
            ):
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


# ---- ingestion domain logic ------------------------------------------------


def sniff_mime_type(content: bytes) -> str | None:
    """Classify raw bytes from magic signatures; ``None`` means unknown."""

    if content.startswith(b"%PDF"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    stripped = content.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith((b"{", b"[")):
        return "application/json"
    if _looks_like_text(content):
        if _looks_like_csv(content):
            return "text/csv"
        return "text/plain"
    return None


def validate_declared_mime(
    *,
    declared_type: ResearchInputType,
    sniffed_mime: str | None,
    client_mime: str | None,
    allowed_mimes: frozenset[str] | None = None,
) -> str | None:
    """Return the authoritative MIME or ``None`` when the content is rejected.

    The declared type must be consistent with the sniffed content, and a
    client-supplied MIME hint (never trusted on its own) must agree as well.
    """

    if sniffed_mime is None:
        return None
    if not _mime_matches_type(sniffed_mime, declared_type):
        return None
    if client_mime is not None and _normalize_mime(client_mime) != sniffed_mime:
        return None
    if not _mime_allowed(sniffed_mime, allowed_mimes):
        return None
    return sniffed_mime


def sanitize_filename(raw: str | None) -> str | None:
    """Return a display-safe basename, or ``None`` when the name is unusable."""

    if raw is None:
        return None
    if not raw:
        return None
    cleaned = _CONTROL_CHARACTERS.sub("", raw).strip()
    cleaned = cleaned.replace("\\", "/")
    basename = _ANY_CHARACTER_BUT_SEPARATORS.search(cleaned)
    if basename is None:
        return None
    cleaned = basename.group(0).strip()
    if not cleaned or cleaned in {".", ".."}:
        return None
    if len(cleaned) > _MAX_FILENAME_LENGTH:
        return None
    return cleaned


def filename_extension_matches(filename: str, sniffed_mime: str) -> bool:
    """Enforce filename-extension/MIME consistency when an extension exists."""

    dot = filename.rfind(".")
    if dot <= 0:
        return True
    extension = filename[dot + 1 :].lower()
    allowed = _FILENAME_EXTENSION_MIME.get(extension)
    return allowed is None or sniffed_mime in allowed


# ---- helpers ---------------------------------------------------------------


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


def _snapshot_query_url(session: Session, row: ResearchInputModel) -> str | None:
    if row.source_snapshot_id is None:
        return None
    snapshot = session.get(SourceSnapshotModel, row.source_snapshot_id)
    if snapshot is None or not isinstance(snapshot.query, str):
        return None
    return snapshot.query


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


def _record(row: ResearchInputModel, *, url: str | None = None) -> ResearchInputRecord:
    return ResearchInputRecord(
        id=str(row.id),
        session_id=row.session_id,
        project_id=str(row.project_id),
        type=ResearchInputType(row.type),
        source_type=row.source_type,
        content_hash=row.content_hash,
        storage_ref=row.storage_ref,
        filename=row.filename,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        status=ResearchInputStatus(row.status),
        source_snapshot_id=(
            str(row.source_snapshot_id) if row.source_snapshot_id is not None else None
        ),
        url=url,
        created_at=_utc(row.created_at),
        expires_at=_utc(row.expires_at) if row.expires_at is not None else None,
    )


def _resurrect(
    session: Session,
    row: ResearchInputModel,
    payload: ResearchInputCreate,
    prepared: PreparedInput,
) -> None:
    row.type = payload.type.value
    row.source_type = _source_type_for(payload)
    row.storage_ref = prepared.storage_ref
    row.filename = prepared.filename
    row.mime_type = prepared.mime_type
    row.size_bytes = prepared.size_bytes
    row.status = ResearchInputStatus.accepted.value
    row.source_snapshot_id = _persist_snapshot(
        session, project_id=str(row.project_id), source=prepared.source_snapshot
    )
    row.expires_at = None



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
                _uuid_or_none(contract_draft_id)
                if contract_draft_id is not None
                else None
            ),
            run_id=_uuid_or_none(run_id) if run_id is not None else None,
            bound_at=datetime.now(UTC),
        )
        session.add(binding)
    else:
        binding.contract_draft_id = (
            _uuid_or_none(contract_draft_id)
            if contract_draft_id is not None
            else None
        )
        binding.run_id = _uuid_or_none(run_id) if run_id is not None else None
        binding.bound_at = datetime.now(UTC)


def _mime_matches_type(mime: str, declared_type: ResearchInputType) -> bool:
    families = _TYPE_MIME_FAMILIES[declared_type]
    return any(mime.startswith(family) for family in families)


def _mime_allowed(mime: str, allowed_mimes: frozenset[str] | None) -> bool:
    if allowed_mimes is None:
        from app.config import settings

        allowed_mimes = frozenset(
            _normalize_mime(item) for item in settings.RESEARCH_INPUT_ALLOWED_MIME_TYPES
        )
    return mime in allowed_mimes


def _looks_like_text(content: bytes) -> bool:
    if b"\x00" in content:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    sample = content[:4096]
    if not sample:
        return False
    binary_bytes = sum(
        1 for byte in sample if byte < 9 or 13 < byte < 32 or byte == 127
    )
    return binary_bytes * 20 < len(sample)


def _looks_like_csv(content: bytes) -> bool:
    head = content[:8192]
    has_newline = b"\n" in head or b"\r" in head
    has_delimiter = any(byte in head for byte in b",;\t")
    return has_newline and has_delimiter


def _normalize_mime(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _is_expired(row: ResearchInputModel) -> bool:
    return row.expires_at is not None and row.expires_at <= datetime.now(UTC)


def _idempotency_conflict() -> SecurityProblem:
    return SecurityProblem(
        status=409,
        code="IDEMPOTENCY_CONFLICT",
        title="Idempotency key reuse conflict",
        detail="The Idempotency-Key header was reused with a different request body",
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


def _memory_cursor_start(
    records: list[ResearchInputRecord], cursor: str | None
) -> int:
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
    "FILE_INPUT_TYPES",
    "InMemoryResearchInputStore",
    "PersistentResearchInputStore",
    "PreparedInput",
    "ResearchInputRecord",
    "ResearchInputStore",
    "filename_extension_matches",
    "sanitize_filename",
    "sniff_mime_type",
    "validate_declared_mime",
]
