"""Authoritative resource facts for the workspace/share application boundary.

The workspace/share store keeps its own snapshot state in memory for the initial
session lifecycle, but every ownership decision and every Artifact/Evidence
scope check must consult *authoritative* facts. In the runtime these come from
PostgreSQL (:class:`PersistentResourceAuthority`); unit tests seed the same
facts through :class:`InMemoryResourceAuthority` instead of poking the store's
private state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    DocumentParseModel,
    ResearchArtifactModel,
    ResearchInputContentModel,
    ResearchProjectModel,
    ResearchRunModel,
)
from app.schemas.core import (
    PublicArtifactVersion,
    PublicEvidence,
    PublicEvidenceBBox,
    PublicEvidenceLocator,
    PublicSourceSnapshot,
)
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.schemas.scientific_skills import (
    FitsImageVisualizationSpec,
    ModelArtifactContent,
    ModelEvaluationArtifactContent,
    VisualizationArtifactContent,
    WwtSceneVisualizationSpec,
)


@dataclass(frozen=True, slots=True)
class ContentReference:
    """One persisted reference to bytes in the shared content-addressed store."""

    project_id: str
    resource_type: str
    resource_id: str
    content_hash: str
    storage_ref: str
    declared_size_bytes: int | None


@dataclass(frozen=True, slots=True)
class ContentReferenceIssue:
    """A persisted record whose binary reference cannot be trusted for GC."""

    project_id: str
    resource_type: str
    resource_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ContentReferenceClosure:
    """Complete server-side reference closure and fail-closed extraction issues."""

    references: tuple[ContentReference, ...]
    issues: tuple[ContentReferenceIssue, ...]


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


class ContentReferenceAuthority(ResourceAuthority, Protocol):
    """Resource authority capability used only by offline blob maintenance.

    This is intentionally not an HTTP/session-scoped API.  Implementations must
    return references from the persisted resource facts across every project,
    otherwise an orphan decision would be unsafe.
    """

    def content_reference_closure(self) -> ContentReferenceClosure:
        """Return all live blob references plus any extraction uncertainty."""


class InMemoryResourceAuthority:
    """Explicitly-seeded authority for contract/security/concurrency unit tests."""

    def __init__(self) -> None:
        self._projects: dict[str, str] = {}
        self._runs: dict[str, str] = {}
        self._versions: dict[str, tuple[str, PublicArtifactVersion]] = {}
        self._evidence: dict[str, tuple[str, PublicEvidence]] = {}
        self._content_references: list[ContentReference] = []
        self._content_reference_issues: list[ContentReferenceIssue] = []

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

    def register_content_reference(self, reference: ContentReference) -> None:
        self._content_references.append(reference)

    def register_content_reference_issue(self, issue: ContentReferenceIssue) -> None:
        self._content_reference_issues.append(issue)

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

    def content_reference_closure(self) -> ContentReferenceClosure:
        return ContentReferenceClosure(
            references=tuple(self._content_references),
            issues=tuple(self._content_reference_issues),
        )


class PersistentResourceAuthority:
    """PostgreSQL-backed authority reading the same facts as the read boundary."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory
        self._artifacts = ArtifactReadService(factory)

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
        if _uuid_or_none(project_id) is None or _uuid_or_none(version_id) is None:
            return None
        owner_session_id = self.project_owner(project_id)
        if owner_session_id is None:
            return None
        try:
            version = self._artifacts.get_version(
                version_id=version_id,
                session_id=owner_session_id,
                full_content=True,
            )
            artifact = self._artifacts.get_artifact(
                artifact_id=version.artifact_id,
                session_id=owner_session_id,
            )
        except SecurityProblem:
            return None
        if version.project_id != project_id:
            return None
        if version.presentation is None:
            return None
        return PublicArtifactVersion(
            id=version.id,
            artifact_id=version.artifact_id,
            kind=artifact.kind,
            title=artifact.title,
            version_number=version.version_number,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            source_mode=version.source_mode,
            created_at=version.created_at,
            presentation=version.presentation,
            evidence_ids=tuple(item.id for item in version.evidence),
        )

    def public_evidence(
        self, project_id: str, evidence_id: str
    ) -> PublicEvidence | None:
        if _uuid_or_none(project_id) is None or _uuid_or_none(evidence_id) is None:
            return None
        owner_session_id = self.project_owner(project_id)
        if owner_session_id is None:
            return None
        try:
            read = self._artifacts.get_evidence(
                evidence_id=evidence_id,
                session_id=owner_session_id,
            )
        except SecurityProblem:
            return None
        locator = _public_locator(read.locator)
        quote = read.quote_or_value
        if quote is not None and not isinstance(quote, str):
            quote = str(quote) if isinstance(quote, (int, float, bool)) else None
        source = read.source_snapshot
        metadata = {
            key: value
            for key, value in source.request_metadata.items()
            if key in {"source_url", "url", "original_url", "landing_url"}
            and isinstance(value, str)
        }
        return PublicEvidence(
            id=read.id,
            artifact_version_id=read.artifact_version_id,
            source_snapshot_id=read.source_snapshot_id,
            locator=locator,
            quote_or_value=quote,
            created_at=read.created_at,
            source=PublicSourceSnapshot(
                source_id=source.source_id,
                source_type=source.source_type,
                retrieved_at=source.retrieved_at,
                license_note=source.license_note,
                request_metadata=metadata,
            ),
        )

    def content_reference_closure(self) -> ContentReferenceClosure:
        """Read the complete PostgreSQL-owned blob reference closure.

        ResearchInput and DocumentParse carry direct storage facts.  Scientific
        binary references live inside immutable ArtifactVersion JSON; those are
        parsed through the same strict Pydantic contracts as the read boundary.
        Any malformed binary-bearing ArtifactVersion is returned as an issue so
        garbage collection must fail closed rather than guess at nested JSON.
        """

        references: list[ContentReference] = []
        issues: list[ContentReferenceIssue] = []
        with self._factory() as session:
            for project_id, content_hash, storage_ref, size_bytes in session.execute(
                select(
                    ResearchInputContentModel.project_id,
                    ResearchInputContentModel.content_hash,
                    ResearchInputContentModel.storage_ref,
                    ResearchInputContentModel.size_bytes,
                )
            ).yield_per(500):
                references.append(
                    ContentReference(
                        project_id=str(project_id),
                        resource_type="research_input_content",
                        resource_id=f"{project_id}:{content_hash}",
                        content_hash=content_hash,
                        storage_ref=storage_ref,
                        declared_size_bytes=size_bytes,
                    )
                )
            for parse_id, project_id, content_hash, storage_ref in session.execute(
                select(
                    DocumentParseModel.id,
                    DocumentParseModel.project_id,
                    DocumentParseModel.payload_content_hash,
                    DocumentParseModel.payload_storage_ref,
                )
            ).yield_per(500):
                references.append(
                    ContentReference(
                        project_id=str(project_id),
                        resource_type="document_parse_payload",
                        resource_id=str(parse_id),
                        content_hash=content_hash,
                        storage_ref=storage_ref,
                        declared_size_bytes=None,
                    )
                )
            artifact_rows = session.execute(
                select(
                    ArtifactVersionModel.id,
                    ArtifactVersionModel.project_id,
                    ResearchArtifactModel.kind,
                    ArtifactVersionModel.content,
                )
                .join(
                    ResearchArtifactModel,
                    ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                )
                .where(
                    ResearchArtifactModel.kind.in_(
                        ("visualization", "model_evaluation", "model_artifact")
                    )
                )
            ).yield_per(200)
            for version_id, project_id, kind, raw_content in artifact_rows:
                try:
                    binaries = _scientific_binary_references(kind, raw_content)
                except ValidationError:
                    issues.append(
                        ContentReferenceIssue(
                            project_id=str(project_id),
                            resource_type="artifact_version",
                            resource_id=str(version_id),
                            reason=(
                                "binary-bearing scientific content failed schema "
                                "validation"
                            ),
                        )
                    )
                    continue
                references.extend(
                    ContentReference(
                        project_id=str(project_id),
                        resource_type="artifact_version_binary",
                        resource_id=str(version_id),
                        content_hash=content_hash,
                        storage_ref=storage_ref,
                        declared_size_bytes=None,
                    )
                    for content_hash, storage_ref in binaries
                )
        return ContentReferenceClosure(
            references=tuple(
                sorted(
                    references,
                    key=lambda item: (
                        item.content_hash,
                        item.resource_type,
                        item.resource_id,
                    ),
                )
            ),
            issues=tuple(
                sorted(
                    issues,
                    key=lambda item: (item.resource_type, item.resource_id),
                )
            ),
        )


