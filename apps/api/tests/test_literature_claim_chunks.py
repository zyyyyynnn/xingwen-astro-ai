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
    CLAIM_CHUNK_BUDGET_EXCEEDED,
    CLAIM_CHUNK_SCHEMA_INVALID,
    ClaimChunkViolation,
    ChunkedLiteratureClaimService,
)
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from packages.prompts.registry import PromptRegistry


def _claim_payload(statement: dict) -> dict:
    return {
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


def _response(payload: dict, request_count: int) -> ModelExecutionResponse:
    return ModelExecutionResponse(
        payload=payload,
        output_hash=compute_canonical_payload_hash(payload),
        token_usage={
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300,
        },
        latency_ms=25,
        provider_request_id=f"request-{request_count}",
        provider_returned_model="test-model-revision",
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
            "claims": [_claim_payload(statement) for statement in selected],
        }
        return _response(payload, len(self.requests))


class _BudgetViolatingModel:
    """Emits one extra claim for the first statement until corrected."""

    def __init__(self) -> None:
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        artifact = request.input_payload["paper_summary_artifact"]
        statements = artifact["statements"]
        corrected = "validation_feedback" in request.input_payload
        claims: list[dict] = []
        for index, statement in enumerate(statements):
            claims.append(_claim_payload(statement))
            if not corrected and index == 0:
                claims.extend(_claim_payload(statement) for _ in range(4))
        return _response({"schema_version": "1.0.0", "claims": claims}, len(self.requests))


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


_EXECUTE_KWARGS = {
    "paper_summary_artifact_version_id": "11111111-1111-4111-8111-111111111111",
    "provider": "test-provider",
    "model": "test-model",
    "model_revision": "test-model-revision",
    "parameters": {"temperature": 0.6, "top_p": 0.8},
}


def test_claim_extraction_uses_bounded_narrow_batches() -> None:
    model = _ClaimModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(17), **_EXECUTE_KWARGS
    )

    assert result.chunk_count == 3
    assert len(result.extraction.claims) == 17
    assert result.correction_count == 0
    assert result.split_count == 0
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 900
    assert result.latency_ms == 75
    assert result.model_response.provider_request_id is None
    assert result.model_response.provider_returned_model == "test-model-revision"
    assert all(
        len(request.input_payload["paper_summary_artifact"]["statements"]) <= 8
        for request in model.requests
    )
    for request in model.requests:
        assert request.response_schema_name == "literature_claim"
        assert request.enable_thinking is False
        schema = request.response_schema
        assert schema is not None
        candidate = schema["$defs"]["LiteratureClaimModelCandidate"]
        statements = request.input_payload["paper_summary_artifact"]["statements"]
        assert candidate["properties"]["source_statement_id"]["enum"] == [
            item["statement_id"] for item in statements
        ]
        expected_evidence = list(
            dict.fromkeys(
                evidence_id
                for statement in statements
                for evidence_id in statement["evidence_ids"]
            )
        )
        assert candidate["properties"]["evidence_ids"]["items"]["enum"] == (
            expected_evidence
        )


def test_claim_extraction_fails_closed_when_batch_coverage_is_incomplete() -> None:
    model = _ClaimModel(omit_last_statement=True)

    with pytest.raises(ClaimChunkViolation, match="did not cover"):
        ChunkedLiteratureClaimService(model).execute(
            summary=_summary(2), **_EXECUTE_KWARGS
        )
    assert len(model.requests) == 2


def test_claim_correction_recovers_with_new_input_identity() -> None:
    model = _BudgetViolatingModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(2), **_EXECUTE_KWARGS
    )

    assert len(result.extraction.claims) == 2
    assert result.correction_count == 1
    assert result.split_count == 0
    assert len(model.requests) == 2
    assert model.requests[0].input_hash != model.requests[1].input_hash
    assert set(model.requests[1].input_payload) == {
        "paper_summary_artifact",
        "validation_feedback",
    }
    feedback = model.requests[1].input_payload["validation_feedback"]
    assert feedback["code"] == CLAIM_CHUNK_BUDGET_EXCEEDED
    assert feedback["max_claims_per_statement"] == 4
    assert feedback["required_statement_ids"] == [
        "statement.000",
        "statement.001",
    ]
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 600
    assert result.latency_ms == 50


class _AlwaysViolatingModel:
    """Emits one extra claim for the first statement even after correction."""

    def __init__(self) -> None:
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        artifact = request.input_payload["paper_summary_artifact"]
        statements = artifact["statements"]
        claims = [_claim_payload(statement) for statement in statements]
        claims.extend(_claim_payload(statements[0]) for _ in range(4))
        return _response(
            {"schema_version": "1.0.0", "claims": claims}, len(self.requests)
        )


def test_claim_correction_budget_fails_closed_without_third_call() -> None:
    model = _AlwaysViolatingModel()

    with pytest.raises(ClaimChunkViolation, match="budget"):
        ChunkedLiteratureClaimService(model).execute(
            summary=_summary(2), **_EXECUTE_KWARGS
        )
    assert len(model.requests) == 2


class _TruncatingClaimModel(_ClaimModel):
    def __init__(self, *, truncate_calls: int = 1) -> None:
        super().__init__()
        self.truncate_calls = truncate_calls

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        if len(self.requests) <= self.truncate_calls:
            raise ModelExecutionError(
                "MODEL_RESPONSE_TRUNCATED",
                "研究助手返回结果不完整，请稍后重试。",
                output_hash="sha256:" + "f" * 64,
                token_usage={
                    "prompt_tokens": 50,
                    "completion_tokens": 100,
                    "total_tokens": 150,
                },
                latency_ms=10,
                provider_request_id=f"truncated-{len(self.requests)}",
            )
        artifact = request.input_payload["paper_summary_artifact"]
        statements = artifact["statements"]
        return _response(
            {
                "schema_version": "1.0.0",
                "claims": [_claim_payload(statement) for statement in statements],
            },
            len(self.requests),
        )


