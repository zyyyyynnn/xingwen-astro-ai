"""Crossref metadata-only source adapter with bounded retries."""

from __future__ import annotations

import html
import json
import logging
import re
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
from app.schemas.enums import PaperDataLevel, SourceMode, UpstreamFailureClass
from app.schemas.evidence import SourceSnapshot
from app.schemas.paper_collection import NormalizedPaperQuery, PaperSourcePage

from ..constants import CROSSREF_ADAPTER_VERSION
from .base import (
    Clock,
    HttpResponse,
    HttpTransport,
    RawSourceRecord,
    Sleeper,
    SourceFailure,
    SourceSearchResult,
)


LOGGER = logging.getLogger(__name__)
_CROSSREF_URL = "https://api.crossref.org/works"
_ALLOWED_HOSTS = frozenset({"api.crossref.org"})
_SAFE_HEADERS = frozenset(
    {
        "date",
        "etag",
        "retry-after",
        "x-api-pool",
        "x-rate-limit-limit",
        "x-rate-limit-interval",
        "x-concurrency-limit",
        "x-request-id",
    }
)
_HTML_TAG = re.compile(r"<[^>]*>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ARXIV = re.compile(
    r"(?:arxiv:\s*|arxiv\.org/(?:abs|pdf)/)?"
    r"(?P<id>(?:[a-z-]+(?:\.[a-z-]+)?/\d{7}|\d{4}\.\d{4,5}))(?:v\d+)?(?:\.pdf)?",
    re.IGNORECASE,
)


class TransportPolicyError(OSError):
    pass


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            raise TransportPolicyError("crossref redirect host is not allowlisted")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UrllibTransport(HttpTransport):
    """Small stdlib transport so production code and tests share one boundary."""

    max_response_bytes = 2_000_000

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
            raise TransportPolicyError("crossref endpoint is not allowlisted")
        encoded = urllib.parse.urlencode(sorted(params.items()))
        request = urllib.request.Request(f"{url}?{encoded}", headers=dict(headers))
        try:
            with self._opener.open(request, timeout=timeout_seconds) as response:
                body = response.read(self.max_response_bytes + 1)
                if len(body) > self.max_response_bytes:
                    raise OSError("crossref response exceeded size limit")
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
                raise TimeoutError("crossref request timed out") from None
            raise OSError("crossref transport failed") from None


