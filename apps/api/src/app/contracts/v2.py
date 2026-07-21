"""OpenAPI-only surface for the accepted ``/api/v2`` transport contract.

The application returned here is intentionally not mounted by ``app.main``.
Runtime behavior, persistence, session security, and workflow execution belong
to later issues; this module freezes operation names and transport schemas only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, NoReturn, cast

from fastapi import FastAPI, Header, Path, Query

from app.schemas.v2 import (
    ArtifactVersion,
    CollectionEnvelope,
    ConfirmResearchContractRequest,
    CreateRunRequest,
    Envelope,
    ProblemDetails,
    ResearchArtifact,
    ResearchContract,
    ResearchContractDraft,
    ResearchProject,
    ResearchRun,
    RunEvent,
    UpdateResearchContractDraftRequest,
)


PROBLEM_RESPONSES = {
    400: {"model": ProblemDetails},
    404: {"model": ProblemDetails},
    409: {"model": ProblemDetails},
    422: {"model": ProblemDetails},
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
        "/api/v2/artifacts/{artifact_id}",
        operation_id="getResearchArtifact",
        response_model=Envelope[ResearchArtifact],
        responses=PROBLEM_RESPONSES,
    )
    def get_research_artifact(artifact_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = artifact_id
        return _contract_only()

    @app.get(
        "/api/v2/artifact-versions/{version_id}",
        operation_id="getArtifactVersion",
        response_model=Envelope[ArtifactVersion],
        responses=PROBLEM_RESPONSES,
    )
    def get_artifact_version(version_id: Annotated[str, Path(min_length=1)]) -> NoReturn:
        _ = version_id
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
