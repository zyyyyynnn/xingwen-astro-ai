"""Canonical description of the HTTP API surface.

This module is the single source of truth for the security-relevant
classification of request paths:

* which paths are public (served without an anonymous session),
* which paths are anonymous public *share reads* (and therefore carry the
  hardened public-share response headers), and
* which paths return the RFC-9457 ``application/problem+json`` error shape
  versus the legacy :class:`ApiResponse` envelope (the data-pipeline surface).

Centralizing these rules keeps the security boundary explicit and testable
instead of being scattered across the middleware and error handlers as ad hoc
``str.startswith`` checks. On the versionless single surface everything lives
under ``/api``; the security decision is therefore *default-deny* — any ``/api``
path that is not on the small public allowlist requires an anonymous session.
Adding a new domain never needs a middleware edit for the default (protected)
case; new anonymous surfaces must be added to the public allowlist here (today
only single-token ``/api/public/shares/{token}`` reads are anonymous).

The functions are pure and allocation-free on the request hot path (a couple of
``str.startswith``/equality checks against module-level tuples), so consuming
them from the middleware adds no measurable per-request cost.
"""

from __future__ import annotations

# --- Surface constants -------------------------------------------------------
API_ROOT = "/api"

# Anonymous session-create endpoint.
SESSION_CREATE_PATH = "/api/sessions"

# Prefix for anonymous public share reads (a single token segment beneath it).
PUBLIC_SHARE_PREFIX = "/api/public/shares/"

# Unauthenticated non-core surface: health probe, data-pipeline task reads, and
# the interactive API docs. These are served without a session cookie.
PUBLIC_UNAUTH_PREFIXES = (
    "/api/health",
    "/api/tasks",
    "/api/docs",
    "/api/openapi.json",
)

# Paths that use the legacy :class:`ApiResponse` envelope on error (the
# data-pipeline task surface). Every other ``/api`` path uses problem+json.
LEGACY_ENVELOPE_PREFIXES = ("/api/health", "/api/tasks")

# Evolution seam (see ADR "versionless single-surface API"): maps a route
# ``path_format`` to a human-readable sunset note. While this map is empty no
# deprecation-header middleware is mounted, so the request hot path pays
# nothing; the first real deprecation populates it and enables the header hook.
DEPRECATED_OPERATIONS: dict[str, str] = {}

_PUBLIC_SHARE_READ_METHODS = frozenset({"GET", "HEAD"})


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    """True when ``path`` equals a prefix or sits directly beneath it.

    Matching on ``prefix`` or ``prefix + "/"`` prevents a sibling such as
    ``/api/tasksfoo`` from being classified as ``/api/tasks``.
    """

    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _is_api_path(path: str) -> bool:
    """True only for the API root or a path segment beneath it."""

    return path == API_ROOT or path.startswith(API_ROOT + "/")


def requires_authentication(method: str, path: str) -> bool:
    """Return ``True`` when the security middleware must enforce a session.

    Default-deny: any ``/api`` path requires an anonymous session unless it is
    on the public allowlist (health/tasks/docs/openapi), the anonymous
    session-create endpoint, or an anonymous public share read.
    """

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
    """Return ``True`` for anonymous ``GET``/``HEAD`` reads of a single share token."""

    if method not in _PUBLIC_SHARE_READ_METHODS:
        return False
    if not path.startswith(PUBLIC_SHARE_PREFIX):
        return False
    token_segment = path.removeprefix(PUBLIC_SHARE_PREFIX)
    return bool(token_segment) and "/" not in token_segment


def uses_problem_details(path: str) -> bool:
    """Return ``True`` when errors on this path use ``application/problem+json``.

    The data-pipeline task surface (and any non-``/api`` path) keeps the legacy
    :class:`ApiResponse` envelope; every other ``/api`` path uses problem+json.
    """

    if not _is_api_path(path):
        return False
    return not _matches_prefix(path, LEGACY_ENVELOPE_PREFIXES)


def public_share_instance() -> str:
    """Return a stable problem ``instance`` for public share reads.

    Using a fixed value instead of the concrete request path avoids leaking the
    raw share token into error responses.
    """

    return f"{PUBLIC_SHARE_PREFIX}public"
