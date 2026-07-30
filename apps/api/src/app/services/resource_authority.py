"""Authoritative resource facts for the workspace/share application boundary.

The workspace/share store keeps its own snapshot state in memory for the M1
session lifecycle, but every ownership decision and every Artifact/Evidence
scope check must consult *authoritative* facts. In the runtime these come from
PostgreSQL (:class:`PersistentResourceAuthority`); unit tests seed the same
facts through :class:`InMemoryResourceAuthority` instead of poking the store's
private state.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    EvidenceModel,
    ResearchArtifactModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.core import PublicArtifactVersion, PublicEvidence


class ResourceAuthority(Protocol):
    """Read-only authoritative facts the snapshot/share store depends on."""

    def project_owner(self, project_id: str) -> str | None:
        """Return the owning session id for a project, or ``None`` if unknown."""

    def run_project(self, run_id: str) -> str | None:
        """Return the project id a run belongs to, or ``None`` if unknown."""

    def public_artifact_version(
        self, project_id: str, version_id: str
    ) -> PublicArtifactVersion | None:
        """Return a redacted version projection scoped to the project."""

    def public_evidence(
        self, project_id: str, evidence_id: str
    ) -> PublicEvidence | None:
        """Return a minimal Evidence projection scoped to the project."""


class InMemoryResourceAuthority:
    """Explicitly-seeded authority for contract/security/concurrency unit tests."""

    def __init__(self) -> None:
        self._projects: dict[str, str] = {}
        self._runs: dict[str, str] = {}
        self._versions: dict[str, tuple[str, PublicArtifactVersion]] = {}
        self._evidence: dict[str, tuple[str, PublicEvidence]] = {}

    def register_project(self, *, project_id: str, owner_session_id: str) -> None:
        self._projects[project_id] = owner_session_id

    def register_run(self, *, run_id: str, project_id: str) -> None:
        self._runs[run_id] = project_id

    def register_artifact_version(
        self, *, project_id: str, projection: PublicArtifactVersion
    ) -> None:
        self._versions[projection.id] = (project_id, projection)

    def register_evidence(self, *, project_id: str, projection: PublicEvidence) -> None:
        self._evidence[projection.id] = (project_id, projection)

    def project_owner(self, project_id: str) -> str | None:
        return self._projects.get(project_id)

    def run_project(self, run_id: str) -> str | None:
        return self._runs.get(run_id)

    def public_artifact_version(
        self, project_id: str, version_id: str
    ) -> PublicArtifactVersion | None:
        entry = self._versions.get(version_id)
        if entry is None or entry[0] != project_id:
            return None
        return entry[1]

    def public_evidence(
        self, project_id: str, evidence_id: str
    ) -> PublicEvidence | None:
        entry = self._evidence.get(evidence_id)
        if entry is None or entry[0] != project_id:
            return None
        return entry[1]


class PersistentResourceAuthority:
    """PostgreSQL-backed authority reading the same facts as the read boundary."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def project_owner(self, project_id: str) -> str | None:
        pid = _uuid_or_none(project_id)
        if pid is None:
            return None
        with self._factory() as session:
            return session.scalar(
                select(ResearchProjectModel.session_id).where(
                    ResearchProjectModel.id == pid
                )
            )

    def run_project(self, run_id: str) -> str | None:
        rid = _uuid_or_none(run_id)
        if rid is None:
            return None
        with self._factory() as session:
            project_id = session.scalar(
                select(ResearchRunModel.project_id).where(ResearchRunModel.id == rid)
            )
        return str(project_id) if project_id is not None else None

    def public_artifact_version(
        self, project_id: str, version_id: str
    ) -> PublicArtifactVersion | None:
        pid, vid = _uuid_or_none(project_id), _uuid_or_none(version_id)
        if pid is None or vid is None:
            return None
        with self._factory() as session:
            row = session.execute(
                select(
                    ArtifactVersionModel,
                    ResearchArtifactModel.kind,
                    ResearchArtifactModel.title,
                )
                .join(
                    ResearchArtifactModel,
                    ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                )
                .where(
                    ArtifactVersionModel.id == vid,
                    ArtifactVersionModel.project_id == pid,
                )
            ).first()
        if row is None:
            return None
        version, kind, title = row
        return PublicArtifactVersion(
            id=str(version.id),
            artifact_id=str(version.artifact_id),
            kind=kind,
            title=title,
            version_number=version.version_number,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            source_mode=version.source_mode,
            created_at=_utc(version.created_at),
        )

    def public_evidence(
        self, project_id: str, evidence_id: str
    ) -> PublicEvidence | None:
        pid, eid = _uuid_or_none(project_id), _uuid_or_none(evidence_id)
        if pid is None or eid is None:
            return None
        with self._factory() as session:
            row = session.get(EvidenceModel, eid)
            if row is None or str(row.project_id) != project_id:
                return None
            return PublicEvidence(
                id=str(row.id),
                artifact_version_id=str(row.artifact_version_id),
                source_snapshot_id=str(row.source_snapshot_id),
            )


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "InMemoryResourceAuthority",
    "PersistentResourceAuthority",
    "ResourceAuthority",
]
