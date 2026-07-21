"""Request ID middleware and API error handlers."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.errors import ApiError
from app.schemas.common import ApiResponse
from app.schemas.v2 import ProblemDetails, ProblemFieldError
from app.security import SecurityProblem, SessionService

ERROR_CODE_MAP = {
    400: "INVALID_REQUEST",
    404: "TASK_NOT_FOUND",
    409: "TASK_NOT_READY",
    422: "SCHEMA_VALIDATION_FAILED",
}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:  # noqa: ANN401
        request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:12])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


class V2SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, sessions: SessionService, cookie_name: str) -> None:
        super().__init__(app)
        self.sessions = sessions
        self.cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:  # noqa: ANN401
        if (
            not request.url.path.startswith("/api/v2")
            or request.url.path.rstrip("/") == "/api/v2/sessions"
        ):
            return await call_next(request)
        try:
            record = self.sessions.authenticate(request.cookies.get(self.cookie_name))
            request.state.session = record
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                self.sessions.verify_csrf(record, request.headers.get("X-CSRF-Token"))
        except SecurityProblem as exc:
            return v2_problem_response(request, exc)
        return await call_next(request)


def v2_problem_response(request: Request, exc: SecurityProblem) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or "unknown"
    problem = ProblemDetails(
        type=f"https://xingwen.example/errors/{exc.code.lower().replace('_', '-')}",
        title=exc.title,
        status=exc.status,
        detail=exc.detail,
        instance=request.url.path,
        code=exc.code,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.status,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
        headers={"X-Request-Id": request_id, "Cache-Control": "no-store"},
    )


async def v2_security_exception_handler(request: Request, exc: SecurityProblem) -> JSONResponse:
    return v2_problem_response(request, exc)


async def api_error_exception_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    response = ApiResponse.fail(exc.code, exc.message, exc.detail, request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})


async def api_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if request.url.path.startswith("/api/v2"):
        problem = SecurityProblem(
            status=exc.status_code,
            code="INVALID_REQUEST" if exc.status_code == 400 else "RESOURCE_NOT_FOUND",
            title="Invalid request" if exc.status_code == 400 else "Resource not found",
            detail="The request could not be completed",
        )
        return v2_problem_response(request, problem)
    request_id = getattr(request.state, "request_id", "")
    response = ApiResponse.fail(ERROR_CODE_MAP.get(exc.status_code, "INVALID_REQUEST"), str(exc.detail), request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})


async def api_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    if request.url.path.startswith("/api/v2"):
        request_id = getattr(request.state, "request_id", "") or "unknown"
        problem = ProblemDetails(
            type="https://xingwen.example/errors/schema-validation-failed",
            title="Request validation failed",
            status=422,
            detail="The request does not match the required schema",
            instance=request.url.path,
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
        return JSONResponse(
            status_code=422,
            content=problem.model_dump(mode="json"),
            media_type="application/problem+json",
            headers={"X-Request-Id": request_id},
        )
    request_id = getattr(request.state, "request_id", "")
    detail = {
        "validation_errors": [
            {"loc": " -> ".join(str(loc) for loc in error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
    }
    response = ApiResponse.fail("SCHEMA_VALIDATION_FAILED", "Request validation failed", detail, request_id=request_id)
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})
