"""Chunked long-paper summary orchestration tests (§35/§38)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryAdmissionStatus,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import (
    DocumentBBox,
    DocumentBlock,
    DocumentBlockKind,
    DocumentPage,
    DocumentParseCandidate,
    DocumentParseProfile,
    DocumentParseQuality,
    ParserBackend,
)
from app.services.document_summary import (
    DocumentSummaryExecution,
    ExecuteDocumentSummaryRequest,
)
from app.services.document_summary_chunks import (
    ChunkedDocumentSummaryExecution,
    ChunkedDocumentSummaryService,
    SummaryChunkViolation,
)
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)

_CONTENT_HASH = "sha256:" + "b" * 64
_CONFIG_HASH = "sha256:" + "c" * 64
_CANONICAL_HASH = "sha256:" + "d" * 64


def _parse_candidate(block_count: int) -> DocumentParseCandidate:
    page = DocumentPage(
        page_index=0,
        width_points=612.0,
        height_points=20_000.0,
        block_ids=tuple(f"b{index}" for index in range(1, block_count + 1)),
    )
    heading = DocumentBlock(
        block_id="b1",
        page_index=0,
        reading_order=1,
        kind=DocumentBlockKind.heading,
        bbox=DocumentBBox(x1=72, y1=72, x2=300, y2=88),
        text="Long Survey",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="chunked-summary-profile",
    )
    blocks = [heading]
    for index in range(2, block_count + 1):
        blocks.append(
            DocumentBlock(
                block_id=f"b{index}",
                page_index=0,
                reading_order=index,
                kind=DocumentBlockKind.paragraph,
                bbox=DocumentBBox(x1=72, y1=100 + index, x2=540, y2=116 + index),
                text=f"Observation paragraph {index} of the survey.",
                quality=DocumentParseQuality.accepted,
                parser_backend=ParserBackend.native,
                parser_profile_id="chunked-summary-profile",
            )
        )
    return DocumentParseCandidate(
        parse_id="parse.chunked-summary",
        research_input_id="00000000-0000-4000-8000-0000000000aa",
        content_hash=_CONTENT_HASH,
        profile=DocumentParseProfile(
            parser_profile_id="chunked-summary-profile",
            parser_profile_version="1.0.0",
            native_backend="native-engine==1.0.0",
            routing_policy_id="native-only",
            resource_policy_id="cpu-capable",
            configuration_hash=_CONFIG_HASH,
        ),
        native_engine="native-engine==1.0.0",
        native_engine_version="1.0.0",
        config_hash=_CONFIG_HASH,
        canonical_output_hash=_CANONICAL_HASH,
        pages=(page,),
        blocks=tuple(blocks),
        overall_quality=DocumentParseQuality.accepted,
        created_at="2026-08-14T00:00:00Z",
    )


def _request(block_count: int) -> ExecuteDocumentSummaryRequest:
    return ExecuteDocumentSummaryRequest(
        document_parse=_parse_candidate(block_count),
        document_parse_id="00000000-0000-4000-8000-0000000000bb",
        source_snapshot=PaperSummarySourceSnapshotReference(
            source_snapshot_id="00000000-0000-4000-8000-0000000000ff",
            source_id="research_input:00000000-0000-4000-8000-0000000000aa",
            source_version=_CONTENT_HASH,
            content_hash=_CONTENT_HASH,
        ),
        paper=PaperSummaryPaperMetadata(
            paper_id="paper.chunked-summary",
            title="Long Survey",
        ),
        source_id="research_input:00000000-0000-4000-8000-0000000000aa",
        source_record_id="long-survey.pdf",
        research_goal="Summarize the survey findings.",
        provider="qwen",
        model="qwen3.8-max",
        model_revision="qwen3.8-max",
        parameters={"temperature": 0, "max_tokens": 2048},
        run_id="00000000-0000-4000-8000-0000000000cc",
        producer_execution_id="execution.chunked-summary",
    )


class _ChunkModel:
    """Answers each chunk with one finding citing that chunk's own Evidence."""

    def __init__(
        self,
        *,
        invent_evidence: bool = False,
        cite_all_evidence: bool = False,
        vary_returned_model: bool = False,
    ) -> None:
        self.requests: list[ModelExecutionRequest] = []
        self.invent_evidence = invent_evidence
        self.cite_all_evidence = cite_all_evidence
        self.vary_returned_model = vary_returned_model

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.requests.append(request)
        paper_payload = request.input_payload["paper_payload"]
        chunk = paper_payload.get("chunk")
        if chunk is None:
            evidence_ids = [item["evidence_id"] for item in paper_payload["evidence"]]
            chunk_id = "single"
        else:
            evidence_ids = [item["evidence_id"] for item in chunk["evidence"]]
            chunk_id = chunk["chunk_id"]
        cited = (
            ["evidence.invented"]
            if self.invent_evidence
            else evidence_ids
            if self.cite_all_evidence
            else [evidence_ids[0]]
        )
        payload = {
            "background": [],
            "methodology": [],
            "dataset": [],
            "experiments": [
                {
                    "statement_id": f"finding.{chunk_id}",
                    "text": f"Chunk {chunk_id} reports an observation.",
                    "evidence_ids": cited,
                }
            ],
            "discussion": [],
            "limitations": [],
            "research_questions": [],
        }
        return ModelExecutionResponse(
            payload=payload,
            output_hash=compute_canonical_payload_hash(payload),
            token_usage={
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            latency_ms=4,
            provider_request_id=f"request-{chunk_id}",
            provider_returned_model=(
                f"qwen3.8-max-route-{len(self.requests) % 2}"
                if self.vary_returned_model
                else "test-returned-model-snapshot"
            ),
        )


def test_small_document_delegates_to_the_single_execution_path() -> None:
    model = _ChunkModel()
    result = ChunkedDocumentSummaryService(model).execute(_request(3))

    assert isinstance(result, DocumentSummaryExecution)
    assert len(model.requests) == 1
    assert "chunk" not in model.requests[0].input_payload["paper_payload"]


def test_long_document_runs_one_bounded_call_per_chunk() -> None:
    model = _ChunkModel()
    result = ChunkedDocumentSummaryService(model).execute(_request(513))

    assert isinstance(result, ChunkedDocumentSummaryExecution)
    assert result.chunk_count == len(model.requests)
    assert result.chunk_count > 1
    assert result.admission.admission_status is PaperSummaryAdmissionStatus.accepted
    summary = result.admission.summary
    assert summary is not None
    experiments = summary.experiments
    assert len(experiments) == result.chunk_count
    # Deterministic statement identities in chunk order.
    assert [item.statement_id for item in experiments] == [
        f"summary.document.experiments.{index:02d}"
        for index in range(1, len(experiments) + 1)
    ]
    # Every finding keeps its chunk Evidence identity.
    assert all(item.evidence_ids for item in experiments)
    assert all(item.status.value == "supported" for item in experiments)
    assert result.token_usage is not None
    assert result.token_usage.total_tokens == 15 * result.chunk_count
    assert result.latency_ms == 4 * result.chunk_count
    assert len(result.chunk_provider_request_ids) == result.chunk_count
    assert result.model_response.provider_request_id is None
    assert result.admission.producer.provider_request_id is None
    assert (
        result.model_response.provider_returned_model == "test-returned-model-snapshot"
    )
    assert (
        result.admission.producer.provider_returned_model
        == "test-returned-model-snapshot"
    )
    assert (
        result.chunk_provider_returned_models
        == ("test-returned-model-snapshot",) * result.chunk_count
    )


def test_oversized_parse_block_keeps_every_bounded_evidence_span() -> None:
    request = _request(2)
    paragraph = request.document_parse.blocks[1]
    long_text = "Observations in the first interval. " * 6000
    request = replace(
        request,
        document_parse=request.document_parse.model_copy(
            update={
                "blocks": (
                    request.document_parse.blocks[0],
                    paragraph.model_copy(update={"text": long_text}),
                ),
            }
        ),
    )
    model = _ChunkModel()
    result = ChunkedDocumentSummaryService(model).execute(request)
    assert isinstance(result, ChunkedDocumentSummaryExecution)
    chunks = [call.input_payload["paper_payload"]["chunk"] for call in model.requests]
    quoted = [item["text"] for chunk in chunks for item in chunk["evidence"]]
    assert "".join(quoted[1:]) == long_text
    assert all(
        sum(len(item["text"]) for item in chunk["evidence"]) <= 12_000
        for chunk in chunks
    )
    assert all("text" not in chunk for chunk in chunks), (
        "do not duplicate full block text outside precise Evidence"
    )


def test_chunked_parent_omits_returned_model_without_child_consensus() -> None:
    result = ChunkedDocumentSummaryService(
        _ChunkModel(vary_returned_model=True)
    ).execute(_request(513))

    assert isinstance(result, ChunkedDocumentSummaryExecution)
    assert len(set(result.chunk_provider_returned_models)) > 1
    assert result.model_response.provider_returned_model is None
    assert result.admission.producer.provider_returned_model is None


def test_chunked_execution_is_deterministic() -> None:
    first = ChunkedDocumentSummaryService(_ChunkModel()).execute(_request(513))
    second = ChunkedDocumentSummaryService(_ChunkModel()).execute(_request(513))
    assert isinstance(first, ChunkedDocumentSummaryExecution)
    assert isinstance(second, ChunkedDocumentSummaryExecution)
    assert first.admission.summary is not None
    assert second.admission.summary is not None
    assert first.admission.summary.output_hash == second.admission.summary.output_hash
    assert first.admission.producer.input_hash == second.admission.producer.input_hash


def test_chunk_statement_citing_foreign_evidence_is_rejected() -> None:
    with pytest.raises(SummaryChunkViolation):
        ChunkedDocumentSummaryService(_ChunkModel(invent_evidence=True)).execute(
            _request(513)
        )


def test_chunk_statement_keeps_all_valid_in_chunk_evidence() -> None:
    result = ChunkedDocumentSummaryService(_ChunkModel(cite_all_evidence=True)).execute(
        _request(513)
    )

    assert isinstance(result, ChunkedDocumentSummaryExecution)
    assert result.admission.admission_status is PaperSummaryAdmissionStatus.accepted
    assert result.admission.summary is not None
    assert (
        max(
            len(statement.evidence_ids)
            for statement in result.admission.summary.experiments
        )
        > 32
    )
