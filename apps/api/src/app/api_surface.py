"""Canonical description of the HTTP API surface.

This module is the single source of truth for the security-relevant
classification of request paths:

* which paths are public (served without an anonymous session),
* which paths are anonymous public *share reads* (and therefore carry the
  hardened public-share response headers), and
* which paths return the RFC-9457 ``application/problem+json`` error shape
  versus the legacy :class:`ApiResponse` envelope.

Centralizing these rules keeps the security boundary explicit and testable
instead of being scattered across the middleware and error handlers as ad hoc
``str.startswith`` checks. The literal prefixes below are the *only* place the
version segment appears in the security decision, so the versionless
single-surface cut-over flips these constants (and the accompanying
``test_api_surface`` table) in one lockstep change.

The functions are pure and allocation-free on the request hot path (a couple of
``str.startswith``/equality checks), so consuming them from the middleware adds
no measurable per-request cost.
"""

from __future__ import annotations

# --- Surface constants -------------------------------------------------------
# Current (versioned) values. The versionless cut-over changes these literals;
# nothing else in the security decision needs to move.
PROTECTED_ROOT = "/api/v2"
SESSION_CREATE_PATH = "/api/v2/sessions"
PUBLIC_SHARE_PREFIX = "/api/v2/shares/"

# Evolution seam (see ADR "versionless single-surface API"): maps a route
# ``path_format`` to a human-readable sunset note. While this map is empty no
# deprecation-header middleware is mounted, so the request hot path pays
# nothing; the first real deprecation populates it and enables the header hook.
DEPRECATED_OPERATIONS: dict[str, str] = {}

_PUBLIC_SHARE_READ_METHODS = frozenset({"GET", "HEAD"})


def requires_authentication(method: str, path: str) -> bool:
    """Return ``True`` when the security middleware must enforce a session.

    A request is public (no session required) when it does not target the
    protected root, when it is the anonymous session-create endpoint, or when
    it is an anonymous public share read.
    """

    if not path.startswith(PROTECTED_ROOT):
        return False
    if path.rstrip("/") == SESSION_CREATE_PATH:
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

    Paths outside the protected root use the legacy :class:`ApiResponse`
    envelope (the data-pipeline task surface).
    """

    return path.startswith(PROTECTED_ROOT)


def public_share_instance() -> str:
    """Return a stable problem ``instance`` for public share reads.

    Using a fixed value instead of the concrete request path avoids leaking the
    raw share token into error responses.
    """

    return f"{PUBLIC_SHARE_PREFIX}public"
