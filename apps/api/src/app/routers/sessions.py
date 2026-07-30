"""Anonymous v2 session transport; security logic remains in application services."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.config import settings
from app.schemas.core import (
    Envelope,
    ResearchSession,
    ResponseLinks,
    ResponseMeta,
    SessionCreated,
)
from app.security import SessionRecord, SessionService


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _service(request: Request) -> SessionService:
    return request.app.state.session_service


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _public(record: SessionRecord) -> ResearchSession:
    return ResearchSession(
        status=record.status,
        created_at=record.created_at,
        expires_at=record.expires_at,
        quota=record.quota,
    )


@router.post(
    "", operation_id="createAnonymousSession", status_code=status.HTTP_201_CREATED
)
def create_session(request: Request, response: Response) -> Envelope[SessionCreated]:
    client_key = request.client.host if request.client is not None else "unknown"
    remaining, reset_seconds = request.app.state.session_rate_limiter.consume(
        client_key
    )

    # Resume an existing valid session (browser refresh recovery) instead of
    # spawning a parallel one: same cookie credential, freshly rotated CSRF.
    existing_credential = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if existing_credential:
        resumed = _service(request).resume(existing_credential)
        if resumed is not None:
            record, csrf_token = resumed
            response.headers["Location"] = "/api/sessions/current"
            response.headers["RateLimit-Limit"] = str(
                settings.SESSION_CREATE_RATE_LIMIT
            )
            response.headers["RateLimit-Remaining"] = str(remaining)
            response.headers["RateLimit-Reset"] = str(reset_seconds)
            response.headers["Cache-Control"] = "no-store"
            return Envelope(
                data=SessionCreated(
                    **_public(record).model_dump(), csrf_token=csrf_token
                ),
                meta=_meta(request),
                links=ResponseLinks(self="/api/sessions/current"),
            )

    record, credential, csrf_token = _service(request).create()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=credential,
        max_age=settings.SESSION_TTL_SECONDS,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        path="/api",
    )
    response.headers["Location"] = "/api/sessions/current"
    response.headers["RateLimit-Limit"] = str(settings.SESSION_CREATE_RATE_LIMIT)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(reset_seconds)
    response.headers["Cache-Control"] = "no-store"
    return Envelope(
        data=SessionCreated(**_public(record).model_dump(), csrf_token=csrf_token),
        meta=_meta(request),
        links=ResponseLinks(self="/api/sessions/current"),
    )


@router.get("/current", operation_id="getAnonymousSession")
def get_session(request: Request, response: Response) -> Envelope[ResearchSession]:
    record: SessionRecord = request.state.session
    response.headers["Cache-Control"] = "no-store"
    return Envelope(
        data=_public(record),
        meta=_meta(request),
        links=ResponseLinks(self="/api/sessions/current"),
    )


@router.delete(
    "/current",
    operation_id="revokeAnonymousSession",
    status_code=204,
    response_class=Response,
)
def revoke_session(
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> None:
    _ = csrf_token
    credential = request.cookies[settings.SESSION_COOKIE_NAME]
    _service(request).revoke(credential)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/api")
    response.headers["Cache-Control"] = "no-store"
