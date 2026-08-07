"""Transport-level request body limits (B-19).

``Content-Length`` is a *hint*, not a security boundary: it is client supplied,
may be absent entirely (``Transfer-Encoding: chunked``), and may lie. The only
sound enforcement point is the ASGI receive channel, counted as bytes actually
arrive and tripped *before* the JSON or multipart parser is allowed to buffer
the whole body.

:func:`bounded_body_request` returns a ``Request`` whose ``receive`` is wrapped
with a running byte counter. ``await request.json()`` / ``await request.form()``
on the returned object therefore cannot be made to buffer more than the limit,
regardless of what the headers claimed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.requests import Request

__all__ = [
    "MULTIPART_OVERHEAD_BYTES",
    "RequestBodyTooLarge",
    "bounded_body_request",
    "declared_content_length",
    "multipart_request_limit",
]

#: Bounded, conservative allowance for multipart framing on top of the file
#: payload itself: boundary delimiters, per-part headers, the small metadata
#: text fields (project_id/type/filename/mime_type) and the trailing boundary.
#: A legal file of exactly ``RESEARCH_INPUT_MAX_SIZE_BYTES`` must still be
#: accepted, so the request ceiling is the file ceiling plus this constant --
#: never an unbounded multiple of it.
MULTIPART_OVERHEAD_BYTES = 65536


class RequestBodyTooLarge(Exception):
    """Raised as soon as the cumulative received body exceeds the limit."""

    def __init__(self, limit_bytes: int) -> None:
        super().__init__(f"request body exceeds {limit_bytes} bytes")
        self.limit_bytes = limit_bytes


def multipart_request_limit(max_file_bytes: int) -> int:
    """Return the total request ceiling for a single-file multipart upload."""

    return max_file_bytes + MULTIPART_OVERHEAD_BYTES


def declared_content_length(request: Request) -> int | None:
    """Return a *trustworthy-shaped* ``Content-Length``, else ``None``.

    A malformed or negative value yields ``None`` so the caller falls through
    to the real streaming boundary instead of treating garbage as a size.
    """

    raw = request.headers.get("content-length")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def bounded_body_request(request: Request, limit_bytes: int) -> Request:
    """Return a ``Request`` that raises once more than ``limit_bytes`` arrive.

    The wrapper preserves ASGI semantics: ``more_body``, empty chunks and
    ``http.disconnect`` are passed through untouched; only the cumulative
    ``body`` byte count is policed.
    """

    receive = request.receive
    state = {"received": 0}

    async def bounded_receive() -> Any:
        message = await receive()
        if message.get("type") != "http.request":
            return message
        chunk = message.get("body", b"")
        if chunk:
            state["received"] += len(chunk)
            if state["received"] > limit_bytes:
                raise RequestBodyTooLarge(limit_bytes)
        return message

    return Request(request.scope, _cast_receive(bounded_receive))


def _cast_receive(fn: Callable[[], Awaitable[Any]]) -> Any:
    """Narrow the callable to the ASGI ``Receive`` shape without a hard import."""

    return fn
