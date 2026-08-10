"""Typed data-artifact reads, cursors, and process-local exports."""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
import secrets
from threading import RLock
from typing import Any, Callable, Literal

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import ArtifactVersionDetail
from app.schemas.data_artifact_api import (
    ArtifactExportDownload,
    ArtifactExportRead,
    DataArtifactReadBase,
    DataArtifactRowRead,
    DatasetArtifactRead,
    FieldDictionaryArtifactRead,
    SourceCollectionArtifactRead,
)
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    DatasetRow,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
)
from app.schemas.manifest import DataType
from app.schemas.data_quality import DataQualityProjection
from app.security import SecurityProblem
from app.config import settings
from app.services.artifacts import ArtifactReadService


_MAX_PAGE_SIZE = 100
_EXPORT_TTL = timedelta(minutes=15)
_MAX_EXPORTS_PER_SESSION = 8
_MAX_EXPORT_BYTES_PER_SESSION = 50 * 1024 * 1024
_MAX_ARTIFACT_CONTENT_BYTES = 50 * 1024 * 1024
_MAX_DATASET_ROWS = 1_000_000
_ROW_ORDERING = "row_id.asc"
_ROW_QUERY_SCOPE = compute_canonical_payload_hash({"filters": {}, "ordering": _ROW_ORDERING})
DataKind = Literal["dataset", "field_dictionary", "source_collection"]


