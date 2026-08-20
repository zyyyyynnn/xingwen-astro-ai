"""Runtime transport for generic Artifact provenance reads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Header, Path, Query, Request, Response
from fastapi.responses import Response as RawResponse
from fastapi.responses import StreamingResponse

from app.schemas.core import (
    ArtifactKind,
    ArtifactVersionDetail,
    ArtifactVersionSummary,
    CollectionEnvelope,
    CursorPage,
    Envelope,
    EvidenceRead,
    ProblemDetails,
    ResearchArtifact,
    ResearchArtifactDetail,
    ResponseLinks,
    ResponseMeta,
    SourceSnapshotDetail,
)
from app.schemas.data_artifact_api import (
    ArtifactExportRead,
    CreateArtifactExportRequest,
    DataArtifactRowRead,
    DatasetArtifactRead,
    FieldDictionaryArtifactRead,
    SourceCollectionArtifactRead,
)
from app.schemas.enums import GraphEdgeType, GraphNodeType
from app.schemas.research_input import ResearchInputType
from app.schemas.scientific_document import SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES
from app.schemas.graph_artifact_api import (
    GraphArtifactRead,
    GraphEdgeRead,
    GraphNodeRead,
)
from app.schemas.literature_artifact_api import (
    LiteratureClaimRead,
    LiteratureReasoningTraceRead,
    LiteratureRelationRead,
)
from app.schemas.literature_claim import LiteratureClaimStatus
from app.schemas.literature_relation import LiteratureRelationStatus
from app.schemas.paper_collection_api import (
    CreatePaperCandidateInputRequest,
    OpenAccessPaperCandidateInputRequest,
    PaperCandidateInputBinding,
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from app.schemas.paper_summary_api import (
    PaperSummaryDocumentSourceRead,
    PaperSummaryRead,
)
from app.services.paper_summary_exports import PaperSummaryExportService
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.content_storage import ContentRangeNotSatisfiable
from app.services.data_artifacts import DataArtifactReadService
from app.services.graph_artifacts import GraphArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService
from app.services.paper_collections import PaperCollectionReadService
from app.services.paper_candidate_inputs import (
    CreatePaperCandidateInputCommand,
    PaperCandidateInputService,
)
from app.services.paper_summaries import (
    DocumentSourceResolver,
    PaperSummaryReadService,
)
from app.services.research_input_store import (
    ResearchInputRecord,
    ResearchInputRepository,
)
from app.services.scientific_artifacts import ScientificArtifactReadService

router = APIRouter(prefix="/api", tags=["artifacts"])


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


def _paper_input_service(request: Request) -> PaperCandidateInputService:
    service = request.app.state.paper_candidate_input_service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="PAPER_CANDIDATE_INPUT_RUNTIME_UNAVAILABLE",
            title="Paper candidate input runtime unavailable",
            detail="The persistent PaperCandidate input bridge is not configured",
        )
    return service


def _summary_service(request: Request) -> PaperSummaryReadService:
    pdf_source_resolver = None
    input_service = request.app.state.paper_candidate_input_service
    if input_service is not None:
        pdf_source_resolver = input_service.accepted_research_input
    research_input_resolver = None
    input_store = request.app.state.research_input_store
    if input_store is not None:
        research_input_resolver = _research_input_by_identity(input_store)
    return PaperSummaryReadService(
        _service(request),
        pdf_source_resolver=pdf_source_resolver,
        research_input_resolver=research_input_resolver,
    )


def _research_input_by_identity(
    store: ResearchInputRepository,
) -> DocumentSourceResolver:
    """Authorize a parsed PDF or document image by immutable input identity."""

    def resolve(
        *,
        session_id: str,
        project_id: str,
        research_input_id: str,
        input_content_hash: str,
    ) -> ResearchInputRecord | None:
        record = store.get(session_id=session_id, input_id=research_input_id)
        if (
            record is None
            or record.project_id != project_id
            or record.content_hash != input_content_hash
        ):
            return None
        if record.type is ResearchInputType.pdf:
            return record if record.mime_type == "application/pdf" else None
        if record.type is ResearchInputType.image:
            return (
                record
                if record.mime_type in SCIENTIFIC_DOCUMENT_IMAGE_MIME_TYPES
                else None
            )
        return None

    return resolve


def _scientific_service(request: Request) -> ScientificArtifactReadService:
    return ScientificArtifactReadService(
        _service(request), request.app.state.content_storage
    )


def _data_service(request: Request) -> DataArtifactReadService:
    service = request.app.state.data_artifact_read_service
    if service is None and request.app.state.artifact_read_service is not None:
        service = DataArtifactReadService(request.app.state.artifact_read_service)
        request.app.state.data_artifact_read_service = service
    if service is None:
        raise SecurityProblem(
            status=503,
            code="DATA_ARTIFACT_READ_UNAVAILABLE",
            title="Data artifact read unavailable",
            detail="The persistent data artifact read adapter is not configured",
        )
    return service


def _literature_service(request: Request) -> LiteratureArtifactReadService:
    return LiteratureArtifactReadService(_service(request))


def _graph_service(request: Request) -> GraphArtifactReadService:
    return GraphArtifactReadService(_service(request))


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
    path = f"/api/runs/{run_id}/artifacts"
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
    path = f"/api/artifacts/{artifact_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifacts/{artifact_id}/versions",
    operation_id="listArtifactVersions",
    response_model=CollectionEnvelope[ArtifactVersionSummary],
)
def list_artifact_versions(
    artifact_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[ArtifactVersionSummary]:
    versions, next_cursor, has_more = _service(request).list_artifact_versions(
        artifact_id=artifact_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifacts/{artifact_id}/versions"
    return CollectionEnvelope(
        data=versions,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


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
    path = f"/api/artifact-versions/{version_id}"
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
    path = f"/api/artifact-versions/{version_id}/paper-collection"
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
    path = f"/api/artifact-versions/{version_id}/paper-summary"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/paper-summary/document-source",
    operation_id="getPaperSummaryDocumentSource",
    response_model=Envelope[PaperSummaryDocumentSourceRead],
)
def get_paper_summary_document_source(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[PaperSummaryDocumentSourceRead]:
    data = _summary_service(request).get_document_source(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/paper-summary/document-source"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/paper-summary/export",
    operation_id="downloadPaperSummaryExport",
    response_class=RawResponse,
    response_model=None,
    responses={
        200: {
            "content": {
                "application/json": {"schema": {"type": "string", "format": "binary"}},
                "text/markdown": {"schema": {"type": "string", "format": "binary"}},
            }
        },
        400: {"model": ProblemDetails},
        401: {"model": ProblemDetails},
        403: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
        409: {"model": ProblemDetails},
        413: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
        429: {"model": ProblemDetails},
    },
)
def download_paper_summary_export(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    export_format: Annotated[
        Literal["json", "markdown"], Query(alias="format")
    ] = "json",
) -> RawResponse:
    """Download one exact PaperSummary ArtifactVersion as JSON or Markdown."""

    download = PaperSummaryExportService(_summary_service(request)).export(
        version_id=version_id,
        session_id=_session_id(request),
        export_format=export_format,
    )
    response = RawResponse(
        content=download.content,
        media_type=download.media_type,
        headers={"Content-Disposition": f'attachment; filename="{download.filename}"'},
    )
    _no_store(response)
    return response


@router.get(
    "/artifact-versions/{version_id}/scientific",
    operation_id="getScientificArtifact",
    response_model=Envelope[ScientificArtifactRead],
)
def get_scientific_artifact(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ScientificArtifactRead]:
    data = _scientific_service(request).get_scientific_artifact(
        version_id=version_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/scientific"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/scientific/content/{content_hash}",
    operation_id="getScientificArtifactContent",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        },
        206: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        },
        416: {"model": ProblemDetails},
    },
)
async def get_scientific_artifact_content(
    version_id: Annotated[str, Path(min_length=1)],
    content_hash: Annotated[str, Path(pattern=r"^sha256:[0-9a-f]{64}$")],
    request: Request,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    try:
        content, media_type = await _scientific_service(request).get_content(
            version_id=version_id,
            content_hash=content_hash,
            session_id=_session_id(request),
            range_header=range_header,
        )
    except ContentRangeNotSatisfiable as exc:
        raise SecurityProblem(
            status=416,
            code="SCIENTIFIC_CONTENT_RANGE_NOT_SATISFIABLE",
            title="Content range not satisfiable",
            detail="The requested byte range cannot be served for this content",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Range": f"bytes */{exc.total_size}",
            },
        ) from exc

    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, immutable, max-age=31536000",
        "Content-Length": str(content.content_length),
    }
    status_code = 200
    if range_header is not None:
        status_code = 206
        headers["Content-Range"] = (
            f"bytes {content.start}-{content.end}/{content.total_size}"
        )
    return StreamingResponse(
        content=content.chunks,
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )


@router.get(
    "/artifact-versions/{version_id}/graph",
    operation_id="getGraphArtifact",
    response_model=Envelope[GraphArtifactRead],
)
def get_graph_artifact(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[GraphArtifactRead]:
    data = _graph_service(request).get_graph(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/graph"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/graph/nodes",
    operation_id="listGraphNodes",
    response_model=CollectionEnvelope[GraphNodeRead],
)
def list_graph_nodes(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    node_type: Annotated[GraphNodeType | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[GraphNodeRead]:
    items, next_cursor, has_more = _graph_service(request).list_nodes(
        version_id=version_id,
        session_id=_session_id(request),
        node_type=node_type,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/graph/nodes"
    return CollectionEnvelope(
        data=items,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/graph/nodes/{node_id}",
    operation_id="getGraphNode",
    response_model=Envelope[GraphNodeRead],
)
def get_graph_node(
    version_id: Annotated[str, Path(min_length=1)],
    node_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[GraphNodeRead]:
    data = _graph_service(request).get_node(
        version_id=version_id, node_id=node_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/graph/nodes/{node_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/graph/edges",
    operation_id="listGraphEdges",
    response_model=CollectionEnvelope[GraphEdgeRead],
)
def list_graph_edges(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    edge_type: Annotated[GraphEdgeType | None, Query()] = None,
    node_id: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[GraphEdgeRead]:
    items, next_cursor, has_more = _graph_service(request).list_edges(
        version_id=version_id,
        session_id=_session_id(request),
        edge_type=edge_type,
        node_id=node_id,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/graph/edges"
    return CollectionEnvelope(
        data=items,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/graph/edges/{edge_id}",
    operation_id="getGraphEdge",
    response_model=Envelope[GraphEdgeRead],
)
def get_graph_edge(
    version_id: Annotated[str, Path(min_length=1)],
    edge_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[GraphEdgeRead]:
    data = _graph_service(request).get_edge(
        version_id=version_id, edge_id=edge_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/graph/edges/{edge_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/literature-claims",
    operation_id="listLiteratureClaims",
    response_model=CollectionEnvelope[LiteratureClaimRead],
)
def list_literature_claims(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    status: Annotated[LiteratureClaimStatus | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[LiteratureClaimRead]:
    items, next_cursor, has_more = _literature_service(request).list_claims(
        version_id=version_id,
        session_id=_session_id(request),
        status=status,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/literature-claims"
    return CollectionEnvelope(
        data=items,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/literature-claims/{claim_id}",
    operation_id="getLiteratureClaim",
    response_model=Envelope[LiteratureClaimRead],
)
def get_literature_claim(
    version_id: Annotated[str, Path(min_length=1)],
    claim_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[LiteratureClaimRead]:
    data = _literature_service(request).get_claim(
        version_id=version_id,
        claim_id=claim_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/literature-claims/{claim_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/literature-relations",
    operation_id="listLiteratureRelations",
    response_model=CollectionEnvelope[LiteratureRelationRead],
)
def list_literature_relations(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    status: Annotated[LiteratureRelationStatus | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[LiteratureRelationRead]:
    items, next_cursor, has_more = _literature_service(request).list_relations(
        version_id=version_id,
        session_id=_session_id(request),
        status=status,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/literature-relations"
    return CollectionEnvelope(
        data=items,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/literature-relations/{relation_id}",
    operation_id="getLiteratureRelation",
    response_model=Envelope[LiteratureRelationRead],
)
def get_literature_relation(
    version_id: Annotated[str, Path(min_length=1)],
    relation_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[LiteratureRelationRead]:
    data = _literature_service(request).get_relation(
        version_id=version_id,
        relation_id=relation_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/literature-relations/{relation_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/reasoning-traces",
    operation_id="listReasoningTraces",
    response_model=CollectionEnvelope[LiteratureReasoningTraceRead],
)
def list_reasoning_traces(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    status: Annotated[LiteratureRelationStatus | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[LiteratureReasoningTraceRead]:
    items, next_cursor, has_more = _literature_service(request).list_reasoning_traces(
        version_id=version_id,
        session_id=_session_id(request),
        status=status,
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/reasoning-traces"
    return CollectionEnvelope(
        data=items,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/reasoning-traces/{trace_id}",
    operation_id="getReasoningTrace",
    response_model=Envelope[LiteratureReasoningTraceRead],
)
def get_reasoning_trace(
    version_id: Annotated[str, Path(min_length=1)],
    trace_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[LiteratureReasoningTraceRead]:
    data = _literature_service(request).get_reasoning_trace(
        version_id=version_id,
        trace_id=trace_id,
        session_id=_session_id(request),
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/reasoning-traces/{trace_id}"
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
    path = f"/api/artifact-versions/{version_id}/paper-candidates"
    return CollectionEnvelope(
        data=candidates,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.post(
    "/artifact-versions/{version_id}/paper-candidates/{candidate_id}/research-input",
    operation_id="createPaperCandidateResearchInput",
    response_model=Envelope[PaperCandidateInputBinding],
    status_code=201,
)
async def create_paper_candidate_research_input(
    version_id: Annotated[str, Path(min_length=1)],
    candidate_id: Annotated[str, Path(min_length=1)],
    payload: CreatePaperCandidateInputRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
) -> Envelope[PaperCandidateInputBinding]:
    _ = csrf_token
    rate_limit = None
    limiter = request.app.state.research_input_rate_limiter
    if isinstance(payload, OpenAccessPaperCandidateInputRequest):
        rate_limit = limiter.consume(_session_id(request))
    result = await _paper_input_service(request).create(
        CreatePaperCandidateInputCommand(
            session_id=_session_id(request),
            paper_collection_version_id=version_id,
            candidate_id=candidate_id,
            idempotency_key=idempotency_key,
            request=payload,
        )
    )
    if result.reused:
        response.status_code = 200
    _no_store(response)
    if rate_limit is not None:
        remaining, reset_seconds = rate_limit
        response.headers["RateLimit-Limit"] = str(limiter.limit)
        response.headers["RateLimit-Remaining"] = str(remaining)
        response.headers["RateLimit-Reset"] = str(reset_seconds)
    path = (
        f"/api/artifact-versions/{version_id}/paper-candidates/"
        f"{candidate_id}/research-input"
    )
    return Envelope(data=result, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/dataset",
    operation_id="getDatasetArtifact",
    response_model=Envelope[DatasetArtifactRead],
)
def get_dataset_artifact(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[DatasetArtifactRead]:
    data = _data_service(request).get_dataset(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/dataset"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/dataset/rows",
    operation_id="listDatasetRows",
    response_model=CollectionEnvelope[DataArtifactRowRead],
)
def list_dataset_rows(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> CollectionEnvelope[DataArtifactRowRead]:
    rows, next_cursor, has_more = _data_service(request).list_dataset_rows(
        version_id=version_id,
        session_id=_session_id(request),
        cursor=cursor,
        limit=limit,
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/dataset/rows"
    return CollectionEnvelope(
        data=rows,
        page=CursorPage(next_cursor=next_cursor, has_more=has_more, limit=limit),
        meta=_meta(request),
        links=ResponseLinks(self=path),
    )


@router.get(
    "/artifact-versions/{version_id}/field-dictionary",
    operation_id="getFieldDictionaryArtifact",
    response_model=Envelope[FieldDictionaryArtifactRead],
)
def get_field_dictionary_artifact(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[FieldDictionaryArtifactRead]:
    data = _data_service(request).get_field_dictionary(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/field-dictionary"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.get(
    "/artifact-versions/{version_id}/source-collection",
    operation_id="getSourceCollectionArtifact",
    response_model=Envelope[SourceCollectionArtifactRead],
)
def get_source_collection_artifact(
    version_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[SourceCollectionArtifactRead]:
    data = _data_service(request).get_source_collection(
        version_id=version_id, session_id=_session_id(request)
    )
    _no_store(response)
    path = f"/api/artifact-versions/{version_id}/source-collection"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))


@router.post(
    "/artifact-versions/{version_id}/exports",
    operation_id="createArtifactExport",
    status_code=202,
    response_model=Envelope[ArtifactExportRead],
)
def create_artifact_export(
    version_id: Annotated[str, Path(min_length=1)],
    payload: CreateArtifactExportRequest,
    request: Request,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
    ],
) -> Envelope[ArtifactExportRead]:
    data = _data_service(request).create_export(
        version_id=version_id,
        session_id=_session_id(request),
        idempotency_key=idempotency_key,
        export_format=payload.format,
    )
    _no_store(response)
    response.headers["Location"] = f"/api/exports/{data.export.id}"
    return Envelope(
        data=data.export,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/exports/{data.export.id}"),
    )


@router.get(
    "/exports/{export_id}",
    operation_id="getArtifactExport",
    response_model=Envelope[ArtifactExportRead],
)
def get_artifact_export(
    export_id: Annotated[str, Path(min_length=1)],
    request: Request,
    response: Response,
) -> Envelope[ArtifactExportRead]:
    data = _data_service(request).get_export(
        export_id=export_id, session_id=_session_id(request)
    )
    _no_store(response)
    return Envelope(
        data=data,
        meta=_meta(request),
        links=ResponseLinks(self=f"/api/exports/{export_id}"),
    )


@router.get(
    "/exports/{export_id}/download",
    operation_id="downloadArtifactExport",
    response_class=RawResponse,
    response_model=None,
)
def download_artifact_export(
    export_id: Annotated[str, Path(min_length=1)],
    request: Request,
) -> RawResponse:
    data = _data_service(request).download_export(
        export_id=export_id, session_id=_session_id(request)
    )
    response = RawResponse(
        content=data.content,
        media_type=data.media_type,
        headers={"Content-Disposition": f'attachment; filename="{data.filename}"'},
    )
    _no_store(response)
    return response


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
    path = f"/api/evidence/{evidence_id}"
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
    path = f"/api/source-snapshots/{snapshot_id}"
    return Envelope(data=data, meta=_meta(request), links=ResponseLinks(self=path))
