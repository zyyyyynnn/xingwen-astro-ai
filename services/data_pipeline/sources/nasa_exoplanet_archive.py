"""NASA Exoplanet Archive TOI TAP adapter with bounded keyset pagination."""

from __future__ import annotations

import json
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime, timezone
from email.message import Message
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import SourceMode, UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.source_acquisition import (
    DataQueryCursor,
    DataSourceDataLevel,
    DataSourcePage,
    NormalizedDataSourceQuery,
    RawDataSourceRecord,
    compute_raw_data_record_hash,
)

from ..constants import (
    FROZEN_X00_MAIN_SHA,
    NASA_TAP_ADAPTER_VERSION,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    RETRY_POLICY_VERSION,
    SOURCE_POLICY_VERSION,
)
from ..manifest import load_frozen_manifest_bundle
from ..query import normalize_toi_query, render_toi_page_query
from .base import (
    Clock,
    DataSourceAcquisitionResult,
    HttpResponse,
    HttpTransport,
    MonotonicClock,
    Sleeper,
    SourceFailure,
)


LOGGER = logging.getLogger(__name__)
NASA_TAP_SYNC_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
NASA_TOI_DOCUMENTATION_URL = (
    "https://exoplanetarchive.ipac.caltech.edu/docs/API_TOI_columns.html"
)
NASA_TOI_LICENSE_NOTE = (
    "NASA Exoplanet Archive TOI metadata is publicly queryable; preserve archive "
    "attribution and follow the archive acknowledgement and citation guidance."
)
_ALLOWED_HOSTS = frozenset({"exoplanetarchive.ipac.caltech.edu"})
SAFE_RESPONSE_HEADERS = frozenset(
    {
        "date",
        "etag",
        "last-modified",
        "retry-after",
        "x-request-id",
        "x-correlation-id",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
        "x-rate-limit-reset",
    }
)


