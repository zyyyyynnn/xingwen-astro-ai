"""Test-only bootstrap router.

Mounted by ``app.main.create_app`` only when ``APP_ENV`` is ``test`` or
``integration``. The endpoint (``POST /api/v2/test/bootstrap``) is absent in
``development`` and ``production`` builds, so it can never drift the frozen
/generated contract (the export and parity checks run without it). Because it
lives under ``/api/v2``, the standard security middleware enforces the same
session cookie + CSRF rules as every other private endpoint — ownership
checks are never bypassed, and no credential is ever returned or logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.security import SecurityProblem
from app.test_support.bootstrap import BootstrapResult, bootstrap_demo_scenario

router = APIRouter(prefix="/api/v2/test", tags=["test-only"])


class BootstrapResponse(BaseModel):
    data: BootstrapResult


def _persistent_runtime_unavailable() -> SecurityProblem:
    return SecurityProblem(
        status=503,
        code="BOOTSTRAP_UNAVAILABLE",
        title="Bootstrap unavailable",
        detail=(
            "The test-only bootstrap requires the persistent runtime "
            "(DATABASE_URL and PERSISTENT_WORKFLOW_ENABLED=true)"
        ),
    )


@router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
def create_bootstrap(
    request: Request,
    complete: bool = Query(
        default=True,
        description="False seeds only the editable Project/Draft browser starting point",
    ),
) -> BootstrapResponse:
    record = request.state.session

    factory = getattr(request.app.state, "db_session_factory", None)
    research_service = request.app.state.research_service
    workflow_store = request.app.state.workflow_store
    if factory is None or research_service is None or workflow_store is None:
        raise _persistent_runtime_unavailable()

    result = bootstrap_demo_scenario(
        session_id=record.id,
        factory=factory,
        research_service=research_service,
        workflow_store=workflow_store,
        complete=complete,
    )
    return BootstrapResponse(data=result)
