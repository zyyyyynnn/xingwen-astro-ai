"""Paper summary endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.paper import PapersResponse
from app.services import task_service

router = APIRouter(tags=["papers"])


@router.get("/api/v1/tasks/{task_id}/papers", response_model=ApiResponse[PapersResponse])
async def get_papers(task_id: str, request: Request):
    return ok(request, task_service.get_papers(task_id))
