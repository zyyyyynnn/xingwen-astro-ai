"""Request ID middleware, security enforcement, and RFC 9457 error handlers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app import api_surface
from app.schemas.core import ProblemDetails, ProblemFieldError
from app.security import SecurityProblem, SessionService


_HTTP_PROBLEMS: dict[int, tuple[str, str]] = {
    400: ("INVALID_REQUEST", "Invalid request"),
    401: ("UNAUTHORIZED", "Unauthorized"),
    403: ("FORBIDDEN", "Forbidden"),
    404: ("RESOURCE_NOT_FOUND", "Resource not found"),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed"),
    409: ("CONFLICT", "Conflict"),
    413: ("PAYLOAD_TOO_LARGE", "Payload too large"),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Unsupported media type"),
    422: ("SCHEMA_VALIDATION_FAILED", "Request validation failed"),
    429: ("RATE_LIMITED", "Too many requests"),
    500: ("INTERNAL_ERROR", "Internal server error"),
    503: ("SERVICE_UNAVAILABLE", "Service unavailable"),
}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:  # noqa: ANN401
        request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:12])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, sessions: SessionService, cookie_name: str) -> None:
        super().__init__(app)
        self.sessions = sessions
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: Any) -> Response:  # noqa: ANN401
        if not api_surface.requires_authentication(request.method, request.url.path):
            return await call_next(request)
        try:
            record = self.sessions.authenticate(request.cookies.get(self.cookie_name))
            request.state.session = record
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                self.sessions.verify_csrf(record, request.headers.get("X-CSRF-Token"))
        except SecurityProblem as exc:
            return problem_response(request, exc)
        return await call_next(request)


def problem_response(request: Request, exc: SecurityProblem) -> JSONResponse:
    """Serialize one application/security failure using the sole error contract."""

    request_id = getattr(request.state, "request_id", "") or "unknown"
    problem = ProblemDetails(
        type=f"https://xingwen.example/errors/{exc.code.lower().replace('_', '-')}",
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        instance=_problem_instance(request),
        code=exc.code,
        request_id=request_id,
    )
    headers = {"X-Request-Id": request_id, "Cache-Control": "no-store"}
    headers.update(exc.headers)
    headers.update(_public_share_headers(request))
    return JSONResponse(
        status_code=exc.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
        headers=headers,
    )


async def security_exception_handler(
    request: Request, exc: SecurityProblem
) -> JSONResponse:
    return problem_response(request, exc)


async def api_http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    code, title = _HTTP_PROBLEMS.get(
        exc.status_code, ("HTTP_ERROR", "Request failed")
    )
    detail = str(exc.detail) if isinstance(exc.detail, str) and exc.detail else title
    return problem_response(
        request,
        SecurityProblem(
            status=exc.status_code,
            code=code,
            title=title,
            detail=detail,
            headers=dict(exc.headers or {}),
        ),
    )


async def api_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or "unknown"
    problem = ProblemDetails(
        type="https://xingwen.example/errors/schema-validation-failed",
        title="Request validation failed",
        status=422,
        detail="The request does not match the required schema",
        instance=_problem_instance(request),
        code="SCHEMA_VALIDATION_FAILED",
        request_id=request_id,
        errors=tuple(
            ProblemFieldError(
                field=".".join(str(loc) for loc in error["loc"]),
                code=error["type"],
                message=error["msg"],
            )
            for error in exc.errors()
        ),
    )
    headers = {"X-Request-Id": request_id, "Cache-Control": "no-store"}
    headers.update(_public_share_headers(request))
    return JSONResponse(
        status_code=422,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
        headers=headers,
    )


def _problem_instance(request: Request) -> str:
    if api_surface.is_public_share_read(request.method, request.url.path):
        return api_surface.public_share_instance()
    return request.url.path


def _public_share_headers(request: Request) -> dict[str, str]:
    if not api_surface.is_public_share_read(request.method, request.url.path):
        return {}
    return {
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
