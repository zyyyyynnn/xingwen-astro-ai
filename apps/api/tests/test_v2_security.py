from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import (
    InMemoryIdempotencyStore,
    InMemoryRateLimiter,
    InMemorySessionStore,
    OwnershipPolicy,
    ShareTokenAccessLogFilter,
    SecurityProblem,
    SessionService,
    require_revision,
)


def test_session_cookie_lifecycle_and_public_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.routers.sessions.settings.SESSION_COOKIE_SECURE", True)
    client = TestClient(create_app(), base_url="https://testserver")
    created = client.post("/api/v2/sessions", headers={"X-Request-Id": "req_session"})
    assert created.status_code == 201
    payload = created.json()
    assert payload["data"]["status"] == "active"
    assert payload["data"]["csrf_token"]
    assert "id" not in payload["data"]
    assert payload["meta"]["request_id"] == "req_session"
    assert created.headers["location"] == "/api/v2/sessions/current"
    assert created.headers["ratelimit-limit"] == "30"
    assert created.headers["ratelimit-remaining"] == "29"
    assert created.headers["cache-control"] == "no-store"

    cookie = created.headers["set-cookie"].lower()
    assert "secure" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api/v2" in cookie

    current = client.get("/api/v2/sessions/current")
    assert current.status_code == 200
    assert current.headers["cache-control"] == "no-store"
    assert "csrf_token" not in current.json()["data"]

    hidden = client.get("/api/v2/private-resource-that-does-not-exist")
    assert hidden.status_code == 404
    assert hidden.headers["content-type"].startswith("application/problem+json")
    assert hidden.json()["code"] == "RESOURCE_NOT_FOUND"
    assert "private-resource-that-does-not-exist" not in hidden.json()["detail"]

    missing_csrf = client.delete("/api/v2/sessions/current")
    assert missing_csrf.status_code == 403
    assert missing_csrf.headers["content-type"].startswith("application/problem+json")
    assert missing_csrf.headers["cache-control"] == "no-store"
    assert missing_csrf.json()["code"] == "CSRF_INVALID"

    revoked = client.delete(
        "/api/v2/sessions/current",
        headers={"X-CSRF-Token": payload["data"]["csrf_token"]},
    )
    assert revoked.status_code == 204
    assert revoked.headers["cache-control"] == "no-store"
    assert client.get("/api/v2/sessions/current").status_code == 401


def test_security_problem_responses_preserve_cors_headers() -> None:
    client = TestClient(create_app(), base_url="https://testserver")
    origin = "http://localhost:5173"

    missing = client.get("/api/v2/sessions/current", headers={"Origin": origin})
    assert missing.status_code == 401
    assert missing.headers["access-control-allow-origin"] == origin
    assert missing.headers["cache-control"] == "no-store"

    created = client.post("/api/v2/sessions", headers={"Origin": origin})
    csrf_failure = client.delete("/api/v2/sessions/current", headers={"Origin": origin})
    assert created.status_code == 201
    assert csrf_failure.status_code == 403
    assert csrf_failure.headers["access-control-allow-origin"] == origin
    assert csrf_failure.headers["cache-control"] == "no-store"


def test_missing_and_expired_sessions_use_same_public_401() -> None:
    client = TestClient(create_app(), base_url="https://testserver")
    missing = client.get("/api/v2/sessions/current")
    assert missing.status_code == 401
    assert missing.json()["code"] == "SESSION_REQUIRED"

    store = InMemorySessionStore()
    service = SessionService(store, ttl_seconds=1)
    start = datetime(2026, 7, 21, tzinfo=UTC)
    _, credential, _ = service.create(now=start)
    with pytest.raises(SecurityProblem) as expired:
        service.authenticate(credential, now=start + timedelta(seconds=2))
    assert expired.value.status == 401
    assert expired.value.code == "SESSION_REQUIRED"


def test_csrf_token_is_session_bound() -> None:
    store = InMemorySessionStore()
    service = SessionService(store, ttl_seconds=60)
    first, _, first_csrf = service.create()
    second, _, second_csrf = service.create()
    service.verify_csrf(first, first_csrf)
    with pytest.raises(SecurityProblem, match="valid CSRF token") as invalid:
        service.verify_csrf(first, second_csrf)
    assert invalid.value.status == 403
    assert second.id != first.id


def test_ownership_hides_cross_session_resource_existence() -> None:
    OwnershipPolicy.require_owner(
        owner_session_id="session_a",
        current_session_id="session_a",
        code="PROJECT_NOT_FOUND",
    )
    with pytest.raises(SecurityProblem) as hidden:
        OwnershipPolicy.require_owner(
            owner_session_id="session_a",
            current_session_id="session_b",
            code="PROJECT_NOT_FOUND",
        )
    assert hidden.value.status == 404
    assert hidden.value.code == "PROJECT_NOT_FOUND"
    assert hidden.value.detail == "Resource not found"


def test_idempotency_replays_same_request_and_rejects_changed_payload() -> None:
    store = InMemoryIdempotencyStore()
    calls = 0

    def operation() -> dict[str, str]:
        nonlocal calls
        calls += 1
        return {"id": "run_01"}

    first, replayed = store.execute(
        session_id="session_a",
        scope="create_run",
        key="key-1",
        payload={"x": 1},
        operation=operation,
    )
    second, replayed_second = store.execute(
        session_id="session_a",
        scope="create_run",
        key="key-1",
        payload={"x": 1},
        operation=operation,
    )
    assert first == second
    assert replayed is False
    assert replayed_second is True
    assert calls == 1

    with pytest.raises(SecurityProblem) as conflict:
        store.execute(
            session_id="session_a",
            scope="create_run",
            key="key-1",
            payload={"x": 2},
            operation=operation,
        )
    assert conflict.value.status == 409
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def test_version_conflict_is_stable() -> None:
    require_revision(expected=2, current=2)
    with pytest.raises(SecurityProblem) as conflict:
        require_revision(expected=1, current=2)
    assert conflict.value.status == 409
    assert conflict.value.code == "VERSION_CONFLICT"


def test_rate_limit_uses_stable_429_problem() -> None:
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    assert limiter.consume("client-a")[0] == 0
    with pytest.raises(SecurityProblem) as limited:
        limiter.consume("client-a")
    assert limited.value.status == 429
    assert limited.value.code == "RATE_LIMITED"

    app = create_app()
    app.state.session_rate_limiter = InMemoryRateLimiter(limit=1)
    client = TestClient(app, base_url="https://testserver")
    assert client.post("/api/v2/sessions").status_code == 201
    response = client.post("/api/v2/sessions")
    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "RATE_LIMITED"


def test_uvicorn_access_log_redacts_raw_share_tokens() -> None:
    raw_token = "secret-share-token-value"
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1234",
            "GET",
            f"/api/v2/shares/{raw_token}?preview=1",
            "1.1",
            200,
        ),
        exc_info=None,
    )
    assert ShareTokenAccessLogFilter().filter(record) is True
    rendered = record.getMessage()
    assert raw_token not in rendered
    assert "/api/v2/shares/[REDACTED]?preview=1" in rendered
