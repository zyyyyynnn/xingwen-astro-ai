"""Runtime transport for private workspace recovery and immutable public shares."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request, Response, status

from app.schemas.core import (
    CollectionEnvelope,
    CreateShareSnapshotRequest,
    CursorPage,
    Envelope,
    PublicShareSnapshot,
    ResponseLinks,
    ResponseMeta,
    ShareSnapshot,
    ShareSnapshotCreated,
    WorkspaceSnapshot,
    WorkspaceSnapshotInput,
)
from app.security import SecurityProblem
from app.services.snapshots import SnapshotService


router = APIRouter(prefix="/api", tags=["snapshots"])


def _service(request: Request) -> SnapshotService:
    service = request.app.state.snapshot_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="SNAPSHOT_RUNTIME_UNAVAILABLE",
            title="Snapshot runtime unavailable",
            detail="The persistent snapshot runtime is not configured",
        )
    return service


def _session_id(request: Request) -> str:
    return request.state.session.id


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _private_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/projects/{project_id}/workspace-snapshot",
    operation_id="getWorkspaceSnapshot",
)
def get_workspace_snapshot(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[WorkspaceSnapshot]:
    snapshot = _service(request).get_workspace(
        project_id=project_id,
        session_id=_session_id(request),
    )
    _private_no_store(response)
    return Envelope(
        data=snapshot,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/projects/{project_id}/workspace-snapshot"),
    )


@router.put(
    "/projects/{project_id}/workspace-snapshot",
    operation_id="putWorkspaceSnapshot",
)
def put_workspace_snapshot(
    project_id: Annotated[str, Path(min_length=1)],
    payload: WorkspaceSnapshotInput,
    request: Request,
    response: Response,
    expected_revision: Annotated[int, Header(alias="If-Match", ge=0)],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[WorkspaceSnapshot]:
    _ = csrf_token
    snapshot = _service(request).save_workspace(
        project_id=project_id,
        session_id=_session_id(request),
        expected_revision=expected_revision,
        payload=payload,
    )
    _private_no_store(response)
    response.headers["ETag"] = str(snapshot.revision)
    return Envelope(
        data=snapshot,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/projects/{project_id}/workspace-snapshot"),
    )


@router.get(
    "/projects/{project_id}/shares",
    operation_id="listShareSnapshots",
)
def list_share_snapshots(
    project_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ShareSnapshot]:
    shares, next_cursor, has_more = _service(request).list_shares(
        project_id=project_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _private_no_store(response)
    return CollectionEnvelope(
        data=shares,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/projects/{project_id}/shares"),
    )


@router.post(
    "/projects/{project_id}/shares",
    operation_id="createShareSnapshot",
    status_code=status.HTTP_201_CREATED,
)
def create_share_snapshot(
    project_id: Annotated[str, Path(min_length=1)],
    payload: CreateShareSnapshotRequest,
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[ShareSnapshotCreated]:
    _ = csrf_token
    limiter = request.app.state.share_rate_limiter
    remaining, reset_seconds = limiter.consume(_session_id(request))
    share = _service(request).create_share(
        project_id=project_id,
        session_id=_session_id(request),
        request=payload,
    )
    _private_no_store(response)
    response.headers["Location"] = f"/api/projects/{project_id}/shares/{share.id}"
    response.headers["RateLimit-Limit"] = str(limiter.limit)
    response.headers["RateLimit-Remaining"] = str(remaining)
    response.headers["RateLimit-Reset"] = str(reset_seconds)
    return Envelope(
        data=share,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/projects/{project_id}/shares"),
    )


@router.delete(
    "/projects/{project_id}/shares/{share_id}",
    operation_id="revokeShareSnapshot",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def revoke_share_snapshot(
    project_id: Annotated[str, Path(min_length=1)],
    share_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> None:
    _ = csrf_token
    _service(request).revoke_share(
        project_id=project_id,
        share_id=share_id,
        session_id=_session_id(request),
    )
    _private_no_store(response)


@router.get(
    "/public/shares/{share_token}",
    operation_id="getPublicShareSnapshot",
)
def get_public_share_snapshot(
    share_token: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[PublicShareSnapshot]:
    projection = _service(request).get_public_share(raw_token=share_token)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return Envelope(
        data=projection,
        meta=_meta(request),
        links=ResponseLinks(self="/api/public/shares/public"),
    )
