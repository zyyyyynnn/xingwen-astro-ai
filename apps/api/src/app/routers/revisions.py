"""HTTP transport for immutable Feedback and revision orchestration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Path, Request, Response, status

from app.schemas.core import Envelope, ResearchRun, ResponseLinks, ResponseMeta
from app.schemas.revision import (
    ConfirmRevisionPlanRequest,
    CreateRevisionPlanRequest,
    CreateUserFeedbackRequest,
    RevisionPlan,
    UserFeedback,
)
from app.security import SecurityProblem
from app.services.research import ResearchApplicationService
from app.services.revisions import RevisionApplicationService

router = APIRouter(prefix="/api", tags=["revisions"])


def _service(request: Request) -> RevisionApplicationService:
    service = request.app.state.revision_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="REVISION_RUNTIME_UNAVAILABLE",
            title="Revision runtime unavailable",
            detail="The persistent revision runtime is not configured",
        )
    return service


def _research_service(request: Request) -> ResearchApplicationService:
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


def _consume_rate_limit(request: Request, response: Response) -> None:
    limiter = request.app.state.revision_rate_limiter
    remaining, reset_seconds = limiter.consume(_session_id(request))
    response.headers["RateLimit-Limit"] = str(limiter.limit)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(reset_seconds)


@router.post(
    "/artifact-versions/{version_id}/feedback",
    operation_id="createUserFeedback",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[UserFeedback],
)
async def create_user_feedback(
    version_id: Annotated[str, Path(min_length=1)],
    payload: CreateUserFeedbackRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[UserFeedback]:
    _ = csrf_token
    _consume_rate_limit(request, response)
    data = await _service(request).create_feedback(
        version_id=version_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/feedback/{data.id}"
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/feedback/{data.id}"),
    )


@router.get(
    "/feedback/{feedback_id}",
    operation_id="getUserFeedback",
    response_model=Envelope[UserFeedback],
)
def get_user_feedback(
    feedback_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[UserFeedback]:
    data = _service(request).get_feedback(
        feedback_id=feedback_id, session_id=_session_id(request)
    )
    _no_store(response)
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/feedback/{feedback_id}"),
    )


@router.post(
    "/projects/{project_id}/revision-plans",
    operation_id="createRevisionPlan",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[RevisionPlan],
)
def create_revision_plan(
    project_id: Annotated[str, Path(min_length=1)],
    payload: CreateRevisionPlanRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[RevisionPlan]:
    _ = csrf_token
    _consume_rate_limit(request, response)
    data = _service(request).create_plan(
        project_id=project_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/revision-plans/{data.id}"
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/revision-plans/{data.id}"),
    )


@router.get(
    "/revision-plans/{plan_id}",
    operation_id="getRevisionPlan",
    response_model=Envelope[RevisionPlan],
)
def get_revision_plan(
    plan_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[RevisionPlan]:
    data = _service(request).get_plan(plan_id=plan_id, session_id=_session_id(request))
    _no_store(response)
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/revision-plans/{plan_id}"),
    )


@router.post(
    "/revision-plans/{plan_id}/confirm",
    operation_id="confirmRevisionPlan",
    status_code=status.HTTP_201_CREATED,
    response_model=Envelope[ResearchRun],
)
def confirm_revision_plan(
    plan_id: Annotated[str, Path(min_length=1)],
    payload: ConfirmRevisionPlanRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[ResearchRun]:
    _ = csrf_token
    _consume_rate_limit(request, response)
    run_id = _service(request).confirm_plan(
        plan_id=plan_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        request=payload,
    )
    data = _research_service(request).get_run(
        run_id=str(run_id), session_id=_session_id(request)
    )
    _no_store(response)
    response.headers["Location"] = f"/api/runs/{run_id}"
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/runs/{run_id}"),
    )


__all__ = ["router"]