def _scientific_binary_references(
    artifact_kind: str, raw_content: object
) -> tuple[tuple[str, str], ...]:
    """Extract only binary references admitted by current scientific schemas."""

    if artifact_kind == "visualization":
        content = VisualizationArtifactContent.model_validate(raw_content)
        if isinstance(content.spec, FitsImageVisualizationSpec):
            return ((content.spec.content_hash, content.spec.content_ref),)
        if isinstance(content.spec, WwtSceneVisualizationSpec):
            return tuple(
                (layer.content_hash, layer.content_ref)
                for layer in (*content.spec.fits_layers, *content.spec.table_layers)
            )
        return ()
    if artifact_kind == "model_evaluation":
        evaluation = ModelEvaluationArtifactContent.model_validate(raw_content)
        if evaluation.model_binary is None:
            return ()
        return (
            (
                evaluation.model_binary.content_hash,
                evaluation.model_binary.content_ref,
            ),
        )
    if artifact_kind == "model_artifact":
        model = ModelArtifactContent.model_validate(raw_content)
        return ((model.model_binary.content_hash, model.model_binary.content_ref),)
    return ()


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_non_negative_int(value: object) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def _public_bbox(value: object) -> PublicEvidenceBBox | None:
    if not isinstance(value, Mapping):
        return None
    coordinates = tuple(value.get(key) for key in ("x1", "y1", "x2", "y2"))
    if not all(
        isinstance(item, (int, float)) and not isinstance(item, bool)
        for item in coordinates
    ):
        return None
    x1, y1, x2, y2 = (float(item) for item in coordinates)
    if x1 > x2 or y1 > y2:
        return None
    return PublicEvidenceBBox(x1=x1, y1=y1, x2=x2, y2=y2)


def _public_locator(value: Mapping[str, object]) -> PublicEvidenceLocator:
    """Copy only documented scientific locator coordinates and references."""

    return PublicEvidenceLocator(
        kind=_optional_text(value.get("kind")) or "source",
        page=_optional_non_negative_int(value.get("page", value.get("page_index"))),
        paragraph=_optional_non_negative_int(value.get("paragraph")),
        section=_optional_text(value.get("section")),
        text_range=_optional_text(value.get("range", value.get("text_range"))),
        field=_optional_text(value.get("field")),
        row_key=_optional_text(value.get("row_key")),
        block_id=_optional_text(value.get("block_id")),
        reading_order=_optional_non_negative_int(value.get("reading_order")),
        table_id=_optional_text(value.get("table_id")),
        cell_id=_optional_text(value.get("cell_id")),
        bbox=_public_bbox(value.get("bbox")),
    )


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "ContentReference",
    "ContentReferenceAuthority",
    "ContentReferenceClosure",
    "ContentReferenceIssue",
    "InMemoryResourceAuthority",
    "PersistentResourceAuthority",
    "ResourceAuthority",
]