class DataArtifactReadService:
    """Validate and project Versioned Data Artifact/Data Quality Evaluation output without rerunning its algorithms."""

    def __init__(self, artifacts: ArtifactReadService) -> None:
        self._artifacts = artifacts

    def get_dataset(self, *, version_id: str, session_id: str) -> DatasetArtifactRead:
        version = self._version(version_id=version_id, session_id=session_id, kind="dataset")
        candidate = self._candidate(version, DatasetArtifactCandidate)
        return DatasetArtifactRead(
            **_base(version).model_dump(),
            dataset=candidate,
        )

    def get_field_dictionary(
        self, *, version_id: str, session_id: str
    ) -> FieldDictionaryArtifactRead:
        version = self._version(
            version_id=version_id, session_id=session_id, kind="field_dictionary"
        )
        candidate = self._candidate(version, FieldDictionaryArtifactCandidate)
        return FieldDictionaryArtifactRead(
            **_base(version).model_dump(),
            field_dictionary=candidate,
        )

    def get_source_collection(
        self, *, version_id: str, session_id: str
    ) -> SourceCollectionArtifactRead:
        version = self._version(
            version_id=version_id, session_id=session_id, kind="source_collection"
        )
        candidate = self._candidate(version, SourceCollectionArtifactCandidate)
        return SourceCollectionArtifactRead(
            **_base(version).model_dump(),
            source_collection=candidate,
        )

    def list_dataset_rows(
        self,
        *,
        version_id: str,
        session_id: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[tuple[DataArtifactRowRead, ...], str | None, bool]:
        if not 1 <= limit <= _MAX_PAGE_SIZE:
            raise _problem(422, "SCHEMA_VALIDATION_FAILED", "Request validation failed", "limit must be between 1 and 100")
        projected_reader = getattr(self._artifacts, "list_dataset_rows", None)
        if callable(projected_reader):
            cursor_id = (
                _decode_cursor(cursor, version_id=version_id)
                if cursor is not None
                else None
            )
            raw_rows = projected_reader(
                version_id=version_id,
                session_id=session_id,
                after_row_id=cursor_id,
                limit=limit + 1,
            )
            try:
                rows = tuple(DatasetRow.model_validate(row) for row in raw_rows)
            except ValidationError as exc:
                raise _schema_problem() from exc
            has_more = len(rows) > limit
            selected = rows[:limit]
            next_cursor = (
                _encode_cursor(version_id=version_id, row_id=selected[-1].row_id)
                if selected and has_more
                else None
            )
            return (
                tuple(
                    DataArtifactRowRead(artifact_version_id=version_id, row=row)
                    for row in selected
                ),
                next_cursor,
                has_more,
            )

        detail = self.get_dataset(version_id=version_id, session_id=session_id)
        rows = tuple(sorted(detail.dataset.rows, key=lambda row: row.row_id))
        row_ids = tuple(row.row_id for row in rows)
        if len(row_ids) != len(set(row_ids)):
            raise _schema_problem()
        start = 0
        if cursor is not None:
            cursor_id = _decode_cursor(cursor, version_id=detail.artifact_version_id)
            try:
                start = row_ids.index(cursor_id) + 1
            except ValueError as exc:
                raise _invalid_cursor() from exc
        selected = rows[start : start + limit]
        has_more = start + len(selected) < len(rows)
        next_cursor = (
            _encode_cursor(version_id=detail.artifact_version_id, row_id=selected[-1].row_id)
            if selected and has_more
            else None
        )
        return tuple(
            DataArtifactRowRead(artifact_version_id=detail.artifact_version_id, row=row)
            for row in selected
        ), next_cursor, has_more

    def create_export(
        self,
        *,
        version_id: str,
        session_id: str,
        idempotency_key: str,
        export_format: Literal["csv", "json", "provenance_report"],
    ) -> ArtifactExportDownload:
        if export_format not in {"csv", "json", "provenance_report"}:
            raise _problem(
                422,
                "EXPORT_FORMAT_UNSUPPORTED",
                "Export format unsupported",
                "format must be csv, json, or provenance_report",
            )
        if not idempotency_key.strip() or len(idempotency_key) > 200:
            raise _problem(
                422,
                "SCHEMA_VALIDATION_FAILED",
                "Request validation failed",
                "Idempotency-Key must contain at most 200 characters",
            )
        replay = _EXPORTS.replay(
            session_id=session_id,
            idempotency_key=idempotency_key,
            version_id=version_id,
            export_format=export_format,
        )
        if replay is not None:
            return replay
        version = self._version(version_id=version_id, session_id=session_id, kind=None)
        artifact = self._artifacts.get_artifact(
            artifact_id=version.artifact_id, session_id=session_id
        )
        kind = artifact.kind.value
        if kind not in {"dataset", "field_dictionary", "source_collection"}:
            raise _problem(409, "ARTIFACT_KIND_MISMATCH", "Artifact kind mismatch", "The ArtifactVersion is not a data artifact")
        typed = self._typed_for_export(version, kind)  # type: ignore[arg-type]
        payload, media_type, filename = _render_export(typed, export_format)
        now = datetime.now(UTC)
        export_id = f"exp_{secrets.token_urlsafe(18)}"
        record = ArtifactExportDownload(
            export=ArtifactExportRead(
                id=export_id,
                artifact_version_id=version.id,
                project_id=version.project_id,
                format=export_format,
                status="completed",
                content_hash=version.content_hash,
                generated_at=now,
                expires_at=now + _EXPORT_TTL,
                download_url=f"/api/exports/{export_id}/download",
            ),
            content=payload,
            media_type=media_type,
            filename=filename,
        )
        return _EXPORTS.put(
            export_id,
            session_id,
            idempotency_key=idempotency_key,
            version_id=version_id,
            export_format=export_format,
            item=record,
        )

    def get_export(self, *, export_id: str, session_id: str) -> ArtifactExportRead:
        return _EXPORTS.get(export_id, session_id).export

    def download_export(self, *, export_id: str, session_id: str) -> ArtifactExportDownload:
        return _EXPORTS.get(export_id, session_id)

    def _version(
        self,
        *,
        version_id: str,
        session_id: str,
        kind: DataKind | None,
        full_content: bool = True,
    ) -> ArtifactVersionDetail:
        version = self._artifacts.get_version(
            version_id=version_id,
            session_id=session_id,
            full_content=full_content,
        )
        if kind is not None:
            artifact = self._artifacts.get_artifact(
                artifact_id=version.artifact_id, session_id=session_id
            )
            if artifact.kind.value != kind:
                raise _problem(409, "ARTIFACT_KIND_MISMATCH", "Artifact kind mismatch", f"The ArtifactVersion is not a {kind}")
        return version

    @staticmethod
    def _candidate(version: ArtifactVersionDetail, model: type[Any]) -> Any:
        try:
            candidate = model.model_validate(version.content)
        except ValidationError as exc:
            raise _schema_problem() from exc
        if len(json.dumps(version.content, ensure_ascii=False).encode("utf-8")) > _MAX_ARTIFACT_CONTENT_BYTES:
            raise _problem(413, "ARTIFACT_SIZE_LIMIT_EXCEEDED", "Artifact size limit exceeded", "The ArtifactVersion exceeds the API read size limit")
        if isinstance(candidate, DatasetArtifactCandidate) and len(candidate.rows) > _MAX_DATASET_ROWS:
            raise _problem(413, "DATASET_ROW_LIMIT_EXCEEDED", "Dataset row limit exceeded", "The Dataset exceeds the API row limit")
        snapshot_ids = tuple(item.id for item in version.source_snapshots)
        evidence_ids = tuple(item.id for item in version.evidence)
        candidate_snapshot_ids = tuple(candidate.source_snapshot_ids)
        candidate_evidence_ids = tuple(candidate.evidence_ids)
        candidate_snapshot_set = set(candidate_snapshot_ids)
        if (
            version.schema_version != candidate.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.input_hash != candidate.input_hash
            or tuple(version.source_snapshot_ids) != candidate_snapshot_ids
            or tuple(version.evidence_ids) != candidate_evidence_ids
            or snapshot_ids != candidate_snapshot_ids
            or evidence_ids != candidate_evidence_ids
            or any(
                item.artifact_version_id != version.id
                or item.source_snapshot_id not in candidate_snapshot_set
                for item in version.evidence
            )
        ):
            raise _schema_problem()
        _quality_projection(version, candidate)
        return candidate

    def _typed_for_export(
        self, version: ArtifactVersionDetail, kind: DataKind
    ) -> DataArtifactReadBase:
        if kind == "dataset":
            candidate = self._candidate(version, DatasetArtifactCandidate)
            return DatasetArtifactRead(**_base(version).model_dump(), dataset=candidate)
        if kind == "field_dictionary":
            candidate = self._candidate(version, FieldDictionaryArtifactCandidate)
            return FieldDictionaryArtifactRead(
                **_base(version).model_dump(), field_dictionary=candidate
            )
        candidate = self._candidate(version, SourceCollectionArtifactCandidate)
        return SourceCollectionArtifactRead(
            **_base(version).model_dump(), source_collection=candidate
        )


class _ExportStore:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._items: dict[str, tuple[str, ArtifactExportDownload]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, str, str]] = {}
        self._lock = RLock()
        self._clock = clock or (lambda: datetime.now(UTC))

    def _cleanup(self, now: datetime) -> None:
        expired_ids = {
            export_id
            for export_id, (_, item) in self._items.items()
            if item.export.expires_at <= now
        }
        for export_id in expired_ids:
            self._items.pop(export_id, None)
        for key, value in tuple(self._idempotency.items()):
            if value[2] in expired_ids:
                self._idempotency.pop(key, None)

    def put(
        self,
        export_id: str,
        session_id: str,
        *,
        idempotency_key: str,
        version_id: str,
        export_format: str,
        item: ArtifactExportDownload,
    ) -> ArtifactExportDownload:
        with self._lock:
            self._cleanup(self._clock())
            key = (session_id, idempotency_key)
            existing = self._idempotency.get(key)
            if existing is not None:
                if existing[:2] != (version_id, export_format):
                    raise _problem(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Idempotency conflict",
                        "The Idempotency-Key was already used for a different export",
                    )
                stored = self._items.get(existing[2])
                if stored is not None:
                    return stored[1]
            session_items = [
                stored
                for owner, stored in self._items.values()
                if owner == session_id
            ]
            session_bytes = sum(len(stored.content) for stored in session_items)
            if len(session_items) >= _MAX_EXPORTS_PER_SESSION:
                raise _problem(429, "EXPORT_QUOTA_EXCEEDED", "Export quota exceeded", "Too many active exports for this session")
            if session_bytes + len(item.content) > _MAX_EXPORT_BYTES_PER_SESSION:
                raise _problem(413, "EXPORT_SIZE_LIMIT_EXCEEDED", "Export size limit exceeded", "The session export byte limit was exceeded")
            self._items[export_id] = (session_id, item)
            self._idempotency[key] = (
                version_id,
                export_format,
                export_id,
            )
            return item

    def replay(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        version_id: str,
        export_format: str,
    ) -> ArtifactExportDownload | None:
        with self._lock:
            self._cleanup(self._clock())
            replay = self._idempotency.get((session_id, idempotency_key))
            if replay is None:
                return None
            if replay[:2] != (version_id, export_format):
                raise _problem(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Idempotency conflict",
                    "The Idempotency-Key was already used for a different export",
                )
            item = self._items.get(replay[2])
        if item is None:
            return None
        return item[1]

    def get(self, export_id: str, session_id: str) -> ArtifactExportDownload:
        with self._lock:
            self._cleanup(self._clock())
            item = self._items.get(export_id)
        if item is None or item[0] != session_id:
            raise _not_found("EXPORT_NOT_FOUND")
        return item[1]


