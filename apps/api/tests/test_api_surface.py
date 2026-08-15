"""Security and generated-contract invariants for the sole HTTP API surface."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import api_surface
from app.main import create_app
import app.routers.health as health_module


ROOT = Path(__file__).parents[3]
_OPENAPI_METHODS = frozenset({"get", "post", "put", "patch", "delete", "options", "head"})

# System endpoints are not product resources. This explicit set makes every
# non-contract route a deliberate, reviewable exception.
SYSTEM_ONLY_OPERATIONS = frozenset({("GET", "/api/health")})

PUBLIC_REQUESTS = [
    ("GET", "/api/health"),
    ("GET", "/api/docs"),
    ("GET", "/api/openapi.json"),
    ("GET", "/"),
    ("POST", "/api/sessions"),
    ("POST", "/api/sessions/"),
    ("GET", "/api/public/shares/tok-123"),
    ("HEAD", "/api/public/shares/tok-123"),
    ("GET", "/apix"),
    ("GET", "/apis"),
]

PROTECTED_REQUESTS = [
    ("GET", "/api/sessions"),
    ("DELETE", "/api/sessions"),
    ("GET", "/api/sessions/current"),
    ("DELETE", "/api/sessions/current"),
    ("GET", "/api/projects"),
    ("POST", "/api/projects"),
    ("GET", "/api/projects/proj-1"),
    ("POST", "/api/projects/proj-1/runs"),
    ("GET", "/api/contracts/drafts/draft-1"),
    ("PATCH", "/api/contracts/drafts/draft-1"),
    ("GET", "/api/contracts/contract-1"),
    ("GET", "/api/runs/run-1"),
    ("DELETE", "/api/runs/run-1"),
    ("GET", "/api/runs/run-1/events"),
    ("GET", "/api/artifacts/art-1"),
    ("GET", "/api/artifact-versions/ver-1"),
    ("GET", "/api/artifact-versions/ver-1/graph"),
    ("GET", "/api/artifact-versions/ver-1/graph/nodes"),
    ("GET", "/api/artifact-versions/ver-1/graph/nodes/node-1"),
    ("GET", "/api/artifact-versions/ver-1/graph/edges"),
    ("GET", "/api/artifact-versions/ver-1/graph/edges/edge-1"),
    ("GET", "/api/evidence/ev-1"),
    ("GET", "/api/source-snapshots/snap-1"),
    ("GET", "/api/projects/proj-1/shares"),
    ("POST", "/api/projects/proj-1/shares"),
    ("POST", "/api/public/shares/tok-123"),
    ("GET", "/api/public/shares/tok-123/extra"),
    ("GET", "/api/public/shares/"),
    ("POST", "/api/test/bootstrap"),
]


@pytest.mark.parametrize(("method", "path"), PUBLIC_REQUESTS)
def test_public_requests_skip_authentication(method: str, path: str) -> None:
    assert api_surface.requires_authentication(method, path) is False


@pytest.mark.parametrize(("method", "path"), PROTECTED_REQUESTS)
def test_product_and_unknown_api_requests_require_authentication(
    method: str, path: str
) -> None:
    assert api_surface.requires_authentication(method, path) is True


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/public/shares/tok-123", True),
        ("HEAD", "/api/public/shares/tok-123", True),
        ("POST", "/api/public/shares/tok-123", False),
        ("GET", "/api/public/shares/", False),
        ("GET", "/api/public/shares/tok-123/extra", False),
        ("GET", "/api/projects", False),
    ],
)
def test_public_share_read_detection(method: str, path: str, expected: bool) -> None:
    assert api_surface.is_public_share_read(method, path) is expected


def test_public_share_instance_hides_token() -> None:
    instance = api_surface.public_share_instance()
    assert instance == "/api/public/shares/public"
    assert api_surface.PUBLIC_SHARE_PREFIX in instance


def test_runtime_api_routes_match_generated_current_contract() -> None:
    """Prevent ungoverned APIs from being mounted beside the generated Contract."""

    generated = json.loads(
        (ROOT / "packages" / "schemas" / "generated" / "core" / "openapi.json").read_text(
            encoding="utf-8"
        )
    )
    contract_operations = {
        (method.upper(), path)
        for path, operations in generated["paths"].items()
        for method in operations
        if method in _OPENAPI_METHODS
    }

    # Build a fresh application and compare its generated HTTP contract rather
    # than depending on a mutable module-level singleton or FastAPI route class
    # identity left behind by unrelated tests.
    runtime_openapi = create_app().openapi()
    runtime_operations = {
        (method.upper(), path)
        for path, operations in runtime_openapi["paths"].items()
        for method in operations
        if method in _OPENAPI_METHODS
    }

    assert runtime_operations == contract_operations | SYSTEM_ONLY_OPERATIONS


def test_health_reports_model_configuration_without_claiming_provider_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module,
        "settings",
        SimpleNamespace(
            APP_ENV="test",
            research_assistant_ready=True,
            DASHSCOPE_MODEL="qwen-test",
            DASHSCOPE_MODEL_REVISION="qwen-test-revision",
        ),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    response = health_module.health(request)  # type: ignore[arg-type]

    assert response["research_assistant"] == {
        "status": "configured",
        "provider": "qwen",
        "model": "qwen-test",
        "model_revision": "qwen-test-revision",
    }
