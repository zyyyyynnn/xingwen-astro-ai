"""Runtime transport for generic Artifact provenance reads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response

from app.schemas.v2 import (
    ArtifactKind,
    ArtifactVersionDetail,
    CollectionEnvelope,
    CursorPage,
    Envelope,
    EvidenceRead,
    ResearchArtifact,
    ResearchArtifactDetail,
    ResponseLinks,
    ResponseMeta,
    SourceSnapshotDetail,
)
from app.schemas.paper_collection_api import (
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from app.schemas.paper_summary_api import PaperSummaryRead
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.paper_collections import PaperCollectionReadService
from app.services.paper_summaries import PaperSummaryReadService


router = APIRouter(prefix="/api/v2", tags=["v2-artifacts"])


def _service(request: Request) -> ArtifactReadService:
    service = request.app.state.artifact_read_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="ARTIFACT_READ_UNAVAILABLE",
            title="Artifact read unavailable",
            detail="The persistent Artifact read adapter is not configured",
        )
    return service


def _session_id(request: Request) -> str:
    return request.state.session.id


def _paper_service(request: Request) -> PaperCollectionReadService:
    return PaperCollectionReadService(_service(request))


def _summary_service(request: Request) -> PaperSummaryReadService:
    return PaperSummaryReadService(_service(request))


def _meta(request: Request) -> ResponseMeta:
    return ResponseMeta(
        request_id=request.state.request_id, generated_at=datetime.now(UTC)
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.get(
    "/runs/{run_id}/artifacts",
    operation_id="listRunArtifacts",
    response_model=CollectionEnvelope[ResearchArtifact],
)
def list_run_artifacts(
    run_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    kind: Annotated[ArtifactKind | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ResearchArtifact]:
    artifacts, next_cursor, has_more = _service(request).list_run_artifacts(
        run_id=run_id,
        session_id=_session_id(request),
        kind=kind.value if kind is not None else None,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/v2/runs/{run_id}/artifacts"
    return CollectionEnvelope(
        data=artifacts,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifacts/{artifact_id}",
    operation_id="getResearchArtifact",
    response_model=Envelope[ResearchArtifactDetail],
)
def get_research_artifact(
    artifact_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ResearchArtifactDetail]:
    data = _service(request).get_artifact(
        artifact_id=artifact_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/artifacts/{artifact_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}",
    operation_id="getArtifactVersion",
    response_model=Envelope[ArtifactVersionDetail],
)
def get_artifact_version(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ArtifactVersionDetail]:
    data = _service(request).get_version(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/artifact-versions/{version_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/paper-collection",
    operation_id="getPaperCollection",
    response_model=Envelope[PaperCollectionRead],
)
def get_paper_collection(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[PaperCollectionRead]:
    data = _paper_service(request).get_collection(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/artifact-versions/{version_id}/paper-collection"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/paper-summary",
    operation_id="getPaperSummary",
    response_model=Envelope[PaperSummaryRead],
)
def get_paper_summary(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[PaperSummaryRead]:
    data = _summary_service(request).get_summary(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/artifact-versions/{version_id}/paper-summary"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/paper-candidates",
    operation_id="listPaperCollectionCandidates",
    response_model=CollectionEnvelope[PaperCollectionCandidateRead],
)
def list_paper_collection_candidates(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[PaperCollectionCandidateRead]:
    candidates, next_cursor, has_more = _paper_service(request).list_candidates(
        version_id=version_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/v2/artifact-versions/{version_id}/paper-candidates"
    return CollectionEnvelope(
        data=candidates,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/evidence/{evidence_id}",
    operation_id="getEvidence",
    response_model=Envelope[EvidenceRead],
)
def get_evidence(
    evidence_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[EvidenceRead]:
    data = _service(request).get_evidence(
        evidence_id=evidence_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/evidence/{evidence_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/source-snapshots/{snapshot_id}",
    operation_id="getSourceSnapshot",
    response_model=Envelope[SourceSnapshotDetail],
)
def get_source_snapshot(
    snapshot_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[SourceSnapshotDetail]:
    data = _service(request).get_source_snapshot(
        snapshot_id=snapshot_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/v2/source-snapshots/{snapshot_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))