_EXPORTS = _ExportStore()


def _base(version: ArtifactVersionDetail) -> DataArtifactReadBase:
    return DataArtifactReadBase(
        artifact_version_id=version.id,
        artifact_id=version.artifact_id,
        project_id=version.project_id,
        schema_version=version.schema_version,
        source_mode=version.source_mode,
        content_hash=version.content_hash,
        input_hash=version.input_hash,
        created_at=version.created_at,
        producer_execution=version.producer_execution,
        source_snapshots=version.source_snapshots,
        evidence=version.evidence,
        quality_projection=DataQualityProjection.model_validate(
            version.quality_projection
        ),
    )


def _render_export(
    typed: DataArtifactReadBase,
    export_format: Literal["csv", "json", "provenance_report"],
) -> tuple[bytes, str, str]:
    payload = typed.model_dump(mode="json")
    version_id = typed.artifact_version_id
    if export_format == "json":
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), "application/json", f"{version_id}.json"
    if export_format == "provenance_report":
        report = {
            key: payload[key]
            for key in (
                "artifact_version_id", "artifact_id", "project_id", "schema_version",
                "source_mode", "content_hash", "input_hash", "created_at",
                "producer_execution", "source_snapshots", "evidence",
                "quality_projection",
            )
        }
        report["quality_projection_hash"] = payload["quality_projection"]["content_hash"]
        return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), "application/json", f"{version_id}.provenance.json"
    if not isinstance(typed, DatasetArtifactRead):
        raise _problem(422, "EXPORT_FORMAT_UNSUPPORTED", "Export format unsupported", "CSV export is only supported for Dataset artifacts")
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    fields = [column.field for column in typed.dataset.columns]
    writer.writerow(["row_id", *(field.field_id for field in fields)])
    for row in typed.dataset.rows:
        values = {item.canonical_field_id: _outcome_value(item) for item in row.fields}
        writer.writerow(
            [
                row.row_id,
                *(
                    _csv_cell(values.get(field.field_id), field.data_type)
                    for field in fields
                ),
            ]
        )
    return output.getvalue().encode("utf-8"), "text/csv; charset=utf-8", f"{version_id}.csv"


