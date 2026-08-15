"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings

router = APIRouter(tags=["system"])


@router.get("/api/health")
def health(request: Request) -> dict[str, object]:
    worker = getattr(request.app.state, "research_run_worker", None)
    worker_status: dict[str, object]
    if worker is None:
        worker_status = {"status": "unavailable"}
    else:
        try:
            snapshot = worker.health_snapshot()
        except RuntimeError:
            worker_status = {"status": "starting", "worker_id": worker.worker_id}
        except SQLAlchemyError:
            worker_status = {
                "status": "unavailable",
                "worker_id": worker.worker_id,
            }
        else:
            worker_status = {
                "status": snapshot.state,
                "worker_id": snapshot.worker_id,
                "configured_capacity": snapshot.configured_capacity,
                "active_run_count": snapshot.active_run_count,
                "heartbeat_at": snapshot.heartbeat_at.isoformat(),
                "drain_requested_at": (
                    snapshot.drain_requested_at.isoformat()
                    if snapshot.drain_requested_at is not None
                    else None
                ),
            }
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "workflow_worker": worker_status,
        "research_assistant": {
            "status": (
                "configured" if settings.research_assistant_ready else "unconfigured"
            ),
            "provider": "qwen",
            "model": settings.DASHSCOPE_MODEL,
            "model_revision": settings.DASHSCOPE_MODEL_REVISION,
        },
    }