def test_claim_truncation_splits_once_with_distinct_child_inputs() -> None:
    model = _TruncatingClaimModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(4), **_EXECUTE_KWARGS
    )

    assert result.split_count == 1
    assert result.correction_count == 0
    assert len(result.extraction.claims) == 4
    assert len(model.requests) == 3
    assert len({request.input_hash for request in model.requests}) == 3
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 750
    assert result.latency_ms == 60


def test_claim_truncation_does_not_recurse_past_one_split() -> None:
    model = _TruncatingClaimModel(truncate_calls=2)

    with pytest.raises(ClaimChunkViolation, match="split depth limit"):
        ChunkedLiteratureClaimService(model).execute(
            summary=_summary(4), **_EXECUTE_KWARGS
        )

    assert len(model.requests) == 2


def test_single_statement_truncation_uses_one_concise_correction() -> None:
    model = _TruncatingClaimModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(1), **_EXECUTE_KWARGS
    )

    assert result.correction_count == 1
    assert result.split_count == 0
    assert len(model.requests) == 2
    feedback = model.requests[1].input_payload["validation_feedback"]
    assert feedback["code"] == "CLAIM_CHUNK_TRUNCATED"
    assert feedback["concise_output"] is True
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 450
    assert result.latency_ms == 35


def test_split_recovery_counts_a_child_contract_correction() -> None:
    class SplitThenBudgetModel(_ClaimModel):
        def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
            self.requests.append(request)
            if len(self.requests) == 1:
                raise ModelExecutionError(
                    "MODEL_RESPONSE_TRUNCATED",
                    "研究助手返回结果不完整，请稍后重试。",
                    output_hash="sha256:" + "c" * 64,
                    token_usage={
                        "prompt_tokens": 50,
                        "completion_tokens": 100,
                        "total_tokens": 150,
                    },
                    latency_ms=10,
                    provider_request_id="split-truncated",
                )
            artifact = request.input_payload["paper_summary_artifact"]
            statements = artifact["statements"]
            claims = [_claim_payload(statement) for statement in statements]
            if len(self.requests) == 2:
                claims.extend(_claim_payload(statements[0]) for _ in range(4))
            return _response(
                {"schema_version": "1.0.0", "claims": claims}, len(self.requests)
            )

    model = SplitThenBudgetModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(4), **_EXECUTE_KWARGS
    )

    assert result.split_count == 1
    assert result.correction_count == 1
    assert len(model.requests) == 4
    assert result.token_usage is not None
    assert result.token_usage["total_tokens"] == 1050
    assert result.latency_ms == 85


class _SchemaViolatingClaimModel:
    """Emits an invalid claim structure on first call, then valid on correction."""

    def __init__(self) -> None:
        self.requests: list[ModelExecutionRequest] = []

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        artifact = request.input_payload["paper_summary_artifact"]
        statements = artifact["statements"]
        if len(self.requests) == 1:
            # Emit invalid schema: missing required fields in candidate
            payload = {
                "schema_version": "1.0.0",
                "claims": [
                    {
                        "source_statement_id": statements[0]["statement_id"],
                        "text": "Invalid polarity claim",
                        "normalized_text": "invalid polarity claim",
                        "claim_type": "finding",
                        "polarity": "not_a_valid_polarity",
                        "objects": ["object"],
                        "evidence_ids": statements[0]["evidence_ids"],
                    }
                ],
            }
            return _response(payload, len(self.requests))
        payload = {
            "schema_version": "1.0.0",
            "claims": [_claim_payload(statement) for statement in statements],
        }
        return _response(payload, len(self.requests))


def test_claim_schema_invalid_correction_provides_sanitized_schema_issues() -> None:
    model = _SchemaViolatingClaimModel()

    result = ChunkedLiteratureClaimService(model).execute(
        summary=_summary(2), **_EXECUTE_KWARGS
    )

    assert result.correction_count == 1
    assert result.split_count == 0
    assert len(result.extraction.claims) == 2
    assert len(model.requests) == 2
    assert "validation_feedback" in model.requests[1].input_payload
    feedback = model.requests[1].input_payload["validation_feedback"]
    assert feedback["code"] == CLAIM_CHUNK_SCHEMA_INVALID
    assert feedback["max_claims_per_statement"] == 4
    assert feedback["required_statement_ids"] == ["statement.000", "statement.001"]
    assert "schema_issues" in feedback
    issues = feedback["schema_issues"]
    assert len(issues) >= 1
    assert len(issues) <= 12
    for issue in issues:
        assert set(issue.keys()) == {"loc", "type", "message"}
        assert isinstance(issue["loc"], list)
        assert isinstance(issue["type"], str)
        assert isinstance(issue["message"], str)
        # Ensure schema issues exclude input, raw payload, and URLs
        assert "input" not in issue
        assert "url" not in issue
        assert "payload" not in issue
        assert "raw" not in issue


def test_literature_claim_prompt_declares_claim_budget() -> None:
    prompt = PromptRegistry().get("literature_claim")

    assert prompt.version == "1.2.1"
    assert "1–4 条 Claim" in prompt.content
    assert "不得超过 4 条" in prompt.content
    assert "validation_feedback" in prompt.content
    assert "schema_issues" in prompt.content