def _outcome_value(outcome: Any) -> Any:
    value = outcome.model_dump(mode="json")
    return value.get("canonical_value", value.get("reason", value.get("status", "")))


def _csv_cell(value: Any, data_type: DataType | None = None) -> Any:
    """Keep exported text from being interpreted as a spreadsheet formula."""
    if (
        isinstance(value, str)
        and data_type not in {DataType.integer, DataType.number}
        and value.lstrip(" \t\r\n")[:1] in {"=", "+", "-", "@"}
    ):
        return "'" + value
    return value


def _encode_cursor(*, version_id: str, row_id: str) -> str:
    payload = {
        "v": 2,
        "version_id": version_id,
        "row_id": row_id,
        "ordering": _ROW_ORDERING,
        "query_scope": _ROW_QUERY_SCOPE,
    }
    payload["signature"] = _cursor_signature(payload)
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(value: str, *, version_id: str) -> str:
    try:
        if len(value) > 4096:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if (
            set(payload)
            != {"v", "version_id", "row_id", "ordering", "query_scope", "signature"}
            or payload["v"] != 2
            or payload["version_id"] != version_id
            or payload["ordering"] != _ROW_ORDERING
            or payload["query_scope"] != _ROW_QUERY_SCOPE
            or not isinstance(payload["signature"], str)
            or not hmac.compare_digest(
                payload["signature"],
                _cursor_signature(
                    {key: item for key, item in payload.items() if key != "signature"}
                ),
            )
        ):
            raise ValueError
        if not isinstance(payload["row_id"], str) or not payload["row_id"]:
            raise ValueError
        return payload["row_id"]
    except (binascii.Error, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise _invalid_cursor() from exc


def _cursor_signature(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    key = settings.CURSOR_SIGNING_KEY.get_secret_value().encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _quality_projection(
    version: ArtifactVersionDetail,
    candidate: DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | SourceCollectionArtifactCandidate,
) -> DataQualityProjection:
    try:
        projection = DataQualityProjection.model_validate(version.quality_projection)
    except ValidationError as exc:
        raise _problem(
            409,
            "DATA_QUALITY_PROJECTION_REQUIRED",
            "Data quality projection required",
            "The ArtifactVersion has no valid passing data quality projection",
        ) from exc
    if (
        version.quality_projection_hash != projection.content_hash
        or projection.candidate_kind != candidate.kind
        or projection.candidate_id != candidate.candidate_id
        or projection.candidate_input_hash != candidate.input_hash
        or projection.candidate_output_hash != candidate.output_hash
        or projection.candidate_content_hash != version.content_hash
        or projection.quality_result_input_hash != projection.quality_input_hash
    ):
        raise _problem(
            409,
            "DATA_QUALITY_PROJECTION_INVALID",
            "Data quality projection invalid",
            "The Data Quality Evaluation projection is not bound to this ArtifactVersion",
        )
    return projection


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


def _schema_problem() -> SecurityProblem:
    return _problem(422, "DATA_ARTIFACT_SCHEMA_INVALID", "Data artifact Schema invalid", "The ArtifactVersion content is not a valid data artifact")


def _invalid_cursor() -> SecurityProblem:
    return _problem(400, "INVALID_CURSOR", "Invalid cursor", "The cursor is invalid for this Dataset")


def _not_found(code: str) -> SecurityProblem:
    return _problem(404, code, "Resource not found", "Resource not found")
