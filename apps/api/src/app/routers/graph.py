"""Graph endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.graph import GraphResponse
from app.services import task_service

router = APIRouter(tags=["graph"])


@router.get("/api/v1/tasks/{task_id}/graph", response_model=ApiResponse[GraphResponse])
async def get_graph(task_id: str, request: Request):
    return ok(request, task_service.get_graph(task_id))