class TransportPolicyError(OSError):
    pass


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise TransportPolicyError("NASA TAP redirect host is not allowlisted")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibTransport(HttpTransport):
    max_response_bytes = 8_000_000

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_AllowlistedRedirectHandler())

    def request(
        self,
        *,
        url: str,
        params: Mapping[str, str | int],
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise TransportPolicyError("NASA TAP endpoint is not allowlisted")
        encoded = urllib.parse.urlencode(sorted(params.items()))
        request = urllib.request.Request(f"{url}?{encoded}", headers=dict(headers))
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise OSError("NASA TAP response exceeded size limit")
                return HttpResponse(
                    status_code=response.status,
                    headers=_message_headers(response.headers),
                    body=body,
                )
        except urllib.error.HTTPError as exc:
            body = exc.read(self.max_response_bytes + 1)
            return HttpResponse(
                status_code=exc.code,
                headers=_message_headers(exc.headers),
                body=body[: self.max_response_bytes],
            )
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise TimeoutError("NASA TAP request timed out") from None
            raise OSError("NASA TAP transport failed") from None


class NasaExoplanetArchiveAdapter:
    source_id = "nasa_exoplanet_archive.toi"
    adapter_name = "nasa_exoplanet_archive_tap"
    adapter_version = NASA_TAP_ADAPTER_VERSION

    def __init__(
        self,
        *,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 4.0,
        page_delay_seconds: float = 0.25,
        clock: Clock | None = None,
        monotonic: MonotonicClock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between one and five")
        if min(base_backoff_seconds, max_backoff_seconds, page_delay_seconds) < 0:
            raise ValueError("delay values must not be negative")
        self.transport = transport or UrllibTransport()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.page_delay_seconds = page_delay_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper

    def acquire(
        self,
        query: NormalizedDataSourceQuery,
        *,
        source_mode: SourceMode,
        data_level: DataSourceDataLevel,
    ) -> DataSourceAcquisitionResult:
        _validate_origin(source_mode, data_level)
        _validate_query_contract(query)

        fixture_metadata = _fixture_metadata(self.transport, source_mode)
        schema_query = render_toi_schema_query(query)
        schema_params = {"query": schema_query, "format": "json"}
        schema_response, schema_attempts, schema_latency_ms = self._request(schema_params)
        schema_rows = _decode_json_array(schema_response.body, "NASA_TAP_SCHEMA_INVALID_JSON")
        _validate_schema_rows(schema_rows, query)
        schema_request_hash = _request_hash(schema_params)
        schema_response_hash = compute_canonical_payload_hash(schema_rows)
        schema_headers = _safe_headers(schema_response.headers)
        schema_request_id = schema_headers.get("x-request-id") or schema_headers.get(
            "x-correlation-id"
        )

        records: list[RawDataSourceRecord] = []
        pages: list[DataSourcePage] = []
        seen_row_keys: set[tuple[tuple[str, str], ...]] = set()
        etags: list[str] = []
        total_retries = schema_attempts - 1
        cursor: DataQueryCursor | None = None
        for page_number in range(1, query.pagination.max_pages + 1):
            remaining = query.pagination.record_limit - len(records)
            if remaining <= 0:
                break
            requested_rows = min(query.pagination.page_size, remaining)
            page_query = render_toi_page_query(
                query,
                cursor=cursor,
                requested_rows=requested_rows,
            )
            params = {"query": page_query, "format": "json"}
            response, attempt_count, latency_ms = self._request(params)
            total_retries += attempt_count - 1
            payload = _decode_json_array(response.body, "NASA_TAP_INVALID_JSON")
            if len(payload) > requested_rows:
                raise SourceFailure(
                    UpstreamFailureClass.invalid_response,
                    "NASA_TAP_PAGE_SIZE_EXCEEDED",
                    retryable=False,
                )
            page_records, cursor_after = _parse_records(payload, query, cursor)
            for record in page_records:
                if record.row_key in seen_row_keys:
                    raise SourceFailure(
                        UpstreamFailureClass.invalid_response,
                        "NASA_TAP_DUPLICATE_ROW_KEY",
                        retryable=False,
                    )
                seen_row_keys.add(record.row_key)
            retrieved_at = self._aware_now()
            normalized_headers = _safe_headers(response.headers)
            if etag := normalized_headers.get("etag"):
                etags.append(etag)
            response_metadata = {
                key: value
                for key, value in normalized_headers.items()
                if key != "etag"
            }
            request_id = normalized_headers.get("x-request-id") or normalized_headers.get(
                "x-correlation-id"
            )
            response_metadata["request_id"] = request_id
            page = DataSourcePage(
                page_number=page_number,
                requested_rows=requested_rows,
                returned_rows=len(page_records),
                attempt_count=attempt_count,
                status_code=response.status_code,
                retrieved_at=retrieved_at,
                latency_ms=latency_ms,
                cursor_before=cursor,
                cursor_after=cursor_after,
                request_hash=_request_hash(params),
                response_hash=compute_canonical_payload_hash(
                    [record.payload for record in page_records]
                ),
                response_metadata=response_metadata,
            )
            pages.append(page)
            records.extend(page_records)
            cursor = cursor_after
            if len(page_records) < requested_rows:
                break
            if page_number < query.pagination.max_pages and remaining > requested_rows:
                self.sleeper(self.page_delay_seconds)

        content_hash = compute_canonical_payload_hash(
            {
                "source_id": self.source_id,
                "query_hash": query.query_hash,
                "record_hashes": [record.content_hash for record in records],
                "pages": [
                    page.model_dump(
                        mode="json",
                        exclude={"retrieved_at", "latency_ms"},
                        exclude_none=True,
                    )
                    for page in pages
                ],
                "schema_response_hash": schema_response_hash,
            }
        )
        snapshot_fingerprint = compute_canonical_payload_hash(
            {
                "source_id": self.source_id,
                "query_hash": query.query_hash,
                "content_hash": content_hash,
            }
        )
        request_ids = [schema_request_id] + [
            page.response_metadata.get("request_id") for page in pages
        ]
        snapshot = SourceSnapshotRecord(
            snapshot_id=(
                "snapshot.nasa-toi."
                f"{snapshot_fingerprint.removeprefix('sha256:')[:24]}"
            ),
            source_id=self.source_id,
            source_type="astronomical_catalog_metadata",
            retrieved_at=pages[0].retrieved_at if pages else self._aware_now(),
            query=json.dumps(
                query.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            query_hash=query.query_hash,
            source_version_or_etag=",".join(sorted(set(etags))) or None,
            content_hash=content_hash,
            license_note=NASA_TOI_LICENSE_NOTE,
            cache_version=None,
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
                "producer": {
                    "name": PRODUCER_NAME,
                    "version": PRODUCER_VERSION,
                },
                "rule_versions": {
                    "query_normalization": query.normalization_rule_version,
                    "retry_policy": RETRY_POLICY_VERSION,
                    "source_policy": SOURCE_POLICY_VERSION,
                },
                "x00_main_sha": FROZEN_X00_MAIN_SHA,
                "endpoint": NASA_TAP_SYNC_URL,
                "documentation_url": NASA_TOI_DOCUMENTATION_URL,
                "source_mode": source_mode.value,
                "data_level": data_level.value,
                "timeout_seconds": self.timeout_seconds,
                "pagination_strategy": "keyset:tid,toi",
                "source_version_or_etag_status": (
                    "available" if etags else "unavailable"
                ),
                "request_id_status": _availability_status(request_ids),
                "schema_preflight": {
                    "adql": schema_query,
                    "request_hash": schema_request_hash,
                    "response_hash": schema_response_hash,
                    "attempt_count": schema_attempts,
                    "status_code": schema_response.status_code,
                    "latency_ms": schema_latency_ms,
                    "column_count": len(schema_rows),
                    "request_id": schema_request_id,
                    "response_date": schema_headers.get("date"),
                    "rate_limit_metadata": {
                        key: value
                        for key, value in schema_headers.items()
                        if key.startswith("x-rate-limit-")
                        or key == "retry-after"
                    },
                },
                "pages": [
                    {
                        "page_number": page.page_number,
                        "requested_rows": page.requested_rows,
                        "returned_rows": page.returned_rows,
                        "attempt_count": page.attempt_count,
                        "status_code": page.status_code,
                        "latency_ms": page.latency_ms,
                        "request_hash": page.request_hash,
                        "response_hash": page.response_hash,
                        "request_id": page.response_metadata.get("request_id"),
                        "adql": render_toi_page_query(
                            query,
                            cursor=page.cursor_before,
                            requested_rows=page.requested_rows,
                        ),
                        "cursor_before": (
                            page.cursor_before.model_dump(mode="json")
                            if page.cursor_before
                            else None
                        ),
                        "cursor_after": (
                            page.cursor_after.model_dump(mode="json")
                            if page.cursor_after
                            else None
                        ),
                        "response_date": page.response_metadata.get("date"),
                        "rate_limit_metadata": {
                            key: value
                            for key, value in page.response_metadata.items()
                            if key.startswith("x-rate-limit-")
                            or key == "retry-after"
                        },
                    }
                    for page in pages
                ],
                **({"fixture": fixture_metadata} if fixture_metadata else {}),
            },
        )
        return DataSourceAcquisitionResult(
            records=tuple(records),
            pages=tuple(pages),
            snapshot=snapshot,
            retry_count=total_retries,
        )

    def _request(
        self, params: Mapping[str, str | int]
    ) -> tuple[HttpResponse, int, int]:
        failure: SourceFailure | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "xingwen-astro-ai/0.1 "
                "(https://github.com/zyyyyynnn/xingwen-astro-ai; scientific metadata)"
            ),
        }
        for attempt in range(1, self.max_attempts + 1):
            started = self.monotonic()
            response: HttpResponse | None = None
            try:
                response = self.transport.request(
                    url=NASA_TAP_SYNC_URL,
                    params=params,
                    headers=headers,
                    timeout_seconds=self.timeout_seconds,
                )
                latency_ms = max(0, round((self.monotonic() - started) * 1000))
                failure = _classify_status(response.status_code)
                if failure is None:
                    return response, attempt, latency_ms
            except TransportPolicyError:
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.policy_violation,
                    "NASA_TAP_TRANSPORT_POLICY_VIOLATION",
                    retryable=False,
                )
            except (TimeoutError, socket.timeout):
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.timeout,
                    "NASA_TAP_TIMEOUT",
                    retryable=True,
                )
            except OSError:
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.transport,
                    "NASA_TAP_TRANSPORT_ERROR",
                    retryable=True,
                )

            assert failure is not None
            LOGGER.warning(
                "data source request failed source=nasa-toi class=%s code=%s attempt=%s",
                failure.classification.value,
                failure.code,
                attempt,
            )
            if not failure.retryable or attempt == self.max_attempts:
                failure.attempt_count = attempt
                raise failure
            retry_after = None
            if response is not None:
                retry_after = _safe_headers(response.headers).get("retry-after")
            self.sleeper(self._retry_delay(attempt, retry_after))
        raise AssertionError("bounded retry loop exited unexpectedly")

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), self.max_backoff_seconds)
            except ValueError:
                pass
        return min(
            self.base_backoff_seconds * (2 ** (attempt - 1)),
            self.max_backoff_seconds,
        )

    def _aware_now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("adapter clock must return timezone-aware datetime")
        return value


