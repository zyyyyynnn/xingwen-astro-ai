"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "research_assistant": {
            "status": "ready" if settings.research_assistant_ready else "unconfigured",
            "provider": "qwen",
            "requested_model": settings.DASHSCOPE_MODEL,
            "explicit_revision": settings.DASHSCOPE_EXPLICIT_MODEL_REVISION,
        },
    }
