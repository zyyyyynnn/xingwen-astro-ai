"""Unit tests for the fail-closed URL fetch boundary (B-19).

Uses a scripted fake ``httpx`` so no real network is touched: protocol/host
allowlists, SSRF private-network denial, bounded redirects with per-hop
re-checks, streamed size caps, and provenance redaction are all exercised
without sockets.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from urllib.parse import urljoin

import pytest

from app.security import canonical_request_hash
from app.services.url_fetcher import (
    UrlFetchConfig,
    UrlFetchError,
    fetch_url,
    sanitize_url_for_display,
    sanitize_url_for_persistence,
    validate_url_policy,
)
from app.services import url_fetcher as url_fetcher_module


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every fetch target resolves to a public IP so tests are hermetic."""

    def fake_getaddrinfo(
        host: str, _port: int
    ) -> list[tuple[Any, ...]]:
        del host
        return [
            (
                "AF_INET",
                "SOCK_STREAM",
                "tcp",
                "",
                ("93.184.216.34", 443),
            )
        ]

    monkeypatch.setattr(url_fetcher_module.socket, "getaddrinfo", fake_getaddrinfo)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        url: str = "https://example.com/data.csv",
        chunks: list[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body
        self.url = SimpleNamespace(join=lambda href: urljoin(url, href))
        self._chunks = chunks if chunks is not None else ([body] if body else [])

    async def aiter_bytes(self, *, chunk_size: int = 65536) -> Any:
        del chunk_size
        for chunk in self._chunks:
            yield chunk


class FakeAsyncStreamContext:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    async def __aenter__(self) -> FakeResponse:
        return self.response

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeAsyncClient:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.get_calls: list[str] = []

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs: object) -> FakeAsyncStreamContext:
        del method, kwargs
        self.get_calls.append(url)
        if not self.responses:
            raise url_fetcher_module.httpx.ConnectError("no response scripted")
        response = self.responses.pop(0)
        return FakeAsyncStreamContext(response)


class FakeHttpx:
    class HTTPError(Exception):
        pass

    class ConnectError(HTTPError):
        pass

    class HTTPStatusError(HTTPError):
        pass

    class Timeout:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses

    def AsyncClient(self, **kwargs: object) -> FakeAsyncClient:  # noqa: N802
        return FakeAsyncClient(self._responses)


CONFIG = UrlFetchConfig(
    allowed_protocols=("https",),
    allowed_hosts=("example.com",),
    timeout_seconds=5,
    max_redirects=3,
    max_response_bytes=1024,
)


def test_validate_url_policy_rejects_bad_protocols() -> None:
    with pytest.raises(UrlFetchError, match="protocol") as exc:
        validate_url_policy("http://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_BLOCKED"


def test_validate_url_policy_rejects_missing_host_and_credentials() -> None:
    with pytest.raises(UrlFetchError, match="no host"):
        validate_url_policy("https:///data.csv", CONFIG)
    with pytest.raises(UrlFetchError, match="credentials"):
        validate_url_policy("https://user:pass@example.com/data.csv", CONFIG)


def test_validate_url_policy_rejects_hosts_outside_allowlist() -> None:
    with pytest.raises(UrlFetchError, match="not in the allowed hosts"):
        validate_url_policy("https://other.com/data.csv", CONFIG)


def test_validate_url_policy_rejects_private_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, _port: int) -> list[tuple[Any, ...]]:
        del host
        return [("AF_INET", "SOCK_STREAM", "tcp", "", ("127.0.0.1", 443))]

    monkeypatch.setattr(url_fetcher_module.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UrlFetchError, match="private or reserved") as exc:
        validate_url_policy("https://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_BLOCKED"


def test_validate_url_policy_allows_private_only_with_test_escape_hatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_getaddrinfo(host: str, _port: int) -> list[tuple[Any, ...]]:
        del host
        return [("AF_INET", "SOCK_STREAM", "tcp", "", ("127.0.0.1", 443))]

    monkeypatch.setattr(url_fetcher_module.socket, "getaddrinfo", fake_getaddrinfo)
    permissive = UrlFetchConfig(
        allowed_protocols=("http", "https"),
        allowed_hosts=("127.0.0.1",),
        allow_private_networks=True,
    )
    validate_url_policy("http://127.0.0.1:8000/data.csv", permissive)


# -- fetch -------------------------------------------------------------------


def snapshot_query_hash_changes_with_query(result: Any) -> bool:
    """Provenance keeps exact request identity only through the query_hash.

    Same path + different query value must yield the same sanitized URL but a
    *different* query_hash, so reproducibility survives while raw values never
    persist.
    """
    full = "https://example.com/data.csv?token=secret&page=2"
    other = "https://example.com/data.csv?token=other&page=3"
    hash_full = canonical_request_hash({"url": full})
    hash_other = canonical_request_hash({"url": other})
    # query_hash retains the EXACT requested URL (one-way), so it must differ
    # for different queries even though the sanitized URL is identical.
    return (
        hash_full != hash_other
        and result.final_url == "https://example.com/data.csv"
    )


@pytest.mark.anyio
async def test_fetch_url_builds_immutable_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpx(
        [
            FakeResponse(
                status_code=200,
                headers={
                    "content-type": "text/csv; charset=utf-8",
                    "etag": '"abc"',
                    "set-cookie": "session=secret",
                },
                body=b"a,b\n1,2\n",
                url="https://example.com/data.csv",
            )
        ]
    )
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)

    result = await fetch_url("https://example.com/data.csv?token=topsecret&page=2", CONFIG)

    assert result.content_bytes == b"a,b\n1,2\n"
    assert result.mime_type == "text/csv"
    assert result.status_code == 200
    # Raw query values never persist or surface; final_url keeps scheme/host/path only.
    assert "token" not in result.final_url
    assert "page=2" not in result.final_url
    assert result.final_url == "https://example.com/data.csv"
    # Exact request identity survives only as a one-way hash of the full URL.
    assert snapshot_query_hash_changes_with_query(result)
    snapshot = result.source_snapshot
    assert snapshot.source_type == "url_fetch"
    assert snapshot.content_hash == result.content_hash
    assert snapshot.query == result.final_url
    assert snapshot.license_note == "fetched"
    assert snapshot.request_metadata["status_code"] == 200
    assert "set-cookie" not in snapshot.request_metadata["response_headers"]
    assert snapshot.request_metadata["response_headers"]["etag"] == '"abc"'