class CrossrefAdapter:
    source_id = "crossref"
    adapter_name = "crossref_rest"
    adapter_version = CROSSREF_ADAPTER_VERSION

    def __init__(
        self,
        *,
        license_note: str,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 15.0,
        max_attempts: int = 3,
        base_backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 2.0,
        conservative_page_delay_seconds: float = 1.0,
        clock: Clock | None = None,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between one and five")
        self.license_note = license_note
        self.transport = transport or UrllibTransport()
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.conservative_page_delay_seconds = conservative_page_delay_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper

    def search(
        self,
        query: NormalizedPaperQuery,
        *,
        source_mode: SourceMode,
        data_level: PaperDataLevel,
    ) -> SourceSearchResult:
        if self.source_id not in query.source_ids:
            raise SourceFailure(
                UpstreamFailureClass.policy_violation,
                "SOURCE_NOT_PERMITTED_BY_QUERY",
                retryable=False,
            )
        base_params = query.source_parameters.get(self.source_id)
        if not base_params:
            raise SourceFailure(
                UpstreamFailureClass.policy_violation,
                "SOURCE_PARAMETERS_MISSING",
                retryable=False,
            )

        records: list[RawSourceRecord] = []
        pages: list[PaperSourcePage] = []
        total_retries = 0
        etags: list[str] = []
        for page_number in range(1, query.pagination.max_pages + 1):
            remaining = query.pagination.candidate_limit - len(records)
            if remaining <= 0:
                break
            rows = min(query.pagination.page_size, remaining)
            offset = (page_number - 1) * query.pagination.page_size
            params = {**base_params, "rows": rows, "offset": offset}
            response, attempt_count = self._request_page(params)
            total_retries += attempt_count - 1
            page_records, total_results = self._parse_page(response.body)
            retrieved_at = self.clock()
            if retrieved_at.tzinfo is None:
                raise ValueError("adapter clock must return timezone-aware datetime")
            normalized_headers = _normalized_headers(response.headers)
            if etag := normalized_headers.get("etag"):
                etags.append(etag)
            request_hash = compute_canonical_payload_hash(
                {"endpoint": _CROSSREF_URL, "params": params}
            )
            response_hash = compute_canonical_payload_hash(
                {
                    "items": [record.hash_payload() for record in page_records],
                    "total_results": total_results,
                }
            )
            rate_limit_metadata = {
                key: value
                for key, value in normalized_headers.items()
                if key in _SAFE_HEADERS and key != "etag"
            }
            pages.append(
                PaperSourcePage(
                    page_number=page_number,
                    offset=offset,
                    requested_rows=rows,
                    returned_rows=len(page_records),
                    total_results=total_results,
                    attempt_count=attempt_count,
                    status_code=response.status_code,
                    retrieved_at=retrieved_at,
                    request_hash=request_hash,
                    response_hash=response_hash,
                    rate_limit_metadata=rate_limit_metadata,
                )
            )
            records.extend(page_records[:remaining])
            if not page_records or len(records) >= total_results:
                break
            if page_number < query.pagination.max_pages:
                self.sleeper(self._page_delay(normalized_headers))

        snapshot_content_hash = compute_canonical_payload_hash(
            {
                "source_id": self.source_id,
                "query_hash": query.query_hash,
                "records": [record.hash_payload() for record in records],
                "pages": [
                    page.model_dump(
                        mode="json", exclude={"retrieved_at"}, exclude_none=True
                    )
                    for page in pages
                ],
            }
        )
        snapshot_id_hash = compute_canonical_payload_hash(
            {
                "source_id": self.source_id,
                "query_hash": query.query_hash,
                "content_hash": snapshot_content_hash,
            }
        )
        snapshot = SourceSnapshot(
            snapshot_id=f"snapshot.crossref.{snapshot_id_hash.removeprefix('sha256:')[:24]}",
            source_id=self.source_id,
            source_type="paper_metadata",
            retrieved_at=pages[0].retrieved_at if pages else self.clock(),
            query=query.normalized_query_string,
            query_hash=query.query_hash,
            source_version_or_etag=",".join(sorted(set(etags))) or None,
            content_hash=snapshot_content_hash,
            license_note=self.license_note,
            cache_version=None,
            request_metadata={
                "adapter_name": self.adapter_name,
                "adapter_version": self.adapter_version,
                "endpoint": _CROSSREF_URL,
                "pagination_strategy": "offset",
                "source_mode": source_mode.value,
                "data_level": data_level.value,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "offset": page.offset,
                        "requested_rows": page.requested_rows,
                        "returned_rows": page.returned_rows,
                        "request_hash": page.request_hash,
                        "response_hash": page.response_hash,
                    }
                    for page in pages
                ],
            },
        )
        return SourceSearchResult(
            records=tuple(records),
            pages=tuple(pages),
            snapshot=snapshot,
            retry_count=total_retries,
        )

    def _request_page(
        self, params: Mapping[str, str | int]
    ) -> tuple[HttpResponse, int]:
        failure: SourceFailure | None = None
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                "xingwen-astro-ai/0.1 "
                "(https://github.com/zyyyyynnn/xingwen-astro-ai; metadata-only)"
            ),
        }
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.transport.request(
                    url=_CROSSREF_URL,
                    params=params,
                    headers=headers,
                    timeout_seconds=self.timeout_seconds,
                )
                failure = _classify_status(response.status_code)
                if failure is None:
                    return response, attempt
            except TransportPolicyError:
                failure = SourceFailure(
                    UpstreamFailureClass.policy_violation,
                    "CROSSREF_REDIRECT_POLICY_VIOLATION",
                    retryable=False,
                )
                response = None
            except (TimeoutError, socket.timeout):
                failure = SourceFailure(
                    UpstreamFailureClass.timeout,
                    "CROSSREF_TIMEOUT",
                    retryable=True,
                )
                response = None
            except OSError:
                failure = SourceFailure(
                    UpstreamFailureClass.transport,
                    "CROSSREF_TRANSPORT_ERROR",
                    retryable=True,
                )
                response = None

            assert failure is not None
            LOGGER.warning(
                "paper source request failed source=crossref class=%s code=%s attempt=%s",
                failure.classification.value,
                failure.code,
                attempt,
            )
            if not failure.retryable or attempt == self.max_attempts:
                failure.attempt_count = attempt
                raise failure
            retry_after = None
            if response is not None:
                retry_after = _normalized_headers(response.headers).get("retry-after")
            self.sleeper(self._retry_delay(attempt, retry_after))
        raise AssertionError("bounded retry loop exited unexpectedly")

    def _parse_page(self, body: bytes) -> tuple[tuple[RawSourceRecord, ...], int]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise SourceFailure(
                UpstreamFailureClass.invalid_response,
                "CROSSREF_INVALID_JSON",
                retryable=False,
            ) from None
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
            raise SourceFailure(
                UpstreamFailureClass.invalid_response,
                "CROSSREF_INVALID_ENVELOPE",
                retryable=False,
            )
        message = payload["message"]
        items = message.get("items")
        total_results = message.get("total-results")
        if not isinstance(items, list) or not isinstance(total_results, int) or total_results < 0:
            raise SourceFailure(
                UpstreamFailureClass.invalid_response,
                "CROSSREF_INVALID_PAGE",
                retryable=False,
            )
        records: list[RawSourceRecord] = []
        for item in items:
            records.append(_parse_item(item))
        return tuple(records), total_results

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

    def _page_delay(self, headers: Mapping[str, str]) -> float:
        try:
            limit = int(headers["x-rate-limit-limit"])
            interval_text = headers["x-rate-limit-interval"].strip().casefold()
            interval = float(interval_text.removesuffix("s"))
            if limit > 0 and interval >= 0:
                return interval / limit
        except (KeyError, TypeError, ValueError):
            pass
        return self.conservative_page_delay_seconds


