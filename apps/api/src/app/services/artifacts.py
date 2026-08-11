"""Generic, ownership-scoped Artifact provenance read application boundary."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
import json
import math
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    DatasetRowProjectionModel,
    EvidenceModel,
    ProducerExecutionModel,
    ResearchArtifactModel,
    ResearchProjectModel,
    ResearchRunModel,
    SourceSnapshotModel,
)
from app.schemas.core import (
    ArtifactVersionDetail,
    ArtifactVersionSummary,
    EvidenceDetail,
    EvidenceRead,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifact,
    ResearchArtifactDetail,
    SourceSnapshotDetail,
)
from app.schemas.data_quality import DataQualityProjection
from pydantic import ValidationError
from app.security import SecurityProblem
from app.workflow.publisher import producer_parameter_key_is_sensitive


_MAX_PAGE_SIZE = 100
_FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "proxy_authorization",
        "cookie",
        "set_cookie",
        "database_url",
        "password",
        "secret",
        "private_key",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "session_token",
        "restricted_full_text",
        "full_text",
        "raw_model_output",
        "model_output",
        "model_response",
        "completion_text",
        "raw_output",
        "raw_response",
        "prompt_text",
        "system_prompt",
        "chain_of_thought",
        "stack_trace",
        "traceback",
    }
)
_SAFE_REQUEST_METADATA_KEYS = frozenset(
    {
        "endpoint",
        "method",
        "request_class",
        "page",
        "page_size",
        "cursor",
        "status_code",
        "response_headers",
        "rate_limit",
        "interval",
        "concurrency",
        "origin_run_id",
        "origin_artifact_version_id",
    }
)
_SAFE_RESPONSE_HEADER_KEYS = frozenset(
    {
        "content_type",
        "etag",
        "last_modified",
        "x_api_pool",
        "rate_limit_ceiling",
        "x_rate_limit_interval",
        "retry_after",
    }
)
_AUTH_VALUE = re.compile(r"(?i)^\s*(?:bearer|basic)\s+\S+")
_ASSIGNMENT_NAME = re.compile(
    r"(?i)(?<![a-z0-9_])[\"']?([a-z][a-z0-9_.-]{1,63})[\"']?\s*[:=]\s*"
)
_STACK_VALUE = re.compile(
    r"(?i)(?:traceback\s*\(most recent call last\)|\bfile\s+\"[^\"]+\",\s+line\s+\d+)"
)


class ArtifactReadService:
    """Read PostgreSQL provenance without exposing cross-project existence."""

    def __init__(self, factory: Callable[[], Session]) -> None:
        self._factory = factory

    def list_run_artifacts(
        self,
        *,
        run_id: str,
        session_id: str,
        kind: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[ResearchArtifact, ...], str | None, bool]:
        _require_limit(limit)
        run_uuid = _uuid_or_not_found(run_id, "RUN_NOT_FOUND")
        cursor_scope = _artifact_cursor_scope(run_id=run_id, kind=kind)
        cursor_value = _decode_cursor(cursor, scope=cursor_scope) if cursor else None
        with self._factory() as session:
            run = session.get(ResearchRunModel, run_uuid)
            if run is None:
                raise _not_found("RUN_NOT_FOUND")
            self._require_project_owner(
                session, run.project_id, session_id, "RUN_NOT_FOUND"
            )
            statement = (
                select(ResearchArtifactModel)
                .join(
                    ArtifactVersionModel,
                    ArtifactVersionModel.artifact_id == ResearchArtifactModel.id,
                )
                .where(ArtifactVersionModel.created_by_run_id == run.id)
                .distinct()
                .order_by(
                    ResearchArtifactModel.created_at.desc(),
                    ResearchArtifactModel.id.desc(),
                )
            )
            if kind is not None:
                statement = statement.where(ResearchArtifactModel.kind == kind)
            if cursor_value is not None:
                created_at, artifact_id = cursor_value
                statement = statement.where(
                    or_(
                        ResearchArtifactModel.created_at < created_at,
                        and_(
                            ResearchArtifactModel.created_at == created_at,
                            ResearchArtifactModel.id < artifact_id,
                        ),
                    )
                )
            rows = tuple(session.scalars(statement.limit(limit + 1)))
            selected = rows[:limit]
            has_more = len(rows) > limit
            next_cursor = (
                _encode_cursor(
                    scope=cursor_scope,
                    created_at=selected[-1].created_at,
                    entity_id=selected[-1].id,
                )
                if selected and has_more
                else None
            )
            return tuple(_artifact(row) for row in selected), next_cursor, has_more

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        artifact_uuid = _uuid_or_not_found(artifact_id, "ARTIFACT_NOT_FOUND")
        with self._factory() as session:
            row = session.get(ResearchArtifactModel, artifact_uuid)
            if row is None:
                raise _not_found("ARTIFACT_NOT_FOUND")
            self._require_project_owner(
                session, row.project_id, session_id, "ARTIFACT_NOT_FOUND"
            )
            versions = tuple(
                session.scalars(
                    select(ArtifactVersionModel)
                    .where(ArtifactVersionModel.artifact_id == row.id)
                    .order_by(
                        ArtifactVersionModel.version_number.desc(),
                        ArtifactVersionModel.id.desc(),
                    )
                )
            )
            return ResearchArtifactDetail(
                **_artifact(row).model_dump(),
                versions=tuple(_version_summary(version) for version in versions),
            )

    def get_version(
        self,
        *,
        version_id: str,
        session_id: str,
        full_content: bool = False,
    ) -> ArtifactVersionDetail:
        version_uuid = _uuid_or_not_found(version_id, "ARTIFACT_VERSION_NOT_FOUND")
        with self._factory() as session:
            row = session.get(ArtifactVersionModel, version_uuid)
            if row is None:
                raise _not_found("ARTIFACT_VERSION_NOT_FOUND")
            self._require_project_owner(
                session, row.project_id, session_id, "ARTIFACT_VERSION_NOT_FOUND"
            )
            producer = session.get(ProducerExecutionModel, row.producer_execution_id)
            if producer is None or producer.run_id != row.created_by_run_id:
                raise _integrity_problem()
            snapshots = self._referenced_snapshots(
                session, row.source_snapshot_ids, row.project_id
            )
            evidence = self._referenced_evidence(
                session, row.evidence_ids, row.project_id, row.id
            )
            return ArtifactVersionDetail(
                id=str(row.id),
                artifact_id=str(row.artifact_id),
                project_id=str(row.project_id),
                created_by_run_id=str(row.created_by_run_id),
                version_number=row.version_number,
                schema_version=row.schema_version,
                content=_sanitize_object(
                    row.content,
                    max_string=1_000_000 if full_content else 8192,
                    max_items=None if full_content else 500,
                ),
                content_hash=row.content_hash,
                input_hash=row.input_hash,
                source_mode=row.source_mode,
                producer=ProducerReference.model_validate(row.producer),
                source_snapshot_ids=tuple(str(item.id) for item in snapshots),
                evidence_ids=tuple(str(item.id) for item in evidence),
                supersedes_version_id=(
                    str(row.supersedes_version_id)
                    if row.supersedes_version_id is not None
                    else None
                ),
                created_at=_utc(row.created_at),
                producer_execution=_producer_execution(producer),
                source_snapshots=tuple(_source_snapshot(item) for item in snapshots),
                evidence=tuple(_evidence(item) for item in evidence),
                quality_projection=row.quality_projection,
                quality_projection_hash=row.quality_projection_hash,
            )

    def list_dataset_rows(
        self,
        *,
        version_id: str,
        session_id: str,
        after_row_id: str | None,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        """Read one bounded, stable row page without loading ArtifactVersion.content."""
        version_uuid = _uuid_or_not_found(version_id, "ARTIFACT_VERSION_NOT_FOUND")
        with self._factory() as session:
            version = session.execute(
                select(
                    ArtifactVersionModel.id,
                    ArtifactVersionModel.project_id,
                    ArtifactVersionModel.artifact_id,
                    ArtifactVersionModel.content_hash,
                    ArtifactVersionModel.content["candidate_id"].astext.label(
                        "candidate_id"
                    ),
                    ArtifactVersionModel.content["input_hash"].astext.label(
                        "candidate_input_hash"
                    ),
                    ArtifactVersionModel.content["output_hash"].astext.label(
                        "candidate_output_hash"
                    ),
                    ArtifactVersionModel.content["row_count"].astext.label("row_count"),
                    ArtifactVersionModel.quality_projection,
                    ArtifactVersionModel.quality_projection_hash,
                    ResearchArtifactModel.kind,
                )
                .join(
                    ResearchArtifactModel,
                    ResearchArtifactModel.id == ArtifactVersionModel.artifact_id,
                )
                .where(ArtifactVersionModel.id == version_uuid)
            ).one_or_none()
            if version is None:
                raise _not_found("ARTIFACT_VERSION_NOT_FOUND")
            self._require_project_owner(
                session,
                version.project_id,
                session_id,
                "ARTIFACT_VERSION_NOT_FOUND",
            )
            if version.kind != "dataset":
                raise SecurityProblem(
                    status=409,
                    code="ARTIFACT_KIND_MISMATCH",
                    title="Artifact kind mismatch",
                    detail="The ArtifactVersion is not a dataset",
                )
            try:
                projection = DataQualityProjection.model_validate(
                    version.quality_projection
                )
            except ValidationError as exc:
                raise SecurityProblem(
                    status=409,
                    code="DATA_QUALITY_PROJECTION_REQUIRED",
                    title="Data quality projection required",
                    detail="The ArtifactVersion has no valid passing data quality projection",
                ) from exc
            if (
                version.quality_projection_hash != projection.content_hash
                or projection.candidate_kind != "dataset"
                or projection.candidate_id != version.candidate_id
                or projection.candidate_input_hash != version.candidate_input_hash
                or projection.candidate_output_hash != version.candidate_output_hash
                or projection.candidate_content_hash != version.content_hash
                or projection.quality_result_input_hash != projection.quality_input_hash
            ):
                raise SecurityProblem(
                    status=409,
                    code="DATA_QUALITY_PROJECTION_INVALID",
                    title="Data quality projection invalid",
                    detail="The Data Quality Evaluation projection is not bound to this ArtifactVersion",
                )
            projected_count = session.scalar(
                select(func.count())
                .select_from(DatasetRowProjectionModel)
                .where(
                    DatasetRowProjectionModel.artifact_version_id == version_uuid,
                    DatasetRowProjectionModel.project_id == version.project_id,
                )
            )
            try:
                expected_count = int(version.row_count)
            except (TypeError, ValueError) as exc:
                raise _integrity_problem() from exc
            if projected_count != expected_count:
                raise _integrity_problem()
            if after_row_id is not None:
                exists = session.scalar(
                    select(DatasetRowProjectionModel.row_id).where(
                        DatasetRowProjectionModel.artifact_version_id == version_uuid,
                        DatasetRowProjectionModel.project_id == version.project_id,
                        DatasetRowProjectionModel.row_id == after_row_id,
                    )
                )
                if exists is None:
                    raise SecurityProblem(
                        status=400,
                        code="INVALID_CURSOR",
                        title="Invalid cursor",
                        detail="The cursor row does not belong to this Dataset",
                    )
            query = select(DatasetRowProjectionModel).where(
                DatasetRowProjectionModel.artifact_version_id == version_uuid,
                DatasetRowProjectionModel.project_id == version.project_id,
            )
            if after_row_id is not None:
                query = query.where(DatasetRowProjectionModel.row_id > after_row_id)
            rows = session.scalars(
                query.order_by(DatasetRowProjectionModel.row_id).limit(limit)
            )
            return tuple(dict(row.row) for row in rows)

    def get_evidence(self, *, evidence_id: str, session_id: str) -> EvidenceRead:
        evidence_uuid = _uuid_or_not_found(evidence_id, "EVIDENCE_NOT_FOUND")
        with self._factory() as session:
            row = session.get(EvidenceModel, evidence_uuid)
            if row is None:
                raise _not_found("EVIDENCE_NOT_FOUND")
            self._require_project_owner(
                session, row.project_id, session_id, "EVIDENCE_NOT_FOUND"
            )
            snapshot = session.get(SourceSnapshotModel, row.source_snapshot_id)
            if snapshot is None or snapshot.project_id != row.project_id:
                raise _integrity_problem()
            return EvidenceRead(
                **_evidence(row).model_dump(),
                source_snapshot=_source_snapshot(snapshot),
            )

    def get_source_snapshot(
        self, *, snapshot_id: str, session_id: str
    ) -> SourceSnapshotDetail:
        snapshot_uuid = _uuid_or_not_found(snapshot_id, "SOURCE_SNAPSHOT_NOT_FOUND")
        with self._factory() as session:
            row = session.get(SourceSnapshotModel, snapshot_uuid)
            if row is None:
                raise _not_found("SOURCE_SNAPSHOT_NOT_FOUND")
            self._require_project_owner(
                session, row.project_id, session_id, "SOURCE_SNAPSHOT_NOT_FOUND"
            )
            return _source_snapshot(row)

    @staticmethod
    def _require_project_owner(
        session: Session,
        project_id: UUID,
        session_id: str,
        not_found_code: str,
    ) -> None:
        owner = session.scalar(
            select(ResearchProjectModel.session_id).where(
                ResearchProjectModel.id == project_id
            )
        )
        if owner is None or owner != session_id:
            raise _not_found(not_found_code)

    @staticmethod
    def _referenced_snapshots(
        session: Session, ids: Sequence[str], project_id: UUID
    ) -> tuple[SourceSnapshotModel, ...]:
        uuids = _reference_uuids(ids)
        rows = tuple(
            session.scalars(
                select(SourceSnapshotModel).where(
                    SourceSnapshotModel.id.in_(uuids),
                    SourceSnapshotModel.project_id == project_id,
                )
            )
        )
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(uuids):
            raise _integrity_problem()
        return tuple(by_id[item] for item in uuids)

    @staticmethod
    def _referenced_evidence(
        session: Session,
        ids: Sequence[str],
        project_id: UUID,
        version_id: UUID,
    ) -> tuple[EvidenceModel, ...]:
        uuids = _reference_uuids(ids)
        rows = tuple(
            session.scalars(
                select(EvidenceModel).where(
                    EvidenceModel.id.in_(uuids),
                    EvidenceModel.project_id == project_id,
                    EvidenceModel.artifact_version_id == version_id,
                )
            )
        )
        by_id = {row.id: row for row in rows}
        if len(by_id) != len(uuids):
            raise _integrity_problem()
        return tuple(by_id[item] for item in uuids)


def _artifact(row: ResearchArtifactModel) -> ResearchArtifact:
    return ResearchArtifact(
        id=str(row.id),
        project_id=str(row.project_id),
        kind=row.kind,
        title=row.title,
        logical_key=row.logical_key,
        created_at=_utc(row.created_at),
        latest_version_id=(
            str(row.latest_version_id) if row.latest_version_id else None
        ),
    )


def _version_summary(row: ArtifactVersionModel) -> ArtifactVersionSummary:
    return ArtifactVersionSummary(
        id=str(row.id),
        artifact_id=str(row.artifact_id),
        version_number=row.version_number,
        schema_version=row.schema_version,
        content_hash=row.content_hash,
        source_mode=row.source_mode,
        supersedes_version_id=(
            str(row.supersedes_version_id) if row.supersedes_version_id else None
        ),
        created_at=_utc(row.created_at),
    )


def _producer_execution(row: ProducerExecutionModel) -> ProducerExecutionDetail:
    parameters = {
        key: value for key, value in row.parameters.items() if not _sensitive_key(key)
    }
    return ProducerExecutionDetail(
        id=str(row.id),
        run_id=str(row.run_id),
        step_key=row.step_key,
        step_attempt_id=str(row.step_attempt_id),
        producer=ProducerReference(
            type=row.producer_type,
            name=row.producer_name,
            version=row.producer_version,
            model_provider=row.model_provider,
            model_name=row.model_name,
            prompt_name=row.prompt_name,
            prompt_version=row.prompt_version,
            prompt_hash=row.prompt_hash,
            parameters_hash=row.parameters_hash,
        ),
        parameters=_sanitize_object(parameters, max_string=256),
        parameters_hash=row.parameters_hash,
        input_hash=row.input_hash,
        output_hash=row.output_hash,
        status=row.status,
        started_at=_utc(row.started_at),
        finished_at=_utc(row.finished_at) if row.finished_at else None,
        token_usage=row.token_usage,
        latency_ms=row.latency_ms,
        error_code=(
            _sanitize_string(row.error_code, 128)
            if row.error_code is not None
            else None
        ),
    )


def _source_snapshot(row: SourceSnapshotModel) -> SourceSnapshotDetail:
    metadata = {
        key: value
        for key, value in row.request_metadata.items()
        if _normalized_key(key) in _SAFE_REQUEST_METADATA_KEYS
    }
    headers = metadata.get("response_headers")
    if isinstance(headers, Mapping):
        metadata["response_headers"] = {
            key: value
            for key, value in headers.items()
            if _normalized_key(str(key)) in _SAFE_RESPONSE_HEADER_KEYS
        }
    return SourceSnapshotDetail(
        id=str(row.id),
        source_id=row.source_id,
        source_type=row.source_type,
        retrieved_at=_utc(row.retrieved_at),
        query=_sanitize_json(row.query, max_string=512),
        query_hash=row.query_hash,
        source_version_or_etag=(
            _sanitize_string(row.source_version_or_etag, 256)
            if row.source_version_or_etag is not None
            else None
        ),
        content_hash=row.content_hash,
        license_note=_sanitize_string(row.license_note, 1000),
        cache_version=(
            _sanitize_string(row.cache_version, 128)
            if row.cache_version is not None
            else None
        ),
        request_metadata=_sanitize_object(metadata, max_string=256),
    )


def _evidence(row: EvidenceModel) -> EvidenceDetail:
    quote = None if row.is_restricted else _safe_quote(row.quote_or_value)
    return EvidenceDetail(
        id=str(row.id),
        artifact_version_id=str(row.artifact_version_id),
        target_type=row.target_type,
        target_id=row.target_id,
        evidence_type=row.evidence_type,
        source_snapshot_id=str(row.source_snapshot_id),
        paper_id=row.paper_id,
        locator=_sanitize_object(row.locator, max_string=512),
        quote_or_value=quote,
        extraction_method=row.extraction_method,
        confidence=row.confidence,
        created_at=_utc(row.created_at),
    )


def _safe_quote(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if not isinstance(value, str) or len(value) > 2000 or _AUTH_VALUE.search(value):
        return None
    return _sanitize_string(value, 2000)


def _sanitize_object(
    value: Mapping[str, Any], *, max_string: int, max_items: int | None = 500
) -> dict[str, Any]:
    sanitized = _sanitize_json(dict(value), max_string=max_string, max_items=max_items)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_json(value: Any, *, max_string: int, max_items: int | None = 500) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _sanitize_string(value, max_string)
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_json(nested, max_string=max_string, max_items=max_items)
            for key, nested in value.items()
            if not _sensitive_key(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = value if max_items is None else value[:max_items]
        return [
            _sanitize_json(item, max_string=max_string, max_items=max_items)
            for item in items
        ]
    return None


def _sanitize_string(value: str, max_length: int) -> str:
    if _AUTH_VALUE.search(value) or _STACK_VALUE.search(value):
        return "[REDACTED]"
    value = _strip_sensitive_url_parameters(value)
    if _contains_sensitive_assignment(value):
        return "[REDACTED]"
    return value if len(value) <= max_length else "[REDACTED]"


def _strip_sensitive_url_parameters(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[REDACTED]"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return value
    safe_query = [
        (key, nested)
        for key, nested in parse_qsl(parsed.query, keep_blank_values=True)
        if not _sensitive_key(key)
    ]
    if parsed.username is not None or parsed.password is not None:
        return "[REDACTED]"
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query), "")
    )


def _sensitive_key(key: str) -> bool:
    normalized = _normalized_key(key)
    return normalized in _FORBIDDEN_KEYS or producer_parameter_key_is_sensitive(
        normalized
    )


def _contains_sensitive_assignment(value: str) -> bool:
    return any(
        _sensitive_key(match.group(1)) for match in _ASSIGNMENT_NAME.finditer(value)
    )


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


def _reference_uuids(values: Sequence[str]) -> tuple[UUID, ...]:
    try:
        parsed = tuple(UUID(value) for value in values)
    except (TypeError, ValueError) as exc:
        raise _integrity_problem() from exc
    if len(parsed) != len(set(parsed)):
        raise _integrity_problem()
    return parsed


def _uuid_or_not_found(value: str, code: str) -> UUID:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise _not_found(code) from exc


def _require_limit(limit: int) -> None:
    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise SecurityProblem(
            status=422,
            code="SCHEMA_VALIDATION_FAILED",
            title="Request validation failed",
            detail="limit must be between 1 and 100",
        )


def _artifact_cursor_scope(*, run_id: str, kind: str | None) -> str:
    return json.dumps(
        {"run_id": run_id, "kind": kind},
        separators=(",", ":"),
        sort_keys=True,
    )


def _encode_cursor(*, scope: str, created_at: datetime, entity_id: UUID) -> str:
    payload = json.dumps(
        {
            "v": 1,
            "scope": scope,
            "created_at": _utc(created_at).isoformat(),
            "id": str(entity_id),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str, *, scope: str) -> tuple[datetime, UUID]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if set(payload) != {"v", "scope", "created_at", "id"}:
            raise ValueError
        if payload["v"] != 1 or payload["scope"] != scope:
            raise ValueError
        created_at = datetime.fromisoformat(payload["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
        return _utc(created_at), UUID(payload["id"])
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SecurityProblem(
            status=400,
            code="INVALID_CURSOR",
            title="Invalid cursor",
            detail="The cursor is invalid for this collection",
        ) from exc


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _not_found(code: str) -> SecurityProblem:
    return SecurityProblem(
        status=404,
        code=code,
        title="Resource not found",
        detail="Resource not found",
    )


def _integrity_problem() -> SecurityProblem:
    return SecurityProblem(
        status=403,
        code="PROVENANCE_SCOPE_VIOLATION",
        title="Provenance access denied",
        detail="The provenance graph is incomplete or outside the authorized project",
    )
