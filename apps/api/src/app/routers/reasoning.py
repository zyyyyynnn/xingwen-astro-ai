"""Literature reasoning endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.reasoning import LiteratureReasoningResponse
from app.services import task_service

router = APIRouter(tags=["reasoning"])


@router.get("/api/v1/tasks/{task_id}/literature-reasoning", response_model=ApiResponse[LiteratureReasoningResponse])
async def get_literature_reasoning(task_id: str, request: Request):
    return ok(request, task_service.get_literature_reasoning(task_id))
