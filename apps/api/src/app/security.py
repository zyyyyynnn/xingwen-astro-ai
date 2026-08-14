"""Anonymous session, CSRF, ownership, and idempotency boundaries."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import RLock
from typing import Any, Protocol

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app import api_surface
from app.db.models import ResearchProjectModel, ResearchSessionModel
from app.schemas.core import SessionQuota, SessionStatus


_SHARE_TOKEN_PATH = re.compile(
    rf"({re.escape(api_surface.PUBLIC_SHARE_PREFIX)})[^/?\s]+"
)
_MAX_CONCURRENT_CSRF_TOKENS = 4


@dataclass(frozen=True, slots=True)
class SessionRecord:
    id: str
    credential_hash: str
    csrf_hashes: tuple[str, ...]
    status: SessionStatus
    created_at: datetime
    expires_at: datetime
    quota: SessionQuota
    security_version: int = 1


class SecurityProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.headers = headers or {}


class SessionStore(Protocol):
    def put(self, record: SessionRecord) -> None: ...

    def get(self, credential_hash: str) -> SessionRecord | None: ...

    def resume(
        self, credential_hash: str, csrf_hash: str, *, now: datetime
    ) -> SessionRecord | None: ...

    def revoke(
        self, credential_hash: str, *, now: datetime
    ) -> SessionRecord | None: ...


class InMemorySessionStore:
    """Process-local adapter for Session and Write Security; durable storage belongs to Workflow Persistence."""

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}
        self._lock = RLock()

    def put(self, record: SessionRecord) -> None:
        with self._lock:
            self._records[record.credential_hash] = record

    def get(self, credential_hash: str) -> SessionRecord | None:
        with self._lock:
            return self._records.get(credential_hash)

    def resume(
        self,
        credential_hash: str,
        csrf_hash: str,
        *,
        now: datetime,
    ) -> SessionRecord | None:
        """Atomically validate a session and append one bounded CSRF hash."""
        with self._lock:
            record = self._records.get(credential_hash)
            if (
                record is None
                or record.status is not SessionStatus.active
                or record.expires_at <= now
            ):
                return None
            resumed = SessionRecord(
                id=record.id,
                credential_hash=record.credential_hash,
                csrf_hashes=(*record.csrf_hashes, csrf_hash)[
                    -_MAX_CONCURRENT_CSRF_TOKENS:
                ],
                status=record.status,
                created_at=record.created_at,
                expires_at=record.expires_at,
                quota=record.quota,
                security_version=record.security_version + 1,
            )
            self._records[credential_hash] = resumed
            return resumed

    def revoke(
        self, credential_hash: str, *, now: datetime
    ) -> SessionRecord | None:
        with self._lock:
            record = self._records.get(credential_hash)
            if record is None:
                return None
            revoked = SessionRecord(
                id=record.id,
                credential_hash=record.credential_hash,
                csrf_hashes=(),
                status=SessionStatus.revoked,
                created_at=record.created_at,
                expires_at=record.expires_at,
                quota=record.quota,
                security_version=record.security_version + 1,
            )
            self._records[credential_hash] = revoked
            return revoked


class PersistentSessionStore:
    """PostgreSQL session store shared by every API process."""

    def __init__(
        self,
        factory: Callable[[], Session],
        *,
        retention: timedelta | None = None,
    ) -> None:
        self._factory = factory
        self._retention = retention

    def put(self, record: SessionRecord) -> None:
        with self._factory() as session, session.begin():
            session.add(
                ResearchSessionModel(
                    id=record.id,
                    credential_hash=record.credential_hash,
                    csrf_hashes=list(record.csrf_hashes),
                    status=record.status.value,
                    created_at=record.created_at,
                    expires_at=record.expires_at,
                    revoked_at=None,
                    security_version=record.security_version,
                    quota=record.quota.model_dump(mode="json"),
                    updated_at=record.created_at,
                )
            )
            session.flush()
            if self._retention is not None:
                self._cleanup(
                    session,
                    now=record.created_at,
                    retention=self._retention,
                )

    def get(self, credential_hash: str) -> SessionRecord | None:
        with self._factory() as session:
            row = session.scalar(
                select(ResearchSessionModel).where(
                    ResearchSessionModel.credential_hash == credential_hash
                )
            )
            return _session_record(row) if row is not None else None

    def resume(
        self,
        credential_hash: str,
        csrf_hash: str,
        *,
        now: datetime,
    ) -> SessionRecord | None:
        with self._factory() as session, session.begin():
            row = session.scalar(
                select(ResearchSessionModel)
                .where(ResearchSessionModel.credential_hash == credential_hash)
                .with_for_update()
            )
            if row is None or row.status != "active" or _utc(row.expires_at) <= now:
                return None
            hashes = tuple(str(item) for item in row.csrf_hashes)
            row.csrf_hashes = list(
                (*hashes, csrf_hash)[-_MAX_CONCURRENT_CSRF_TOKENS:]
            )
            row.security_version += 1
            row.updated_at = now
            session.flush()
            return _session_record(row)

    def revoke(
        self, credential_hash: str, *, now: datetime
    ) -> SessionRecord | None:
        with self._factory() as session, session.begin():
            row = session.scalar(
                select(ResearchSessionModel)
                .where(ResearchSessionModel.credential_hash == credential_hash)
                .with_for_update()
            )
            if row is None:
                return None
            if row.status != "revoked":
                row.status = "revoked"
                row.csrf_hashes = []
                row.revoked_at = now
                row.security_version += 1
                row.updated_at = now
                session.flush()
            return _session_record(row)

    def cleanup(self, *, now: datetime, retention: timedelta) -> int:
        """Delete old unreferenced sessions without deleting owned research history."""

        with self._factory() as session, session.begin():
            return self._cleanup(session, now=now, retention=retention)

    @staticmethod
    def _cleanup(
        session: Session, *, now: datetime, retention: timedelta
    ) -> int:
        cutoff = now - retention
        referenced_project = (
            select(ResearchProjectModel.id)
            .where(ResearchProjectModel.session_id == ResearchSessionModel.id)
            .exists()
        )
        result = session.execute(
            delete(ResearchSessionModel).where(
                ~referenced_project,
                or_(
                    ResearchSessionModel.expires_at <= cutoff,
                    (
                        (ResearchSessionModel.status == "revoked")
                        & (ResearchSessionModel.updated_at <= cutoff)
                    ),
                ),
            )
        )
        return int(result.rowcount or 0)


class SessionService:
    def __init__(self, store: SessionStore, *, ttl_seconds: int) -> None:
        self.store = store
        self.ttl_seconds = ttl_seconds

    def create(self, *, now: datetime | None = None) -> tuple[SessionRecord, str, str]:
        current = now or datetime.now(UTC)
        credential = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        record = SessionRecord(
            id=f"sess_{secrets.token_urlsafe(18)}",
            credential_hash=_hash_secret(credential),
            csrf_hashes=(_hash_secret(csrf_token),),
            status=SessionStatus.active,
            created_at=current,
            expires_at=current + timedelta(seconds=self.ttl_seconds),
            quota=SessionQuota(),
            security_version=1,
        )
        self.store.put(record)
        return record, credential, csrf_token

    def resume(
        self, credential: str, *, now: datetime | None = None
    ) -> tuple[SessionRecord, str] | None:
        """Resume an existing session from its cookie credential.

        Returns the session record plus a freshly issued CSRF token when the
        credential maps to an active, unexpired session; ``None`` otherwise.
        The cookie credential is preserved, so a browser refresh recovers the
        same anonymous session instead of spawning a parallel one.

        The new token is *added* to a bounded set of valid CSRF tokens (most
        recent ``_MAX_CONCURRENT_CSRF_TOKENS``): previously issued tokens stay
        valid so parallel tabs and integration clients holding an earlier
        token are not silently broken, while the set cannot grow unbounded.
        """
        csrf_token = secrets.token_urlsafe(32)
        resumed = self.store.resume(
            _hash_secret(credential),
            _hash_secret(csrf_token),
            now=now or datetime.now(UTC),
        )
        return (resumed, csrf_token) if resumed is not None else None

    def authenticate(
        self, credential: str | None, *, now: datetime | None = None
    ) -> SessionRecord:
        if not credential:
            raise session_required()
        record = self.store.get(_hash_secret(credential))
        current = now or datetime.now(UTC)
        if record is None or record.status is not SessionStatus.active:
            raise session_required()
        if record.expires_at <= current:
            raise session_required()
        return record

    def verify_csrf(self, record: SessionRecord, csrf_token: str | None) -> None:
        candidate = _hash_secret(csrf_token) if csrf_token else ""
        if not csrf_token or not any(
            hmac.compare_digest(stored, candidate) for stored in record.csrf_hashes
        ):
            raise SecurityProblem(
                status=403,
                code="CSRF_INVALID",
                title="CSRF validation failed",
                detail="A valid CSRF token is required for this request",
            )

    def revoke(self, credential: str, *, now: datetime | None = None) -> None:
        self.store.revoke(
            _hash_secret(credential), now=now or datetime.now(UTC)
        )


class OwnershipPolicy:
    @staticmethod
    def require_owner(
        *, owner_session_id: str, current_session_id: str, code: str
    ) -> None:
        if not hmac.compare_digest(owner_session_id, current_session_id):
            raise SecurityProblem(
                status=404,
                code=code,
                title="Resource not found",
                detail="Resource not found",
            )


def require_revision(*, expected: int, current: int) -> None:
    if expected != current:
        raise SecurityProblem(
            status=409,
            code="VERSION_CONFLICT",
            title="Version conflict",
            detail="The resource changed since it was read",
        )


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    response: Any


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str], IdempotencyRecord] = {}
        self._lock = RLock()

    def execute(
        self, *, session_id: str, scope: str, key: str, payload: Any, operation: Any
    ) -> tuple[Any, bool]:
        request_hash = canonical_request_hash(payload)
        identity = (session_id, scope, key)
        with self._lock:
            existing = self._records.get(identity)
            if existing is not None:
                if not hmac.compare_digest(existing.request_hash, request_hash):
                    raise SecurityProblem(
                        status=409,
                        code="IDEMPOTENCY_CONFLICT",
                        title="Idempotency conflict",
                        detail="The idempotency key was already used with a different request",
                    )
                return existing.response, True
            response = operation()
            self._records[identity] = IdempotencyRecord(
                request_hash=request_hash, response=response
            )
            return response, False


class InMemoryRateLimiter:
    def __init__(self, *, limit: int, window_seconds: int = 60) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._windows: dict[str, tuple[datetime, int]] = {}
        self._lock = RLock()

    def consume(self, key: str, *, now: datetime | None = None) -> tuple[int, int]:
        current = now or datetime.now(UTC)
        with self._lock:
            window_start, count = self._windows.get(key, (current, 0))
            if current >= window_start + timedelta(seconds=self.window_seconds):
                window_start, count = current, 0
            if count >= self.limit:
                reset_seconds = max(
                    1,
                    int(
                        (
                            window_start
                            + timedelta(seconds=self.window_seconds)
                            - current
                        ).total_seconds()
                    ),
                )
                raise SecurityProblem(
                    status=429,
                    code="RATE_LIMITED",
                    title="Rate limit exceeded",
                    detail="Too many requests; retry after the current window",
                    headers={
                        "RateLimit-Limit": str(self.limit),
                        "RateLimit-Remaining": "0",
                        "RateLimit-Reset": str(reset_seconds),
                        "Retry-After": str(reset_seconds),
                    },
                )
            count += 1
            self._windows[key] = (window_start, count)
            reset_seconds = max(
                0,
                int(
                    (
                        window_start + timedelta(seconds=self.window_seconds) - current
                    ).total_seconds()
                ),
            )
            return self.limit - count, reset_seconds


class ShareTokenAccessLogFilter(logging.Filter):
    """Redact raw share-token path segments from Uvicorn access records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_share_path(str(record.msg))
        if isinstance(record.args, tuple):
            record.args = tuple(
                _redact_share_path(value) if isinstance(value, str) else value
                for value in record.args
            )
        elif isinstance(record.args, dict):
            record.args = {
                key: _redact_share_path(value) if isinstance(value, str) else value
                for key, value in record.args.items()
            }
        return True


def install_share_token_access_log_filter() -> None:
    """Install one idempotent token-redaction filter on Uvicorn access logging."""

    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, ShareTokenAccessLogFilter) for item in logger.filters):
        logger.addFilter(ShareTokenAccessLogFilter())


def canonical_request_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _session_record(row: ResearchSessionModel) -> SessionRecord:
    return SessionRecord(
        id=row.id,
        credential_hash=row.credential_hash,
        csrf_hashes=tuple(str(item) for item in row.csrf_hashes),
        status=SessionStatus(row.status),
        created_at=_utc(row.created_at),
        expires_at=_utc(row.expires_at),
        quota=SessionQuota.model_validate(row.quota),
        security_version=row.security_version,
    )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def session_required() -> SecurityProblem:
    return SecurityProblem(
        status=401,
        code="SESSION_REQUIRED",
        title="Session required",
        detail="A valid anonymous session is required",
    )


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _redact_share_path(value: str) -> str:
    return _SHARE_TOKEN_PATH.sub(r"\1[REDACTED]", value)
