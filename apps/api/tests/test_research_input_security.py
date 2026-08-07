"""HTTP-level security and transport contract tests for B-19 ingestion.

Exercises the mounted runtime boundary: CSRF/Idempotency headers, MIME
sniffing rejections, filename sanitization, size and rate limits, URL fetch
error mapping, ownership isolation and the metadata-only public DTOs.
"""

from __future__ import annotations

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
    monkeypatch: pytest.MonkeyPatch,
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

    monkeypatch.setattr(url_fetcher_module, "fetch_url", fake_fetch)
    monkeypatch.setattr(
        "app.routers.research_inputs.fetch_url", fake_fetch
    )
    monkeypatch.setattr(
        "app.routers.research_inputs.validate_url_policy", lambda url, config: None
    )


def test_url_ingestion_records_provenance_without_content(
    app_and_client: tuple[FastAPI, TestClient, str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)
    _stub_fetch(monkeypatch)

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    def blocked(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del url, config
        raise UrlFetchError(
            code="URL_FETCH_BLOCKED", detail="URL host is not in the allowed hosts"
        )

    monkeypatch.setattr("app.routers.research_inputs.fetch_url", blocked)

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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, client, session_id, csrf_token = app_and_client
    _seed_project(app, session_id)

    def failing(url: str, config: UrlFetchConfig) -> UrlFetchResult:  # noqa: ANN001
        del url, config
        raise UrlFetchError(
            code="URL_FETCH_TOO_LARGE", detail="URL response exceeds the maximum size"
        )

    monkeypatch.setattr("app.routers.research_inputs.fetch_url", failing)
    monkeypatch.setattr(
        "app.routers.research_inputs.validate_url_policy", lambda url, config: None
    )

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

