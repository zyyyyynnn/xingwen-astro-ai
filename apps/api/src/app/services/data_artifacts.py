"""B-05 typed data artifact reads, cursors and process-local exports."""

from __future__ import annotations

import base64
import binascii
import csv
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from io import StringIO
import json
import secrets
from threading import RLock
from typing import Any, Literal

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
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
)
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService


_MAX_PAGE_SIZE = 100
_EXPORT_TTL = timedelta(minutes=15)
DataKind = Literal["dataset", "field_dictionary", "source_collection"]


class DataArtifactReadService:
    """Validate and project C-04/C-05 output without rerunning its algorithms."""

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
        self, *, version_id: str, session_id: str, kind: DataKind | None
    ) -> ArtifactVersionDetail:
        version = self._artifacts.get_version(
            version_id=version_id, session_id=session_id, full_content=True
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
        if (
            version.schema_version != candidate.schema_version
            or version.content_hash != compute_canonical_payload_hash(version.content)
            or version.input_hash != candidate.input_hash
            or len(version.source_snapshot_ids) != len(candidate.source_snapshot_ids)
            or len(version.evidence_ids) != len(candidate.evidence_ids)
            or len(version.source_snapshots) != len(candidate.source_snapshot_ids)
            or len(version.evidence) != len(candidate.evidence_ids)
        ):
            raise _schema_problem()
        if _contains_unsafe_html(candidate.model_dump(mode="json")):
            raise _schema_problem()
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
    def __init__(self) -> None:
        self._items: dict[str, tuple[str, ArtifactExportDownload]] = {}
        self._idempotency: dict[tuple[str, str], tuple[str, str, str]] = {}
        self._lock = RLock()

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
        if item is None or item[1].export.expires_at <= datetime.now(UTC):
            return None
        return item[1]

    def get(self, export_id: str, session_id: str) -> ArtifactExportDownload:
        with self._lock:
            item = self._items.get(export_id)
        if item is None or item[0] != session_id:
            raise _not_found("EXPORT_NOT_FOUND")
        if item[1].export.expires_at <= datetime.now(UTC):
            raise _problem(404, "EXPORT_EXPIRED", "Export expired", "The export is no longer available")
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
            )
        }
        return json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"), "application/json", f"{version_id}.provenance.json"
    if not isinstance(typed, DatasetArtifactRead):
        raise _problem(422, "EXPORT_FORMAT_UNSUPPORTED", "Export format unsupported", "CSV export is only supported for Dataset artifacts")
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    fields = [column.field.field_id for column in typed.dataset.columns]
    writer.writerow(["row_id", *fields])
    for row in typed.dataset.rows:
        values = {item.canonical_field_id: _outcome_value(item) for item in row.fields}
        writer.writerow(
            [row.row_id, *(_csv_cell(values.get(field)) for field in fields)]
        )
    return output.getvalue().encode("utf-8"), "text/csv; charset=utf-8", f"{version_id}.csv"


def _outcome_value(outcome: Any) -> Any:
    value = outcome.model_dump(mode="json")
    return value.get("canonical_value", value.get("reason", value.get("status", "")))


def _csv_cell(value: Any) -> Any:
    """Keep exported text from being interpreted as a spreadsheet formula."""
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value


def _encode_cursor(*, version_id: str, row_id: str) -> str:
    payload = json.dumps({"v": 1, "version_id": version_id, "row_id": row_id}, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str, *, version_id: str) -> str:
    try:
        if len(value) > 4096:
            raise ValueError
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
        if set(payload) != {"v", "version_id", "row_id"} or payload["v"] != 1 or payload["version_id"] != version_id:
            raise ValueError
        if not isinstance(payload["row_id"], str) or not payload["row_id"]:
            raise ValueError
        return payload["row_id"]
    except (binascii.Error, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise _invalid_cursor() from exc


def _contains_unsafe_html(value: Any) -> bool:
    if isinstance(value, str):
        return "<script" in value.lower() or "</" in value.lower()
    if isinstance(value, Mapping):
        return any(_contains_unsafe_html(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_unsafe_html(item) for item in value)
    return False


def _problem(status: int, code: str, title: str, detail: str) -> SecurityProblem:
    return SecurityProblem(status=status, code=code, title=title, detail=detail)


def _schema_problem() -> SecurityProblem:
    return _problem(422, "DATA_ARTIFACT_SCHEMA_INVALID", "Data artifact Schema invalid", "The ArtifactVersion content is not a valid data artifact")


def _invalid_cursor() -> SecurityProblem:
    return _problem(400, "INVALID_CURSOR", "Invalid cursor", "The cursor is invalid for this Dataset")


def _not_found(code: str) -> SecurityProblem:
    return _problem(404, code, "Resource not found", "Resource not found")
