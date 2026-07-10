"""Application errors mapped to API_CONTRACT.md error codes."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}


def task_not_found(task_id: str) -> ApiError:
    return ApiError(
        code="TASK_NOT_FOUND",
        message="Task not found",
        status_code=404,
        detail={"task_id": task_id},
    )


def task_not_ready(task_id: str, status: str) -> ApiError:
    return ApiError(
        code="TASK_NOT_READY",
        message="Task result is not ready",
        status_code=409,
        detail={"task_id": task_id, "status": status},
    )
