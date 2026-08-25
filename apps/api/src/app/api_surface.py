"""Canonical security classification for the current HTTP API surface.

The generated OpenAPI contract owns resource shape. This module owns only the
small security-relevant path classification needed before routing:

* which API paths are intentionally public,
* which anonymous share reads receive hardened response handling, and
* the default-deny rule for every other ``/api`` request.

Every other API route and error-envelope shape remains outside this surface.
"""

from __future__ import annotations

API_ROOT = "/api"
SESSION_CREATE_PATH = "/api/sessions"
PUBLIC_SHARE_PREFIX = "/api/public/shares/"

# System surfaces that are intentionally reachable before an anonymous session
# exists. Product resources are protected by default.
PUBLIC_UNAUTH_PREFIXES = (
    "/api/health",
    "/api/docs",
    "/api/openapi.json",
)

_PUBLIC_SHARE_READ_METHODS = frozenset({"GET", "HEAD"})


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    """Return whether ``path`` equals a prefix or is a child path beneath it."""

    return any(path == prefix or path.startswith(prefix + "/") for prefix in prefixes)


def _is_api_path(path: str) -> bool:
    return path == API_ROOT or path.startswith(API_ROOT + "/")


def requires_authentication(method: str, path: str) -> bool:
    """Return whether the request must carry an authenticated anonymous session."""

    if not _is_api_path(path):
        return False
    if _matches_prefix(path, PUBLIC_UNAUTH_PREFIXES):
        return False
    if method == "POST" and path.rstrip("/") == SESSION_CREATE_PATH:
        return False
    if is_public_share_read(method, path):
        return False
    return True


def is_public_share_read(method: str, path: str) -> bool:
    """Return ``True`` only for a share projection or its frozen Dataset CSV."""

    if method not in _PUBLIC_SHARE_READ_METHODS:
        return False
    if not path.startswith(PUBLIC_SHARE_PREFIX):
        return False
    segments = path.removeprefix(PUBLIC_SHARE_PREFIX).split("/")
    if len(segments) == 1:
        return bool(segments[0])
    return (
        len(segments) == 5
        and all(segments)
        and segments[1] == "artifacts"
        and segments[3:] == ["exports", "csv"]
    )


def public_share_instance() -> str:
    """Return a token-free Problem Details instance for public share reads."""

    return f"{PUBLIC_SHARE_PREFIX}public"