def _validate_origin(source_mode: SourceMode, data_level: DataSourceDataLevel) -> None:
    allowed = {
        SourceMode.live: {DataSourceDataLevel.live_result},
        SourceMode.fixture: {
            DataSourceDataLevel.recorded_response,
            DataSourceDataLevel.fixture,
        },
    }
    if data_level not in allowed.get(source_mode, set()):
        raise SourceFailure(
            UpstreamFailureClass.policy_violation,
            "NASA_TAP_SOURCE_MODE_DATA_LEVEL_MISMATCH",
            retryable=False,
        )


def _validate_query_contract(query: NormalizedDataSourceQuery) -> None:
    expected = normalize_toi_query(
        load_frozen_manifest_bundle(),
        page_size=query.pagination.page_size,
        max_pages=query.pagination.max_pages,
        record_limit=query.pagination.record_limit,
    )
    if query != expected:
        raise SourceFailure(
            UpstreamFailureClass.policy_violation,
            "NASA_TAP_QUERY_CONTRACT_MISMATCH",
            retryable=False,
        )


def render_toi_schema_query(query: NormalizedDataSourceQuery) -> str:
    columns = ",".join(f"'{column}'" for column in sorted(query.selected_columns))
    return (
        "select table_name,column_name,datatype from TAP_SCHEMA.columns "
        f"where table_name = '{query.source_table}' and column_name in ({columns}) "
        "order by column_name"
    )


