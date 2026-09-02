"""Execute and admit a DocumentParse-backed paper summary."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryAdmissionResult,
    PaperSummaryEvidenceCandidate,
    PaperSummaryModelUsage,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import DocumentParseCandidate
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
    model_execution_failure_response,
)
from packages.prompts.registry import PromptRegistry
from services.paper_pipeline.summary import (
    PaperSummaryPipeline,
    build_document_evidence_candidates,
    build_document_summary_input_identity,
)

MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS = 512
MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS = 200_000


class DocumentSummaryInputTooLargeError(ValueError):
    """The current bounded execution cannot safely fit the parsed document."""


@dataclass(frozen=True, slots=True)
class ExecuteDocumentSummaryRequest:
    document_parse: DocumentParseCandidate
    document_parse_id: str
    source_snapshot: PaperSummarySourceSnapshotReference
    paper: PaperSummaryPaperMetadata
    source_id: str
    source_record_id: str
    research_goal: str
    provider: str
    model: str
    model_revision: str | None
    parameters: dict[str, Any]
    run_id: str | None = None
    producer_execution_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentSummaryExecution:
    admission: PaperSummaryAdmissionResult
    model_response: ModelExecutionResponse
    provider_request_id: str | None
    token_usage: PaperSummaryModelUsage | None
    latency_ms: int


@dataclass(frozen=True, slots=True)
class PreparedDocumentSummary:
    """Immutable model request plus the exact ProducerExecution input identity."""

    request: ExecuteDocumentSummaryRequest
    evidence_candidates: tuple[PaperSummaryEvidenceCandidate, ...]
    model_request: ModelExecutionRequest
    input_hash: str
    parameters_hash: str


class DocumentSummaryService:
    """Bounded model execution followed by the canonical summary admission."""

    def __init__(
        self,
        model_execution: ModelExecutionPort,
        *,
        prompt_registry: PromptRegistry | None = None,
        pipeline: PaperSummaryPipeline | None = None,
    ) -> None:
        self._models = model_execution
        self._prompts = prompt_registry or PromptRegistry()
        self._pipeline = pipeline or PaperSummaryPipeline(prompt_registry=self._prompts)

    def execute(
        self, request: ExecuteDocumentSummaryRequest
    ) -> DocumentSummaryExecution:
        return self.execute_prepared(self.prepare(request))

    def prepare(
        self, request: ExecuteDocumentSummaryRequest
    ) -> PreparedDocumentSummary:
        evidence = build_document_evidence_candidates(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            paper_id=request.paper.paper_id,
            source_id=request.source_id,
            source_record_id=request.source_record_id,
            source_snapshot_id=request.source_snapshot.source_snapshot_id,
        )
        character_count = sum(len(item.quote_or_value) for item in evidence)
        if (
            len(evidence) > MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS
            or character_count > MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS
        ):
            raise DocumentSummaryInputTooLargeError(
                "parsed document exceeds the bounded single-execution summary budget"
            )
        prompt = self._prompts.get("paper_summary")
        input_payload = {
            "research_goal": request.research_goal,
            "paper_payload": {
                "paper": request.paper.model_dump(mode="json"),
                "document_parse": {
                    "document_parse_id": request.document_parse_id,
                    "candidate_parse_id": request.document_parse.parse_id,
                    "canonical_output_hash": (
                        request.document_parse.canonical_output_hash
                    ),
                    "input_content_hash": request.document_parse.content_hash,
                    "parser_profile_id": (
                        request.document_parse.profile.parser_profile_id
                    ),
                    "overall_quality": request.document_parse.overall_quality.value,
                },
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "section": item.locator.section,
                        "paragraph": item.locator.paragraph,
                        "locator": item.locator.document_locator.model_dump(
                            mode="json", exclude_none=True
                        )
                        if item.locator.document_locator is not None
                        else None,
                        "text": item.quote_or_value,
                    }
                    for item in evidence
                ],
            },
        }
        model_request = ModelExecutionRequest(
            provider=request.provider,
            requested_model=request.model,
            explicit_revision=request.model_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            prompt=prompt.content,
            input_payload=input_payload,
            parameters=request.parameters,
        )
        _, input_hash, parameters_hash = build_document_summary_input_identity(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            source_snapshot=request.source_snapshot,
            paper=request.paper,
            model_name=request.model,
            parameters=request.parameters,
            evidence_candidates=evidence,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
        )
        return PreparedDocumentSummary(
            request=request,
            evidence_candidates=evidence,
            model_request=model_request,
            input_hash=input_hash,
            parameters_hash=parameters_hash,
        )

    def execute_prepared(
        self,
        prepared: PreparedDocumentSummary,
        *,
        producer_execution_id: str | None = None,
    ) -> DocumentSummaryExecution:
        request = prepared.request
        observed_responses: list[ModelExecutionResponse] = []
        try:
            response = self._models.execute(prepared.model_request)
            _validate_model_response(response)
        except ModelExecutionError as exc:
            if exc.code != "MODEL_RESPONSE_TRUNCATED":
                raise
            failed_response = model_execution_failure_response(exc)
            if failed_response is not None:
                observed_responses.append(failed_response)
            response = self._models.execute(
                replace(
                    prepared.model_request,
                    input_payload={
                        **prepared.model_request.input_payload,
                        "validation_feedback": {
                            "code": "DOCUMENT_SUMMARY_TRUNCATED",
                            "concise_output": True,
                        },
                    },
                )
            )
            _validate_model_response(response)
        observed_responses.append(response)
        aggregate_response = _aggregate_model_responses(
            tuple(observed_responses), final_response=response
        )
        usage = _model_usage(aggregate_response.token_usage)
        admission = self._pipeline.admit_document(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            source_snapshot=request.source_snapshot,
            paper=request.paper,
            model_response=json.dumps(
                response.payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            model_name=request.model,
            model_revision=request.model_revision,
            provider=request.provider,
            provider_returned_model=aggregate_response.provider_returned_model,
            provider_request_id=aggregate_response.provider_request_id,
            usage=usage,
            latency_ms=aggregate_response.latency_ms,
            parameters=request.parameters,
            evidence_candidates=prepared.evidence_candidates,
            run_id=request.run_id,
            execution_id=producer_execution_id or request.producer_execution_id,
        )
        if admission.producer.input_hash != prepared.input_hash:
            raise ValueError("prepared summary input identity drifted during admission")
        return DocumentSummaryExecution(
            admission=admission,
            model_response=aggregate_response,
            provider_request_id=aggregate_response.provider_request_id,
            token_usage=usage,
            latency_ms=aggregate_response.latency_ms,
        )


def _validate_model_response(response: ModelExecutionResponse) -> None:
    if response.latency_ms < 0:
        raise ValueError("model response latency must be non-negative")
    expected_hash = compute_canonical_payload_hash(response.payload)
    if response.output_hash != expected_hash:
        raise ValueError("model response output hash mismatch")


def _model_usage(payload: dict[str, Any] | None) -> PaperSummaryModelUsage | None:
    if payload is None:
        return None
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    values = {key: payload.get(key) for key in keys}
    if any(
        not isinstance(value, int) or isinstance(value, bool)
        for value in values.values()
    ):
        raise ValueError("model token usage is incomplete or invalid")
    return PaperSummaryModelUsage.model_validate(values)


def _aggregate_model_responses(
    responses: tuple[ModelExecutionResponse, ...],
    *,
    final_response: ModelExecutionResponse,
) -> ModelExecutionResponse:
    if len(responses) == 1:
        return final_response
    usage_keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    usage_totals = dict.fromkeys(usage_keys, 0)
    usage_complete = True
    returned_models: list[str] = []
    returned_models_complete = True
    for response in responses:
        if response.token_usage is None:
            usage_complete = False
        else:
            for key in usage_keys:
                value = response.token_usage.get(key)
                if not isinstance(value, int) or isinstance(value, bool):
                    usage_complete = False
                else:
                    usage_totals[key] += value
        if response.provider_returned_model is None:
            returned_models_complete = False
        else:
            returned_models.append(response.provider_returned_model)
    returned_model = (
        returned_models[0]
        if returned_models_complete
        and returned_models
        and len(set(returned_models)) == 1
        else None
    )
    return ModelExecutionResponse(
        payload=final_response.payload,
        output_hash=final_response.output_hash,
        token_usage=usage_totals if usage_complete else None,
        latency_ms=sum(response.latency_ms for response in responses),
        provider_request_id=None,
        provider_returned_model=returned_model,
    )


__all__ = [
    "DocumentSummaryExecution",
    "DocumentSummaryInputTooLargeError",
    "DocumentSummaryService",
    "ExecuteDocumentSummaryRequest",
    "MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS",
    "MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS",
    "PreparedDocumentSummary",
]
