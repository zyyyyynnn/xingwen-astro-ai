"""Test-only bootstrap router.

Mounted by ``app.main.create_app`` only when ``APP_ENV`` is ``test`` or
``integration``. The endpoint (``POST /api/test/bootstrap``) is absent in
``development`` and ``production`` builds, so it can never drift the frozen
/generated contract (the export and parity checks run without it). Because it
lives under ``/api``, the standard security middleware enforces the same
session cookie + CSRF rules as every other private endpoint — ownership
checks are never bypassed, and no credential is ever returned or logged.

The bootstrap does not inject Project, ContractDraft, Contract,
Run, credentials or Share tokens: the browser main chain creates those through
the public Authoring Chain. The bootstrap only publishes the frozen main
case's deterministic ``demo_replay``/``fixture`` ArtifactVersion + Evidence
onto a session-owned Run via the real Persistence/Publisher boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.security import SecurityProblem
from app.test_support.bootstrap import (
    BootstrapResult,
    UnsupportedExportBootstrapResult,
    bootstrap_fixture_artifacts,
    bootstrap_unsupported_export_artifact,
)
from app.test_support.integration_research import (
    ResearchResultsBootstrapResult,
    bootstrap_fixture_research_results,
)

router = APIRouter(prefix="/api/test", tags=["test-only"])


class BootstrapResponse(BaseModel):
    data: BootstrapResult


class ResearchResultsBootstrapResponse(BaseModel):
    data: ResearchResultsBootstrapResult


class UnsupportedExportBootstrapResponse(BaseModel):
    data: UnsupportedExportBootstrapResult


def _persistent_runtime_unavailable() -> SecurityProblem:
    return SecurityProblem(
        status=503,
        code="BOOTSTRAP_UNAVAILABLE",
        title="Bootstrap unavailable",
        detail=(
            "The test-only bootstrap requires the configured PostgreSQL runtime "
            "(DATABASE_URL)"
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


@router.post(
    "/bootstrap/research-results",
    response_model=ResearchResultsBootstrapResponse,
    status_code=201,
)
def create_research_results_bootstrap(
    request: Request,
    run_id: str = Query(
        min_length=1,
        description="Session-owned demo_replay run executed by the fixture runtime",
    ),
) -> ResearchResultsBootstrapResponse:
    record = request.state.session
    factory = getattr(request.app.state, "db_session_factory", None)
    research_service = request.app.state.research_service
    workflow_store = request.app.state.workflow_store
    if factory is None or research_service is None or workflow_store is None:
        raise _persistent_runtime_unavailable()
    result = bootstrap_fixture_research_results(
        session_id=record.id,
        run_id=run_id,
        factory=factory,
        research_service=research_service,
        workflow_store=workflow_store,
    )
    return ResearchResultsBootstrapResponse(data=result)


@router.post(
    "/bootstrap/unsupported-export",
    response_model=UnsupportedExportBootstrapResponse,
    status_code=201,
)
def create_unsupported_export_bootstrap(
    request: Request,
    run_id: str = Query(min_length=1),
    source_version_id: str = Query(min_length=1),
) -> UnsupportedExportBootstrapResponse:
    record = request.state.session
    factory = getattr(request.app.state, "db_session_factory", None)
    research_service = request.app.state.research_service
    workflow_store = request.app.state.workflow_store
    if factory is None or research_service is None or workflow_store is None:
        raise _persistent_runtime_unavailable()
    result = bootstrap_unsupported_export_artifact(
        session_id=record.id,
        run_id=run_id,
        source_version_id=source_version_id,
        factory=factory,
        research_service=research_service,
        workflow_store=workflow_store,
    )
    return UnsupportedExportBootstrapResponse(data=result)