def _classify_status(status_code: int) -> SourceFailure | None:
    if status_code == 200:
        return None
    if status_code == 429:
        return SourceFailure(
            UpstreamFailureClass.rate_limited,
            "CROSSREF_RATE_LIMITED",
            retryable=True,
            status_code=status_code,
        )
    if 500 <= status_code <= 599:
        return SourceFailure(
            UpstreamFailureClass.upstream_server,
            "CROSSREF_UPSTREAM_SERVER_ERROR",
            retryable=True,
            status_code=status_code,
        )
    if 400 <= status_code <= 499:
        return SourceFailure(
            UpstreamFailureClass.upstream_client,
            "CROSSREF_UPSTREAM_CLIENT_ERROR",
            retryable=False,
            status_code=status_code,
        )
    return SourceFailure(
        UpstreamFailureClass.invalid_response,
        "CROSSREF_UNEXPECTED_STATUS",
        retryable=False,
        status_code=status_code,
    )


def _parse_item(item: object) -> RawSourceRecord:
    if not isinstance(item, dict):
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            "CROSSREF_ITEM_NOT_OBJECT",
            retryable=False,
        )
    raw_titles = item.get("title")
    if not isinstance(raw_titles, list) or not raw_titles or not isinstance(raw_titles[0], str):
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            "CROSSREF_ITEM_TITLE_MISSING",
            retryable=False,
        )
    title = _sanitize_text(raw_titles[0], max_length=500)
    if not title:
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            "CROSSREF_ITEM_TITLE_EMPTY",
            retryable=False,
        )
    doi = _optional_text(item.get("DOI"), 300)
    url = _safe_url(item.get("URL")) or _resource_url(item.get("resource"))
    authors = _parse_authors(item.get("author"))
    year = _parse_year(item)
    arxiv_id = _extract_arxiv_id(url)
    alternative_ids = item.get("alternative-id")
    if arxiv_id is None and isinstance(alternative_ids, list):
        for alternative_id in alternative_ids:
            if isinstance(alternative_id, str) and (match := _ARXIV.search(alternative_id)):
                arxiv_id = match.group("id")
                break
    record_id = doi or arxiv_id or url
    if not record_id:
        raise SourceFailure(
            UpstreamFailureClass.invalid_response,
            "CROSSREF_ITEM_IDENTIFIER_MISSING",
            retryable=False,
        )
    return RawSourceRecord(
        source_id="crossref",
        source_record_id=record_id,
        title=title,
        authors=authors,
        year=year,
        doi=doi,
        arxiv_id=arxiv_id,
        url=url,
    )


def _parse_authors(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    authors: list[str] = []
    for author in value[:100]:
        if not isinstance(author, dict):
            continue
        given = _optional_text(author.get("given"), 200)
        family = _optional_text(author.get("family"), 200)
        name = _optional_text(author.get("name"), 300)
        combined = " ".join(part for part in (given, family) if part) or name
        if combined:
            authors.append(combined)
    return tuple(dict.fromkeys(authors))


def _parse_year(item: Mapping[str, Any]) -> int | None:
    for field in ("published-print", "published-online", "published", "created"):
        value = item.get(field)
        if not isinstance(value, dict):
            continue
        date_parts = value.get("date-parts")
        if (
            isinstance(date_parts, list)
            and date_parts
            and isinstance(date_parts[0], list)
            and date_parts[0]
            and isinstance(date_parts[0][0], int)
        ):
            year = date_parts[0][0]
            return year if 1900 <= year <= 2100 else None
    return None


def _sanitize_text(value: str, *, max_length: int) -> str:
    without_html = _HTML_TAG.sub(" ", html.unescape(value))
    without_control = _CONTROL.sub("", without_html)
    return " ".join(without_control.split())[:max_length].strip()


def _optional_text(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    sanitized = _sanitize_text(value, max_length=max_length)
    return sanitized or None


def _safe_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    sanitized = _sanitize_text(value, max_length=2_000)
    parsed = urllib.parse.urlsplit(sanitized)
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return urllib.parse.urlunsplit(
        (parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path, parsed.query, "")
    )


def _resource_url(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    primary = value.get("primary")
    if not isinstance(primary, dict):
        return None
    return _safe_url(primary.get("URL"))


def _extract_arxiv_id(url: str | None) -> str | None:
    if not url:
        return None
    match = _ARXIV.search(url)
    return match.group("id") if match else None


def _normalized_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).casefold(): str(value) for key, value in headers.items()}


def _message_headers(headers: Message | Mapping[str, str]) -> dict[str, str]:
    return {str(key): str(value) for key, value in headers.items()}
