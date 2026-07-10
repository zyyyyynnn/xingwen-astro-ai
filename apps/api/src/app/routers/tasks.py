"""Task lifecycle endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.task import TaskCreateRequest, TaskCreateResponse, TaskStatusResponse
from app.services import task_service

router = APIRouter(tags=["tasks"])


@router.post("/api/v1/tasks", response_model=ApiResponse[TaskCreateResponse])
async def create_task(req: TaskCreateRequest, request: Request):
    return ok(request, task_service.create_task(req))


@router.get("/api/v1/tasks/{task_id}", response_model=ApiResponse[TaskStatusResponse])
async def get_task(task_id: str, request: Request):
    data = task_service.get_task(task_id)
    return ok(request, data, cached=data.used_cache)
