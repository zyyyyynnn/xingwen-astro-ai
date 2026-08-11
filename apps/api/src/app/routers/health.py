"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.APP_ENV}
