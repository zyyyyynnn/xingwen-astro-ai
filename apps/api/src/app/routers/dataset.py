"""Dataset endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.dataset import DatasetResponse
from app.services import task_service

router = APIRouter(tags=["dataset"])


@router.get("/api/v1/tasks/{task_id}/dataset", response_model=ApiResponse[DatasetResponse])
async def get_dataset(task_id: str, request: Request):
    return ok(request, task_service.get_dataset(task_id))
