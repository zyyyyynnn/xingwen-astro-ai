"""Bounded model extraction for Claims from large PaperSummary artifacts.

The published PaperSummary remains the sole scientific input authority. Model
calls receive only the statement fields required to author Claims; Evidence
objects, locators, ProducerExecution metadata and artifact hashes remain at the
deterministic admission boundary instead of being copied into every request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

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
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from packages.prompts.registry import PromptRegistry


MAX_CLAIM_STATEMENTS_PER_CHUNK = 8
MAX_CLAIM_STATEMENT_CHARACTERS_PER_CHUNK = 4_000
MAX_CLAIMS_PER_STATEMENT = 4


class ClaimChunkCoverageError(ValueError):
    """A model batch did not preserve the frozen Summary statement boundary."""


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

        for chunk in chunks:
            response = self._models.execute(
                ModelExecutionRequest(
                    provider=provider,
                    requested_model=model,
                    explicit_revision=model_revision,
                    prompt_name=prompt.name,
                    prompt_version=prompt.version,
                    prompt_hash=prompt.content_hash,
                    prompt=prompt.content,
                    input_payload={
                        "paper_summary_artifact": _chunk_model_input(
                            summary=summary,
                            paper_summary_artifact_version_id=(
                                paper_summary_artifact_version_id
                            ),
                            chunk=chunk,
                        )
                    },
                    parameters=dict(parameters),
                    response_mode="json",
                    enable_thinking=True,
                )
            )
            _validate_model_response(response)
            extraction = LiteratureClaimExtractionOutput.model_validate(
                response.payload
            )
            _validate_chunk_coverage(chunk, extraction)
            claims.extend(extraction.claims)
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
        raise ClaimChunkCoverageError(
            "PaperSummary has no evidence-bearing statements for Claim extraction"
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
            raise ClaimChunkCoverageError(
                f"{chunk.chunk_id} referenced a statement outside its batch"
            )
        if not set(claim.evidence_ids).issubset(statement.evidence_ids):
            raise ClaimChunkCoverageError(
                f"{chunk.chunk_id} referenced Evidence outside its source statement"
            )
        counts[claim.source_statement_id] += 1
        if counts[claim.source_statement_id] > MAX_CLAIMS_PER_STATEMENT:
            raise ClaimChunkCoverageError(
                f"{chunk.chunk_id} exceeded the per-statement Claim budget"
            )
    missing = tuple(
        statement_id for statement_id, count in counts.items() if count == 0
    )
    if missing:
        raise ClaimChunkCoverageError(
            f"{chunk.chunk_id} did not cover {len(missing)} source statements"
        )


def _consensus_returned_model(models: list[str | None]) -> str | None:
    if not models or any(model is None for model in models):
        return None
    distinct = set(models)
    return next(iter(distinct)) if len(distinct) == 1 else None


__all__ = [
    "ClaimChunkCoverageError",
    "ChunkedLiteratureClaimExecution",
    "ChunkedLiteratureClaimService",
    "build_claim_extraction_chunks",
]
