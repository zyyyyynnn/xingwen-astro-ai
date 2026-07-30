"""Shared NASA Exoplanet Archive TAP transport and evidence primitives."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from email.message import Message
from typing import Any, Literal

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import UpstreamFailureClass
from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.source_acquisition import DataSourcePage

from .base import (
    HttpResponse,
    HttpTransport,
    MonotonicClock,
    Sleeper,
    SourceFailure,
)


NASA_TAP_SYNC_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
NASA_TAP_ALLOWED_HOSTS = frozenset({"exoplanetarchive.ipac.caltech.edu"})
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
        if parsed.scheme != "https" or parsed.hostname not in NASA_TAP_ALLOWED_HOSTS:
            raise TransportPolicyError("NASA TAP redirect host is not allowlisted")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibTransport(HttpTransport):
    """Bounded stdlib transport shared by all NASA TAP adapters."""

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
        if parsed.scheme != "https" or parsed.hostname not in NASA_TAP_ALLOWED_HOSTS:
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


class NasaTapRequester:
    """Provider-level bounded request policy used by TOI and PS adapters."""

    def __init__(
        self,
        *,
        failure_prefix: str,
        source_label: str,
        logger: logging.Logger,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 4.0,
        monotonic: MonotonicClock = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between one and five")
        if min(base_backoff_seconds, max_backoff_seconds) < 0:
            raise ValueError("backoff values must not be negative")
        self.failure_prefix = failure_prefix
        self.source_label = source_label
        self.logger = logger
        self.transport = transport or UrllibTransport()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.monotonic = monotonic
        self.sleeper = sleeper

    def request(
        self,
        params: Mapping[str, str | int],
    ) -> tuple[HttpResponse, int, int]:
        failure: SourceFailure | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "xingwen-astro-ai/0.1 "
                "(https://github.com/zyyyyynnn/xingwen-astro-ai; "
                "scientific metadata)"
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
                failure = classify_status(response.status_code, self.failure_prefix)
                if failure is None:
                    return response, attempt, latency_ms
            except TransportPolicyError:
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.policy_violation,
                    f"{self.failure_prefix}_TRANSPORT_POLICY_VIOLATION",
                    retryable=False,
                )
            except (TimeoutError, socket.timeout):
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.timeout,
                    f"{self.failure_prefix}_TIMEOUT",
                    retryable=True,
                )
            except OSError:
                self.monotonic()
                failure = SourceFailure(
                    UpstreamFailureClass.transport,
                    f"{self.failure_prefix}_TRANSPORT_ERROR",
                    retryable=True,
                )

            assert failure is not None
            self.logger.warning(
                "data source request failed source=%s class=%s code=%s attempt=%s",
                self.source_label,
                failure.classification.value,
                failure.code,
                attempt,
            )
            if not failure.retryable or attempt == self.max_attempts:
                failure.attempt_count = attempt
                raise failure
            retry_after = None
            if response is not None:
                retry_after = safe_headers(response.headers).get("retry-after")
            self.sleeper(self.retry_delay(attempt, retry_after))
        raise AssertionError("bounded retry loop exited unexpectedly")

    def retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(
                    max(float(retry_after), 0.0),
                    self.max_backoff_seconds,
                )
            except ValueError:
                pass
        return min(
            self.base_backoff_seconds * (2 ** (attempt - 1)),
            self.max_backoff_seconds,
        )


def classify_status(status_code: int, failure_prefix: str) -> SourceFailure | None:
    if status_code == 200:
        return None
    if status_code == 429:
        return SourceFailure(
            UpstreamFailureClass.rate_limited,
            f"{failure_prefix}_RATE_LIMITED",
            retryable=True,
            status_code=status_code,
        )
    if 500 <= status_code <= 599:
        return SourceFailure(
            UpstreamFailureClass.upstream_server,
            f"{failure_prefix}_UPSTREAM_SERVER_ERROR",
            retryable=True,
            status_code=status_code,
        )
    if 400 <= status_code <= 499:
        return SourceFailure(
            UpstreamFailureClass.upstream_client,
            f"{failure_prefix}_UPSTREAM_CLIENT_ERROR",
            retryable=False,
            status_code=status_code,
        )
    return SourceFailure(
        UpstreamFailureClass.invalid_response,
        f"{failure_prefix}_UNEXPECTED_STATUS",
        retryable=False,
        status_code=status_code,
    )


def safe_headers(headers: Mapping[str, str]) -> dict[str, str]:
    normalized = {str(key).casefold(): str(value) for key, value in headers.items()}
    return {
        key: value for key, value in normalized.items() if key in SAFE_RESPONSE_HEADERS
    }


def request_id(headers: Mapping[str, str]) -> str | None:
    return headers.get("x-request-id") or headers.get("x-correlation-id")


def availability_status(values: list[object]) -> str:
    available = sum(isinstance(value, str) and bool(value) for value in values)
    if available == 0:
        return "unavailable"
    if available == len(values):
        return "available"
    return "partially_available"


def rate_limit_metadata(headers: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in headers.items()
        if key.startswith("x-rate-limit-") or key == "retry-after"
    }


def request_hash(params: Mapping[str, str | int]) -> str:
    return compute_canonical_payload_hash(
        {"endpoint": NASA_TAP_SYNC_URL, "params": dict(params)}
    )


def resolve_consistent_data_etag(
    etags: list[str],
    *,
    failure_prefix: str,
) -> str | None:
    distinct = tuple(sorted(set(etags)))
    if not distinct:
        return None
    if len(distinct) > 1:
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            f"{failure_prefix}_SOURCE_VERSION_CHANGED",
            retryable=False,
        )
    return distinct[0]


def tap_type_category(datatype: str) -> str | None:
    normalized = datatype.casefold().replace("_", " ").strip()
    tokens = set(normalized.replace("(", " ").replace(")", " ").split())
    if tokens & {"char", "varchar", "string", "unicode", "text"}:
        return "string"
    if tokens & {"int", "integer", "long", "short", "smallint", "bigint"}:
        return "integer"
    if tokens & {"double", "float", "real", "numeric", "decimal", "number"}:
        return "number"
    return None


@dataclass(frozen=True)
class BoundedCompletion:
    status: Literal["complete", "truncated", "unknown"]
    continuation_cursor: dict[str, Any] | None


def classify_bounded_completion(
    *,
    pages: list[DataSourcePage],
    record_count: int,
    record_limit: int,
    max_pages: int,
) -> BoundedCompletion:
    if not pages:
        return BoundedCompletion(status="unknown", continuation_cursor=None)
    last_page = pages[-1]
    if last_page.returned_rows < last_page.requested_rows:
        return BoundedCompletion(status="complete", continuation_cursor=None)
    bounded = record_count >= record_limit or len(pages) >= max_pages
    continuation_cursor = (
        last_page.cursor_after.model_dump(mode="json")
        if bounded and last_page.cursor_after is not None
        else None
    )
    return BoundedCompletion(
        status="truncated" if bounded else "unknown",
        continuation_cursor=continuation_cursor,
    )


def build_source_snapshot(
    *,
    snapshot_prefix: str,
    source_id: str,
    source_type: str,
    retrieved_at: Any,
    query: str,
    query_hash: str,
    source_version_or_etag: str | None,
    content_hash: str,
    license_note: str,
    request_metadata: dict[str, Any],
) -> SourceSnapshotRecord:
    snapshot_fingerprint = compute_canonical_payload_hash(
        {
            "source_id": source_id,
            "query_hash": query_hash,
            "content_hash": content_hash,
        }
    )
    return SourceSnapshotRecord(
        snapshot_id=(
            f"{snapshot_prefix}."
            f"{snapshot_fingerprint.removeprefix('sha256:')[:24]}"
        ),
        source_id=source_id,
        source_type=source_type,
        retrieved_at=retrieved_at,
        query=query,
        query_hash=query_hash,
        source_version_or_etag=source_version_or_etag,
        content_hash=content_hash,
        license_note=license_note,
        cache_version=None,
        request_metadata=request_metadata,
    )


def _message_headers(headers: Message | Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}
