"""Source records endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.source import SourcesResponse
from app.services import task_service

router = APIRouter(tags=["sources"])


@router.get("/api/v1/tasks/{task_id}/sources", response_model=ApiResponse[SourcesResponse])
async def get_sources(task_id: str, request: Request):
    return ok(request, task_service.get_sources(task_id))
