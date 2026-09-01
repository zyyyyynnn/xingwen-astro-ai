"""Bounded model extraction for Claims from large PaperSummary artifacts.

The published PaperSummary remains the sole scientific input authority. Model
calls receive only the statement fields required to author Claims; Evidence
objects, locators, ProducerExecution metadata and artifact hashes remain at the
deterministic admission boundary instead of being copied into every request.

Each chunk gets one original call plus at most one bounded recovery step: a
schema/coverage violation receives exactly one structured correction request,
and a provider truncation receives exactly one deterministic binary split
(multi-statement chunks) or one concise correction request (single-statement
chunks). Every recovery failure fails closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.literature_claim import (
    LiteratureClaimExtractionOutput,
    LiteratureClaimModelCandidate,
)
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummarySectionKind,
    PaperSummaryStatement,
)
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from packages.prompts.registry import PromptRecord, PromptRegistry


MAX_CLAIM_STATEMENTS_PER_CHUNK = 8
MAX_CLAIM_STATEMENT_CHARACTERS_PER_CHUNK = 4_000
MAX_CLAIMS_PER_STATEMENT = 4

CLAIM_CHUNK_SCHEMA_INVALID = "CLAIM_CHUNK_SCHEMA_INVALID"
CLAIM_CHUNK_STATEMENT_OUT_OF_SCOPE = "CLAIM_CHUNK_STATEMENT_OUT_OF_SCOPE"
CLAIM_CHUNK_EVIDENCE_OUT_OF_SCOPE = "CLAIM_CHUNK_EVIDENCE_OUT_OF_SCOPE"
CLAIM_CHUNK_BUDGET_EXCEEDED = "CLAIM_CHUNK_BUDGET_EXCEEDED"
CLAIM_CHUNK_STATEMENT_UNCOVERED = "CLAIM_CHUNK_STATEMENT_UNCOVERED"
CLAIM_CHUNK_TRUNCATED = "CLAIM_CHUNK_TRUNCATED"

_MODEL_RESPONSE_TRUNCATED = "MODEL_RESPONSE_TRUNCATED"


class ClaimChunkViolation(ValueError):
    """Typed, stable chunk-contract violation raised after bounded recovery."""

    def __init__(
        self,
        *,
        code: str,
        chunk_id: str,
        affected_statement_ids: tuple[str, ...] = (),
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.chunk_id = chunk_id
        self.affected_statement_ids = affected_statement_ids


@dataclass(frozen=True, slots=True)
class ClaimExtractionStatement:
    section: PaperSummarySectionKind
    statement: PaperSummaryStatement


@dataclass(frozen=True, slots=True)
class ClaimExtractionChunk:
    chunk_id: str
    statements: tuple[ClaimExtractionStatement, ...]


@dataclass(frozen=True, slots=True)
class ChunkedLiteratureClaimExecution:
    extraction: LiteratureClaimExtractionOutput
    model_response: ModelExecutionResponse
    chunk_count: int
    chunk_provider_request_ids: tuple[str | None, ...]
    chunk_provider_returned_models: tuple[str | None, ...]
    token_usage: dict[str, int] | None
    latency_ms: int
    correction_count: int = 0
    split_count: int = 0


class ChunkedLiteratureClaimService:
    """Extract all evidence-bearing Summary statements in bounded model calls."""

    def __init__(
        self,
        model_execution: ModelExecutionPort,
        *,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self._models = model_execution
        self._prompts = prompt_registry or PromptRegistry()

    def execute(
        self,
        *,
        summary: PaperSummaryArtifactContent,
        paper_summary_artifact_version_id: str,
        provider: str,
        model: str,
        model_revision: str | None,
        parameters: Mapping[str, float | int],
    ) -> ChunkedLiteratureClaimExecution:
        chunks = build_claim_extraction_chunks(summary)
        prompt = self._prompts.get("literature_claim")
        claims: list[LiteratureClaimModelCandidate] = []
        request_ids: list[str | None] = []
        returned_models: list[str | None] = []
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage_complete = True
        latency_total = 0
        correction_total = 0
        split_total = 0

        for chunk in chunks:
            responses, extraction, corrections, splits = (
                _execute_chunk_with_bounded_recovery(
                    self._models,
                    prompt=prompt,
                    chunk=chunk,
                    summary=summary,
                    paper_summary_artifact_version_id=(
                        paper_summary_artifact_version_id
                    ),
                    provider=provider,
                    model=model,
                    model_revision=model_revision,
                    parameters=parameters,
                )
            )
            correction_total += corrections
            split_total += splits
            claims.extend(extraction.claims)
            for response in responses:
                request_ids.append(response.provider_request_id)
                returned_models.append(response.provider_returned_model)
                latency_total += response.latency_ms
                if response.token_usage is None:
                    usage_complete = False
                else:
                    for key in usage_totals:
                        value = response.token_usage.get(key)
                        if not isinstance(value, int) or isinstance(value, bool):
                            usage_complete = False
                        else:
                            usage_totals[key] += value

        extraction = LiteratureClaimExtractionOutput(
            schema_version="1.0.0",
            claims=tuple(claims),
        )
        payload = extraction.model_dump(mode="json")
        token_usage = usage_totals if usage_complete else None
        aggregate_response = ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage=token_usage,
            latency_ms=latency_total,
            provider_request_id=None,
            provider_returned_model=_consensus_returned_model(returned_models),
        )
        return ChunkedLiteratureClaimExecution(
            extraction=extraction,
            model_response=aggregate_response,
            chunk_count=len(chunks),
            chunk_provider_request_ids=tuple(request_ids),
            chunk_provider_returned_models=tuple(returned_models),
            token_usage=token_usage,
            latency_ms=latency_total,
            correction_count=correction_total,
            split_count=split_total,
        )


def build_claim_extraction_chunks(
    summary: PaperSummaryArtifactContent,
    *,
    max_statements: int = MAX_CLAIM_STATEMENTS_PER_CHUNK,
    max_characters: int = MAX_CLAIM_STATEMENT_CHARACTERS_PER_CHUNK,
) -> tuple[ClaimExtractionChunk, ...]:
    if max_statements < 1:
        raise ValueError("max_statements must be positive")
    if max_characters < 1_000:
        raise ValueError("max_characters must be at least 1000")

    eligible = tuple(
        ClaimExtractionStatement(section=section, statement=statement)
        for section in PaperSummarySectionKind
        for statement in getattr(summary, section.value)
        if statement.evidence_ids
    )
    if not eligible:
        raise ClaimChunkViolation(
            code=CLAIM_CHUNK_STATEMENT_UNCOVERED,
            chunk_id="claim-chunk.0000",
            message=(
                "PaperSummary has no evidence-bearing statements for Claim extraction"
            ),
        )

    chunks: list[ClaimExtractionChunk] = []
    current: list[ClaimExtractionStatement] = []
    current_characters = 0

    def flush() -> None:
        nonlocal current, current_characters
        if not current:
            return
        chunks.append(
            ClaimExtractionChunk(
                chunk_id=f"claim-chunk.{len(chunks) + 1:04d}",
                statements=tuple(current),
            )
        )
        current = []
        current_characters = 0

    for item in eligible:
        statement_characters = len(item.statement.text)
        if current and (
            len(current) >= max_statements
            or current_characters + statement_characters > max_characters
        ):
            flush()
        current.append(item)
        current_characters += statement_characters
    flush()
    return tuple(chunks)


def _execute_chunk_with_bounded_recovery(
    models: ModelExecutionPort,
    *,
    prompt: PromptRecord,
    chunk: ClaimExtractionChunk,
    summary: PaperSummaryArtifactContent,
    paper_summary_artifact_version_id: str,
    provider: str,
    model: str,
    model_revision: str | None,
    parameters: Mapping[str, float | int],
) -> tuple[tuple[ModelExecutionResponse, ...], LiteratureClaimExtractionOutput, int, int]:
    def run(
        target: ClaimExtractionChunk,
        payload: dict[str, Any],
    ) -> tuple[ModelExecutionResponse, LiteratureClaimExtractionOutput]:
        return _chunk_call(
            models,
            prompt=prompt,
            chunk=target,
            payload=payload,
            provider=provider,
            model=model,
            model_revision=model_revision,
            parameters=parameters,
        )

    def base_payload(target: ClaimExtractionChunk) -> dict[str, Any]:
        return _chunk_payload(
            summary=summary,
            paper_summary_artifact_version_id=paper_summary_artifact_version_id,
            chunk=target,
        )

    try:
        response, extraction = run(chunk, base_payload(chunk))
        return (response,), extraction, 0, 0
    except ModelExecutionError as exc:
        if exc.code != _MODEL_RESPONSE_TRUNCATED:
            raise
        return _recover_truncated_chunk(
            run=run,
            base_payload=base_payload,
            chunk=chunk,
        )
    except ClaimChunkViolation as violation:
        try:
            response, extraction = run(
                chunk,
                _validation_feedback_payload(
                    base_payload(chunk),
                    chunk=chunk,
                    code=violation.code,
                    affected_statement_ids=violation.affected_statement_ids,
                ),
            )
        except ClaimChunkViolation as correction_violation:
            raise correction_violation from violation
        except ModelExecutionError as correction_error:
            if correction_error.code == _MODEL_RESPONSE_TRUNCATED:
                raise ClaimChunkViolation(
                    code=CLAIM_CHUNK_TRUNCATED,
                    chunk_id=chunk.chunk_id,
                    affected_statement_ids=violation.affected_statement_ids,
                    message=f"{chunk.chunk_id} correction response was truncated",
                ) from violation
            raise
        return (response,), extraction, 1, 0


def _recover_truncated_chunk(
    *,
    run,
    base_payload,
    chunk: ClaimExtractionChunk,
) -> tuple[tuple[ModelExecutionResponse, ...], LiteratureClaimExtractionOutput, int, int]:
    if len(chunk.statements) < 2:
        single = chunk.statements[0].statement.statement_id
        try:
            response, extraction = run(
                chunk,
                _validation_feedback_payload(
                    base_payload(chunk),
                    chunk=chunk,
                    code=CLAIM_CHUNK_TRUNCATED,
                    affected_statement_ids=(single,),
                    concise=True,
                ),
            )
        except ModelExecutionError as exc:
            if exc.code == _MODEL_RESPONSE_TRUNCATED:
                raise ClaimChunkViolation(
                    code=CLAIM_CHUNK_TRUNCATED,
                    chunk_id=chunk.chunk_id,
                    affected_statement_ids=(single,),
                    message=(
                        f"{chunk.chunk_id} single-statement output remained truncated"
                    ),
                ) from exc
            raise
        return (response,), extraction, 1, 1

    middle = (len(chunk.statements) + 1) // 2
    halves = (
        ClaimExtractionChunk(
            chunk_id=f"{chunk.chunk_id}L",
            statements=chunk.statements[:middle],
        ),
        ClaimExtractionChunk(
            chunk_id=f"{chunk.chunk_id}R",
            statements=chunk.statements[middle:],
        ),
    )
    responses: list[ModelExecutionResponse] = []
    claims: list[LiteratureClaimModelCandidate] = []
    for half in halves:
        try:
            response, extraction = run(half, base_payload(half))
        except ModelExecutionError as exc:
            if exc.code == _MODEL_RESPONSE_TRUNCATED:
                raise ClaimChunkViolation(
                    code=CLAIM_CHUNK_TRUNCATED,
                    chunk_id=half.chunk_id,
                    affected_statement_ids=tuple(
                        item.statement.statement_id for item in half.statements
                    ),
                    message=(
                        f"{half.chunk_id} remained truncated at the split depth limit"
                    ),
                ) from exc
            raise
        except ClaimChunkViolation as violation:
            try:
                response, extraction = run(
                    half,
                    _validation_feedback_payload(
                        base_payload(half),
                        chunk=half,
                        code=violation.code,
                        affected_statement_ids=violation.affected_statement_ids,
                    ),
                )
            except ClaimChunkViolation as correction_violation:
                raise correction_violation from violation
            except ModelExecutionError as correction_error:
                if correction_error.code == _MODEL_RESPONSE_TRUNCATED:
                    raise ClaimChunkViolation(
                        code=CLAIM_CHUNK_TRUNCATED,
                        chunk_id=half.chunk_id,
                        affected_statement_ids=violation.affected_statement_ids,
                        message=(
                            f"{half.chunk_id} correction response was truncated"
                        ),
                    ) from violation
                raise
        responses.append(response)
        claims.extend(extraction.claims)
    combined = LiteratureClaimExtractionOutput(
        schema_version="1.0.0",
        claims=tuple(claims),
    )
    return tuple(responses), combined, 0, 1


def _chunk_call(
    models: ModelExecutionPort,
    *,
    prompt: PromptRecord,
    chunk: ClaimExtractionChunk,
    payload: dict[str, Any],
    provider: str,
    model: str,
    model_revision: str | None,
    parameters: Mapping[str, float | int],
) -> tuple[ModelExecutionResponse, LiteratureClaimExtractionOutput]:
    response = models.execute(
        ModelExecutionRequest(
            provider=provider,
            requested_model=model,
            explicit_revision=model_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            prompt=prompt.content,
            input_payload=payload,
            parameters=dict(parameters),
            response_mode="json",
            enable_thinking=True,
        )
    )
    _validate_model_response(response)
    try:
        extraction = LiteratureClaimExtractionOutput.model_validate(response.payload)
    except ValidationError as exc:
        raise ClaimChunkViolation(
            code=CLAIM_CHUNK_SCHEMA_INVALID,
            chunk_id=chunk.chunk_id,
            message=f"{chunk.chunk_id} model output did not match the Claim schema",
        ) from exc
    _validate_chunk_coverage(chunk, extraction)
    return response, extraction


def _chunk_payload(
    *,
    summary: PaperSummaryArtifactContent,
    paper_summary_artifact_version_id: str,
    chunk: ClaimExtractionChunk,
) -> dict[str, Any]:
    return {
        "paper_summary_artifact": _chunk_model_input(
            summary=summary,
            paper_summary_artifact_version_id=paper_summary_artifact_version_id,
            chunk=chunk,
        )
    }


def _validation_feedback_payload(
    base_payload: dict[str, Any],
    *,
    chunk: ClaimExtractionChunk,
    code: str,
    affected_statement_ids: Iterable[str],
    concise: bool = False,
) -> dict[str, Any]:
    payload = dict(base_payload)
    feedback: dict[str, Any] = {
        "code": code,
        "required_statement_ids": [
            item.statement.statement_id for item in chunk.statements
        ],
        "affected_statement_ids": list(affected_statement_ids),
        "max_claims_per_statement": MAX_CLAIMS_PER_STATEMENT,
    }
    if concise:
        feedback["concise_output"] = True
    payload["validation_feedback"] = feedback
    return payload


def _chunk_model_input(
    *,
    summary: PaperSummaryArtifactContent,
    paper_summary_artifact_version_id: str,
    chunk: ClaimExtractionChunk,
) -> dict[str, object]:
    return {
        "artifact_version_id": paper_summary_artifact_version_id,
        "schema_version": summary.schema_version,
        "paper_id": summary.paper_id,
        "summary_id": summary.summary_id,
        "statements": [
            {
                "section": item.section.value,
                "statement_id": item.statement.statement_id,
                "text": item.statement.text,
                "status": item.statement.status.value,
                "evidence_ids": list(item.statement.evidence_ids),
            }
            for item in chunk.statements
        ],
    }


def _validate_model_response(response: ModelExecutionResponse) -> None:
    if response.latency_ms < 0:
        raise ValueError("model response latency must be non-negative")
    if response.tool_calls:
        raise ValueError("Claim JSON response must not contain tool calls")
    if response.output_hash != compute_canonical_payload_hash(response.payload):
        raise ValueError("model response output hash mismatch")


def _validate_chunk_coverage(
    chunk: ClaimExtractionChunk,
    extraction: LiteratureClaimExtractionOutput,
) -> None:
    statements = {
        item.statement.statement_id: item.statement for item in chunk.statements
    }
    counts = dict.fromkeys(statements, 0)
    for claim in extraction.claims:
        statement = statements.get(claim.source_statement_id)
        if statement is None:
            raise ClaimChunkViolation(
                code=CLAIM_CHUNK_STATEMENT_OUT_OF_SCOPE,
                chunk_id=chunk.chunk_id,
                affected_statement_ids=(claim.source_statement_id,),
                message=f"{chunk.chunk_id} referenced a statement outside its batch",
            )
        if not set(claim.evidence_ids).issubset(statement.evidence_ids):
            raise ClaimChunkViolation(
                code=CLAIM_CHUNK_EVIDENCE_OUT_OF_SCOPE,
                chunk_id=chunk.chunk_id,
                affected_statement_ids=(claim.source_statement_id,),
                message=(
                    f"{chunk.chunk_id} referenced Evidence outside its source statement"
                ),
            )
        counts[claim.source_statement_id] += 1
        if counts[claim.source_statement_id] > MAX_CLAIMS_PER_STATEMENT:
            raise ClaimChunkViolation(
                code=CLAIM_CHUNK_BUDGET_EXCEEDED,
                chunk_id=chunk.chunk_id,
                affected_statement_ids=(claim.source_statement_id,),
                message=f"{chunk.chunk_id} exceeded the per-statement Claim budget",
            )
    missing = tuple(
        statement_id for statement_id, count in counts.items() if count == 0
    )
    if missing:
        raise ClaimChunkViolation(
            code=CLAIM_CHUNK_STATEMENT_UNCOVERED,
            chunk_id=chunk.chunk_id,
            affected_statement_ids=missing,
            message=f"{chunk.chunk_id} did not cover {len(missing)} source statements",
        )


def _consensus_returned_model(models: list[str | None]) -> str | None:
    if not models or any(model is None for model in models):
        return None
    distinct = set(models)
    return next(iter(distinct)) if len(distinct) == 1 else None


__all__ = [
    "CLAIM_CHUNK_BUDGET_EXCEEDED",
    "CLAIM_CHUNK_EVIDENCE_OUT_OF_SCOPE",
    "CLAIM_CHUNK_SCHEMA_INVALID",
    "CLAIM_CHUNK_STATEMENT_OUT_OF_SCOPE",
    "CLAIM_CHUNK_STATEMENT_UNCOVERED",
    "CLAIM_CHUNK_TRUNCATED",
    "ClaimChunkViolation",
    "ChunkedLiteratureClaimExecution",
    "ChunkedLiteratureClaimService",
    "build_claim_extraction_chunks",
]
