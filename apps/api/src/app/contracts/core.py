"""OpenAPI-only surface for the accepted ``/api`` transport contract.

The application returned here is intentionally not mounted by ``app.main``.
Runtime routers selectively implement this surface; this module remains the
single generated operation and transport-schema document.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal, NoReturn, cast

from fastapi import Body, FastAPI, Header, Path, Query, Response
from pydantic import TypeAdapter

from app.schemas.core import (
    ArtifactKind,
    ArtifactVersionDetail,
    CollectionEnvelope,
    ConfirmResearchContractRequest,
    CreateResearchContractDraftRequest,
    CreateResearchProjectRequest,
    CreateRunRequest,
    CreateShareSnapshotRequest,
    Envelope,
    EvidenceRead,
    ProblemDetails,
    PublicShareSnapshot,
    ResearchArtifact,
    ResearchArtifactDetail,
    ResearchContract,
    ResearchContractDraft,
    ResearchProject,
    ResearchPlanningCatalog,
    ResearchRun,
    RunCheckpointRead,
    RunDecisionRequest,
    RunDecisionResult,
    ResearchSession,
    ResearchThreadEntry,
    ResearchTurnRequest,
    ResearchTurnResult,
    RunStepRead,
    RunEvent,
    SessionCreated,
    ShareSnapshot,
    ShareSnapshotCreated,
    SourceSnapshotDetail,
    UpdateResearchProjectRequest,
    UpdateResearchContractDraftRequest,
    WorkspaceSnapshot,
    WorkspaceSnapshotInput,
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
from app.schemas.research_input import (
    BindResearchInputRequest,
    CreateResearchInputMultipartRequest,
    CreateResearchInputRequest,
    ResearchInputDetail,
    ResearchInputRef,
)

PROBLEM_RESPONSES = {
    400: {"model": ProblemDetails},
    404: {"model": ProblemDetails},
    409: {"model": ProblemDetails},
    413: {"model": ProblemDetails},
    422: {"model": ProblemDetails},
    401: {"model": ProblemDetails},
    403: {"model": ProblemDetails},
    429: {"model": ProblemDetails},
    502: {"model": ProblemDetails},
}

#: Research input ingestion adds body/type rejections on top of the common set.
RESEARCH_INPUT_PROBLEM_RESPONSES = {
    **PROBLEM_RESPONSES,
    413: {"model": ProblemDetails},
    415: {"model": ProblemDetails},
}


def _contract_only() -> NoReturn:
    raise RuntimeError("the /api contract application is not a runtime API")


def create_contract_app() -> FastAPI:
    app = FastAPI(
        title="Xingwen Astro AI /api Contract",
        version="2.0.0",
        openapi_version="3.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.post(
        "/api/sessions",
        operation_id="createAnonymousSession",
        response_model=Envelope[SessionCreated],
        status_code=201,
        responses=PROBLEM_RESPONSES,
        description="Creates an anonymous session and sets a Secure, HttpOnly, SameSite cookie.",
    )
    def create_anonymous_session() -> NoReturn:
        return _contract_only()

    @app.get(
        "/api/sessions/current",
        operation_id="getAnonymousSession",
        response_model=Envelope[ResearchSession],
        responses=PROBLEM_RESPONSES,
    )
    def get_anonymous_session() -> NoReturn:
        return _contract_only()

    @app.delete(
        "/api/sessions/current",
        operation_id="revokeAnonymousSession",
        status_code=204,
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    def revoke_anonymous_session(
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> Response:
        _ = csrf_token
        return _contract_only()

    @app.get(
        "/api/projects",
        operation_id="listResearchProjects",
        response_model=CollectionEnvelope[ResearchProject],
        responses=PROBLEM_RESPONSES,
        description="Lists only the projects owned by the current anonymous session.",
    )
    def list_research_projects(
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (cursor, limit)
        return _contract_only()

    @app.post(
        "/api/projects",
        operation_id="createResearchProject",
        response_model=Envelope[ResearchProject],
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    def create_research_project(
        request: CreateResearchProjectRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> NoReturn:
        _ = (request, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/projects/{project_id}",
        operation_id="getResearchProject",
        response_model=Envelope[ResearchProject],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_project(
        project_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = project_id
        return _contract_only()

    @app.get(
        "/api/projects/{project_id}/research-catalog",
        operation_id="getResearchPlanningCatalog",
        response_model=Envelope[ResearchPlanningCatalog],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_planning_catalog(
        project_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = project_id
        return _contract_only()

    @app.patch(
        "/api/projects/{project_id}",
        operation_id="updateResearchProject",
        response_model=Envelope[ResearchProject],
        responses=PROBLEM_RESPONSES,
    )
    def update_research_project(
        project_id: Annotated[str, Path(min_length=1)],
        request: UpdateResearchProjectRequest,
        if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, if_match)
        return _contract_only()

    @app.delete(
        "/api/projects/{project_id}",
        operation_id="deleteResearchProject",
        status_code=204,
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    def delete_research_project(
        project_id: Annotated[str, Path(min_length=1)],
        if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, if_match)
        return _contract_only()

    @app.get(
        "/api/projects/{project_id}/research-turns",
        operation_id="listResearchTurns",
        response_model=CollectionEnvelope[ResearchThreadEntry],
        responses=PROBLEM_RESPONSES,
    )
    def list_research_turns(
        project_id: Annotated[str, Path(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (project_id, cursor, limit)
        return _contract_only()

    @app.post(
        "/api/projects/{project_id}/research-turns",
        operation_id="submitResearchTurn",
        response_model=Envelope[ResearchTurnResult],
        responses=PROBLEM_RESPONSES,
    )
    def submit_research_turn(
        project_id: Annotated[str, Path(min_length=1)],
        request: ResearchTurnRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, idempotency_key)
        return _contract_only()

    @app.post(
        "/api/projects/{project_id}/contract-drafts",
        operation_id="createResearchContractDraft",
        response_model=Envelope[ResearchContractDraft],
        status_code=201,
        responses=PROBLEM_RESPONSES,
        description=(
            "Creates an editable draft bound to a project owned by the current "
            "session; drafts never carry execution_mode."
        ),
    )
    def create_research_contract_draft(
        project_id: Annotated[str, Path(min_length=1)],
        request: CreateResearchContractDraftRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/contracts/drafts/{draft_id}",
        operation_id="getResearchContractDraft",
        response_model=Envelope[ResearchContractDraft],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_contract_draft(
        draft_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = draft_id
        return _contract_only()

    @app.patch(
        "/api/contracts/drafts/{draft_id}",
        operation_id="updateResearchContractDraft",
        response_model=Envelope[ResearchContractDraft],
        responses=PROBLEM_RESPONSES,
    )
    def update_research_contract_draft(
        draft_id: Annotated[str, Path(min_length=1)],
        request: UpdateResearchContractDraftRequest,
        if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
    ) -> NoReturn:
        _ = (draft_id, request, if_match)
        return _contract_only()

    @app.get(
        "/api/contracts/{contract_id}",
        operation_id="getResearchContract",
        response_model=Envelope[ResearchContract],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_contract(
        contract_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = contract_id
        return _contract_only()

    @app.post(
        "/api/projects/{project_id}/contracts",
        operation_id="confirmResearchContract",
        response_model=Envelope[ResearchContract],
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    def confirm_research_contract(
        project_id: Annotated[str, Path(min_length=1)],
        request: ConfirmResearchContractRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/runs/{run_id}",
        operation_id="getResearchRun",
        response_model=Envelope[ResearchRun],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_run(run_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = run_id
        return _contract_only()

    @app.delete(
        "/api/runs/{run_id}",
        operation_id="cancelResearchRun",
        response_model=Envelope[ResearchRun],
        responses=PROBLEM_RESPONSES,
    )
    def cancel_research_run(
        run_id: Annotated[str, Path(min_length=1)],
        if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
    ) -> NoReturn:
        _ = (run_id, if_match)
        return _contract_only()

    @app.get(
        "/api/runs/{run_id}/checkpoint",
        operation_id="getResearchRunCheckpoint",
        response_model=Envelope[RunCheckpointRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_run_checkpoint(
        run_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = run_id
        return _contract_only()

    @app.post(
        "/api/runs/{run_id}/decisions",
        operation_id="decideResearchRun",
        response_model=Envelope[RunDecisionResult],
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    def decide_research_run(
        run_id: Annotated[str, Path(min_length=1)],
        request: RunDecisionRequest,
        if_match: Annotated[str, Header(alias="If-Match", min_length=1)],
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1)
        ],
    ) -> NoReturn:
        _ = (run_id, request, if_match, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/runs/{run_id}/steps",
        operation_id="listRunSteps",
        response_model=CollectionEnvelope[RunStepRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_run_steps(run_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = run_id
        return _contract_only()

    @app.post(
        "/api/projects/{project_id}/runs",
        operation_id="createResearchRun",
        response_model=Envelope[ResearchRun],
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    def create_research_run(
        project_id: Annotated[str, Path(min_length=1)],
        request: CreateRunRequest,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/runs/{run_id}/events",
        operation_id="listRunEvents",
        response_model=CollectionEnvelope[RunEvent],
        responses=PROBLEM_RESPONSES,
    )
    def list_run_events(
        run_id: Annotated[str, Path(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (run_id, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/runs/{run_id}/artifacts",
        operation_id="listRunArtifacts",
        response_model=CollectionEnvelope[ResearchArtifact],
        responses=PROBLEM_RESPONSES,
    )
    def list_run_artifacts(
        run_id: Annotated[str, Path(min_length=1)],
        kind: Annotated[ArtifactKind | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (run_id, kind, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifacts/{artifact_id}",
        operation_id="getResearchArtifact",
        response_model=Envelope[ResearchArtifactDetail],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_artifact(
        artifact_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = artifact_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}",
        operation_id="getArtifactVersion",
        response_model=Envelope[ArtifactVersionDetail],
        responses=PROBLEM_RESPONSES,
    )
    def get_artifact_version(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/paper-collection",
        operation_id="getPaperCollection",
        response_model=Envelope[PaperCollectionRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_paper_collection(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/paper-summary",
        operation_id="getPaperSummary",
        response_model=Envelope[PaperSummaryRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_paper_summary(version_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/paper-summary/export",
        operation_id="downloadPaperSummaryExport",
        response_class=Response,
        response_model=None,
        responses={
            **PROBLEM_RESPONSES,
            200: {
                "content": {
                    "application/json": {"schema": {"type": "string"}},
                    "text/markdown": {"schema": {"type": "string"}},
                }
            },
        },
    )
    def download_paper_summary_export(
        version_id: Annotated[str, Path(min_length=1)],
        format: Annotated[Literal["json", "markdown"], Query()] = "json",
    ) -> NoReturn:
        _ = (version_id, format)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/scientific",
        operation_id="getScientificArtifact",
        response_model=Envelope[ScientificArtifactRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_scientific_artifact(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/scientific/content/{content_hash}",
        operation_id="getScientificArtifactContent",
        response_class=Response,
        response_model=None,
        responses={
            **PROBLEM_RESPONSES,
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
    def get_scientific_artifact_content(
        version_id: Annotated[str, Path(min_length=1)],
        content_hash: Annotated[str, Path(pattern=r"^sha256:[0-9a-f]{64}$")],
        range_header: Annotated[str | None, Header(alias="Range")] = None,
    ) -> Response:
        _ = (version_id, content_hash, range_header)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/graph",
        operation_id="getGraphArtifact",
        response_model=Envelope[GraphArtifactRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_graph_artifact(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/graph/nodes",
        operation_id="listGraphNodes",
        response_model=CollectionEnvelope[GraphNodeRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_graph_nodes(
        version_id: Annotated[str, Path(min_length=1)],
        node_type: Annotated[GraphNodeType | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, node_type, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/graph/nodes/{node_id}",
        operation_id="getGraphNode",
        response_model=Envelope[GraphNodeRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_graph_node(
        version_id: Annotated[str, Path(min_length=1)],
        node_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = (version_id, node_id)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/graph/edges",
        operation_id="listGraphEdges",
        response_model=CollectionEnvelope[GraphEdgeRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_graph_edges(
        version_id: Annotated[str, Path(min_length=1)],
        edge_type: Annotated[GraphEdgeType | None, Query()] = None,
        node_id: Annotated[str | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, edge_type, node_id, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/graph/edges/{edge_id}",
        operation_id="getGraphEdge",
        response_model=Envelope[GraphEdgeRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_graph_edge(
        version_id: Annotated[str, Path(min_length=1)],
        edge_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = (version_id, edge_id)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/literature-claims",
        operation_id="listLiteratureClaims",
        response_model=CollectionEnvelope[LiteratureClaimRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_literature_claims(
        version_id: Annotated[str, Path(min_length=1)],
        status: Annotated[LiteratureClaimStatus | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, status, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/literature-claims/{claim_id}",
        operation_id="getLiteratureClaim",
        response_model=Envelope[LiteratureClaimRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_literature_claim(
        version_id: Annotated[str, Path(min_length=1)],
        claim_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = (version_id, claim_id)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/literature-relations",
        operation_id="listLiteratureRelations",
        response_model=CollectionEnvelope[LiteratureRelationRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_literature_relations(
        version_id: Annotated[str, Path(min_length=1)],
        status: Annotated[LiteratureRelationStatus | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, status, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/literature-relations/{relation_id}",
        operation_id="getLiteratureRelation",
        response_model=Envelope[LiteratureRelationRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_literature_relation(
        version_id: Annotated[str, Path(min_length=1)],
        relation_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = (version_id, relation_id)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/reasoning-traces",
        operation_id="listReasoningTraces",
        response_model=CollectionEnvelope[LiteratureReasoningTraceRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_reasoning_traces(
        version_id: Annotated[str, Path(min_length=1)],
        status: Annotated[LiteratureRelationStatus | None, Query()] = None,
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, status, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/reasoning-traces/{trace_id}",
        operation_id="getReasoningTrace",
        response_model=Envelope[LiteratureReasoningTraceRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_reasoning_trace(
        version_id: Annotated[str, Path(min_length=1)],
        trace_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = (version_id, trace_id)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/paper-candidates",
        operation_id="listPaperCollectionCandidates",
        response_model=CollectionEnvelope[PaperCollectionCandidateRead],
        responses=PROBLEM_RESPONSES,
    )
    def list_paper_collection_candidates(
        version_id: Annotated[str, Path(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/evidence/{evidence_id}",
        operation_id="getEvidence",
        response_model=Envelope[EvidenceRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_evidence(evidence_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = evidence_id
        return _contract_only()

    @app.get(
        "/api/source-snapshots/{snapshot_id}",
        operation_id="getSourceSnapshot",
        response_model=Envelope[SourceSnapshotDetail],
        responses=PROBLEM_RESPONSES,
    )
    def get_source_snapshot(
        snapshot_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = snapshot_id
        return _contract_only()

    @app.get(
        "/api/projects/{project_id}/workspace-snapshot",
        operation_id="getWorkspaceSnapshot",
        response_model=Envelope[WorkspaceSnapshot],
        responses=PROBLEM_RESPONSES,
    )
    def get_workspace_snapshot(
        project_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = project_id
        return _contract_only()

    @app.put(
        "/api/projects/{project_id}/workspace-snapshot",
        operation_id="putWorkspaceSnapshot",
        response_model=Envelope[WorkspaceSnapshot],
        responses=PROBLEM_RESPONSES,
    )
    def put_workspace_snapshot(
        project_id: Annotated[str, Path(min_length=1)],
        request: WorkspaceSnapshotInput,
        if_match: Annotated[int, Header(alias="If-Match", ge=0)],
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, if_match, csrf_token)
        return _contract_only()

    @app.get(
        "/api/projects/{project_id}/shares",
        operation_id="listShareSnapshots",
        response_model=CollectionEnvelope[ShareSnapshot],
        responses=PROBLEM_RESPONSES,
    )
    def list_share_snapshots(
        project_id: Annotated[str, Path(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (project_id, cursor, limit)
        return _contract_only()

    @app.post(
        "/api/projects/{project_id}/shares",
        operation_id="createShareSnapshot",
        response_model=Envelope[ShareSnapshotCreated],
        status_code=201,
        responses=PROBLEM_RESPONSES,
    )
    def create_share_snapshot(
        project_id: Annotated[str, Path(min_length=1)],
        request: CreateShareSnapshotRequest,
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> NoReturn:
        _ = (project_id, request, csrf_token)
        return _contract_only()

    @app.delete(
        "/api/projects/{project_id}/shares/{share_id}",
        operation_id="revokeShareSnapshot",
        status_code=204,
        response_model=None,
        responses=PROBLEM_RESPONSES,
    )
    def revoke_share_snapshot(
        project_id: Annotated[str, Path(min_length=1)],
        share_id: Annotated[str, Path(min_length=1)],
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> Response:
        _ = (project_id, share_id, csrf_token)
        return _contract_only()

    @app.get(
        "/api/public/shares/{share_token}",
        operation_id="getPublicShareSnapshot",
        response_model=Envelope[PublicShareSnapshot],
        responses=PROBLEM_RESPONSES,
        description=(
            "Anonymous read-only projection; invalid, expired, and revoked tokens are "
            "indistinguishable."
        ),
    )
    def get_public_share_snapshot(
        share_token: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = share_token
        return _contract_only()

    @app.post(
        "/api/research-inputs",
        operation_id="createResearchInput",
        response_model=Envelope[ResearchInputRef],
        status_code=201,
        responses=RESEARCH_INPUT_PROBLEM_RESPONSES,
        description=(
            "Ingests one controlled research input (URL, PDF, CSV, JSON, image or "
            "text) into an immutable, content-addressed boundary. Files arrive as "
            "multipart/form-data (field ``file``); URLs and text arrive as a JSON "
            "body. The response is a reference only — binary content and full text "
            "never leave this boundary."
        ),
    )
    def create_research_input(
        request: Annotated[CreateResearchInputRequest, Body()],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1)],
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> NoReturn:
        _ = (request, idempotency_key, csrf_token)
        return _contract_only()

    @app.get(
        "/api/research-inputs",
        operation_id="listResearchInputs",
        response_model=CollectionEnvelope[ResearchInputRef],
        responses=PROBLEM_RESPONSES,
        description="Lists only the research inputs owned by the current anonymous session.",
    )
    def list_research_inputs(
        project_id: Annotated[str, Query(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (project_id, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/research-inputs/{input_id}",
        operation_id="getResearchInput",
        response_model=Envelope[ResearchInputDetail],
        responses=PROBLEM_RESPONSES,
        description=(
            "Metadata-only detail read of one ingested input. Missing inputs are "
            "indistinguishable from foreign inputs (404)."
        ),
    )
    def get_research_input(input_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = input_id
        return _contract_only()

    @app.delete(
        "/api/research-inputs/{input_id}",
        operation_id="deleteResearchInput",
        status_code=204,
        response_model=None,
        responses=PROBLEM_RESPONSES,
        description=(
            "Soft-deletes a research input reference; already-bound references are "
            "still deleted because binding never becomes ownership."
        ),
    )
    def delete_research_input(
        input_id: Annotated[str, Path(min_length=1)],
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> Response:
        _ = (input_id, csrf_token)
        return _contract_only()

    @app.post(
        "/api/research-inputs/{input_id}/bind",
        operation_id="bindResearchInput",
        response_model=Envelope[ResearchInputRef],
        responses=PROBLEM_RESPONSES,
        description=(
            "Attaches one ingested input reference to a ContractDraft or a Run "
            "owned by the current session. Only the reference is bound."
        ),
    )
    def bind_research_input(
        input_id: Annotated[str, Path(min_length=1)],
        request: BindResearchInputRequest,
        csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)],
    ) -> NoReturn:
        _ = (input_id, request, csrf_token)
        return _contract_only()

    generated_openapi = app.openapi

    def problem_details_openapi() -> dict[str, Any]:
        document = generated_openapi()
        for path_item in document["paths"].values():
            for operation in path_item.values():
                if not isinstance(operation, dict) or "responses" not in operation:
                    continue
                for status, response in operation["responses"].items():
                    if not str(status).isdigit() or int(status) < 400:
                        continue
                    content = response.get("content", {})
                    json_schema = content.pop("application/json", None)
                    if json_schema is not None:
                        content["application/problem+json"] = json_schema
        _apply_research_input_request_body_schema(document)
        return document

    app.openapi = cast(Callable[[], dict[str, Any]], problem_details_openapi)
    return app


def _apply_research_input_request_body_schema(document: dict[str, Any]) -> None:
    """Declare both create media types from the Pydantic schema authority.

    FastAPI derives a single ``application/json`` body from the operation
    signature, but ``POST /api/research-inputs`` genuinely accepts two media
    types. Rather than hand-writing a second field list (which would become a
    rival source of truth), the multipart body is compiled from
    :class:`CreateResearchInputMultipartRequest` itself and merged in, with its
    ``$defs`` hoisted into ``components.schemas``.
    """

    operation = document.get("paths", {}).get("/api/research-inputs", {}).get("post")
    if not isinstance(operation, dict):
        return

    schema = CreateResearchInputMultipartRequest.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    defs = schema.pop("$defs", {})
    if defs:
        components = document.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in defs.items():
            components.setdefault(name, definition)

    components = document.setdefault("components", {}).setdefault("schemas", {})
    components["CreateResearchInputMultipartRequest"] = schema

    request_body = operation.setdefault("requestBody", {})
    content = request_body.setdefault("content", {})
    content["multipart/form-data"] = {
        "schema": {"$ref": "#/components/schemas/CreateResearchInputMultipartRequest"}
    }
    request_body["required"] = True

    _apply_bind_request_body_schema(document)


def _apply_bind_request_body_schema(document: dict[str, Any]) -> None:
    """Publish the bind XOR union as a named, referenceable component.

    FastAPI inlines the union at the operation, which is still machine-checkable
    but leaves no stable name for consumers. Registering it keeps
    ``components.schemas.BindResearchInputRequest`` as the contract handle while
    the schema body remains generated from the Pydantic union.
    """

    operation = (
        document.get("paths", {})
        .get("/api/research-inputs/{input_id}/bind", {})
        .get("post")
    )
    if not isinstance(operation, dict):
        return

    schema = TypeAdapter(BindResearchInputRequest).json_schema(
        ref_template="#/components/schemas/{model}"
    )
    defs = schema.pop("$defs", {})
    components = document.setdefault("components", {}).setdefault("schemas", {})
    for name, definition in defs.items():
        components.setdefault(name, definition)
    components["BindResearchInputRequest"] = schema

    content = operation.setdefault("requestBody", {}).setdefault("content", {})
    content["application/json"] = {
        "schema": {"$ref": "#/components/schemas/BindResearchInputRequest"}
    }
