"""Controlled external URL ingestion for Research Inputs (B-19).

Fail-closed fetch boundary: protocol allowlist, host allowlist, SSRF denial of
private/link-local/loopback targets, bounded redirects with per-hop re-checks,
streamed size cap, timeout, no forwarded credentials, and a SourceSnapshot
record (variant B, ``app.schemas.evidence.SourceSnapshotRecord``) as the
provenance of every fetched byte.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.schemas.evidence import SourceSnapshotRecord
from app.schemas.research_input import (
    URL_FETCH_BLOCKED,
    URL_FETCH_FAILED,
    URL_FETCH_TOO_LARGE,
)

_READ_CHUNK_BYTES = 65536

_SENSITIVE_QUERY_KEY_FRAGMENTS = frozenset(
    {
        "access_token",
        "apikey",
        "auth",
        "authorization",
        "credential",
        "password",
        "privatekey",
        "refresh_token",
        "secret",
        "session",
        "sig",
        "signature",
        "token",
    }
)

#: Response headers that may enter ``request_metadata`` (normalized keys).
_SAFE_RESPONSE_HEADER_KEYS = frozenset(
    {
        "content_encoding",
        "content_length",
        "content_type",
        "etag",
        "last_modified",
        "retry_after",
    }
)

_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


@dataclass(frozen=True, slots=True)
class UrlFetchConfig:
    """Safe fetch policy. Production derives every field from ``Settings``."""

    allowed_protocols: tuple[str, ...] = ("https",)
    allowed_hosts: tuple[str, ...] = ()
    timeout_seconds: float = 15.0
    max_redirects: int = 3
    max_response_bytes: int = 26214400
    # Test-only escape hatch so local test servers are reachable while the
    # production gate keeps rejecting every private network target. Never
    # sourced from environment configuration.
    allow_private_networks: bool = False


class UrlFetchError(Exception):
    def __init__(self, *, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class UrlFetchResult:
    content_hash: str
    content_bytes: bytes
    mime_type: str | None
    status_code: int
    final_url: str
    source_snapshot: SourceSnapshotRecord


def fetch_url(url: str, config: UrlFetchConfig) -> UrlFetchResult:
    """Fetch ``url`` under ``config`` policy and freeze its provenance.

    Raises :class:`UrlFetchError` with ``URL_FETCH_BLOCKED`` for policy
    denials, ``URL_FETCH_TOO_LARGE`` when the streamed response exceeds the
    cap, and ``URL_FETCH_FAILED`` for transport/upstream failures. No
    credentials, cookies or auth headers are ever forwarded.
    """
    first_hop = _validate_url(url, config)
    target = first_hop
    redirects_left = config.max_redirects
    with httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(config.timeout_seconds),
        headers={"User-Agent": "xingwen-research-input/1.0"},
    ) as client:
        while True:
            response = _request(client, target, config)
            if response.status_code in _REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                if not location:
                    raise UrlFetchError(
                        code=URL_FETCH_FAILED,
                        detail="Redirect response without a Location header",
                    )
                redirects_left -= 1
                if redirects_left < 0:
                    raise UrlFetchError(
                        code=URL_FETCH_FAILED,
                        detail="Maximum redirect count exceeded",
                    )
                next_url = str(response.url.join(location))
                target = _validate_url(next_url, config)
                continue
            if response.status_code >= 400:
                raise UrlFetchError(
                    code=URL_FETCH_FAILED,
                    detail=f"Upstream responded with HTTP {response.status_code}",
                )
            content = _read_bounded(client, response, config.max_response_bytes)
            return _build_result(content, response, target)


def validate_url_policy(url: str, config: UrlFetchConfig) -> None:
    """Public policy gate used by the router before any network I/O."""

    _validate_url(url, config)


def sanitize_url_for_display(url: str) -> str:
    """Redact credentials and sensitive query parameters for public DTOs."""

    try:
        parsed = urlsplit(url)
    except ValueError:
        return "[REDACTED]"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return url
    if parsed.username is not None or parsed.password is not None:
        return "[REDACTED]"
    safe_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _key_is_sensitive(key)
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(safe_query), "")
    )


def _validate_url(url: str, config: UrlFetchConfig) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in config.allowed_protocols:
        raise UrlFetchError(
            code=URL_FETCH_BLOCKED,
            detail="URL protocol is not in the allowed protocols",
        )
    if not parsed.netloc:
        raise UrlFetchError(
            code=URL_FETCH_BLOCKED,
            detail="URL has no host",
        )
    if parsed.username is not None or parsed.password is not None:
        raise UrlFetchError(
            code=URL_FETCH_BLOCKED,
            detail="URLs with embedded credentials are not allowed",
        )
    host = parsed.hostname or ""
    if host not in config.allowed_hosts:
        raise UrlFetchError(
            code=URL_FETCH_BLOCKED,
            detail="URL host is not in the allowed hosts",
        )
    _reject_private_resolution(host, config)
    return url


def _reject_private_resolution(host: str, config: UrlFetchConfig) -> None:
    try:
        addresses = [
            address[4][0] for address in socket.getaddrinfo(host, None)
        ]
    except OSError as exc:
        raise UrlFetchError(
            code=URL_FETCH_BLOCKED, detail="URL host does not resolve"
        ) from exc
    for raw_address in addresses:
        address = ipaddress.ip_address(raw_address)
        if _address_is_private(address):
            if config.allow_private_networks:
                continue
            raise UrlFetchError(
                code=URL_FETCH_BLOCKED,
                detail="URL host resolves to a private or reserved network",
            )


def _address_is_private(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if address.is_loopback or address.is_link_local or address.is_unspecified:
        return True
    if address.is_multicast or address.is_reserved:
        return True
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return _address_is_private(address.ipv4_mapped)
        if address.sixtofour is not None:
            return _address_is_private(address.sixtofour)
        return address.is_private
    return address.is_private


def _request(client: httpx.Client, url: str, config: UrlFetchConfig) -> httpx.Response:
    try:
        return client.get(url)
    except httpx.HTTPError as exc:
        raise UrlFetchError(
            code=URL_FETCH_FAILED,
            detail=f"URL fetch failed: {type(exc).__name__}",
        ) from exc


def _read_bounded(
    client: httpx.Client, response: httpx.Response, max_bytes: int
) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in response.iter_bytes(chunk_size=_READ_CHUNK_BYTES):
            total += len(chunk)
            if total > max_bytes:
                raise UrlFetchError(
                    code=URL_FETCH_TOO_LARGE,
                    detail="URL response exceeds the maximum size",
                )
            chunks.append(chunk)
    except httpx.HTTPError as exc:
        raise UrlFetchError(
            code=URL_FETCH_FAILED,
            detail=f"URL fetch failed: {type(exc).__name__}",
        ) from exc
    return b"".join(chunks)


def _build_result(
    content: bytes, response: httpx.Response, final_url: str
) -> UrlFetchResult:
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    mime_type = _clean_mime_type(response.headers.get("content-type"))
    displayed_url = sanitize_url_for_display(final_url)
    snapshot = SourceSnapshotRecord(
        snapshot_id=f"snap_{secrets.token_hex(9)}",
        source_id=_source_id(final_url),
        source_type="url_fetch",
        retrieved_at=datetime.now(UTC),
        query=displayed_url,
        query_hash="sha256:" + hashlib.sha256(final_url.encode("utf-8")).hexdigest(),
        source_version_or_etag=response.headers.get("etag"),
        content_hash=content_hash,
        license_note="fetched",
        request_metadata={
            "status_code": response.status_code,
            "final_url": displayed_url,
            "response_headers": _safe_response_headers(response),
        },
    )
    return UrlFetchResult(
        content_hash=content_hash,
        content_bytes=content,
        mime_type=mime_type,
        status_code=response.status_code,
        final_url=displayed_url,
        source_snapshot=snapshot,
    )


def _source_id(url: str) -> str:
    host = (urlsplit(url).hostname or "unknown")[:120]
    return f"url_{host}"


def _clean_mime_type(value: str | None) -> str | None:
    if not value:
        return None
    mime = value.split(";", 1)[0].strip().lower()
    return mime or None


def _safe_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        _normalize_header_key(key): value
        for key, value in response.headers.items()
        if _normalize_header_key(key) in _SAFE_RESPONSE_HEADER_KEYS
    }


def _normalize_header_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def _key_is_sensitive(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    segments = frozenset(normalized.split("_"))
    return bool(segments & _SENSITIVE_QUERY_KEY_FRAGMENTS)


__all__ = [
    "UrlFetchConfig",
    "UrlFetchError",
    "UrlFetchResult",
    "fetch_url",
    "sanitize_url_for_display",
    "validate_url_policy",
]
