"""Runtime transport for generic Artifact provenance reads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, Path, Query, Request, Response
from fastapi.responses import Response as RawResponse

from app.schemas.core import (
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
from app.schemas.data_artifact_api import (
    ArtifactExportRead,
    CreateArtifactExportRequest,
    DataArtifactRowRead,
    DatasetArtifactRead,
    FieldDictionaryArtifactRead,
    SourceCollectionArtifactRead,
)
from app.schemas.enums import GraphEdgeType, GraphNodeType
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
    PaperCollectionCandidateRead,
    PaperCollectionRead,
)
from app.schemas.paper_summary_api import PaperSummaryRead
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from app.security import SecurityProblem
from app.services.artifacts import ArtifactReadService
from app.services.data_artifacts import DataArtifactReadService
from app.services.graph_artifacts import GraphArtifactReadService
from app.services.literature_artifacts import LiteratureArtifactReadService
from app.services.paper_collections import PaperCollectionReadService
from app.services.paper_summaries import PaperSummaryReadService
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


def _summary_service(request: Request) -> PaperSummaryReadService:
    return PaperSummaryReadService(_service(request))


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
    response_class=RawResponse,
    responses={
        200: {
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            }
        }
    },
)
async def get_scientific_artifact_content(
    version_id: Annotated[str, Path(min_length=1)],
    content_hash: Annotated[str, Path(pattern=r"^sha256:[0-9a-f]{64}$")],
    request: Request,
) -> RawResponse:
    content, media_type = await _scientific_service(request).get_content(
        version_id=version_id,
        content_hash=content_hash,
        session_id=_session_id(request),
    )
    return RawResponse(
        content=content,
        media_type=media_type,
        headers={"Cache-Control": "private, immutable, max-age=31536000"},
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
