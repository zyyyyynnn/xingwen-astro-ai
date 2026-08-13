"""Resolve scientific task input refs against current persisted authorities."""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchInputModel,
    SourceSnapshotModel,
)
from app.schemas.core import ScientificSkillId, ScientificTaskInput
from app.schemas.data_artifacts import DatasetArtifactCandidate
from app.services.content_storage import ContentStorage
from services.scientific_skills.execution import ScientificInputBinding
from services.scientific_skills.types import ScientificSourceReference


_ROW_SKILLS = frozenset(
    {
        ScientificSkillId.data_profile,
        ScientificSkillId.statistical_analysis,
        ScientificSkillId.correlation_analysis,
        ScientificSkillId.chart_visualization,
        ScientificSkillId.tabular_machine_learning,
        ScientificSkillId.time_series_forecast,
    }
)


class DatabaseScientificInputResolver:
    """Project-scoped resolver for ArtifactVersion, SourceSnapshot and input refs."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        content_storage: ContentStorage,
        *,
        project_id: str,
    ) -> None:
        self._session_factory = session_factory
        self._content_storage = content_storage
        self._project_id = UUID(project_id)

    async def resolve(
        self, task: ScientificTaskInput
    ) -> tuple[ScientificInputBinding, ...]:
        return tuple(
            [await self._resolve_one(task, ref_id) for ref_id in task.input_refs]
        )

    async def _resolve_one(
        self, task: ScientificTaskInput, ref_id: str
    ) -> ScientificInputBinding:
        try:
            reference_uuid = UUID(ref_id)
        except ValueError as exc:
            raise ValueError(
                "scientific input refs must use persisted UUID identities"
            ) from exc
        with self._session_factory() as session:
            version = session.scalar(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.id == reference_uuid,
                    ArtifactVersionModel.project_id == self._project_id,
                )
            )
            if version is not None:
                return _artifact_binding(session, task, version)
            source = session.scalar(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.id == reference_uuid,
                    SourceSnapshotModel.project_id == self._project_id,
                )
            )
            if source is not None:
                return _source_binding(source)
            research_input = session.scalar(
                select(ResearchInputModel).where(
                    ResearchInputModel.id == reference_uuid,
                    ResearchInputModel.project_id == self._project_id,
                    ResearchInputModel.expires_at.is_(None),
                )
            )
            if research_input is None:
                raise ValueError(
                    "scientific input ref was not found in the Run Project"
                )
            content_hash = research_input.content_hash
            source_snapshot_id = research_input.source_snapshot_id
            source_reference = None
            if source_snapshot_id is not None:
                snapshot = session.scalar(
                    select(SourceSnapshotModel).where(
                        SourceSnapshotModel.id == source_snapshot_id,
                        SourceSnapshotModel.project_id == self._project_id,
                    )
                )
                if snapshot is None:
                    raise ValueError("Research Input SourceSnapshot is missing")
                source_reference = ScientificSourceReference(
                    source_snapshot_id=str(snapshot.id),
                    content_hash=snapshot.content_hash,
                )
        content = await self._content_storage.retrieve(content_hash)
        if content is None:
            raise ValueError("scientific input content blob is missing")
        return ScientificInputBinding(
            ref_id=ref_id,
            kind="content_blob",
            parameters=_content_parameters(task.skill_id, content),
            source_references=(source_reference,)
            if source_reference is not None
            else (),
        )


def _artifact_binding(
    session: Session,
    task: ScientificTaskInput,
    version: ArtifactVersionModel,
) -> ScientificInputBinding:
    if task.skill_id not in _ROW_SKILLS:
        raise ValueError(
            f"{task.skill_id.value} does not accept an ArtifactVersion input"
        )
    if version.content.get("kind") != "dataset":
        raise ValueError(f"{task.skill_id.value} requires a Dataset ArtifactVersion")
    dataset = DatasetArtifactCandidate.model_validate(version.content)
    snapshots = _source_references(
        session,
        project_id=version.project_id,
        source_snapshot_ids=tuple(version.source_snapshot_ids),
    )
    return ScientificInputBinding(
        ref_id=str(version.id),
        kind="artifact_version",
        parameters={"rows": _dataset_rows(dataset)},
        source_references=snapshots,
        evidence_ids=tuple(sorted(version.evidence_ids)),
    )


def _source_binding(source: SourceSnapshotModel) -> ScientificInputBinding:
    return ScientificInputBinding(
        ref_id=str(source.id),
        kind="source_snapshot",
        parameters={},
        source_references=(
            ScientificSourceReference(
                source_snapshot_id=str(source.id),
                content_hash=source.content_hash,
            ),
        ),
    )


def _source_references(
    session: Session,
    *,
    project_id: UUID,
    source_snapshot_ids: tuple[str, ...],
) -> tuple[ScientificSourceReference, ...]:
    if not source_snapshot_ids:
        return ()
    try:
        ids = tuple(UUID(item) for item in source_snapshot_ids)
    except ValueError as exc:
        raise ValueError("ArtifactVersion SourceSnapshot ids are invalid") from exc
    rows = tuple(
        session.scalars(
            select(SourceSnapshotModel).where(
                SourceSnapshotModel.id.in_(ids),
                SourceSnapshotModel.project_id == project_id,
            )
        )
    )
    by_id = {row.id: row for row in rows}
    if set(by_id) != set(ids):
        raise ValueError("ArtifactVersion SourceSnapshot closure is incomplete")
    return tuple(
        ScientificSourceReference(
            source_snapshot_id=str(item),
            content_hash=by_id[item].content_hash,
        )
        for item in ids
    )


def _dataset_rows(dataset: DatasetArtifactCandidate) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in dataset.rows:
        projection: dict[str, object] = {"row_id": row.row_id}
        for field in row.fields:
            if field.status == "mapped":
                projection[field.canonical_field_id] = _coerce_scalar(
                    field.canonical_value
                )
            else:
                projection[field.canonical_field_id] = None
        rows.append(projection)
    return rows


def _coerce_scalar(value: str) -> object:
    normalized = value.strip()
    try:
        return int(normalized)
    except ValueError:
        try:
            return float(normalized)
        except ValueError:
            return normalized


def _content_parameters(
    skill_id: ScientificSkillId, content: bytes
) -> dict[str, object]:
    if skill_id in {
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
    }:
        return {"ephemeris_base64": b64encode(content).decode("ascii")}
    if skill_id is ScientificSkillId.fits_image_analysis:
        return {"fits_base64": b64encode(content).decode("ascii")}
    if skill_id is ScientificSkillId.image_classification:
        try:
            payload = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "image classification input must be a UTF-8 JSON tensor"
            ) from exc
        images = payload.get("images") if isinstance(payload, dict) else payload
        if not isinstance(images, list):
            raise ValueError("image classification JSON requires an images array")
        return {"images": images}
    raise ValueError(f"{skill_id.value} does not accept a content blob input")


__all__ = ["DatabaseScientificInputResolver"]
