"""Router helpers."""

from __future__ import annotations

from fastapi import Request

from app.schemas.common import ApiResponse


def ok(request: Request, data, *, cached: bool = False) -> ApiResponse:
    request_id = getattr(request.state, "request_id", "")
    return ApiResponse.ok(data=data, request_id=request_id, cached=cached)
