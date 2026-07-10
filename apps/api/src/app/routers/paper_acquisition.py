"""Paper acquisition endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.paper import PaperAcquisitionResponse
from app.services import task_service

router = APIRouter(tags=["paper-acquisition"])


@router.get("/api/v1/tasks/{task_id}/paper-acquisition", response_model=ApiResponse[PaperAcquisitionResponse])
async def get_paper_acquisition(task_id: str, request: Request):
    return ok(request, task_service.get_paper_acquisition(task_id))
