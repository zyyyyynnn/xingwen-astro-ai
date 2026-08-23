"""Persist provenance for scientific service and bundled-data observations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import GaiaTapResponseCacheModel, SourceSnapshotModel
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ScientificSkillId, ScientificTaskInput
from app.schemas.evidence import SourceSnapshotRecord
from services.scientific_skills.astro_acquisition import GAIA_CACHE_VERSION
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
    ScientificSkillId.gaia_cone_search: (
        "esa_gaia_dr3.gaiadr3.gaia_source",
        "remote_catalog_service",
        "ESA Gaia Archive DR3 TAP service; Gaia data use and attribution rules apply.",
    ),
    ScientificSkillId.vizier_tap: (
        "vizier_tap",
        "remote_catalog_service",
        "CDS VizieR catalogue service over TAP; VizieR acknowledgement and catalogue-specific terms apply.",
    ),
    ScientificSkillId.spectrum_acquisition: (
        "sdss_dr17",
        "remote_spectrum_archive",
        "SDSS DR17 optical spectrum from the official Science Archive Server; SDSS data-use terms apply.",
    ),
    ScientificSkillId.light_curve_acquisition: (
        "mast_tess",
        "remote_light_curve_archive",
        "Mission-produced TESS light curve from MAST; NASA/STScI and TESS acknowledgement rules apply.",
    ),
}


@dataclass(frozen=True, slots=True)
class _ProducedSource:
    source_id: str
    source_type: str
    license_note: str
    query: dict[str, object]
    query_hash: str | None
    content_hash: str
    source_version_or_etag: str | None
    retrieved_at: datetime
    cache_version: str | None
    request_metadata: dict[str, object]


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
    ) -> tuple[ScientificSourceReference, ...]:
        sources = _produced_sources(task=task, request=request, result=result)
        project_uuid = UUID(project_id)
        references: list[ScientificSourceReference] = []
        with self._session_factory() as session, session.begin():
            for source in sources:
                query_hash = source.query_hash or compute_canonical_payload_hash(
                    source.query
                )
                if compute_canonical_payload_hash(source.query) != query_hash:
                    raise ValueError(
                        "scientific SourceSnapshot query identity does not match query_hash"
                    )
                snapshot_id = _scientific_source_snapshot_id(
                    project_id=project_id,
                    source_id=source.source_id,
                    query_hash=query_hash,
                    content_hash=source.content_hash,
                    retrieved_at=source.retrieved_at,
                )
                row = session.get(SourceSnapshotModel, snapshot_id)
                if row is None:
                    row = SourceSnapshotModel(
                        id=snapshot_id,
                        project_id=project_uuid,
                        source_id=source.source_id,
                        source_type=source.source_type,
                        retrieved_at=source.retrieved_at,
                        query=source.query,
                        query_hash=query_hash,
                        source_version_or_etag=source.source_version_or_etag,
                        content_hash=source.content_hash,
                        license_note=source.license_note,
                        cache_version=source.cache_version,
                        request_metadata={
                            "run_id": run_id,
                            "request_id": request.request_id,
                            "skill_revision": result.skill_revision,
                            **source.request_metadata,
                        },
                    )
                    session.add(row)
                    session.flush()
                _require_same_snapshot(
                    row,
                    project_id=project_uuid,
                    source_id=source.source_id,
                    source_type=source.source_type,
                    query_hash=query_hash,
                    content_hash=source.content_hash,
                    retrieved_at=source.retrieved_at,
                )
                references.append(
                    ScientificSourceReference(
                        source_snapshot_id=str(snapshot_id),
                        content_hash=source.content_hash,
                        source_id=source.source_id,
                        query_hash=query_hash,
                        retrieved_at=source.retrieved_at,
                        source_snapshot=SourceSnapshotRecord(
                            snapshot_id=str(row.id),
                            source_id=row.source_id,
                            source_type=row.source_type,
                            retrieved_at=row.retrieved_at,
                            query=json.dumps(
                                row.query,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            query_hash=row.query_hash,
                            source_version_or_etag=row.source_version_or_etag,
                            content_hash=row.content_hash,
                            license_note=row.license_note,
                            cache_version=row.cache_version,
                            request_metadata=dict(row.request_metadata),
                        ),
                    )
                )
        return tuple(references)


def _scientific_source_snapshot_id(
    *,
    project_id: str,
    source_id: str,
    query_hash: str,
    content_hash: str,
    retrieved_at: datetime,
) -> UUID:
    """Identify one physical retrieval, even when its bytes match an older result."""

    if retrieved_at.tzinfo is None:
        raise ValueError(
            "scientific SourceSnapshot retrieved_at must be timezone-aware"
        )
    retrieved_at_utc = retrieved_at.astimezone(UTC).isoformat()
    return uuid5(
        NAMESPACE_URL,
        (
            f"xingwen:{project_id}:{source_id}:{query_hash}:"
            f"{content_hash}:{retrieved_at_utc}"
        ),
    )


def _require_same_snapshot(
    row: SourceSnapshotModel,
    *,
    project_id: UUID,
    source_id: str,
    source_type: str,
    query_hash: str,
    content_hash: str,
    retrieved_at: datetime,
) -> None:
    if (
        row.project_id != project_id
        or row.source_id != source_id
        or row.source_type != source_type
        or row.query_hash != query_hash
        or row.content_hash != content_hash
        or row.retrieved_at != retrieved_at
    ):
        raise RuntimeError(
            "scientific SourceSnapshot identity was reused with different content"
        )


def _source_metadata(
    skill_id: ScientificSkillId,
    parameters: dict[str, object],
) -> tuple[tuple[str, str, str], ...]:
    """Return one metadata entry per physical source, never a composite source."""

    source_id, source_type, license_note = _SOURCE_METADATA[skill_id]
    if skill_id not in {
        ScientificSkillId.ephemeris,
        ScientificSkillId.celestial_events,
    }:
        return ((source_id, source_type, license_note),)
    location_name = parameters.get("location_name")
    if not isinstance(location_name, str) or not location_name.strip():
        return ((source_id, source_type, license_note),)
    return (
        (source_id, source_type, license_note),
        (
            "nominatim_openstreetmap",
            "remote_geocoding_service",
            "Observer coordinates resolved through HTTPS Nominatim from OpenStreetMap data; OpenStreetMap attribution and Nominatim usage terms apply.",
        ),
    )


def _produced_sources(
    *,
    task: ScientificTaskInput,
    request: ScientificSkillRequest,
    result: ScientificSkillResult,
) -> tuple[_ProducedSource, ...]:
    try:
        metadata = _source_metadata(task.skill_id, task.parameters)
    except KeyError as exc:
        raise ValueError(
            f"scientific skill does not produce a SourceSnapshot: {task.skill_id}"
        ) from exc
    base_query = {
        "skill_id": task.skill_id.value,
        "task_id": task.task_id,
        "parameters": task.parameters,
    }
    acquisition = result.output.get("acquisition")
    acquisition_metadata = acquisition if isinstance(acquisition, dict) else {}
    response_hash = acquisition_metadata.get("response_content_hash")
    if not isinstance(response_hash, str):
        response_hash = acquisition_metadata.get("raw_content_hash")
    source_version = acquisition_metadata.get("source_version_or_etag")
    if not isinstance(source_version, str):
        source_version = acquisition_metadata.get("etag")
    if not isinstance(response_hash, str):
        response_hash = None
    if not isinstance(source_version, str):
        source_version = None
    retrieved_at = datetime.now(UTC)
    raw_retrieved_at = acquisition_metadata.get("retrieved_at")
    if isinstance(raw_retrieved_at, str):
        try:
            retrieved_at = datetime.fromisoformat(raw_retrieved_at)
        except ValueError as exc:
            raise ValueError("scientific acquisition retrieved_at is invalid") from exc
        if retrieved_at.tzinfo is None:
            raise ValueError(
                "scientific acquisition retrieved_at must be timezone-aware"
            )
    raw_cache_version = acquisition_metadata.get("cache_version")
    cache_version = raw_cache_version if isinstance(raw_cache_version, str) else None

    sources: list[_ProducedSource] = []
    for source_id, source_type, license_note in metadata:
        query = dict(base_query)
        query_hash: str | None = None
        content_hash = result.output_hash
        request_metadata: dict[str, object] = {}
        if source_id == "nominatim_openstreetmap":
            location_name = task.parameters.get("location_name")
            resolved_location = result.output.get("resolved_location")
            if not isinstance(location_name, str) or not isinstance(
                resolved_location, dict
            ):
                raise ValueError(
                    "Nominatim SourceSnapshot requires a resolved location fact"
                )
            query = {"location_name": location_name}
            raw_response_hash = resolved_location.get("response_content_hash")
            if not isinstance(raw_response_hash, str):
                raw_response_hash = compute_canonical_payload_hash(resolved_location)
            content_hash = raw_response_hash
            response_uri = resolved_location.get("response_uri")
            upstream_revision = resolved_location.get("source_version_or_etag")
            source_version = (
                upstream_revision if isinstance(upstream_revision, str) else None
            )
            request_metadata = {
                "adapter": "nominatim",
                "endpoint_host": "nominatim.openstreetmap.org",
                **(
                    {"response_uri": response_uri}
                    if isinstance(response_uri, str)
                    else {}
                ),
            }
        elif source_id == "jpl_de421":
            jpl_output = {
                key: value
                for key, value in result.output.items()
                if key != "resolved_location"
            }
            content_hash = compute_canonical_payload_hash(jpl_output)
            source_version = "DE421"
        elif response_hash is not None:
            content_hash = response_hash
            request_metadata = {
                key: value
                for key, value in acquisition_metadata.items()
                if key
                in {
                    "source_mode",
                    "adapter",
                    "adapter_version",
                    "endpoint",
                    "response_uri",
                    "provider_uri",
                    "provider_revision",
                    "etag",
                    "raw_content_hash",
                    "status_code",
                    "content_length",
                    "product_filename",
                    "product_uri",
                    "plate",
                    "mjd",
                    "fiber",
                    "tic_id",
                    "sector",
                    "cache_version",
                    "query_hash",
                    "retrieved_at",
                    "schema_revision",
                    "schema_response_content_hash",
                }
            }
        if task.skill_id is ScientificSkillId.gaia_cone_search:
            raw_query = acquisition_metadata.get("query")
            raw_response_format = acquisition_metadata.get("response_format")
            raw_cache_version = acquisition_metadata.get("cache_version")
            raw_query_hash = acquisition_metadata.get("query_hash")
            if not all(
                isinstance(value, str)
                for value in (
                    raw_query,
                    raw_response_format,
                    raw_cache_version,
                    raw_query_hash,
                )
            ):
                raise ValueError(
                    "Gaia acquisition query identity is missing or invalid"
                )
            query = {
                "query": raw_query,
                "response_format": raw_response_format,
                "cache_version": raw_cache_version,
            }
            query_hash = raw_query_hash
        sources.append(
            _ProducedSource(
                source_id=source_id,
                source_type=source_type,
                license_note=license_note,
                query=query,
                query_hash=query_hash,
                content_hash=content_hash,
                source_version_or_etag=source_version,
                retrieved_at=retrieved_at,
                cache_version=cache_version,
                request_metadata=request_metadata,
            )
        )
    return tuple(sources)


class DatabaseGaiaTapResponseCache:
    """Persist validated Gaia responses for a short, project-scoped window."""

    _TTL = timedelta(minutes=15)

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def get(self, *, project_id: str, query_hash: str) -> dict[str, object] | None:
        now = datetime.now(UTC)
        with self._session_factory() as session:
            row = session.scalar(
                select(GaiaTapResponseCacheModel).where(
                    GaiaTapResponseCacheModel.project_id == UUID(project_id),
                    GaiaTapResponseCacheModel.query_hash == query_hash,
                    GaiaTapResponseCacheModel.cache_version == GAIA_CACHE_VERSION,
                    GaiaTapResponseCacheModel.expires_at > now,
                )
            )
        return None if row is None else dict(row.payload)

    def put(
        self,
        *,
        project_id: str,
        query_hash: str,
        payload: dict[str, object],
        retrieved_at: datetime,
    ) -> None:
        expires_at = retrieved_at + self._TTL
        statement = insert(GaiaTapResponseCacheModel).values(
            project_id=UUID(project_id),
            query_hash=query_hash,
            cache_version=GAIA_CACHE_VERSION,
            payload=payload,
            retrieved_at=retrieved_at,
            expires_at=expires_at,
        )
        statement = statement.on_conflict_do_update(
            index_elements=("project_id", "query_hash", "cache_version"),
            set_={
                "payload": statement.excluded.payload,
                "retrieved_at": statement.excluded.retrieved_at,
                "expires_at": statement.excluded.expires_at,
            },
            where=GaiaTapResponseCacheModel.expires_at <= retrieved_at,
        )
        with self._session_factory() as session, session.begin():
            session.execute(statement)


__all__ = ["DatabaseGaiaTapResponseCache", "DatabaseScientificSourceRecorder"]
