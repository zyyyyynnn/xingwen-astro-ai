"""Table-driven guard for the centralized API-surface classification.

These expectations pin the versionless single-surface behavior: everything
lives under ``/api``; a small public allowlist (health, data-pipeline tasks,
docs, openapi, anonymous session-create, public share reads) is served without
a session, and every other ``/api`` path is protected by default.
"""

from __future__ import annotations

import pytest

from app import api_surface

# Requests that must be served WITHOUT an anonymous session.
PUBLIC_REQUESTS = [
    ("GET", "/api/health"),
    ("POST", "/api/tasks"),
    ("GET", "/api/tasks/task-123"),
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

# Requests that MUST require an authenticated session.
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
    ("GET", "/api/runs/run-1/events"),
    ("GET", "/api/artifacts/art-1"),
    ("GET", "/api/artifact-versions/ver-1"),
    ("GET", "/api/evidence/ev-1"),
    ("GET", "/api/source-snapshots/snap-1"),
    ("GET", "/api/projects/proj-1/shares"),
    ("POST", "/api/projects/proj-1/shares"),
    ("POST", "/api/public/shares/tok-123"),  # non-read method on a share token
    ("GET", "/api/public/shares/tok-123/extra"),  # multi-segment is not a token read
    ("GET", "/api/public/shares/"),  # empty token is not a public share read
    ("POST", "/api/test/bootstrap"),
    ("GET", "/api/tasksfoo"),  # sibling of /api/tasks must NOT be public
]


@pytest.mark.parametrize(("method", "path"), PUBLIC_REQUESTS)
def test_public_requests_skip_authentication(method: str, path: str) -> None:
    assert api_surface.requires_authentication(method, path) is False


@pytest.mark.parametrize(("method", "path"), PROTECTED_REQUESTS)
def test_protected_requests_require_authentication(method: str, path: str) -> None:
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


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/projects", True),
        ("/api/public/shares/tok-123", True),
        ("/api/sessions", True),
        ("/api/contracts/drafts/draft-1", True),
        ("/api/health", False),
        ("/api/tasks/task-1", False),
        ("/", False),
        ("/apix", False),
        ("/apis", False),
    ],
)
def test_problem_details_classification(path: str, expected: bool) -> None:
    assert api_surface.uses_problem_details(path) is expected


def test_public_share_instance_hides_token() -> None:
    instance = api_surface.public_share_instance()
    assert instance == "/api/public/shares/public"
    assert api_surface.PUBLIC_SHARE_PREFIX in instance
