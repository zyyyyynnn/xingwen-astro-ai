"""Persist provenance for scientific service and bundled-data observations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.orm import Session

from app.db.models import SourceSnapshotModel
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId, ScientificTaskInput
from services.scientific_skills.types import (
    ScientificSkillRequest,
    ScientificSkillResult,
    ScientificSourceReference,
)


_SOURCE_METADATA: dict[ScientificSkillId, tuple[str, str, str]] = {
    ScientificSkillId.simbad_lookup: (
        "simbad",
        "remote_service",
        "CDS SIMBAD service; use and attribution remain subject to the service terms.",
    ),
    ScientificSkillId.skyview_fits: (
        "skyview",
        "remote_service",
        "NASA SkyView service; survey-specific rights remain attached to the selected survey.",
    ),
    ScientificSkillId.ephemeris: (
        "jpl_de421",
        "bundled_ephemeris",
        "JPL DE421 ephemeris distributed by skyfield-data and evaluated with Skyfield.",
    ),
    ScientificSkillId.celestial_events: (
        "jpl_de421",
        "bundled_ephemeris",
        "JPL DE421 ephemeris distributed by skyfield-data and evaluated with Skyfield.",
    ),
}


class DatabaseScientificSourceRecorder:
    """Idempotently persist one SourceSnapshot per exact query/result identity."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    async def record(
        self,
        *,
        project_id: str,
        run_id: str,
        task: ScientificTaskInput,
        request: ScientificSkillRequest,
        result: ScientificSkillResult,
    ) -> ScientificSourceReference:
        try:
            source_id, source_type, license_note = _SOURCE_METADATA[task.skill_id]
        except KeyError as exc:
            raise ValueError(
                f"scientific skill does not produce a SourceSnapshot: {task.skill_id}"
            ) from exc
        project_uuid = UUID(project_id)
        query = {
            "skill_id": task.skill_id.value,
            "task_id": task.task_id,
            "parameters": task.parameters,
        }
        query_hash = compute_canonical_payload_hash(query)
        snapshot_id = uuid5(
            NAMESPACE_URL,
            f"xingwen:{project_id}:{source_id}:{query_hash}:{result.output_hash}",
        )
        with self._session_factory() as session, session.begin():
            row = session.get(SourceSnapshotModel, snapshot_id)
            if row is None:
                row = SourceSnapshotModel(
                    id=snapshot_id,
                    project_id=project_uuid,
                    source_id=source_id,
                    source_type=source_type,
                    retrieved_at=datetime.now(UTC),
                    query=query,
                    query_hash=query_hash,
                    source_version_or_etag=result.skill_revision,
                    content_hash=result.output_hash,
                    license_note=license_note,
                    cache_version=None,
                    request_metadata={
                        "run_id": run_id,
                        "request_id": request.request_id,
                        "skill_revision": result.skill_revision,
                    },
                )
                session.add(row)
                session.flush()
            _require_same_snapshot(
                row,
                project_id=project_uuid,
                source_id=source_id,
                source_type=source_type,
                query_hash=query_hash,
                content_hash=result.output_hash,
            )
        return ScientificSourceReference(
            source_snapshot_id=str(snapshot_id),
            content_hash=result.output_hash,
        )


def _require_same_snapshot(
    row: SourceSnapshotModel,
    *,
    project_id: UUID,
    source_id: str,
    source_type: str,
    query_hash: str,
    content_hash: str,
) -> None:
    if (
        row.project_id != project_id
        or row.source_id != source_id
        or row.source_type != source_type
        or row.query_hash != query_hash
        or row.content_hash != content_hash
    ):
        raise RuntimeError(
            "scientific SourceSnapshot identity was reused with different content"
        )


__all__ = ["DatabaseScientificSourceRecorder"]
