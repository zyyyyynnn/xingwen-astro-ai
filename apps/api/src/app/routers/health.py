"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter(tags=["system"])


@router.get("/api/health")
async def health(request: Request) -> dict[str, object]:
    service = request.app.state.model_provider_configuration_service
    configuration = service.status() if service is not None else None
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "research_assistant": {
            "status": (
                configuration.status
                if configuration is not None
                else "ready"
                if settings.research_assistant_ready
                else "unconfigured"
            ),
            "provider": (
                configuration.preset.value
                if configuration is not None and configuration.preset is not None
                else "qwen"
            ),
            "requested_model": (
                configuration.model
                if configuration is not None and configuration.model is not None
                else settings.DASHSCOPE_MODEL
            ),
            "explicit_revision": settings.DASHSCOPE_EXPLICIT_MODEL_REVISION,
        },
    }
