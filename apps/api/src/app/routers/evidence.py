"""Evidence detail endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.routers.utils import ok
from app.schemas.common import ApiResponse
from app.schemas.evidence import EvidenceResponse
from app.services import task_service

router = APIRouter(tags=["evidence"])


@router.get("/api/tasks/{task_id}/evidence/{evidence_id}", response_model=ApiResponse[EvidenceResponse])
async def get_evidence(task_id: str, evidence_id: str, request: Request):
    return ok(request, task_service.get_evidence(task_id, evidence_id))
