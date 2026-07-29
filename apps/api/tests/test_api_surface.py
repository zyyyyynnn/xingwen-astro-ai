"""Table-driven guard for the centralized API-surface classification.

These expectations mirror the *current* behavior of the security middleware and
error handlers. They must stay green through the security-surface extraction
(PR-1, this change), and the versionless single-surface cut-over (PR-2) flips
both the ``api_surface`` constants and this table in one lockstep change.
"""

from __future__ import annotations

import pytest

from app import api_surface

# Requests that must be served WITHOUT an anonymous session.
PUBLIC_REQUESTS = [
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/tasks"),
    ("GET", "/api/v1/tasks/task-123"),
    ("GET", "/api/v1/docs"),
    ("GET", "/api/v1/openapi.json"),
    ("GET", "/"),
    ("POST", "/api/v2/sessions"),
    ("POST", "/api/v2/sessions/"),
    ("GET", "/api/v2/shares/tok-123"),
    ("HEAD", "/api/v2/shares/tok-123"),
]

# Requests that MUST require an authenticated session.
PROTECTED_REQUESTS = [
    ("GET", "/api/v2/sessions/current"),
    ("DELETE", "/api/v2/sessions/current"),
    ("GET", "/api/v2/projects"),
    ("POST", "/api/v2/projects"),
    ("GET", "/api/v2/projects/proj-1"),
    ("POST", "/api/v2/projects/proj-1/runs"),
    ("GET", "/api/v2/runs/run-1"),
    ("GET", "/api/v2/runs/run-1/events"),
    ("GET", "/api/v2/artifacts/art-1"),
    ("GET", "/api/v2/artifact-versions/ver-1"),
    ("GET", "/api/v2/evidence/ev-1"),
    ("GET", "/api/v2/source-snapshots/snap-1"),
    ("GET", "/api/v2/projects/proj-1/shares"),
    ("POST", "/api/v2/projects/proj-1/shares"),
    ("POST", "/api/v2/shares/tok-123"),  # non-read method on a share token
    ("GET", "/api/v2/shares/tok-123/extra"),  # multi-segment is not a token read
    ("GET", "/api/v2/shares/"),  # empty token is not a public share read
    ("POST", "/api/v2/test/bootstrap"),
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
        ("GET", "/api/v2/shares/tok-123", True),
        ("HEAD", "/api/v2/shares/tok-123", True),
        ("POST", "/api/v2/shares/tok-123", False),
        ("GET", "/api/v2/shares/", False),
        ("GET", "/api/v2/shares/tok-123/extra", False),
        ("GET", "/api/v2/projects", False),
    ],
)
def test_public_share_read_detection(method: str, path: str, expected: bool) -> None:
    assert api_surface.is_public_share_read(method, path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/v2/projects", True),
        ("/api/v2/shares/tok-123", True),
        ("/api/v2/sessions", True),
        ("/api/v1/health", False),
        ("/api/v1/tasks/task-1", False),
        ("/", False),
    ],
)
def test_problem_details_classification(path: str, expected: bool) -> None:
    assert api_surface.uses_problem_details(path) is expected


def test_public_share_instance_hides_token() -> None:
    instance = api_surface.public_share_instance()
    assert instance == "/api/v2/shares/public"
    assert api_surface.PUBLIC_SHARE_PREFIX in instance


def test_deprecated_operations_seam_is_empty() -> None:
    # The evolution seam is documented but dormant: no deprecation-header
    # middleware is mounted while this map is empty.
    assert api_surface.DEPRECATED_OPERATIONS == {}
