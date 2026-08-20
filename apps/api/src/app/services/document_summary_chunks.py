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

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryAdmissionResult,
    PaperSummaryEvidenceCandidate,
    PaperSummaryModelOutput,
    PaperSummaryModelUsage,
    PaperSummarySectionKind,
)
from app.schemas.scientific_document import (
    DocumentBlockKind,
    DocumentParseQuality,
)
from app.services.document_summary import (
    DocumentSummaryExecution,
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
    MAX_SINGLE_EXECUTION_EVIDENCE_CHARACTERS,
    MAX_SINGLE_EXECUTION_EVIDENCE_ITEMS,
)
from app.services.model_execution import (
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

_MAX_STATEMENTS_PER_FIELD_PER_CHUNK = 32


class ChunkEvidenceViolationError(ValueError):
    """A chunk output cited Evidence identity outside its own chunk."""


@dataclass(frozen=True, slots=True)
class ChunkedDocumentSummaryExecution:
    admission: PaperSummaryAdmissionResult
    chunk_count: int
    chunk_provider_request_ids: tuple[str | None, ...]
    token_usage: PaperSummaryModelUsage | None
    latency_ms: int


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
        self._pipeline = pipeline or PaperSummaryPipeline(
            prompt_registry=self._prompts
        )
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
        chunks = _build_chunks(request, evidence)
        chunk_outputs: list[PaperSummaryModelOutput] = []
        request_ids: list[str | None] = []
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        usage_complete = True
        latency_total = 0
        for chunk in chunks:
            response = self._models.execute(
                _chunk_request(self._prompts, request, chunk, evidence)
            )
            _validate_chunk_response(response)
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
            output = PaperSummaryModelOutput.model_validate(response.payload)
            _enforce_chunk_evidence_allowlist(chunk, output)
            chunk_outputs.append(output)

        merged_payload = _reduce_chunk_outputs(chunks, chunk_outputs)
        model_response = json.dumps(
            merged_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        admission = self._pipeline.admit_document(
            document_parse=request.document_parse,
            document_parse_id=request.document_parse_id,
            source_snapshot=request.source_snapshot,
            paper=request.paper,
            model_response=model_response,
            model_name=request.model,
            model_revision=request.model_revision,
            provider=request.provider,
            provider_request_id=request_ids[0] if request_ids else None,
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
        return ChunkedDocumentSummaryExecution(
            admission=admission,
            chunk_count=len(chunks),
            chunk_provider_request_ids=tuple(request_ids),
            token_usage=(
                PaperSummaryModelUsage.model_validate(usage_totals)
                if usage_complete
                else None
            ),
            latency_ms=latency_total,
        )


def _build_chunks(
    request: ExecuteDocumentSummaryRequest,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
) -> tuple[SummaryChunk, ...]:
    """Project parse blocks into chunks with per-block Evidence identity."""

    first_evidence_by_block: dict[str, str] = {}
    for candidate in evidence:
        locator = candidate.locator.document_locator
        if locator is None or locator.block_id is None:
            continue
        first_evidence_by_block.setdefault(locator.block_id, candidate.evidence_id)

    blocks: list[ChunkDocumentBlock] = []
    section: str | None = None
    ordered = sorted(
        request.document_parse.blocks,
        key=lambda block: (
            block.page_index,
            block.reading_order if block.reading_order is not None else 0,
            block.block_id,
        ),
    )
    for block in ordered:
        if block.kind is DocumentBlockKind.heading and block.text:
            section = block.text[:512]
        if (
            block.kind is DocumentBlockKind.reference
            or block.text is None
            or block.quality is DocumentParseQuality.unsupported
        ):
            continue
        blocks.append(
            ChunkDocumentBlock(
                block_id=block.block_id,
                page_index=block.page_index,
                text=block.text,
                section=section,
                reading_order=block.reading_order,
            )
        )
    return build_summary_chunks(blocks, first_evidence_by_block)


def _chunk_request(
    prompts: PromptRegistry,
    request: ExecuteDocumentSummaryRequest,
    chunk: SummaryChunk,
    evidence: tuple[PaperSummaryEvidenceCandidate, ...],
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
                "text": chunk.text,
            },
        },
    }
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
        if len(statement.evidence_ids) > _MAX_STATEMENTS_PER_FIELD_PER_CHUNK:
            raise ValueError(
                f"{chunk.chunk_id} statement exceeds the evidence budget"
            )
        unknown = set(statement.evidence_ids) - allowed
        if unknown:
            raise ChunkEvidenceViolationError(
                f"{chunk.chunk_id} references evidence ids outside its chunk: "
                f"{sorted(unknown)}"
            )


def _reduce_chunk_outputs(
    chunks: tuple[SummaryChunk, ...],
    chunk_outputs: list[PaperSummaryModelOutput],
) -> dict[str, Any]:
    """Use the canonical seven-section reducer for the final model payload."""

    if len(chunks) != len(chunk_outputs):
        raise ValueError("chunk output count does not match the frozen chunk plan")
    reduced = reduce_chunk_sections(
        tuple(
            ChunkSectionExtraction(
                chunk_id=chunk.chunk_id,
                chunk_evidence_ids=chunk.evidence_ids,
                sections={
                    section.value: tuple(
                        SectionStatement(
                            text=statement.text,
                            evidence_ids=statement.evidence_ids,
                        )
                        for statement in getattr(output, section.value)
                    )
                    for section in PaperSummarySectionKind
                },
            )
            for chunk, output in zip(chunks, chunk_outputs, strict=True)
        )
    )
    payload: dict[str, Any] = {
        section.section: [] for section in reduced
    }
    all_evidence: set[str] = set()
    for section in reduced:
        for index, statement in enumerate(section.statements, start=1):
            all_evidence.update(statement.evidence_ids)
            payload[section.section].append(
                {
                    "statement_id": (
                        f"summary.document.{section.section}.{index:02d}"
                    ),
                    "text": statement.text,
                    "evidence_ids": list(statement.evidence_ids),
                }
            )
    payload["evidence_ids"] = sorted(all_evidence)
    # Validate the merged shape before admission (fail closed on any drift).
    PaperSummaryModelOutput.model_validate(payload)
    return payload


__all__ = [
    "ChunkEvidenceViolationError",
    "ChunkedDocumentSummaryExecution",
    "ChunkedDocumentSummaryService",
    "fits_single_execution",
]
