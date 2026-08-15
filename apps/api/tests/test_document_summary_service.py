"""Production DocumentParse-to-PaperSummary model execution bridge."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from uuid import uuid4

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import DocumentParseInput
from app.services.document_summary import (
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
)
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.services.scientific_document.parser import ScientificDocumentParser
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
        empty = lambda kind: {  # noqa: E731
            "section_kind": kind,
            "overview": None,
            "items": [],
        }
        payload = {
            "background": {
                "section_kind": "background",
                "overview": {
                    "statement_id": "summary.document.background",
                    "item_kind": "narrative",
                    "text": "The paper studies transit signals.",
                    "evidence_ids": [evidence_id],
                },
                "items": [],
            },
            "methodology": empty("methodology"),
            "dataset": empty("dataset"),
            "experiments": empty("experiments"),
            "discussion": empty("discussion"),
            "limitations": empty("limitations"),
            "research_questions": empty("research_questions"),
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


def _request() -> ExecuteDocumentSummaryRequest:
    content = b"# Transit Study\n\nThe paper studies transit signals."
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    parsed = ScientificDocumentParser().parse_document(
        DocumentParseInput(
            research_input_id="research-input.document-summary",
            content_hash=content_hash,
            source_type="upload",
            mime_type="text/markdown",
            filename="transit.md",
            input_bytes=content,
        )
    )
    return ExecuteDocumentSummaryRequest(
        document_parse=parsed,
        document_parse_id="document-parse.document-summary",
        source_snapshot=PaperSummarySourceSnapshotReference(
            source_snapshot_id="source-snapshot.document-summary",
            source_id="research-input",
            source_version=content_hash,
            content_hash=content_hash,
        ),
        paper=PaperSummaryPaperMetadata(
            paper_id="paper.document-summary",
            title="Transit Study",
        ),
        source_id="research-input",
        source_record_id="transit.md",
        research_goal="Summarize the transit method.",
        provider="qwen",
        model="qwen-plus",
        model_revision="qwen-plus-2026-07-28",
        parameters={"temperature": 0, "max_tokens": 2048},
        run_id="run.document-summary",
        producer_execution_id="execution.document-summary",
    )


def test_document_summary_executes_real_model_port_and_records_metadata() -> None:
    model = _Model()
    pipeline = PaperSummaryPipeline(
        clock=lambda: datetime(2026, 8, 14, tzinfo=timezone.utc)
    )
    result = DocumentSummaryService(model, pipeline=pipeline).execute(_request())

    assert model.request is not None
    assert "{{" not in model.request.prompt
    assert model.request.input_payload["paper_payload"]["evidence"][0]["locator"]
    assert result.admission.summary is not None
    producer = result.admission.summary.producer
    assert producer.provider == "qwen"
    assert producer.model_revision == "qwen-plus-2026-07-28"
    assert producer.provider_request_id == "request-qwen-1"
    assert producer.latency_ms == 37
    assert producer.usage is not None and producer.usage.total_tokens == 125


def test_document_summary_prepares_exact_identity_before_model_execution() -> None:
    request = _request()
    model = _Model()
    service = DocumentSummaryService(model)

    prepared = service.prepare(request)

    assert model.request is None
    assert prepared.input_hash.startswith("sha256:")
    result = service.execute_prepared(
        prepared,
        producer_execution_id="00000000-0000-4000-8000-000000000001",
    )
    assert result.admission.producer.input_hash == prepared.input_hash
    assert (
        result.admission.producer.execution_id
        == "00000000-0000-4000-8000-000000000001"
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
            target_id=summary.summary_id,
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
    assert all(
        item.extraction_method == "paper_summary_admission"
        for item in admitted.literature_evidence_materializations
    )
