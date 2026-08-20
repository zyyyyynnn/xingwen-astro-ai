"""Production DocumentParse-to-PaperSummary model execution bridge."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
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
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
)
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.workflow.publisher import (
    ArtifactEvidenceBinding,
    ArtifactSourceSnapshotBinding,
    admit_artifact_candidate,
)
from services.paper_pipeline.summary import PaperSummaryPipeline


class _Model:
    def __init__(self, *, tamper_hash: bool = False) -> None:
        self.request: ModelExecutionRequest | None = None
        self.tamper_hash = tamper_hash

    def execute(self, request: ModelExecutionRequest) -> ModelExecutionResponse:
        self.request = request
        evidence_id = request.input_payload["paper_payload"]["evidence"][0][
            "evidence_id"
        ]
        payload = {
            "background": [{
                "statement_id": "summary.document.research_goal",
                "text": "The paper studies transit signals.",
                "evidence_ids": [evidence_id],
            }],
            "methodology": [],
            "dataset": [],
            "experiments": [],
            "discussion": [],
            "limitations": [],
            "research_questions": [],
            "evidence_ids": [evidence_id],
        }
        output_hash = compute_canonical_payload_hash(payload)
        if self.tamper_hash:
            output_hash = "sha256:" + "0" * 64
        return ModelExecutionResponse(
            payload=payload,
            output_hash=output_hash,
            token_usage={
                "prompt_tokens": 100,
                "completion_tokens": 25,
                "total_tokens": 125,
            },
            latency_ms=37,
            provider_request_id="request-qwen-1",
        )


_CONTENT_HASH = "sha256:" + "b" * 64
_CONFIG_HASH = "sha256:" + "c" * 64
_CANONICAL_HASH = "sha256:" + "d" * 64
_PARAGRAPH_TEXT = "The paper studies transit signals."


def _parse_candidate() -> DocumentParseCandidate:
    page = DocumentPage(
        page_index=0, width_points=612.0, height_points=792.0, block_ids=("b1", "b2")
    )
    heading = DocumentBlock(
        block_id="b1",
        page_index=0,
        reading_order=1,
        kind=DocumentBlockKind.heading,
        bbox=DocumentBBox(x1=72, y1=72, x2=300, y2=88),
        text="Transit Study",
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="document-summary-profile",
    )
    paragraph = DocumentBlock(
        block_id="b2",
        page_index=0,
        reading_order=2,
        kind=DocumentBlockKind.paragraph,
        bbox=DocumentBBox(x1=72, y1=100, x2=540, y2=116),
        text=_PARAGRAPH_TEXT,
        quality=DocumentParseQuality.accepted,
        parser_backend=ParserBackend.native,
        parser_profile_id="document-summary-profile",
    )
    return DocumentParseCandidate(
        parse_id="parse.document-summary",
        research_input_id="00000000-0000-4000-8000-0000000000aa",
        content_hash=_CONTENT_HASH,
        profile=DocumentParseProfile(
            parser_profile_id="document-summary-profile",
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
        blocks=(heading, paragraph),
        overall_quality=DocumentParseQuality.accepted,
        created_at="2026-08-14T00:00:00Z",
    )


def _request() -> ExecuteDocumentSummaryRequest:
    return ExecuteDocumentSummaryRequest(
        document_parse=_parse_candidate(),
        document_parse_id="00000000-0000-4000-8000-0000000000bb",
        source_snapshot=PaperSummarySourceSnapshotReference(
            source_snapshot_id="source-snapshot.document-summary",
            source_id="research-input",
            source_version=_CONTENT_HASH,
            content_hash=_CONTENT_HASH,
        ),
        paper=PaperSummaryPaperMetadata(
            paper_id="paper.document-summary",
            title="Transit Study",
        ),
        source_id="research-input",
        source_record_id="transit-study.pdf",
        research_goal="Summarize the transit method.",
        provider="qwen",
        model="qwen3.8-max",
        model_revision="qwen3.8-max",
        parameters={"temperature": 0, "max_tokens": 2048},
        run_id="00000000-0000-4000-8000-0000000000cc",
        producer_execution_id="execution.document-summary",
    )


def test_document_summary_executes_real_model_port_and_records_metadata() -> None:
    model = _Model()
    pipeline = PaperSummaryPipeline(
        clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc)
    )
    result = DocumentSummaryService(model, pipeline=pipeline).execute(_request())

    assert model.request is not None
    assert model.request.prompt_name == "paper_summary"
    assert model.request.input_payload["paper_payload"]["evidence"][0]["locator"]
    assert result.admission.summary is not None
    producer = result.admission.summary.producer
    assert producer.provider == "qwen"
    assert producer.model_revision == "qwen3.8-max"
    assert producer.provider_request_id == "request-qwen-1"
    assert producer.latency_ms == 37
    assert producer.usage is not None and producer.usage.total_tokens == 125
    assert result.admission.summary.paper is not None
    assert result.admission.summary.input_versions.document_parses


def test_document_summary_prepares_exact_identity_before_model_execution() -> None:
    request = _request()
    model = _Model()
    service = DocumentSummaryService(model)

    prepared = service.prepare(request)

    assert model.request is None
    assert prepared.input_hash.startswith("sha256:")
    result = service.execute_prepared(
        prepared,
        producer_execution_id="execution.document-summary.fixed",
    )
    assert result.admission.producer.input_hash == prepared.input_hash
    assert (
        result.admission.producer.execution_id
        == "execution.document-summary.fixed"
    )


def test_document_summary_rejects_model_hash_drift() -> None:
    with pytest.raises(ValueError, match="output hash mismatch"):
        DocumentSummaryService(_Model(tamper_hash=True)).execute(_request())


def test_admitted_document_summary_closes_persisted_provenance_bindings() -> None:
    result = DocumentSummaryService(_Model()).execute(_request())
    summary = result.admission.summary
    assert summary is not None
    persisted_snapshot_id = str(uuid4())
    bindings = tuple(
        ArtifactEvidenceBinding(
            target_type="paper_summary",
            target_id=next(
                statement.statement_id
                for statement in summary.statements()
                if item.evidence_id in statement.evidence_ids
            ),
            pipeline_evidence_id=item.evidence_id,
            pipeline_source_snapshot_id=item.source_snapshot_id,
            persisted_evidence_id=str(uuid4()),
            persisted_source_snapshot_id=persisted_snapshot_id,
        )
        for item in summary.evidence
    )

    admitted = admit_artifact_candidate(
        summary,
        schema_version=summary.schema_version,
        source_snapshot_ids=tuple(
            item.source_snapshot_id for item in summary.input_versions.source_snapshots
        ),
        evidence_ids=summary.evidence_ids,
        evidence_validator=lambda _context: None,
        domain_validator=lambda _context: None,
        quality_validator=lambda _context: None,
        source_snapshot_bindings=(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=(
                    summary.input_versions.source_snapshots[0].source_snapshot_id
                ),
                persisted_source_snapshot_id=persisted_snapshot_id,
            ),
        ),
        evidence_bindings=bindings,
    )

    assert admitted.source_snapshot_ids == (persisted_snapshot_id,)
    assert admitted.content["output_hash"] == summary.output_hash
    assert set(admitted.evidence_ids) == {
        item.persisted_evidence_id for item in bindings
    }
