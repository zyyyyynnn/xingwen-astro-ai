from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummarySectionKind,
    PaperSummaryStatement,
    PaperSummarySupportStatus,
)
from app.services.literature_claim_chunks import (
    ClaimChunkCoverageError,
    ChunkedLiteratureClaimService,
)
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)


class _ClaimModel:
    def __init__(self, *, omit_last_statement: bool = False) -> None:
        self.omit_last_statement = omit_last_statement
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        artifact = request.input_payload["paper_summary_artifact"]
        assert isinstance(artifact, dict)
        assert set(artifact) == {
            "artifact_version_id",
            "paper_id",
            "schema_version",
            "statements",
            "summary_id",
        }
        statements = artifact["statements"]
        assert isinstance(statements, list)
        selected = statements[:-1] if self.omit_last_statement else statements
        payload = {
            "schema_version": "1.0.0",
            "claims": [
                {
                    "source_statement_id": statement["statement_id"],
                    "text": statement["text"],
                    "normalized_text": statement["text"].lower(),
                    "claim_type": "finding",
                    "polarity": "positive",
                    "objects": ["transiting exoplanets"],
                    "metric": None,
                    "unit": None,
                    "conditions": [],
                    "scope": [],
                    "limitations": [],
                    "qualifiers": [],
                    "uncertainty": None,
                    "comparison_basis": None,
                    "evidence_ids": statement["evidence_ids"],
                }
                for statement in selected
            ],
        }
        return ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage={
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "total_tokens": 300,
            },
            latency_ms=25,
            provider_request_id=f"request-{len(self.requests)}",
            provider_returned_model="test-model-revision",
        )


def _summary(statement_count: int) -> PaperSummaryArtifactContent:
    sections = {section.value: [] for section in PaperSummarySectionKind}
    for index in range(statement_count):
        sections[PaperSummarySectionKind.experiments.value].append(
            PaperSummaryStatement(
                statement_id=f"statement.{index:03d}",
                text=f"Supported scientific result {index}.",
                evidence_ids=(f"evidence.{index:03d}",),
                status=PaperSummarySupportStatus.supported,
                validation_code="evidence.supported",
            )
        )
    return cast(
        PaperSummaryArtifactContent,
        SimpleNamespace(
            schema_version="2.0.0",
            paper_id="paper.test",
            summary_id="summary.test",
            **sections,
        ),
    )


def test_claim_extraction_uses_bounded_narrow_batches() -> None:
    model = _ClaimModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(17),
        paper_summary_artifact_version_id="11111111-1111-4111-8111-111111111111",
        provider="test-provider",
        model="test-model",
        model_revision="test-model-revision",
        parameters={"temperature": 0.6, "top_p": 0.8, "max_tokens": 8192},
    )

    assert result.chunk_count == 3
    assert len(result.extraction.claims) == 17
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 900
    assert result.latency_ms == 75
    assert result.model_response.provider_request_id is None
    assert result.model_response.provider_returned_model == "test-model-revision"
    assert all(
        len(request.input_payload["paper_summary_artifact"]["statements"]) <= 8
        for request in model.requests
    )


def test_claim_extraction_fails_closed_when_batch_coverage_is_incomplete() -> None:
    model = _ClaimModel(omit_last_statement=True)

    with pytest.raises(ClaimChunkCoverageError, match="did not cover"):
        ChunkedLiteratureClaimService(model).execute(
            summary=_summary(2),
            paper_summary_artifact_version_id=("11111111-1111-4111-8111-111111111111"),
            provider="test-provider",
            model="test-model",
            model_revision="test-model-revision",
            parameters={"temperature": 0.6, "top_p": 0.8, "max_tokens": 8192},
        )
