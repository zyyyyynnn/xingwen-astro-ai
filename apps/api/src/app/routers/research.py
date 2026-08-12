"""Runtime transport for the minimal ``/api`` research chain.

Project, ContractDraft, Contract, Run and RunEvent transport. Business logic
and persistence live in :class:`ResearchApplicationService`; this router only
maps HTTP to that boundary and matches the generated contract surface.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request, Response, status

from app.schemas.core import (
    CollectionEnvelope,
    ConfirmResearchContractRequest,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    CursorPage,
    Envelope,
    ModelExecutionRecord,
    ResearchContract,
    ResearchContractDraft,
    ResearchProject,
    ResearchPlanningCatalog,
    ResearchRun,
    ResearchThreadEntry,
    ResearchTurnRequest,
    ResearchTurnResult,
    ResponseLinks,
    ResponseMeta,
    RunEvent,
    RunStepRead,
    UpdateResearchProjectRequest,
    UpdateResearchContractDraftRequest,
)
from app.security import SecurityProblem
from app.services.research import ResearchApplicationService


router = APIRouter(prefix="/api", tags=["research"])


def _service(request: Request) -> ResearchApplicationService:
    service = request.app.state.research_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="RESEARCH_RUNTIME_UNAVAILABLE",
            title="Research runtime unavailable",
            detail="The persistent research runtime is not configured",
        )
    return service


def _session_id(request: Request) -> str:
    return request.state.session.id


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/projects",
    operation_id="listResearchProjects",
    response_model=CollectionEnvelope[ResearchProject],
)
def list_research_projects(
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ResearchProject]:
    projects, next_cursor, has_more = _service(request).list_projects(
        session_id=_session_id(request), cursor=cursor, limit=limit
    )
    _no_store(response)
    path = "/api/projects"
    return CollectionEnvelope(
        data=projects,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.post(
    "/projects",
    operation_id="createResearchProject",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchProject],
)
def create_research_project(
    payload: CreateResearchProjectRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> Envelope[ResearchProject]:
    data = _service(request).create_project(
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/projects/{data.id}"
    path = f"/api/projects/{data.id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/projects/{project_id}",
    operation_id="getResearchProject",
    response_model=Envelope[ResearchProject],
)
def get_research_project(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchProject]:
    data = _service(request).get_project(
        project_id=project_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/projects/{project_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/projects/{project_id}/research-catalog",
    operation_id="getResearchPlanningCatalog",
    response_model=Envelope[ResearchPlanningCatalog],
)
def get_research_planning_catalog(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchPlanningCatalog]:
    data = _service(request).get_research_catalog(
        project_id=project_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/projects/{project_id}/research-catalog"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.patch(
    "/projects/{project_id}",
    operation_id="updateResearchProject",
    response_model=Envelope[ResearchProject],
)
def update_research_project(
    project_id: Annotated[str, Path(min_length=1)],
    payload: UpdateResearchProjectRequest,
    request: Request,
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
) -> Envelope[ResearchProject]:
    data = _service(request).update_project(
        project_id=project_id,
        session_id=_session_id(request),
        if_match=if_match,
        request=payload,
    )
    _no_store(response)
    response.headers["ETag"] = str(data.revision)
    path = f"/api/projects/{project_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.delete(
    "/projects/{project_id}",
    operation_id="deleteResearchProject",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_research_project(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
) -> None:
    _service(request).delete_project(
        project_id=project_id,
        session_id=_session_id(request),
        if_match=if_match,
    )
    _no_store(response)


@router.get(
    "/projects/{project_id}/research-turns",
    operation_id="listResearchTurns",
    response_model=CollectionEnvelope[ResearchThreadEntry],
)
def list_research_turns(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ResearchThreadEntry]:
    entries, next_cursor, has_more = _service(request).list_thread_entries(
        project_id=project_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/projects/{project_id}/research-turns"
    return CollectionEnvelope(
        data=entries,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.post(
    "/projects/{project_id}/research-turns",
    operation_id="submitResearchTurn",
    response_model=Envelope[ResearchTurnResult],
)
def submit_research_turn(
    project_id: Annotated[str, Path(min_length=1)],
    payload: ResearchTurnRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> Envelope[ResearchTurnResult]:
    data = _service(request).submit_research_turn(
        project_id=project_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    path = f"/api/projects/{project_id}/research-turns"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.post(
    "/projects/{project_id}/contract-drafts",
    operation_id="createResearchContractDraft",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchContractDraft],
)
def create_research_contract_draft(
    project_id: Annotated[str, Path(min_length=1)],
    payload: CreateResearchContractDraftRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> Envelope[ResearchContractDraft]:
    data = _service(request).create_draft(
        project_id=project_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/contracts/drafts/{data.id}"
    response.headers["ETag"] = str(data.version)
    path = f"/api/contracts/drafts/{data.id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/contracts/drafts/{draft_id}",
    operation_id="getResearchContractDraft",
    response_model=Envelope[ResearchContractDraft],
)
def get_research_contract_draft(
    draft_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchContractDraft]:
    data = _service(request).get_draft(
        draft_id=draft_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/contracts/drafts/{draft_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.patch(
    "/contracts/drafts/{draft_id}",
    operation_id="updateResearchContractDraft",
    response_model=Envelope[ResearchContractDraft],
)
def update_research_contract_draft(
    draft_id: Annotated[str, Path(min_length=1)],
    payload: UpdateResearchContractDraftRequest,
    request: Request,
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
) -> Envelope[ResearchContractDraft]:
    data = _service(request).update_draft(
        draft_id=draft_id,
        session_id=_session_id(request),
        if_match=if_match,
        request=payload,
    )
    _no_store(response)
    response.headers["ETag"] = str(data.version)
    path = f"/api/contracts/drafts/{draft_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/contracts/{contract_id}",
    operation_id="getResearchContract",
    response_model=Envelope[ResearchContract],
)
def get_research_contract(
    contract_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchContract]:
    data = _service(request).get_contract(
        contract_id=contract_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/contracts/{contract_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.post(
    "/projects/{project_id}/contracts",
    operation_id="confirmResearchContract",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchContract],
)
def confirm_research_contract(
    project_id: Annotated[str, Path(min_length=1)],
    payload: ConfirmResearchContractRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> Envelope[ResearchContract]:
    data = _service(request).confirm_contract(
        project_id=project_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/contracts/{data.id}"
    path = f"/api/contracts/{data.id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/projects/{project_id}/model-executions/{execution_id}",
    operation_id="getModelExecution",
    response_model=Envelope[ModelExecutionRecord],
)
def get_model_execution(
    project_id: Annotated[str, Path(min_length=1)],
    execution_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ModelExecutionRecord]:
    data = _service(request).get_model_execution(
        project_id=project_id,
        execution_id=execution_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/projects/{project_id}/model-executions/{execution_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/runs/{run_id}",
    operation_id="getResearchRun",
    response_model=Envelope[ResearchRun],
)
def get_research_run(
    run_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchRun]:
    data = _service(request).get_run(run_id=run_id, session_id=_session_id(request))
    _no_store(response)
    path = f"/api/runs/{run_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/runs/{run_id}/steps",
    operation_id="listRunSteps",
    response_model=CollectionEnvelope[RunStepRead],
)
def list_run_steps(
    run_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> CollectionEnvelope[RunStepRead]:
    steps = _service(request).list_run_steps(
        run_id=run_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/runs/{run_id}/steps"
    return CollectionEnvelope(
        data=steps,
        page=CursorPage(next_cursor=None, has_more=False, limit=max(1, len(steps))),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.post(
    "/projects/{project_id}/runs",
    operation_id="createResearchRun",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchRun],
)
def create_research_run(
    project_id: Annotated[str, Path(min_length=1)],
    payload: CreateRunRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
) -> Envelope[ResearchRun]:
    data = _service(request).create_run(
        project_id=project_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/runs/{data.id}"
    path = f"/api/runs/{data.id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/runs/{run_id}/events",
    operation_id="listRunEvents",
    response_model=CollectionEnvelope[RunEvent],
)
def list_run_events(
    run_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[RunEvent]:
    events, next_cursor, has_more = _service(request).list_run_events(
        run_id=run_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/runs/{run_id}/events"
    return CollectionEnvelope(
        data=events,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )
