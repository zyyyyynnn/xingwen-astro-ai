"""HTTP-level security and transport contract tests for Research Input ingestion.

Exercises the mounted runtime boundary: CSRF/Idempotency headers, MIME
sniffing rejections, filename sanitization, size and rate limits, URL fetch
error mapping, ownership isolation and the metadata-only public DTOs.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app
from app.schemas.evidence import SourceSnapshotRecord
from app.security import InMemoryRateLimiter
from app.services import url_fetcher as url_fetcher_module
from app.services.content_storage import sha256_content_hash
from app.services.research_input_store import InMemoryResearchInputStore
from app.services.url_fetcher import UrlFetchConfig, UrlFetchError, UrlFetchResult

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURES_BYTES = {name: (FIXTURES / name).read_bytes() for name in ("sample.pdf", "sample.csv", "sample.json", "sample.png", "sample.txt")}


@pytest.fixture()
def app_and_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[FastAPI, TestClient, str, str]:
    monkeypatch.setattr(settings, "DATABASE_URL", None)
    monkeypatch.setattr(settings, "PERSISTENT_WORKFLOW_ENABLED", False)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_UPLOAD_DIR", tmp_path / "inputs")
    app = create_app()
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/sessions")
    assert created.status_code == 201
    csrf_token = created.json()["data"]["csrf_token"]
    credential = client.cookies.get(settings.SESSION_COOKIE_NAME)
    assert credential is not None
    session_id = app.state.session_service.authenticate(credential).id
    return app, client, session_id, csrf_token


import secrets

def _headers(csrf_token: str, idempotency_key: str | None = None, **extra: str) -> dict[str, str]:
    headers: dict[str, str] = {
        "X-CSRF-Token": csrf_token,
        "Idempotency-Key": idempotency_key or f"idem-{secrets.token_hex(4)}",
    }
    headers.update(extra)
    return headers


def _seed_project(
    app: FastAPI,
    session_id: str,
    *,
    project_id: str = "proj_01",
    owner: str | None = None,
) -> None:
    store: InMemoryResearchInputStore = app.state.research_input_store
    store.register_project(
        project_id=project_id, owner_session_id=owner or session_id
    )


def _install_fetcher(app: FastAPI, fetcher: object) -> None:
    """Replace the URL fetch port on the ingestion service.

    The fetcher is a constructor-injected dependency of the application
    service, so tests substitute it there rather than monkeypatching a module
    global inside the router.
    """

    app.state.research_input_ingestion._url_fetcher = fetcher


def _create_text(
    client: TestClient,
    csrf_token: str,
    *,
    project_id: str = "proj_01",
    text: str = "hello research composer",
    idempotency_key: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/research-inputs",
        json={"project_id": project_id, "type": "text", "text_content": text},
        headers=_headers(csrf_token, idempotency_key=idempotency_key),
    )
    assert response.status_code == 201
    return response.json()["data"]



# ---- transport envelope ----------------------------------------------------


def test_text_input_returns_metadata_only_reference(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    response = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "hello"},
        headers=_headers(csrf_token),
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["type"] == "text"
    assert body["source_type"] == "text"
    assert body["content_hash"].startswith("sha256:")
    assert body["status"] == "accepted"
    assert body["filename"] is None
    assert body["mime_type"] == "text/plain"
    assert body["size_bytes"] == len(b"hello")
    assert "storage_ref" not in body
    assert "text_content" not in body
    assert response.headers["location"].startswith("/api/research-inputs/")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["ratelimit-limit"] == "30"

    detail = client.get(response.headers["location"]).json()["data"]
    assert detail["project_id"] == "proj_01"
    assert detail["url"] is None


def test_missing_csrf_and_idempotency_are_rejected(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    no_csrf = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "hello"},
        headers={"Idempotency-Key": "idem-2"},
    )
    assert no_csrf.status_code == 403
    assert no_csrf.json()["code"] == "CSRF_INVALID"

    no_idempotency = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "hello"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert no_idempotency.status_code == 422


def test_unowned_project_is_hidden_behind_404(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id, project_id="proj_01", owner="somebody_else")

    response = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "hello"},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "PROJECT_NOT_FOUND"
    assert response.json()["detail"] == "Resource not found"


# ---- file ingestion --------------------------------------------------------


def test_pdf_upload_is_accepted_and_sniffed(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    response = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf", "filename": "report.pdf"},
        files={"file": ("report.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")},
        headers=_headers(csrf_token),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["type"] == "pdf"
    assert data["source_type"] == "upload"
    assert data["mime_type"] == "application/pdf"
    assert data["filename"] == "report.pdf"
    assert data["content_hash"] == sha256_content_hash(FIXTURES_BYTES["sample.pdf"])


def test_lying_client_mime_and_unknown_binary_are_rejected_415(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    lying = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf", "mime_type": "application/pdf"},
        files={"file": ("fake.pdf", FIXTURES_BYTES["sample.csv"], "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert lying.status_code == 415
    assert lying.json()["code"] == "RESEARCH_INPUT_MIME_REJECTED"

    unknown = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf"},
        files={"file": ("binary.pdf", b"\x00\x01\x02\x03\x04\x05", "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert unknown.status_code == 415


def test_declared_type_must_match_sniffed_content(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    response = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "json"},
        files={"file": ("data.json", FIXTURES_BYTES["sample.csv"], "application/json")},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 415


def test_filename_traversal_is_sanitized_and_extension_mismatch_rejected(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    traversal = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf", "filename": "..\\..\\evil.pdf"},
        files={"file": ("evil.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert traversal.status_code == 201
    assert traversal.json()["data"]["filename"] == "evil.pdf"

    mismatch = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf", "filename": "report.csv"},
        files={"file": ("report.csv", FIXTURES_BYTES["sample.pdf"], "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert mismatch.status_code == 415


def test_oversized_upload_is_rejected_413(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", 100)

    response = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "text"},
        files={"file": ("big.txt", b"x" * 5000, "text/plain")},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 413
    assert response.json()["code"] == "RESEARCH_INPUT_TOO_LARGE"


def test_rate_limit_applies_per_session(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    app.state.research_input_rate_limiter = InMemoryRateLimiter(limit=1)

    first = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "one"},
        headers=_headers(csrf_token),
    )
    assert first.status_code == 201

    second = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "two"},
        headers=_headers(csrf_token),
    )
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"
    assert second.headers["retry-after"]


# ---- URL ingestion ---------------------------------------------------------


def _stub_fetch(
    app: FastAPI,
    *,
    content: bytes = b"a,b\n1,2\n",
    mime: str = "text/csv",
) -> None:
    content_hash = sha256_content_hash(content)
    snapshot = SourceSnapshotRecord(
        snapshot_id="snap_1a2b3c",
        source_id="url_example.com",
        source_type="url_fetch",
        retrieved_at="2026-08-06T08:00:00Z",
        query="https://example.com/data.csv",
        query_hash="sha256:" + "0" * 64,
        content_hash=content_hash,
        license_note="fetched",
        request_metadata={"status_code": 200},
    )

    async def fake_fetch(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del config
        return UrlFetchResult(
            content_hash=content_hash,
            content_bytes=content,
            mime_type=mime,
            status_code=200,
            final_url=url,
            source_snapshot=snapshot,
        )

    _install_fetcher(app, fake_fetch)


def test_url_ingestion_records_provenance_without_content(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    _stub_fetch(app)

    response = client.post(
        "/api/research-inputs",
        json={
            "project_id": "proj_01",
            "type": "url",
            "url": "https://example.com/data.csv",
        },
        headers=_headers(csrf_token),
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["source_type"] == "url_fetch"
    assert data["source_snapshot_id"].startswith("snap_")
    assert data["content_hash"].startswith("sha256:")
    assert "url" not in data

    detail = client.get(response.headers["location"]).json()["data"]
    assert detail["url"] == "https://example.com/data.csv"


def test_url_policy_denial_maps_to_422(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    async def blocked(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del url, config
        raise UrlFetchError(
            code="URL_FETCH_BLOCKED", detail="URL host is not in the allowed hosts"
        )

    _install_fetcher(app, blocked)

    response = client.post(
        "/api/research-inputs",
        json={
            "project_id": "proj_01",
            "type": "url",
            "url": "https://example.com/data.csv",
        },
        headers=_headers(csrf_token),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "URL_FETCH_BLOCKED"


def test_url_fetch_failure_maps_to_502(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    async def failing(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del url, config
        raise UrlFetchError(
            code="URL_FETCH_TOO_LARGE", detail="URL response exceeds the maximum size"
        )

    _install_fetcher(app, failing)

    response = client.post(
        "/api/research-inputs",
        json={
            "project_id": "proj_01",
            "type": "url",
            "url": "https://example.com/data.csv",
        },
        headers=_headers(csrf_token),
    )
    assert response.status_code == 502
    assert response.json()["code"] == "URL_FETCH_TOO_LARGE"


# ---- listing / ownership / binding -----------------------------------------


def test_ownership_isolation_hides_foreign_inputs(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    created = _create_text(client, csrf_token)

    other, other_client, _, other_csrf = _seed_second_session(app)
    _seed_project(app, other, project_id="proj_02", owner=other)

    hidden = other_client.get(f"/api/research-inputs/{created['id']}")
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == "Resource not found"

    hidden_delete = other_client.delete(
        f"/api/research-inputs/{created['id']}",
        headers={"X-CSRF-Token": other_csrf},
    )
    assert hidden_delete.status_code == 404

    still_there = client.get(f"/api/research-inputs/{created['id']}")
    assert still_there.status_code == 200


def _seed_second_session(app: FastAPI) -> tuple[str, TestClient, str, str]:
    other_client = TestClient(app, base_url="https://testserver")
    created = other_client.post("/api/sessions")
    assert created.status_code == 201
    csrf_token = created.json()["data"]["csrf_token"]
    credential = other_client.cookies.get(settings.SESSION_COOKIE_NAME)
    assert credential is not None
    session_id = app.state.session_service.authenticate(credential).id
    return session_id, other_client, "", csrf_token


def test_list_is_project_scoped_and_cursor_paginates(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    _seed_project(app, session_id, project_id="proj_02")
    first = _create_text(client, csrf_token, project_id="proj_01", text="one")
    second = _create_text(client, csrf_token, project_id="proj_01", text="two")
    _ = _create_text(client, csrf_token, project_id="proj_02", text="other")
    _ = second

    listed = client.get(
        "/api/research-inputs?project_id=proj_01&limit=1", headers=_headers(csrf_token)
    )
    assert listed.status_code == 200
    page = listed.json()["page"]
    assert len(listed.json()["data"]) == 1
    assert page["has_more"] is True
    assert page["next_cursor"]

    second_page = client.get(
        f"/api/research-inputs?project_id=proj_01&limit=1&cursor={page['next_cursor']}",
        headers=_headers(csrf_token),
    )
    assert second_page.status_code == 200
    assert second_page.json()["page"]["has_more"] is False
    seen = {
        listed.json()["data"][0]["id"],
        second_page.json()["data"][0]["id"],
    }
    assert seen == {first["id"], second["id"]}


def test_delete_soft_removes_and_bind_requires_owned_targets(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    store: InMemoryResearchInputStore = app.state.research_input_store
    store.register_contract_draft(draft_id="draft_01", owner_session_id=session_id)
    created = _create_text(client, csrf_token)

    missing = client.post(
        f"/api/research-inputs/{created['id']}/bind",
        json={"project_id": "proj_01", "contract_draft_id": "draft_missing"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "RESOURCE_NOT_FOUND"

    bound = client.post(
        f"/api/research-inputs/{created['id']}/bind",
        json={"project_id": "proj_01", "contract_draft_id": "draft_01"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert bound.status_code == 200
    assert bound.json()["data"]["id"] == created["id"]

    deleted = client.delete(
        f"/api/research-inputs/{created['id']}",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert deleted.status_code == 204
    assert deleted.headers["cache-control"] == "no-store"

    gone = client.get(f"/api/research-inputs/{created['id']}")
    assert gone.status_code == 404
    assert gone.json()["code"] == "RESEARCH_INPUT_NOT_FOUND"


def test_content_is_never_exposed_in_any_response(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    response = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "secret prose"},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201
    dump = str(response.json())
    assert "secret prose" not in dump



def test_project_isolation_dedup(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id, project_id="proj_01")
    _seed_project(app, session_id, project_id="proj_02")

    res1 = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "same content"},
        headers=_headers(csrf_token, idempotency_key="key-p1"),
    )
    assert res1.status_code == 201
    id1 = res1.json()["data"]["id"]

    res2 = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_02", "type": "text", "text_content": "same content"},
        headers=_headers(csrf_token, idempotency_key="key-p2"),
    )
    assert res2.status_code == 201
    id2 = res2.json()["data"]["id"]

    assert id1 != id2


def test_idempotency_key_replay_and_conflict(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id, project_id="proj_01")

    headers = _headers(csrf_token, idempotency_key="fixed-idem-key")
    res1 = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "text content"},
        headers=headers,
    )
    assert res1.status_code == 201
    id1 = res1.json()["data"]["id"]

    # Replay with identical payload
    res2 = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "text content"},
        headers=headers,
    )
    assert res2.status_code == 201
    assert res2.json()["data"]["id"] == id1

    # Conflict with different payload under same idempotency key
    res3 = client.post(
        "/api/research-inputs",
        json={"project_id": "proj_01", "type": "text", "text_content": "different content"},
        headers=headers,
    )
    assert res3.status_code == 409
    assert res3.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_bind_target_xor_validation(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    created = _create_text(client, csrf_token)

    # Reject both non-null
    both = client.post(
        f"/api/research-inputs/{created['id']}/bind",
        json={
            "project_id": "proj_01",
            "contract_draft_id": "draft_01",
            "run_id": "run_01",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert both.status_code == 422

    # Reject both null
    neither = client.post(
        f"/api/research-inputs/{created['id']}/bind",
        json={"project_id": "proj_01"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert neither.status_code == 422


# ---- request idempotency matrix --------------------------------------------
#
# Content dedup and request idempotency are different identities. These tests
# pin both directions: one key must never straddle two different requests, and
# two different keys are free to resolve to the same immutable input.


def _snapshot(content_hash: str, snapshot_id: str) -> SourceSnapshotRecord:
    return SourceSnapshotRecord(
        snapshot_id=snapshot_id,
        source_id="url_example.com",
        source_type="url_fetch",
        retrieved_at="2026-08-06T08:00:00Z",
        query="https://example.com/data.csv",
        query_hash="sha256:" + "0" * 64,
        content_hash=content_hash,
        license_note="fetched",
        request_metadata={"status_code": 200},
    )


def _counting_fetcher(snapshot_id: str) -> tuple[object, dict[str, int]]:
    content = b"a,b\n1,2\n"
    content_hash = sha256_content_hash(content)
    snapshot = _snapshot(content_hash, snapshot_id)
    calls = {"count": 0}

    async def fetch(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del config
        calls["count"] += 1
        return UrlFetchResult(
            content_hash=content_hash,
            content_bytes=content,
            mime_type="text/csv",
            status_code=200,
            final_url=url,
            source_snapshot=snapshot,
        )

    return fetch, calls


def test_same_key_same_upload_bytes_replays_same_input(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    headers = _headers(csrf_token, idempotency_key="upload-key-1")

    def upload():  # noqa: ANN202
        return client.post(
            "/api/research-inputs",
            data={"project_id": "proj_01", "type": "pdf"},
            files={
                "file": ("report.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")
            },
            headers=headers,
        )

    first = upload()
    assert first.status_code == 201
    second = upload()
    assert second.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


def test_same_key_same_filename_different_bytes_conflicts(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    """The fingerprint binds real byte identity, not just the filename."""

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    headers = _headers(csrf_token, idempotency_key="upload-key-2")

    first = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf"},
        files={"file": ("same.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")},
        headers=headers,
    )
    assert first.status_code == 201

    other_bytes = FIXTURES_BYTES["sample.pdf"] + b"\n% appended\n"
    second = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf"},
        files={"file": ("same.pdf", other_bytes, "application/pdf")},
        headers=headers,
    )
    assert second.status_code == 409
    assert second.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_different_keys_same_content_both_succeed_and_dedup(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    """Two independent requests carrying identical bytes are both valid.

    Distinct idempotency keys denote distinct *ingestions* -- they must produce
    two separate Research Input rows. Content identity is decoupled: the bytes
    are deduplicated onto a single immutable ``research_input_contents`` row,
    so both inputs share the same ``content_hash`` while keeping different ids.
    """

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    body = {"project_id": "proj_01", "type": "text", "text_content": "shared body"}

    first = client.post(
        "/api/research-inputs",
        json=body,
        headers=_headers(csrf_token, idempotency_key="key-A"),
    )
    second = client.post(
        "/api/research-inputs",
        json=body,
        headers=_headers(csrf_token, idempotency_key="key-B"),
    )
    assert first.status_code == 201
    assert second.status_code == 201
    # Different ingestions (different keys) -> different row ids.
    first_id = first.json()["data"]["id"]
    second_id = second.json()["data"]["id"]
    assert first_id != second_id
    # Cross-source content dedup: same content hash, one shared blob.
    assert first.json()["data"]["content_hash"] == second.json()["data"]["content_hash"]

    # Each key still replays independently to *its own* ingestion row.
    replay_a = client.post(
        "/api/research-inputs",
        json=body,
        headers=_headers(csrf_token, idempotency_key="key-A"),
    )
    assert replay_a.status_code == 201
    assert replay_a.json()["data"]["id"] == first_id
    replay_b = client.post(
        "/api/research-inputs",
        json=body,
        headers=_headers(csrf_token, idempotency_key="key-B"),
    )
    assert replay_b.status_code == 201
    assert replay_b.json()["data"]["id"] == second_id


def test_url_replay_does_not_refetch_the_network(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    """Replay is decided before the fetch, so the network is touched once."""

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    fetcher, calls = _counting_fetcher("snap_counted")
    _install_fetcher(app, fetcher)

    body = {
        "project_id": "proj_01",
        "type": "url",
        "url": "https://example.com/data.csv",
    }
    headers = _headers(csrf_token, idempotency_key="url-key-1")

    first = client.post("/api/research-inputs", json=body, headers=headers)
    assert first.status_code == 201
    assert calls["count"] == 1

    replay = client.post("/api/research-inputs", json=body, headers=headers)
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert calls["count"] == 1


def test_same_key_different_url_conflicts_without_fetching(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    fetcher, calls = _counting_fetcher("snap_conflict")
    _install_fetcher(app, fetcher)
    headers = _headers(csrf_token, idempotency_key="url-key-2")

    first = client.post(
        "/api/research-inputs",
        json={
            "project_id": "proj_01",
            "type": "url",
            "url": "https://example.com/data.csv",
        },
        headers=headers,
    )
    assert first.status_code == 201
    assert calls["count"] == 1

    conflict = client.post(
        "/api/research-inputs",
        json={
            "project_id": "proj_01",
            "type": "url",
            "url": "https://example.com/other.csv",
        },
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    # The conflicting request is rejected before any network call is made.
    assert calls["count"] == 1


def test_failed_url_fetch_leaves_the_key_retryable(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    """A failed fetch must not leave a permanent completed mapping behind."""

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    content = b"a,b\n1,2\n"
    content_hash = sha256_content_hash(content)
    snapshot = _snapshot(content_hash, "snap_retry")
    state = {"fail": True}

    async def flaky(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del config
        if state["fail"]:
            raise UrlFetchError(code="URL_FETCH_FAILED", detail="upstream exploded")
        return UrlFetchResult(
            content_hash=content_hash,
            content_bytes=content,
            mime_type="text/csv",
            status_code=200,
            final_url=url,
            source_snapshot=snapshot,
        )

    _install_fetcher(app, flaky)
    body = {
        "project_id": "proj_01",
        "type": "url",
        "url": "https://example.com/data.csv",
    }
    headers = _headers(csrf_token, idempotency_key="url-key-3")

    failed = client.post("/api/research-inputs", json=body, headers=headers)
    assert failed.status_code == 502

    state["fail"] = False
    retried = client.post("/api/research-inputs", json=body, headers=headers)
    assert retried.status_code == 201


# ---- request body ceilings -------------------------------------------------
#
# Content-Length is client supplied and may be absent entirely, so every test
# below streams its body with no declared length. The ceiling must still hold,
# which is only possible if it is enforced on the ASGI receive channel rather
# than after the parser has already buffered the body.


async def _stream_request(
    app: FastAPI,
    *,
    path: str,
    headers: dict[str, str],
    chunks: list[bytes],
    cookies: dict[str, str],
) -> tuple[int, dict]:
    """Drive one POST through the ASGI app with a chunked, unsized body."""

    cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in headers.items()
    ]
    if cookie_header:
        raw_headers.append((b"cookie", cookie_header.encode("latin-1")))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }

    pending = list(chunks)

    async def receive() -> dict:
        if pending:
            chunk = pending.pop(0)
            return {
                "type": "http.request",
                "body": chunk,
                "more_body": bool(pending),
            }
        return {"type": "http.request", "body": b"", "more_body": False}

    captured: dict = {"status": None, "body": b""}

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            captured["status"] = message["status"]
        elif message["type"] == "http.response.body":
            captured["body"] += message.get("body", b"")

    await app(scope, receive, send)
    try:
        payload = json.loads(captured["body"] or b"{}")
    except ValueError:
        payload = {}
    return captured["status"], payload


def _asgi_headers(csrf_token: str, content_type: str) -> dict[str, str]:
    return {
        "content-type": content_type,
        "x-csrf-token": csrf_token,
        "idempotency-key": "asgi-" + secrets.token_hex(6),
        "host": "testserver",
    }


def test_unsized_json_body_over_limit_is_rejected_413(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", 2048)

    oversized = json.dumps(
        {"project_id": "proj_01", "type": "text", "text_content": "x" * 8192}
    ).encode()
    chunks = [oversized[i : i + 1024] for i in range(0, len(oversized), 1024)]

    status, payload = asyncio.run(
        _stream_request(
            app,
            path="/api/research-inputs",
            headers=_asgi_headers(csrf_token, "application/json"),
            chunks=chunks,
            cookies=dict(client.cookies),
        )
    )
    assert status == 413
    assert payload.get("code") == "RESEARCH_INPUT_TOO_LARGE"


def _multipart_body(file_bytes: bytes, boundary: str) -> bytes:
    def part(name: str, value: str) -> bytes:
        return (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()

    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="big.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    return (
        part("project_id", "proj_01")
        + part("type", "pdf")
        + head
        + file_bytes
        + f"\r\n--{boundary}--\r\n".encode()
    )


def test_unsized_multipart_body_over_limit_is_rejected_413(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", 4096)

    boundary = "----b19boundary"
    body = _multipart_body(b"%PDF-1.4\n" + b"y" * 200000, boundary)
    chunks = [body[i : i + 8192] for i in range(0, len(body), 8192)]

    status, payload = asyncio.run(
        _stream_request(
            app,
            path="/api/research-inputs",
            headers=_asgi_headers(
                csrf_token, f"multipart/form-data; boundary={boundary}"
            ),
            chunks=chunks,
            cookies=dict(client.cookies),
        )
    )
    assert status == 413
    assert payload.get("code") == "RESEARCH_INPUT_TOO_LARGE"


def test_file_of_exactly_the_limit_is_accepted_despite_multipart_overhead(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Framing bytes must not push a legal maximum-size file over the ceiling."""

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    pdf = FIXTURES_BYTES["sample.pdf"]
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", len(pdf))

    response = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf"},
        files={"file": ("exact.pdf", pdf, "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert response.status_code == 201
    assert response.json()["data"]["size_bytes"] == len(pdf)


def test_multipart_with_too_many_fields_is_rejected(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    data = {"project_id": "proj_01", "type": "pdf"}
    for index in range(40):
        data[f"filler_{index}"] = "x"

    response = client.post(
        "/api/research-inputs",
        data=data,
        files={"file": ("a.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")},
        headers=_headers(csrf_token),
    )
    assert response.status_code in {400, 413, 422}
    assert response.status_code != 201


def test_multipart_with_more_than_one_file_is_rejected(
    app_and_client: tuple[FastAPI, TestClient, str, str],
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    response = client.post(
        "/api/research-inputs",
        data={"project_id": "proj_01", "type": "pdf"},
        files=[
            ("file", ("a.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")),
            ("extra", ("b.pdf", FIXTURES_BYTES["sample.pdf"], "application/pdf")),
        ],
        headers=_headers(csrf_token),
    )
    assert response.status_code in {400, 413, 422}
    assert response.status_code != 201


def test_understated_content_length_cannot_bypass_the_ceiling(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A lying Content-Length must not buy more body than the real ceiling."""

    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", 2048)

    oversized = json.dumps(
        {"project_id": "proj_01", "type": "text", "text_content": "x" * 8192}
    ).encode()
    headers = _asgi_headers(csrf_token, "application/json")
    headers["content-length"] = "10"  # deliberately understated

    status, payload = asyncio.run(
        _stream_request(
            app,
            path="/api/research-inputs",
            headers=headers,
            chunks=[oversized[i : i + 1024] for i in range(0, len(oversized), 1024)],
            cookies=dict(client.cookies),
        )
    )
    assert status != 201
    assert status in {400, 413, 422}


def test_malformed_content_length_does_not_bypass_the_ceiling(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    monkeypatch.setattr(settings, "RESEARCH_INPUT_MAX_SIZE_BYTES", 2048)

    oversized = json.dumps(
        {"project_id": "proj_01", "type": "text", "text_content": "x" * 8192}
    ).encode()
    headers = _asgi_headers(csrf_token, "application/json")
    headers["content-length"] = "not-a-number"

    status, _ = asyncio.run(
        _stream_request(
            app,
            path="/api/research-inputs",
            headers=headers,
            chunks=[oversized[i : i + 1024] for i in range(0, len(oversized), 1024)],
            cookies=dict(client.cookies),
        )
    )
    assert status != 201
