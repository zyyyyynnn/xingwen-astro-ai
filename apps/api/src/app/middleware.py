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


async def api_error_exception_handler(request: Request, exc: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    response = ApiResponse.fail(exc.code, exc.message, exc.detail, request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})


async def api_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    response = ApiResponse.fail(ERROR_CODE_MAP.get(exc.status_code, "INVALID_REQUEST"), str(exc.detail), request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})


async def api_validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    detail = {
        "validation_errors": [
            {"loc": " -> ".join(str(loc) for loc in error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
    }
    response = ApiResponse.fail("SCHEMA_VALIDATION_FAILED", "Request validation failed", detail, request_id=request_id)
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"), headers={"X-Request-Id": request_id})