def _fixture_metadata(
    transport: HttpTransport,
    source_mode: SourceMode,
) -> dict[str, Any] | None:
    raw_metadata = getattr(transport, "fixture_metadata", None)
    if source_mode is not SourceMode.fixture:
        return None
    required = {
        "fixture_id",
        "schema_version",
        "scenario",
        "recorded_at",
        "content_hash",
        "provenance_note",
    }
    if not isinstance(raw_metadata, Mapping) or not required.issubset(raw_metadata):
        raise SourceFailure(
            UpstreamFailureClass.policy_violation,
            "NASA_TAP_FIXTURE_PROVENANCE_MISSING",
            retryable=False,
        )
    return {str(key): value for key, value in raw_metadata.items()}


def _validate_schema_rows(
    rows: list[object], query: NormalizedDataSourceQuery
) -> None:
    actual: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise _schema_drift()
        if row.get("table_name") != query.source_table:
            raise _schema_drift()
        column_name = row.get("column_name")
        datatype = row.get("datatype")
        if not isinstance(column_name, str) or not isinstance(datatype, str):
            raise _schema_drift()
        if column_name in actual:
            raise _schema_drift()
        actual[column_name] = datatype.casefold()
    if set(actual) != set(query.selected_columns):
        raise _schema_drift()
    if actual["tid"] not in {"int", "integer", "long"}:
        raise _schema_drift()
    if not any(token in actual["toi"] for token in ("char", "string")):
        raise _schema_drift()


