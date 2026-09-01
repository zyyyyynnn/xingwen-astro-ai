"""Chunked DocumentParse-backed summary execution for long papers.

§38: a parsed document that exceeds the bounded single-execution budget must
use the summary_chunks path instead of truncation. This service:

1. projects parse blocks into section-aware ``SummaryChunk`` objects carrying
   the Evidence identity of every contributing block;
2. executes one bounded governed model call per chunk;
3. refuses any chunk statement that cites Evidence outside that chunk;
4. deterministically reduces per-chunk outputs into the current
   ``PaperSummaryModelOutput`` shape (no second model call, no invented
   provenance) and admits the result through the canonical document
   admission path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from pydantic import ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryAdmissionResult,
    PaperSummaryEvidenceCandidate,
    PaperSummaryModelOutput,
    PaperSummaryModelUsage,
    PaperSummarySectionKind,
)
from app.services.document_summary import (
    DocumentSummaryExecution,
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
    MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS,
    MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS,
)
from app.services.model_execution import (
    ModelExecutionError,
    ModelExecutionPort,
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from packages.prompts.registry import PromptRegistry
from services.paper_pipeline.summary import (
    PaperSummaryPipeline,
    build_document_evidence_candidates,
)
from services.paper_pipeline.summary_chunks import (
    ChunkSectionExtraction,
    ChunkDocumentBlock,
    SectionStatement,
    SummaryChunk,
    build_summary_chunks,
    reduce_chunk_sections,
)


DOCUMENT_SUMMARY_CHUNK_SCHEMA_INVALID = "DOCUMENT_SUMMARY_CHUNK_SCHEMA_INVALID"
DOCUMENT_SUMMARY_CHUNK_EVIDENCE_OUT_OF_SCOPE = (
    "DOCUMENT_SUMMARY_CHUNK_EVIDENCE_OUT_OF_SCOPE"
)
DOCUMENT_SUMMARY_CHUNK_TRUNCATED = "DOCUMENT_SUMMARY_CHUNK_TRUNCATED"

_MODEL_RESPONSE_TRUNCATED = "MODEL_RESPONSE_TRUNCATED"


class SummaryChunkViolation(ValueError):
    """Typed, stable Summary chunk-contract violation after bounded recovery."""

    def __init__(
        self,
        *,
        code: str,
        chunk_id: str,
        affected_evidence_ids: tuple[str, ...] = (),
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.chunk_id = chunk_id
        self.affected_evidence_ids = affected_evidence_ids


@dataclass(frozen=True, slots=True)
class ChunkedDocumentSummaryExecution:
    admission: PaperSummaryAdmissionResult
    model_response: ModelExecutionResponse
    chunk_count: int
    chunk_provider_request_ids: tuple[str | None, ...]
    chunk_provider_returned_models: tuple[str | None, ...]
    token_usage: PaperSummaryModelUsage | None
    latency_ms: int
    correction_count: int = 0
    split_count: int = 0


def fits_single_execution(
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
) -> bool:
    character_count = sum(len(item.quote_or_value) for item in evidence)
    return (
        len(evidence) <= MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS
        and character_count <= MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS
    )


class ChunkedDocumentSummaryService:
    """Bounded chunked extraction with deterministic evidence-preserving merge."""

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
        self._single = DocumentSummaryService(
            model_execution,
            prompt_registry=self._prompts,
            pipeline=self._pipeline,
        )

    def execute(
        self, request: ExecuteDocumentSummaryRequest
    ) -> DocumentSummaryExecution | ChunkedDocumentSummaryExecution:
        evidence = build_document_evidence_candidates(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            paper_id=request.paper.paper_id,
            source_id=request.source_id,
            source_record_id=request.source_record_id,
            source_snapshot_id=request.source_snapshot.source_snapshot_id,
        )
        if fits_single_execution(evidence):
            return self._single.execute(request)
        return self._execute_chunked(request, evidence)

    def _execute_chunked(
        self,
        request: ExecuteDocumentSummaryRequest,
        evidence: tuple[PaperSummaryEvidenceCandidate, ...],
    ) -> ChunkedDocumentSummaryExecution:
        chunks = _build_chunks(evidence)
        chunk_sections: list[dict[str, tuple[SectionStatement, ...]]] = []
        request_ids: list[str | None] = []
        returned_models: list[str | None] = []
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage_complete = True
        latency_total = 0
        correction_total = 0
        split_total = 0
        for chunk in chunks:
            responses, sections, corrections, splits = (
                _execute_summary_chunk_with_bounded_recovery(
                    self._models,
                    prompts=self._prompts,
                    request=request,
                    chunk=chunk,
                    evidence=evidence,
                )
            )
            correction_total += corrections
            split_total += splits
            for response in responses:
                if response.token_usage is None:
                    usage_complete = False
                else:
                    for key in usage_totals:
                        value = response.token_usage.get(key)
                        if not isinstance(value, int) or isinstance(value, bool):
                            usage_complete = False
                        else:
                            usage_totals[key] += value
                latency_total += response.latency_ms
                request_ids.append(response.provider_request_id)
                returned_models.append(response.provider_returned_model)
            chunk_sections.append(sections)

        merged_payload = _reduce_chunk_outputs(chunks, chunk_sections)
        model_response = json.dumps(
            merged_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        aggregate_returned_model = _consensus_returned_model(returned_models)
        admission = self._pipeline.admit_document(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            source_snapshot=request.source_snapshot,
            paper=request.paper,
            model_response=model_response,
            model_name=request.model,
            model_revision=request.model_revision,
            provider=request.provider,
            provider_returned_model=aggregate_returned_model,
            provider_request_id=None,
            usage=(
                PaperSummaryModelUsage.model_validate(usage_totals)
                if usage_complete
                else None
            ),
            latency_ms=latency_total,
            parameters=request.parameters,
            evidence_candidates=evidence,
            run_id=request.run_id,
            execution_id=request.producer_execution_id,
        )
        aggregate_response = ModelExecutionResponse(
            payload=merged_payload,
            output_hash=compute_canonical_payload_hash(merged_payload),
            token_usage=usage_totals if usage_complete else None,
            latency_ms=latency_total,
            provider_request_id=None,
            provider_returned_model=aggregate_returned_model,
        )
        return ChunkedDocumentSummaryExecution(
            admission=admission,
            model_response=aggregate_response,
            chunk_count=len(chunks),
            chunk_provider_request_ids=tuple(request_ids),
            chunk_provider_returned_models=tuple(returned_models),
            token_usage=(
                PaperSummaryModelUsage.model_validate(usage_totals)
                if usage_complete
                else None
            ),
            latency_ms=latency_total,
            correction_count=correction_total,
            split_count=split_total,
        )


def _consensus_returned_model(models: list[str | None]) -> str | None:
    """Summarize complete, identical child model facts without inventing one."""

    if not models or any(model is None for model in models):
        return None
    distinct = set(models)
    return next(iter(distinct)) if len(distinct) == 1 else None


def _build_chunks(
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
) -> tuple[SummaryChunk, ...]:
    """Chunk canonical Evidence excerpts, including every span of a large block.

    Chunk units use Evidence identity: original page/block/span identity remains
    on each candidate's locator. No full block is paired with just its first quote.
    """
    blocks: list[ChunkDocumentBlock] = []
    for order, candidate in enumerate(evidence):
        locator = candidate.locator.document_locator
        if locator is None or locator.text_span is None:
            raise ValueError("document chunk evidence requires a precise text span")
        blocks.append(
            ChunkDocumentBlock(
                block_id=candidate.evidence_id,
                page_index=locator.page_index,
                reading_order=order,
                section=candidate.locator.section,
                text=candidate.quote_or_value,
            )
        )
    return build_summary_chunks(
        blocks, {item.evidence_id: item.evidence_id for item in evidence}
    )


def _chunk_request(
    prompts: PromptRegistry,
    request: ExecuteDocumentSummaryRequest,
    chunk: SummaryChunk,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
    validation_feedback: dict[str, Any] | None = None,
) -> ModelExecutionRequest:
    prompt = prompts.get("paper_summary")
    chunk_evidence = set(chunk.evidence_ids)
    evidence_by_id = {
        candidate.evidence_id: candidate
        for candidate in evidence
        if candidate.evidence_id in chunk_evidence
    }
    input_payload = {
        "research_goal": request.research_goal,
        "paper_payload": {
            "paper": request.paper.model_dump(mode="json"),
            "chunk": {
                "chunk_id": chunk.chunk_id,
                "order": chunk.order,
                "section_hint": chunk.section_hint,
                "evidence": [
                    {
                        "evidence_id": evidence_id,
                        "section": evidence_by_id[evidence_id].locator.section,
                        "text": evidence_by_id[evidence_id].quote_or_value,
                    }
                    for evidence_id in chunk.evidence_ids
                    if evidence_id in evidence_by_id
                ],
            },
        },
    }
    if validation_feedback is not None:
        input_payload["validation_feedback"] = validation_feedback
    return ModelExecutionRequest(
        provider=request.provider,
        requested_model=request.model,
        explicit_revision=request.model_revision,
        prompt_name=prompt.name,
        prompt_version=prompt.version,
        prompt_hash=prompt.content_hash,
        prompt=prompt.content,
        input_payload=input_payload,
        parameters=dict(request.parameters),
    )


def _validate_chunk_response(response: ModelExecutionResponse) -> None:
    if response.latency_ms < 0:
        raise ValueError("model response latency must be non-negative")
    expected_hash = compute_canonical_payload_hash(response.payload)
    if response.output_hash != expected_hash:
        raise ValueError("model response output hash mismatch")


def _enforce_chunk_evidence_allowlist(
    chunk: SummaryChunk, output: PaperSummaryModelOutput
) -> None:
    allowed = set(chunk.evidence_ids)
    for statement in output.statements():
        unknown = set(statement.evidence_ids) - allowed
        if unknown:
            raise SummaryChunkViolation(
                code=DOCUMENT_SUMMARY_CHUNK_EVIDENCE_OUT_OF_SCOPE,
                chunk_id=chunk.chunk_id,
                affected_evidence_ids=tuple(sorted(unknown)),
                message=(
                    f"{chunk.chunk_id} references evidence ids outside its chunk: "
                    f"{sorted(unknown)}"
                ),
            )


def _chunk_sections(
    output: PaperSummaryModelOutput,
) -> dict[str, tuple[SectionStatement, ...]]:
    return {
        section.value: tuple(
            SectionStatement(
                text=statement.text,
                evidence_ids=statement.evidence_ids,
            )
            for statement in getattr(output, section.value)
        )
        for section in PaperSummarySectionKind
    }


def _merged_half_sections(
    left: dict[str, tuple[SectionStatement, ...]],
    right: dict[str, tuple[SectionStatement, ...]],
) -> dict[str, tuple[SectionStatement, ...]]:
    return {section: left[section] + right[section] for section in left}


def _reduce_chunk_outputs(
    chunks: tuple[SummaryChunk, ...],
    chunk_sections: list[dict[str, tuple[SectionStatement, ...]]],
) -> dict[str, Any]:
    """Use the canonical seven-section reducer for the final model payload."""

    if len(chunks) != len(chunk_sections):
        raise ValueError("chunk output count does not match the frozen chunk plan")
    reduced = reduce_chunk_sections(
        tuple(
            ChunkSectionExtraction(
                chunk_id=chunk.chunk_id,
                chunk_evidence_ids=chunk.evidence_ids,
                sections=sections,
            )
            for chunk, sections in zip(chunks, chunk_sections, strict=True)
        )
    )
    payload: dict[str, Any] = {section.section: [] for section in reduced}
    for section in reduced:
        for index, statement in enumerate(section.statements, start=1):
            payload[section.section].append(
                {
                    "statement_id": (f"summary.document.{section.section}.{index:02d}"),
                    "text": statement.text,
                    "evidence_ids": list(statement.evidence_ids),
                }
            )
    # Validate the merged shape before admission (fail closed on any drift).
    PaperSummaryModelOutput.model_validate(payload)
    return payload


def _execute_summary_chunk_with_bounded_recovery(
    models: ModelExecutionPort,
    *,
    prompts: PromptRegistry,
    request: ExecuteDocumentSummaryRequest,
    chunk: SummaryChunk,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
) -> tuple[
    tuple[ModelExecutionResponse, ...],
    dict[str, tuple[SectionStatement, ...]],
    int,
    int,
]:
    def run(
        target: SummaryChunk,
        feedback: dict[str, Any] | None,
    ) -> tuple[ModelExecutionResponse, PaperSummaryModelOutput]:
        response = models.execute(
            _chunk_request(prompts, request, target, evidence, feedback)
        )
        _validate_chunk_response(response)
        try:
            output = PaperSummaryModelOutput.model_validate(response.payload)
        except ValidationError as exc:
            raise SummaryChunkViolation(
                code=DOCUMENT_SUMMARY_CHUNK_SCHEMA_INVALID,
                chunk_id=target.chunk_id,
                message=f"{target.chunk_id} model output did not match the Summary schema",
            ) from exc
        _enforce_chunk_evidence_allowlist(target, output)
        return response, output

    try:
        response, output = run(chunk, None)
        return (response,), _chunk_sections(output), 0, 0
    except ModelExecutionError as exc:
        if exc.code != _MODEL_RESPONSE_TRUNCATED:
            raise
        return _recover_truncated_summary_chunk(
            run=run,
            chunk=chunk,
            evidence=evidence,
        )
    except SummaryChunkViolation as violation:
        try:
            response, output = run(
                chunk,
                _chunk_validation_feedback(
                    chunk,
                    code=violation.code,
                    affected_evidence_ids=violation.affected_evidence_ids,
                ),
            )
        except SummaryChunkViolation as correction_violation:
            raise correction_violation from violation
        except ModelExecutionError as correction_error:
            if correction_error.code == _MODEL_RESPONSE_TRUNCATED:
                raise SummaryChunkViolation(
                    code=DOCUMENT_SUMMARY_CHUNK_TRUNCATED,
                    chunk_id=chunk.chunk_id,
                    affected_evidence_ids=violation.affected_evidence_ids,
                    message=f"{chunk.chunk_id} correction response was truncated",
                ) from violation
            raise
        return (response,), _chunk_sections(output), 1, 0


def _recover_truncated_summary_chunk(
    *,
    run,
    chunk: SummaryChunk,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
) -> tuple[
    tuple[ModelExecutionResponse, ...],
    dict[str, tuple[SectionStatement, ...]],
    int,
    int,
]:
    if len(chunk.block_ids) < 2:
        try:
            response, output = run(
                chunk,
                _chunk_validation_feedback(
                    chunk,
                    code=DOCUMENT_SUMMARY_CHUNK_TRUNCATED,
                    affected_evidence_ids=tuple(chunk.block_ids),
                    concise=True,
                ),
            )
        except ModelExecutionError as exc:
            if exc.code == _MODEL_RESPONSE_TRUNCATED:
                raise SummaryChunkViolation(
                    code=DOCUMENT_SUMMARY_CHUNK_TRUNCATED,
                    chunk_id=chunk.chunk_id,
                    affected_evidence_ids=tuple(chunk.block_ids),
                    message=(
                        f"{chunk.chunk_id} single-block output remained truncated"
                    ),
                ) from exc
            raise
        return (response,), _chunk_sections(output), 1, 1

    middle = (len(chunk.block_ids) + 1) // 2
    text_by_id = {item.evidence_id: item.quote_or_value for item in evidence}
    halves = tuple(
        SummaryChunk(
            chunk_id=f"{chunk.chunk_id}{suffix}",
            order=chunk.order,
            section_hint=chunk.section_hint,
            block_ids=ids,
            evidence_ids=ids,
            text="\n\n".join(text_by_id.get(item, "") for item in ids),
        )
        for suffix, ids in zip(
            ("L", "R"),
            (chunk.block_ids[:middle], chunk.block_ids[middle:]),
            strict=True,
        )
    )
    responses: list[ModelExecutionResponse] = []
    half_sections: list[dict[str, tuple[SectionStatement, ...]]] = []
    for half in halves:
        try:
            response, output = run(half, None)
        except ModelExecutionError as exc:
            if exc.code == _MODEL_RESPONSE_TRUNCATED:
                raise SummaryChunkViolation(
                    code=DOCUMENT_SUMMARY_CHUNK_TRUNCATED,
                    chunk_id=half.chunk_id,
                    affected_evidence_ids=tuple(half.block_ids),
                    message=(
                        f"{half.chunk_id} remained truncated at the split depth limit"
                    ),
                ) from exc
            raise
        except SummaryChunkViolation as violation:
            try:
                response, output = run(
                    half,
                    _chunk_validation_feedback(
                        half,
                        code=violation.code,
                        affected_evidence_ids=violation.affected_evidence_ids,
                    ),
                )
            except SummaryChunkViolation as correction_violation:
                raise correction_violation from violation
            except ModelExecutionError as correction_error:
                if correction_error.code == _MODEL_RESPONSE_TRUNCATED:
                    raise SummaryChunkViolation(
                        code=DOCUMENT_SUMMARY_CHUNK_TRUNCATED,
                        chunk_id=half.chunk_id,
                        affected_evidence_ids=violation.affected_evidence_ids,
                        message=f"{half.chunk_id} correction response was truncated",
                    ) from violation
                raise
        responses.append(response)
        half_sections.append(_chunk_sections(output))
    merged = _merged_half_sections(half_sections[0], half_sections[1])
    return tuple(responses), merged, 0, 1


def _chunk_validation_feedback(
    chunk: SummaryChunk,
    *,
    code: str,
    affected_evidence_ids: tuple[str, ...],
    concise: bool = False,
) -> dict[str, Any]:
    feedback: dict[str, Any] = {
        "code": code,
        "required_evidence_ids": list(chunk.evidence_ids),
        "affected_evidence_ids": list(affected_evidence_ids),
    }
    if concise:
        feedback["concise_output"] = True
    return feedback


__all__ = [
    "ChunkedDocumentSummaryExecution",
    "ChunkedDocumentSummaryService",
    "SummaryChunkViolation",
    "fits_single_execution",
]
