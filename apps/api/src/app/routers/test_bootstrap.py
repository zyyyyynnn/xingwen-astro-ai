"""Test-only bootstrap router.

Mounted by ``app.main.create_app`` only when ``APP_ENV`` is ``test`` or
``integration``. The endpoint (``POST /api/test/bootstrap``) is absent in
``development`` and ``production`` builds, so it can never drift the frozen
/generated contract (the export and parity checks run without it). Because it
lives under ``/api``, the standard security middleware enforces the same
session cookie + CSRF rules as every other private endpoint — ownership
checks are never bypassed, and no credential is ever returned or logged.

Since #131 the bootstrap no longer injects Project, ContractDraft, Contract,
Run, credentials or Share tokens: the browser main chain creates those through
the public Authoring Chain. The bootstrap only publishes the frozen main
case's deterministic ``demo_replay``/``fixture`` ArtifactVersion + Evidence
onto a session-owned Run via the real Persistence/Publisher boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.security import SecurityProblem
from app.test_support.bootstrap import BootstrapResult, bootstrap_fixture_artifacts

router = APIRouter(prefix="/api/test", tags=["test-only"])


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
    run_id: str = Query(
        min_length=1,
        description="Session-owned demo_replay run the fixture is published onto",
    ),
) -> BootstrapResponse:
    record = request.state.session

    factory = getattr(request.app.state, "db_session_factory", None)
    research_service = request.app.state.research_service
    workflow_store = request.app.state.workflow_store
    if factory is None or research_service is None or workflow_store is None:
        raise _persistent_runtime_unavailable()

    result = bootstrap_fixture_artifacts(
        session_id=record.id,
        run_id=run_id,
        factory=factory,
        research_service=research_service,
        workflow_store=workflow_store,
    )
    return BootstrapResponse(data=result)
