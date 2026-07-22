"""OpenAPI-only surface for the accepted ``/api/v2`` transport contract.

The application returned here is intentionally not mounted by ``app.main``.
Runtime routers selectively implement this surface; this module remains the
single generated operation and transport-schema document.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, NoReturn, cast

from fastapi import FastAPI, Header, Path, Query, Response

from app.schemas.v2 import (
    ArtifactKind,
    ArtifactVersionDetail,
    CollectionEnvelope,
    ConfirmResearchContractRequest,
    CreateShareSnapshotRequest,
    CreateRunRequest,
    Envelope,
    EvidenceRead,
    ProblemDetails,
    PublicShareSnapshot,
    ResearchArtifact,
    ResearchArtifactDetail,
    ResearchContract,
    ResearchContractDraft,
    ResearchProject,
    ResearchRun,
    RunEvent,
    ResearchSession,
    SessionCreated,
    ShareSnapshot,
    ShareSnapshotCreated,
    UpdateResearchContractDraftRequest,
    WorkspaceSnapshot,
    WorkspaceSnapshotInput,
    SourceSnapshotDetail,
)


PROBLEM_RESPONSES = {
    400: {"model": ProblemDetails},
    404: {"model": ProblemDetails},
    409: {"model": ProblemDetails},
    422: {"model": ProblemDetails},
    401: {"model": ProblemDetails},
    403: {"model": ProblemDetails},
    429: {"model": ProblemDetails},
}


def _contract_only() -> NoReturn:
    raise RuntimeError("the /api/v2 contract application is not a runtime API")


def create_v2_contract_app() -> FastAPI:
    app = FastAPI(
        title="Xingwen Astro AI /api/v2 Contract",
        version="2.0.0",
        openapi_version="3.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.post(
        "/api/v2/sessions",
        operation_id="createAnonymousSession",
        response_model=Envelope[SessionCreated],
        status_code=201,
        responses=PROBLEM_RESPONSES,
        description="Creates an anonymous session and sets a Secure, HttpOnly, SameSite cookie.",
    )
    def create_anonymous_session() -> NoReturn:
        return _contract_only()

    @app.get(
        "/api/v2/sessions/current",
        operation_id="getAnonymousSession",
        response_model=Envelope[ResearchSession],
        responses=PROBLEM_RESPONSES,
    )
    def get_anonymous_session() -> NoReturn:
        return _contract_only()

    @app.delete(
        "/api/v2/sessions/current",
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
        "/api/v2/projects/{project_id}",
        operation_id="getResearchProject",
        response_model=Envelope[ResearchProject],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_project(project_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = project_id
        return _contract_only()

    @app.get(
        "/api/v2/research-contract-drafts/{draft_id}",
        operation_id="getResearchContractDraft",
        response_model=Envelope[ResearchContractDraft],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_contract_draft(draft_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = draft_id
        return _contract_only()

    @app.patch(
        "/api/v2/research-contract-drafts/{draft_id}",
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
        "/api/v2/research-contracts/{contract_id}",
        operation_id="getResearchContract",
        response_model=Envelope[ResearchContract],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_contract(contract_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = contract_id
        return _contract_only()

    @app.post(
        "/api/v2/projects/{project_id}/contracts",
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
        "/api/v2/runs/{run_id}",
        operation_id="getResearchRun",
        response_model=Envelope[ResearchRun],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_run(run_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = run_id
        return _contract_only()

    @app.post(
        "/api/v2/projects/{project_id}/runs",
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
        "/api/v2/runs/{run_id}/events",
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
        "/api/v2/runs/{run_id}/artifacts",
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
        "/api/v2/artifacts/{artifact_id}",
        operation_id="getResearchArtifact",
        response_model=Envelope[ResearchArtifactDetail],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_artifact(artifact_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = artifact_id
        return _contract_only()

    @app.get(
        "/api/v2/artifact-versions/{version_id}",
        operation_id="getArtifactVersion",
        response_model=Envelope[ArtifactVersionDetail],
        responses=PROBLEM_RESPONSES,
    )
    def get_artifact_version(version_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/v2/evidence/{evidence_id}",
        operation_id="getEvidence",
        response_model=Envelope[EvidenceRead],
        responses=PROBLEM_RESPONSES,
    )
    def get_evidence(evidence_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = evidence_id
        return _contract_only()

    @app.get(
        "/api/v2/source-snapshots/{snapshot_id}",
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
        "/api/v2/projects/{project_id}/workspace-snapshot",
        operation_id="getWorkspaceSnapshot",
        response_model=Envelope[WorkspaceSnapshot],
        responses=PROBLEM_RESPONSES,
    )
    def get_workspace_snapshot(project_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = project_id
        return _contract_only()

    @app.put(
        "/api/v2/projects/{project_id}/workspace-snapshot",
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
        "/api/v2/projects/{project_id}/shares",
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
        "/api/v2/projects/{project_id}/shares",
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
        "/api/v2/projects/{project_id}/shares/{share_id}",
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
        "/api/v2/shares/{share_token}",
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
        return document

    app.openapi = cast(Callable[[], dict[str, Any]], problem_details_openapi)
    return app
