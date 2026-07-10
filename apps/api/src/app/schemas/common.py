"""Generic API response wrapper."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Meta(BaseModel):
    request_id: str = Field(default="")
    cached: bool = False


class ErrorInfo(BaseModel):
    code: str
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorInfo | None = None
    meta: Meta = Field(default_factory=Meta)

    @classmethod
    def ok(cls, data: T, request_id: str = "", cached: bool = False) -> ApiResponse[T]:
        return cls(success=True, data=data, error=None, meta=Meta(request_id=request_id, cached=cached))

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        detail: dict[str, Any] | None = None,
        request_id: str = "",
        cached: bool = False,
    ) -> ApiResponse:
        return cls(
            success=False,
            data=None,
            error=ErrorInfo(code=code, message=message, detail=detail or {}),
            meta=Meta(request_id=request_id, cached=cached),
        )
