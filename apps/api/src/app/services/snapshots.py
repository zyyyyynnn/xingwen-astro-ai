"""Private workspace recovery and immutable public-share application boundary."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock

from app.schemas.v2 import (
    CreateShareSnapshotRequest,
    PublicArtifactVersion,
    PublicEvidence,
    PublicShareSnapshot,
    ShareSnapshot,
    ShareSnapshotCreated,
    ShareStatus,
    WorkspaceObjectRef,
    WorkspaceSnapshot,
    WorkspaceSnapshotInput,
)
from app.security import OwnershipPolicy, SecurityProblem, require_revision
from app.services.resource_authority import (
    InMemoryResourceAuthority,
    ResourceAuthority,
)


SHARE_TOKEN_BYTES = 32


@dataclass(frozen=True, slots=True)
class _WorkspaceRecord:
    owner_session_id: str
    payload: WorkspaceSnapshotInput
    snapshot: WorkspaceSnapshot


@dataclass(frozen=True, slots=True)
class _ShareRecord:
    owner_session_id: str
    token_hash: str
    snapshot: ShareSnapshot
    artifact_versions: tuple[PublicArtifactVersion, ...]
    evidence: tuple[PublicEvidence, ...]


class InMemorySnapshotStore:
    """Process-local adapter preserving B-17 concurrency and security semantics."""

    def __init__(self, authority: ResourceAuthority | None = None) -> None:
        self._authority: ResourceAuthority = authority or InMemoryResourceAuthority()
        self._workspaces: dict[tuple[str, str], _WorkspaceRecord] = {}
        self._shares: dict[str, _ShareRecord] = {}
        self._share_by_token_hash: dict[str, str] = {}
        self._lock = RLock()

    def _memory_authority(self) -> InMemoryResourceAuthority:
        if not isinstance(self._authority, InMemoryResourceAuthority):
            raise TypeError(
                "register_* is only supported by the in-memory resource authority"
            )
        return self._authority

    def register_project(self, *, project_id: str, owner_session_id: str) -> None:
        """Seed an ownership fact (in-memory authority only; tests/back-compat)."""

        self._memory_authority().register_project(
            project_id=project_id, owner_session_id=owner_session_id
        )

    def register_run(self, *, run_id: str, project_id: str) -> None:
        """Seed a Run reference that workspace state may restore (in-memory only)."""

        self._memory_authority().register_run(run_id=run_id, project_id=project_id)

    def register_artifact_version(
        self, *, project_id: str, projection: PublicArtifactVersion
    ) -> None:
        """Seed immutable version metadata eligible for a share (in-memory only)."""

        self._memory_authority().register_artifact_version(
            project_id=project_id, projection=projection
        )

    def register_evidence(self, *, project_id: str, projection: PublicEvidence) -> None:
        """Seed minimal Evidence metadata eligible for a share (in-memory only)."""

        self._memory_authority().register_evidence(
            project_id=project_id, projection=projection
        )

    def get_workspace(self, *, project_id: str, session_id: str) -> WorkspaceSnapshot:
        """Return the private snapshot owned by the current session."""

        with self._lock:
            self._require_project_owner(project_id=project_id, session_id=session_id)
            record = self._workspaces.get((session_id, project_id))
            if record is None:
                raise _not_found("WORKSPACE_SNAPSHOT_NOT_FOUND")
            return record.snapshot

    def save_workspace(
        self,
        *,
        project_id: str,
        session_id: str,
        expected_revision: int,
        payload: WorkspaceSnapshotInput,
        now: datetime,
    ) -> WorkspaceSnapshot:
        """Atomically create or replace private state using an optimistic revision."""

        with self._lock:
            self._require_project_owner(project_id=project_id, session_id=session_id)
            self._validate_workspace_references(project_id=project_id, payload=payload)
            identity = (session_id, project_id)
            current = self._workspaces.get(identity)
            if current is not None and current.payload == payload:
                return current.snapshot
            current_revision = current.snapshot.revision if current is not None else 0
            require_revision(expected=expected_revision, current=current_revision)
            snapshot = WorkspaceSnapshot(
                **payload.model_dump(),
                id=current.snapshot.id if current is not None else _new_id("ws"),
                project_id=project_id,
                revision=current_revision + 1,
                updated_at=now,
            )
            self._workspaces[identity] = _WorkspaceRecord(
                owner_session_id=session_id,
                payload=payload,
                snapshot=snapshot,
            )
            return snapshot

    def create_share(
        self,
        *,
        project_id: str,
        session_id: str,
        request: CreateShareSnapshotRequest,
        now: datetime,
    ) -> ShareSnapshotCreated:
        """Freeze one public projection and return its raw token exactly once."""

        with self._lock:
            self._require_project_owner(project_id=project_id, session_id=session_id)
            if request.expires_at <= now:
                raise SecurityProblem(
                    status=422,
                    code="SHARE_EXPIRY_INVALID",
                    title="Invalid share expiry",
                    detail="Share expiry must be in the future",
                )
            versions = self._share_versions(project_id, request.artifact_version_ids)
            evidence = self._share_evidence(
                project_id,
                request.evidence_ids,
                allowed_version_ids=set(request.artifact_version_ids),
            )
            share_id = _new_id("share")
            raw_token = secrets.token_urlsafe(SHARE_TOKEN_BYTES)
            token_hash = _hash_token(raw_token)
            snapshot = ShareSnapshot(
                id=share_id,
                project_id=project_id,
                title=request.title,
                artifact_version_ids=request.artifact_version_ids,
                evidence_ids=request.evidence_ids,
                redaction_policy=request.redaction_policy,
                status=ShareStatus.active,
                created_at=now,
                expires_at=request.expires_at,
            )
            self._shares[share_id] = _ShareRecord(
                owner_session_id=session_id,
                token_hash=token_hash,
                snapshot=snapshot,
                artifact_versions=versions,
                evidence=evidence,
            )
            self._share_by_token_hash[token_hash] = share_id
            return ShareSnapshotCreated(
                **snapshot.model_dump(),
                share_token=raw_token,
                share_url=f"/api/v2/shares/{raw_token}",
            )

    def list_shares(
        self,
        *,
        project_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
        now: datetime,
    ) -> tuple[tuple[ShareSnapshot, ...], str | None, bool]:
        """List private share metadata with a stable opaque cursor and no token material."""

        with self._lock:
            self._require_project_owner(project_id=project_id, session_id=session_id)
            records = sorted(
                (
                    record
                    for record in self._shares.values()
                    if record.snapshot.project_id == project_id
                    and hmac.compare_digest(record.owner_session_id, session_id)
                ),
                key=lambda item: (item.snapshot.created_at, item.snapshot.id),
                reverse=True,
            )
            start = self._cursor_start(records, cursor)
            selected = records[start : start + limit]
            has_more = start + len(selected) < len(records)
            next_cursor = (
                _encode_cursor(selected[-1].snapshot.id)
                if selected and has_more
                else None
            )
            return (
                tuple(
                    self._snapshot_status(record.snapshot, now) for record in selected
                ),
                next_cursor,
                has_more,
            )

    def revoke_share(
        self,
        *,
        project_id: str,
        share_id: str,
        session_id: str,
        now: datetime,
    ) -> None:
        """Idempotently revoke a share owned by the current Project session."""

        with self._lock:
            self._require_project_owner(project_id=project_id, session_id=session_id)
            record = self._shares.get(share_id)
            if (
                record is None
                or record.snapshot.project_id != project_id
                or not hmac.compare_digest(record.owner_session_id, session_id)
            ):
                raise _not_found("SHARE_NOT_FOUND")
            if record.snapshot.revoked_at is None:
                snapshot = record.snapshot.model_copy(
                    update={"status": ShareStatus.revoked, "revoked_at": now}
                )
                self._shares[share_id] = replace(record, snapshot=snapshot)

    def resolve_public_share(
        self, *, raw_token: str, now: datetime
    ) -> PublicShareSnapshot:
        """Resolve only active shares while making invalid, expired, and revoked tokens identical."""

        with self._lock:
            token_hash = _hash_token(raw_token)
            share_id = self._share_by_token_hash.get(token_hash)
            record = self._shares.get(share_id) if share_id is not None else None
            if record is None or not hmac.compare_digest(record.token_hash, token_hash):
                raise _not_found("SHARE_NOT_FOUND")
            snapshot = self._snapshot_status(record.snapshot, now)
            if snapshot.status is not ShareStatus.active:
                raise _not_found("SHARE_NOT_FOUND")
            return PublicShareSnapshot(
                id=snapshot.id,
                title=snapshot.title,
                artifact_versions=record.artifact_versions,
                evidence=record.evidence,
                redaction_policy=snapshot.redaction_policy,
                created_at=snapshot.created_at,
                expires_at=snapshot.expires_at,
            )

    def token_hash_for_testing(self, share_id: str) -> str:
        """Expose only the irreversible hash for storage-policy contract tests."""

        with self._lock:
            return self._shares[share_id].token_hash

    def _require_project_owner(self, *, project_id: str, session_id: str) -> None:
        owner_session_id = self._authority.project_owner(project_id)
        if owner_session_id is None:
            raise _not_found("PROJECT_NOT_FOUND")
        OwnershipPolicy.require_owner(
            owner_session_id=owner_session_id,
            current_session_id=session_id,
            code="PROJECT_NOT_FOUND",
        )

    def _validate_workspace_references(
        self, *, project_id: str, payload: WorkspaceSnapshotInput
    ) -> None:
        if (
            payload.active_run_id is not None
            and self._authority.run_project(payload.active_run_id) != project_id
        ):
            raise _not_found("RUN_NOT_FOUND")
        version_ids = {
            slot.artifact_version_id
            for slot in payload.panel_slots
            if slot.artifact_version_id is not None
        }
        evidence_ids = {
            slot.evidence_id
            for slot in payload.panel_slots
            if slot.evidence_id is not None
        }
        evidence_ids.update(payload.pinned_evidence_ids)
        if payload.observatory_state.active_artifact_version_id is not None:
            version_ids.add(payload.observatory_state.active_artifact_version_id)
        if payload.observatory_state.active_evidence_id is not None:
            evidence_ids.add(payload.observatory_state.active_evidence_id)
        for reference in (
            payload.selected_object_ref,
            payload.atlas_state.selected_object_ref,
        ):
            self._collect_object_version(version_ids, reference)
        for version_id in version_ids:
            self._require_version(project_id, version_id)
        for evidence_id in evidence_ids:
            self._require_evidence(project_id, evidence_id)

    @staticmethod
    def _collect_object_version(
        version_ids: set[str], reference: WorkspaceObjectRef | None
    ) -> None:
        if reference is not None and reference.artifact_version_id is not None:
            version_ids.add(reference.artifact_version_id)

    def _require_version(
        self, project_id: str, version_id: str
    ) -> PublicArtifactVersion:
        projection = self._authority.public_artifact_version(project_id, version_id)
        if projection is None:
            raise _not_found("ARTIFACT_VERSION_NOT_FOUND")
        return projection

    def _require_evidence(self, project_id: str, evidence_id: str) -> PublicEvidence:
        projection = self._authority.public_evidence(project_id, evidence_id)
        if projection is None:
            raise _not_found("EVIDENCE_NOT_FOUND")
        return projection

    def _share_versions(
        self, project_id: str, version_ids: tuple[str, ...]
    ) -> tuple[PublicArtifactVersion, ...]:
        return tuple(
            self._require_version(project_id, item) for item in version_ids
        )

    def _share_evidence(
        self,
        project_id: str,
        evidence_ids: tuple[str, ...],
        *,
        allowed_version_ids: set[str],
    ) -> tuple[PublicEvidence, ...]:
        projections = tuple(
            self._require_evidence(project_id, item) for item in evidence_ids
        )
        if any(
            projection.artifact_version_id not in allowed_version_ids
            for projection in projections
        ):
            raise SecurityProblem(
                status=422,
                code="SHARE_SCOPE_INVALID",
                title="Invalid share scope",
                detail="Shared Evidence must belong to a selected ArtifactVersion",
            )
        return projections

    @staticmethod
    def _snapshot_status(snapshot: ShareSnapshot, now: datetime) -> ShareSnapshot:
        if snapshot.revoked_at is not None:
            status = ShareStatus.revoked
        elif snapshot.expires_at <= now:
            status = ShareStatus.expired
        else:
            status = ShareStatus.active
        return (
            snapshot
            if snapshot.status is status
            else snapshot.model_copy(update={"status": status})
        )

    @staticmethod
    def _cursor_start(records: list[_ShareRecord], cursor: str | None) -> int:
        if cursor is None:
            return 0
        share_id = _decode_cursor(cursor)
        for index, record in enumerate(records):
            if record.snapshot.id == share_id:
                return index + 1
        raise _invalid_cursor()


class SnapshotService:
    """Application service used by runtime routers and replaceable persistence adapters."""

    def __init__(self, store: InMemorySnapshotStore) -> None:
        self.store = store

    def get_workspace(self, *, project_id: str, session_id: str) -> WorkspaceSnapshot:
        return self.store.get_workspace(project_id=project_id, session_id=session_id)

    def save_workspace(
        self,
        *,
        project_id: str,
        session_id: str,
        expected_revision: int,
        payload: WorkspaceSnapshotInput,
        now: datetime | None = None,
    ) -> WorkspaceSnapshot:
        return self.store.save_workspace(
            project_id=project_id,
            session_id=session_id,
            expected_revision=expected_revision,
            payload=payload,
            now=now or datetime.now(UTC),
        )

    def create_share(
        self,
        *,
        project_id: str,
        session_id: str,
        request: CreateShareSnapshotRequest,
        now: datetime | None = None,
    ) -> ShareSnapshotCreated:
        return self.store.create_share(
            project_id=project_id,
            session_id=session_id,
            request=request,
            now=now or datetime.now(UTC),
        )

    def list_shares(
        self,
        *,
        project_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
        now: datetime | None = None,
    ) -> tuple[tuple[ShareSnapshot, ...], str | None, bool]:
        return self.store.list_shares(
            project_id=project_id,
            session_id=session_id,
            cursor=cursor,
            limit=limit,
            now=now or datetime.now(UTC),
        )

    def revoke_share(
        self,
        *,
        project_id: str,
        share_id: str,
        session_id: str,
        now: datetime | None = None,
    ) -> None:
        self.store.revoke_share(
            project_id=project_id,
            share_id=share_id,
            session_id=session_id,
            now=now or datetime.now(UTC),
        )

    def get_public_share(
        self, *, raw_token: str, now: datetime | None = None
    ) -> PublicShareSnapshot:
        return self.store.resolve_public_share(
            raw_token=raw_token, now=now or datetime.now(UTC)
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(18)}"


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _encode_cursor(share_id: str) -> str:
    encoded = base64.urlsafe_b64encode(share_id.encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_cursor(cursor: str) -> str:
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        share_id = decoded.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        raise _invalid_cursor() from None
    if not share_id.startswith("share_"):
        raise _invalid_cursor()
    return share_id


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404,
        code=code,
        title="Resource not found",
        detail="Resource not found",
    )


def _invalid_cursor() -> SecurityProblem:
    return SecurityProblem(
        status=400,
        code="INVALID_CURSOR",
        title="Invalid cursor",
        detail="The cursor is invalid or no longer available",
    )


__all__ = ["InMemorySnapshotStore", "SnapshotService"]