def _schema_drift() -> SourceFailure:
    return SourceFailure(
        UpstreamFailureClass.invalid_response,
        "NASA_TAP_SCHEMA_DRIFT",
        retryable=False,
    )


def _parse_records(
    rows: list[object],
    query: NormalizedDataSourceQuery,
    cursor_before: DataQueryCursor | None,
) -> tuple[list[RawDataSourceRecord], DataQueryCursor | None]:
    records: list[RawDataSourceRecord] = []
    cursor = cursor_before
    expected_columns = set(query.selected_columns)
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_columns:
            raise _schema_drift()
        try:
            next_cursor = DataQueryCursor(tid=row["tid"], toi=row["toi"])
        except Exception:
            raise _schema_drift() from None
        if cursor is not None and (next_cursor.tid, next_cursor.toi) <= (
            cursor.tid,
            cursor.toi,
        ):
            raise SourceFailure(
                UpstreamFailureClass.invalid_response,
                "NASA_TAP_UNSTABLE_PAGE_ORDER",
                retryable=False,
            )
        row_key = tuple((field, str(row[field])) for field in query.row_key_fields)
        payload = {column: row[column] for column in query.selected_columns}
        records.append(
            RawDataSourceRecord(
                source_id=query.table_source_id,
                row_key=row_key,
                payload=payload,
                content_hash=compute_raw_data_record_hash(
                    source_id=query.table_source_id,
                    row_key=row_key,
                    payload=payload,
                ),
            )
        )
        cursor = next_cursor
    return records, cursor if records else None


def _decode_json_array(body: bytes, code: str) -> list[object]:
    try:
        payload = json.loads(
            body.decode("utf-8"),
            parse_constant=_reject_non_finite_json_constant,
        )
    except ValueError:
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            code,
            retryable=False,
        ) from None
    if not isinstance(payload, list):
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            code,
            retryable=False,
        )
    return payload


def _reject_non_finite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _request_hash(params: Mapping[str, str | int]) -> str:
    return compute_canonical_payload_hash(
        {"endpoint": NASA_TAP_SYNC_URL, "params": dict(params)}
    )


def _classify_status(status_code: int) -> SourceFailure | None:
    if status_code == 200:
        return None
    if status_code == 429:
        return SourceFailure(
            UpstreamFailureClass.rate_limited,
            "NASA_TAP_RATE_LIMITED",
            retryable=True,
            status_code=status_code,
        )
    if 500 <= status_code <= 599:
        return SourceFailure(
            UpstreamFailureClass.upstream_server,
            "NASA_TAP_UPSTREAM_SERVER_ERROR",
            retryable=True,
            status_code=status_code,
        )
    if 400 <= status_code <= 499:
        return SourceFailure(
            UpstreamFailureClass.upstream_client,
            "NASA_TAP_UPSTREAM_CLIENT_ERROR",
            retryable=False,
            status_code=status_code,
        )
    return SourceFailure(
        UpstreamFailureClass.invalid_response,
        "NASA_TAP_UNEXPECTED_STATUS",
        retryable=False,
        status_code=status_code,
    )


def _safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    normalized = {str(key).casefold(): str(value) for key, value in headers.items()}
    return {
        key: value for key, value in normalized.items() if key in SAFE_RESPONSE_HEADERS
    }


def _availability_status(values: list[object]) -> str:
    available = sum(isinstance(value, str) and bool(value) for value in values)
    if available == 0:
        return "unavailable"
    if available == len(values):
        return "available"
    return "partially_available"


def _message_headers(headers: Message | Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}
