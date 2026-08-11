"""Contract-only Data Artifact HTTP operations.

This module owns the transport declarations for current Data Artifact reads and
exports. It contains no runtime service wiring; ``app.contracts.api``
composes these operations with the core contract before OpenAPI generation.
"""

from __future__ import annotations

from typing import Annotated, Any, NoReturn

from fastapi import FastAPI, Header, Path, Query, Response

from app.schemas.core import CollectionEnvelope, Envelope
from app.schemas.data_artifact_api import (
    ArtifactExportRead,
    CreateArtifactExportRequest,
    DataArtifactRowRead,
    DatasetArtifactRead,
    FieldDictionaryArtifactRead,
    SourceCollectionArtifactRead,
)


def _contract_only() -> NoReturn:
    raise RuntimeError("the /api contract application is not a runtime API")


def register_data_artifact_contract(
    app: FastAPI,
    *,
    problem_responses: dict[int, dict[str, Any]],
) -> None:
    """Register the complete current Data Artifact transport surface."""

    @app.get(
        "/api/artifact-versions/{version_id}/dataset",
        operation_id="getDatasetArtifact",
        response_model=Envelope[DatasetArtifactRead],
        responses=problem_responses,
    )
    def get_dataset_artifact(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/dataset/rows",
        operation_id="listDatasetRows",
        response_model=CollectionEnvelope[DataArtifactRowRead],
        responses=problem_responses,
    )
    def list_dataset_rows(
        version_id: Annotated[str, Path(min_length=1)],
        cursor: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> NoReturn:
        _ = (version_id, cursor, limit)
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/field-dictionary",
        operation_id="getFieldDictionaryArtifact",
        response_model=Envelope[FieldDictionaryArtifactRead],
        responses=problem_responses,
    )
    def get_field_dictionary_artifact(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.get(
        "/api/artifact-versions/{version_id}/source-collection",
        operation_id="getSourceCollectionArtifact",
        response_model=Envelope[SourceCollectionArtifactRead],
        responses=problem_responses,
    )
    def get_source_collection_artifact(
        version_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = version_id
        return _contract_only()

    @app.post(
        "/api/artifact-versions/{version_id}/exports",
        operation_id="createArtifactExport",
        status_code=202,
        response_model=Envelope[ArtifactExportRead],
        responses=problem_responses,
    )
    def create_artifact_export(
        version_id: Annotated[str, Path(min_length=1)],
        request: CreateArtifactExportRequest,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=1, max_length=200)
        ],
    ) -> NoReturn:
        _ = (version_id, request, idempotency_key)
        return _contract_only()

    @app.get(
        "/api/exports/{export_id}",
        operation_id="getArtifactExport",
        response_model=Envelope[ArtifactExportRead],
        responses=problem_responses,
    )
    def get_artifact_export(
        export_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = export_id
        return _contract_only()

    @app.get(
        "/api/exports/{export_id}/download",
        operation_id="downloadArtifactExport",
        response_class=Response,
        response_model=None,
        responses=problem_responses,
    )
    def download_artifact_export(
        export_id: Annotated[str, Path(min_length=1)],
    ) -> NoReturn:
        _ = export_id
        return _contract_only()