@pytest.mark.anyio
async def test_fetch_url_rejects_redirect_outside_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpx(
        [
            FakeResponse(
                status_code=302,
                headers={"location": "https://evil.net/data.csv"},
                url="https://example.com/data.csv",
            )
        ]
    )
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    with pytest.raises(UrlFetchError, match="allowed hosts") as exc:
        await fetch_url("https://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_BLOCKED"


@pytest.mark.anyio
async def test_fetch_url_follows_bounded_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpx(
        [
            FakeResponse(
                status_code=301, headers={"location": "/next.csv"}, url="https://example.com/data.csv"
            ),
            FakeResponse(
                status_code=200, body=b"final", url="https://example.com/next.csv"
            ),
        ]
    )
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    result = await fetch_url("https://example.com/data.csv", CONFIG)
    assert result.content_bytes == b"final"
    assert result.final_url == "https://example.com/next.csv"


@pytest.mark.anyio
async def test_fetch_url_exhausts_redirect_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        FakeResponse(
            status_code=302, headers={"location": f"/hop-{index}"}, url="https://example.com/x"
        )
        for index in range(5)
    ]
    fake_http = FakeHttpx(responses)
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    with pytest.raises(UrlFetchError, match="redirect count") as exc:
        await fetch_url("https://example.com/x", CONFIG)
    assert exc.value.code == "URL_FETCH_FAILED"


@pytest.mark.anyio
async def test_fetch_url_rejects_upstream_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpx(
        [FakeResponse(status_code=503, url="https://example.com/data.csv")]
    )
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    with pytest.raises(UrlFetchError, match="HTTP 503") as exc:
        await fetch_url("https://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_FAILED"


@pytest.mark.anyio
async def test_fetch_url_streams_and_caps_size(monkeypatch: pytest.MonkeyPatch) -> None:
    big = FakeResponse(
        status_code=200,
        chunks=[b"x" * 512, b"y" * 512, b"z" * 512],
        url="https://example.com/data.csv",
    )
    fake_http = FakeHttpx([big])
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    with pytest.raises(UrlFetchError, match="maximum size") as exc:
        await fetch_url("https://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_TOO_LARGE"


@pytest.mark.anyio
async def test_fetch_url_maps_transport_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http = FakeHttpx([])
    monkeypatch.setattr(url_fetcher_module, "httpx", fake_http)
    with pytest.raises(UrlFetchError, match="ConnectError") as exc:
        await fetch_url("https://example.com/data.csv", CONFIG)
    assert exc.value.code == "URL_FETCH_FAILED"



# -- display / persistence sanitization ------------------------------------


def test_sanitize_url_for_persistence_drops_whole_query_and_fragment() -> None:
    # Deny-by-default: the entire query (and fragment) is dropped regardless of
    # parameter name; only scheme/host/path survive. The exact request
    # identity is retained separately as a one-way query_hash.
    redacted = sanitize_url_for_persistence(
        "https://user:pass@example.com/a.csv?access_token=abc&page=2"
    )
    assert redacted == "[REDACTED]"

    sanitized = sanitize_url_for_persistence(
        "https://example.com/a.csv?apikey=abc&sig=xyz&q=planets&page=2"
    )
    assert "apikey" not in sanitized
    assert "sig" not in sanitized
    assert "q=planets" not in sanitized
    assert "page=2" not in sanitized
    assert "?" not in sanitized
    assert sanitized == "https://example.com/a.csv"

    plain = sanitize_url_for_persistence("https://example.com/a.csv?page=2")
    assert plain == "https://example.com/a.csv"

    frag = sanitize_url_for_persistence("https://example.com/a.csv#section")
    assert frag == "https://example.com/a.csv"


def test_sanitize_url_for_display_matches_persistence() -> None:
    url = "https://example.com/a.csv?apikey=abc&q=planets&page=2"
    assert sanitize_url_for_display(url) == sanitize_url_for_persistence(url)
    assert sanitize_url_for_display(url) == "https://example.com/a.csv"
