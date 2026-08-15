"""DocumentParse provenance survives the PaperSummary read boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    SourceMode,
    SourceSnapshotDetail,
)
from app.schemas.paper_summary import (
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import DocumentParseInput
from app.security import SecurityProblem
from app.services.paper_summaries import PaperSummaryReadService
from app.services.scientific_document.parser import ScientificDocumentParser
from services.paper_pipeline.summary import (
    PaperSummaryPipeline,
    build_document_evidence_candidates,
)

NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
PROJECT_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
INPUT_ID = "33333333-3333-4333-8333-333333333333"
SNAPSHOT_ID = "44444444-4444-4444-8444-444444444444"
PARSE_ID = "55555555-5555-4555-8555-555555555555"
VERSION_ID = "66666666-6666-4666-8666-666666666666"


def _model_output(evidence_id: str) -> str:
    import json

    empty = lambda kind: {  # noqa: E731
        "section_kind": kind,
        "overview": None,
        "items": [],
    }
    return json.dumps(
        {
            "background": {
                "section_kind": "background",
                "overview": {
                    "statement_id": "summary.document.background",
                    "item_kind": "narrative",
                    "text": "The paper studies a transit signal.",
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
        },
        sort_keys=True,
    )


def _version() -> tuple[ArtifactVersionDetail, dict[str, object]]:
    content = b"# Transit Signal\n\nThe paper studies a transit signal."
    content_hash = "sha256:" + hashlib.sha256(content).hexdigest()
    parsed = ScientificDocumentParser().parse_document(
        DocumentParseInput(
            research_input_id=INPUT_ID,
            content_hash=content_hash,
            source_type="upload",
            mime_type="text/markdown",
            filename="transit.md",
            input_bytes=content,
        )
    )
    snapshot_ref = PaperSummarySourceSnapshotReference(
        source_snapshot_id=SNAPSHOT_ID,
        source_id="research-input",
        source_version=content_hash,
        content_hash=content_hash,
    )
    paper = PaperSummaryPaperMetadata(
        paper_id="paper.document-summary-read",
        title="Transit Signal",
    )
    candidates = build_document_evidence_candidates(
        document_parse=parsed,
        document_parse_id=PARSE_ID,
        paper_id=paper.paper_id,
        source_id=snapshot_ref.source_id,
        source_record_id="transit.md",
        source_snapshot_id=SNAPSHOT_ID,
    )
    evidence_candidate = candidates[0]
    admission = PaperSummaryPipeline(clock=lambda: NOW).admit_document(
        document_parse=parsed,
        document_parse_id=PARSE_ID,
        source_snapshot=snapshot_ref,
        paper=paper,
        model_response=_model_output(evidence_candidate.evidence_id),
        model_name="qwen-plus",
        model_revision="qwen-plus-2026-07-28",
        provider="qwen",
        parameters={"temperature": 0},
        evidence_candidates=candidates,
        run_id=RUN_ID,
        execution_id="execution.document-summary-read",
    )
    assert admission.summary is not None
    summary = admission.summary
    summary_content = summary.model_dump(mode="json")
    version_content_hash = compute_canonical_payload_hash(summary_content)
    producer = ProducerReference(
        type="model",
        name=summary.producer.producer_name,
        version=summary.producer.producer_version,
        model_provider=summary.producer.provider,
        model_name=summary.producer.model_name,
        prompt_name=summary.producer.prompt_name,
        prompt_version=summary.producer.prompt_version,
        prompt_hash=summary.producer.prompt_hash,
        parameters_hash=summary.producer.parameters_hash,
    )
    runtime = ProducerExecutionDetail(
        id=summary.producer.execution_id,
        run_id=RUN_ID,
        step_key=summary.producer.step_key,
        step_attempt_id="77777777-7777-4777-8777-777777777777",
        producer=producer,
        parameters={},
        parameters_hash=summary.producer.parameters_hash,
        input_hash=summary.input_hash,
        output_hash=version_content_hash,
        status="completed",
        started_at=summary.producer.started_at,
        finished_at=summary.producer.finished_at,
        latency_ms=summary.producer.latency_ms,
    )
    snapshot = SourceSnapshotDetail(
        id=SNAPSHOT_ID,
        source_id=snapshot_ref.source_id,
        source_type="research_input_upload",
        retrieved_at=NOW,
        query={"research_input_id": INPUT_ID},
        query_hash=compute_canonical_payload_hash({"research_input_id": INPUT_ID}),
        source_version_or_etag=content_hash,
        content_hash=content_hash,
        license_note="user-provided upload",
        request_metadata={"ingestion_source": "upload"},
    )
    admitted_evidence = summary.evidence[0]
    generic_evidence = EvidenceDetail(
        id="88888888-8888-4888-8888-888888888888",
        artifact_version_id=VERSION_ID,
        target_type="paper_summary",
        target_id="summary.document.background",
        evidence_type="paper_text",
        source_snapshot_id=SNAPSHOT_ID,
        paper_id=summary.paper_id,
        locator={
            "summary_evidence_id": admitted_evidence.evidence_id,
            "source_record_id": admitted_evidence.source_record_id,
            "paper_summary_locator": admitted_evidence.locator.model_dump(
                mode="json", exclude_none=True
            ),
        },
        extraction_method="literature_admission",
        confidence=1.0,
        created_at=NOW,
    )
    version = ArtifactVersionDetail(
        id=VERSION_ID,
        artifact_id="99999999-9999-4999-8999-999999999999",
        project_id=PROJECT_ID,
        created_by_run_id=RUN_ID,
        version_number=1,
        schema_version=summary.schema_version,
        content=summary_content,
        content_hash=version_content_hash,
        input_hash=summary.input_hash,
        source_mode=SourceMode.live,
        producer=producer,
        source_snapshot_ids=(SNAPSHOT_ID,),
        evidence_ids=(generic_evidence.id,),
        created_at=NOW,
        producer_execution=runtime,
        source_snapshots=(snapshot,),
        evidence=(generic_evidence,),
    )
    expected = {
        "project_id": UUID(PROJECT_ID),
        "document_parse_id": UUID(PARSE_ID),
        "candidate_parse_id": parsed.parse_id,
        "research_input_id": UUID(INPUT_ID),
        "source_snapshot_id": UUID(SNAPSHOT_ID),
        "input_content_hash": content_hash,
        "canonical_output_hash": parsed.canonical_output_hash,
        "parser_profile_id": parsed.profile.parser_profile_id,
        "parser_profile_version": parsed.profile.parser_profile_version,
        "config_hash": parsed.config_hash,
    }
    return version, expected


class _Artifacts:
    def __init__(self, version: ArtifactVersionDetail) -> None:
        self.version = version

    def get_version(self, *, version_id: str, session_id: str):  # type: ignore[no-untyped-def]
        return self.version

    def get_artifact(self, *, artifact_id: str, session_id: str):  # type: ignore[no-untyped-def]
        return SimpleNamespace(kind=SimpleNamespace(value="paper_summary"))


class _Parses:
    def __init__(self, expected: dict[str, object]) -> None:
        self.expected = expected
        self.calls = 0

    def verify_reference(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        assert kwargs == self.expected


def test_document_summary_read_verifies_parse_and_preserves_locator() -> None:
    version, expected = _version()
    parses = _Parses(expected)
    read = PaperSummaryReadService(_Artifacts(version), parses).get_summary(
        version_id=VERSION_ID,
        session_id="owner",
    )

    assert parses.calls == 1
    assert read.paper.title == "Transit Signal"
    locator = read.summary.evidence[0].locator
    assert locator.document_parse_id == PARSE_ID
    assert locator.document_locator is not None
    assert locator.document_locator.block_id is not None


def test_document_summary_read_rejects_generic_locator_loss() -> None:
    version, expected = _version()
    evidence = version.evidence[0].model_copy(
        update={
            "locator": {
                key: value
                for key, value in version.evidence[0].locator.items()
                if key != "paper_summary_locator"
            }
        }
    )
    version = version.model_copy(update={"evidence": (evidence,)})

    with pytest.raises(SecurityProblem) as exc_info:
        PaperSummaryReadService(_Artifacts(version), _Parses(expected)).get_summary(
            version_id=VERSION_ID,
            session_id="owner",
        )
    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"
