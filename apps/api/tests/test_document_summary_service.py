"""Production DocumentParse-to-PaperSummary model execution bridge."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.routers.artifacts import _research_input_by_identity
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactKind,
    ArtifactVersionDetail,
    EvidenceDetail,
    ProducerExecutionDetail,
    ProducerReference,
    ResearchArtifactDetail,
    SourceMode,
    SourceSnapshotDetail,
)
from app.services.public_presentation import build_artifact_presentation
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryInputVersions,
    PaperSummaryModelOutput,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
    compute_paper_summary_output_hash,
)
from app.schemas.research_input import ResearchInputStatus, ResearchInputType
from app.schemas.revision import (
    CreateUserFeedbackRequest,
    FeedbackCategory,
    FeedbackTargetType,
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
from app.services.feedback_targets import FeedbackTargetAuthority
from app.services.document_parse_store import DocumentParseSourceSnapshot
from app.services.model_execution import (
    ModelExecutionRequest,
    ModelExecutionResponse,
)
from app.services.paper_summaries import PaperSummaryReadService
from app.services.paper_summary_exports import PaperSummaryExportService
from app.services.research_input_store import ResearchInputRecord
from app.security import SecurityProblem
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
            "background": [
                {
                    "statement_id": "summary.document.research_goal",
                    "text": "The paper studies transit signals.",
                    "evidence_ids": [evidence_id],
                }
            ],
            "methodology": [],
            "dataset": [],
            "experiments": [],
            "discussion": [],
            "limitations": [],
            "research_questions": [],
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
_VERSION_ID = "version.document-summary"
_ARTIFACT_ID = "artifact.document-summary"
_PROJECT_ID = "00000000-0000-4000-8000-0000000000ee"
_SOURCE_SNAPSHOT_ID = "00000000-0000-4000-8000-0000000000ff"
_SOURCE_ID = "research_input:00000000-0000-4000-8000-0000000000aa"
_SESSION_ID = "owner"


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
            source_snapshot_id=_SOURCE_SNAPSHOT_ID,
            source_id=_SOURCE_ID,
            source_version=_CONTENT_HASH,
            content_hash=_CONTENT_HASH,
        ),
        paper=PaperSummaryPaperMetadata(
            paper_id="paper.document-summary",
            title="Transit Study",
        ),
        source_id=_SOURCE_ID,
        source_record_id="transit-study.pdf",
        research_goal="Summarize the transit method.",
        provider="qwen",
        model="qwen3.8-max",
        model_revision="qwen3.8-max",
        parameters={"temperature": 0, "max_tokens": 2048},
        run_id="00000000-0000-4000-8000-0000000000cc",
        producer_execution_id="execution.document-summary",
    )


def _published_summary_version(
    summary: PaperSummaryArtifactContent,
) -> ArtifactVersionDetail:
    producer = summary.producer
    assert producer.run_id is not None
    snapshot_reference = summary.input_versions.source_snapshots[0]
    persisted_snapshot_id = "snapshot.document-summary.persisted"
    producer_reference = ProducerReference(
        type=producer.producer_type,
        name=producer.producer_name,
        version=producer.producer_version,
        model_provider=producer.provider,
        requested_model=producer.model_name,
        explicit_revision=producer.model_revision,
        prompt_name=producer.prompt_name,
        prompt_version=producer.prompt_version,
        prompt_hash=producer.prompt_hash,
        parameters_hash=producer.parameters_hash,
    )
    content = summary.model_dump(mode="json")
    content_hash = compute_canonical_payload_hash(content)
    evidence = tuple(
        EvidenceDetail(
            id=f"persisted.{item.evidence_id}",
            artifact_version_id=_VERSION_ID,
            target_type="paper_summary",
            target_id=next(
                statement.statement_id
                for statement in summary.statements()
                if item.evidence_id in statement.evidence_ids
            ),
            evidence_type="document_quote",
            source_snapshot_id=persisted_snapshot_id,
            paper_id=item.paper_id,
            locator={
                "source_record_id": item.source_record_id,
                "summary_evidence_id": item.evidence_id,
            },
            quote_or_value=item.quote_or_value,
            extraction_method="document_parse",
            confidence=1.0,
            created_at=producer.finished_at,
        )
        for item in summary.evidence
    )
    return ArtifactVersionDetail(
        id=_VERSION_ID,
        artifact_id=_ARTIFACT_ID,
        project_id=_PROJECT_ID,
        created_by_run_id=producer.run_id,
        version_number=1,
        schema_version=summary.schema_version,
        content=content,
        presentation=build_artifact_presentation(
            ArtifactKind.paper_summary, content, evidence
        ),
        content_hash=content_hash,
        input_hash=summary.input_hash,
        source_mode=SourceMode.live,
        producer=producer_reference,
        source_snapshot_ids=(persisted_snapshot_id,),
        evidence_ids=tuple(item.id for item in evidence),
        created_at=producer.finished_at,
        producer_execution=ProducerExecutionDetail(
            id=producer.execution_id,
            run_id=producer.run_id,
            step_key=producer.step_key,
            step_attempt_id="attempt.document-summary",
            producer=producer_reference,
            parameters=_request().parameters,
            parameters_hash=producer.parameters_hash,
            input_hash=summary.input_hash,
            output_hash=content_hash,
            status="completed",
            started_at=producer.started_at,
            finished_at=producer.finished_at,
            token_usage=(
                producer.usage.model_dump(mode="json")
                if producer.usage is not None
                else None
            ),
            latency_ms=producer.latency_ms,
            provider_request_id=producer.provider_request_id,
        ),
        source_snapshots=(
            SourceSnapshotDetail(
                id=persisted_snapshot_id,
                source_id=snapshot_reference.source_id,
                source_type="research_input",
                retrieved_at=producer.finished_at,
                query={},
                query_hash=compute_canonical_payload_hash({}),
                source_version_or_etag=snapshot_reference.source_version,
                content_hash=snapshot_reference.content_hash,
                license_note="Test-owned immutable ResearchInput",
                request_metadata={},
            ),
        ),
        evidence=evidence,
    )


class _PublishedSummaryArtifacts:
    def __init__(self, version: ArtifactVersionDetail) -> None:
        self._version = version

    def get_version(self, *, version_id: str, session_id: str) -> ArtifactVersionDetail:
        assert version_id == _VERSION_ID
        assert session_id == _SESSION_ID
        return self._version

    def get_artifact(
        self, *, artifact_id: str, session_id: str
    ) -> ResearchArtifactDetail:
        assert artifact_id == _ARTIFACT_ID
        assert session_id == _SESSION_ID
        return ResearchArtifactDetail(
            id=_ARTIFACT_ID,
            project_id=_PROJECT_ID,
            kind="paper_summary",
            title="Document summary",
            logical_key="paper_summary.document",
            created_at=self._version.created_at,
            latest_version_id=_VERSION_ID,
            versions=(),
        )


class _ResearchInputs:
    def __init__(self, record: ResearchInputRecord) -> None:
        self._record = record

    def get(self, *, session_id: str, input_id: str) -> ResearchInputRecord | None:
        if session_id != self._record.session_id or input_id != self._record.id:
            return None
        return self._record


class _DocumentParses:
    async def get_candidate(
        self, *, project_id: UUID, document_parse_id: UUID
    ) -> DocumentParseCandidate:
        assert project_id == UUID(_PROJECT_ID)
        assert document_parse_id == UUID("00000000-0000-4000-8000-0000000000bb")
        return _parse_candidate()

    def source_snapshot(
        self, *, project_id: UUID, document_parse_id: UUID
    ) -> DocumentParseSourceSnapshot:
        assert project_id == UUID(_PROJECT_ID)
        assert document_parse_id == UUID("00000000-0000-4000-8000-0000000000bb")
        return DocumentParseSourceSnapshot(
            id=UUID(_SOURCE_SNAPSHOT_ID),
            source_id=_SOURCE_ID,
            source_version_or_etag=_CONTENT_HASH,
            content_hash=_CONTENT_HASH,
            source_type="research_input_upload",
            retrieved_at=_parse_candidate().created_at,
            query={"research_input_id": "00000000-0000-4000-8000-0000000000aa"},
            query_hash=_CONTENT_HASH,
            license_note="user-provided upload",
            cache_version=None,
            request_metadata={},
        )


def _document_input_record(
    *, input_type: ResearchInputType, mime_type: str, filename: str
) -> ResearchInputRecord:
    return ResearchInputRecord(
        id=str(_parse_candidate().research_input_id),
        session_id=_SESSION_ID,
        project_id=_PROJECT_ID,
        type=input_type,
        source_type="upload",
        content_hash=_CONTENT_HASH,
        storage_ref="local:document-summary",
        filename=filename,
        mime_type=mime_type,
        size_bytes=1024,
        status=ResearchInputStatus.accepted,
        source_snapshot_id=_SOURCE_SNAPSHOT_ID,
        url=None,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        expires_at=None,
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
    assert prepared.model_request.response_schema_name == "paper_summary"
    assert (
        prepared.model_request.response_schema
        == PaperSummaryModelOutput.model_json_schema()
    )
    result = service.execute_prepared(
        prepared,
        producer_execution_id="execution.document-summary.fixed",
    )
    assert result.admission.producer.input_hash == prepared.input_hash
    assert result.admission.producer.execution_id == "execution.document-summary.fixed"


def test_document_summary_rejects_model_hash_drift() -> None:
    with pytest.raises(ValueError, match="output hash mismatch"):
        DocumentSummaryService(_Model(tamper_hash=True)).execute(_request())


def test_document_summary_requires_one_pinned_document_parse() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    payload = summary.input_versions.model_dump(mode="json")
    second_parse = dict(payload["document_parses"][0])
    second_parse["document_parse_id"] = "00000000-0000-4000-8000-0000000000dd"
    payload["document_parses"].append(second_parse)

    with pytest.raises(ValueError, match="at most 1 item"):
        PaperSummaryInputVersions.model_validate(payload)


def test_document_parse_summary_is_readable_and_exportable() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    read_service = PaperSummaryReadService(
        _PublishedSummaryArtifacts(_published_summary_version(summary)),
        document_parses=_DocumentParses(),
    )

    read = asyncio.run(
        read_service.get_summary(
            version_id=_VERSION_ID,
            session_id=_SESSION_ID,
        )
    )
    download = asyncio.run(
        PaperSummaryExportService(read_service).export(
            version_id=_VERSION_ID,
            session_id=_SESSION_ID,
            export_format="json",
        )
    )

    assert read.paper == summary.paper
    assert b'"title": "Transit Study"' in download.content


def test_document_parse_summary_fails_closed_without_persisted_parse_reader() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    read_service = PaperSummaryReadService(
        _PublishedSummaryArtifacts(_published_summary_version(summary))
    )

    with pytest.raises(SecurityProblem) as exc_info:
        asyncio.run(
            read_service.get_summary(
                version_id=_VERSION_ID,
                session_id=_SESSION_ID,
            )
        )

    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"


def _whole_summary_feedback(
    *, target_type: FeedbackTargetType
) -> CreateUserFeedbackRequest:
    target_id = (
        _ARTIFACT_ID if target_type is FeedbackTargetType.artifact else _VERSION_ID
    )
    locator = (
        {"artifact_id": _ARTIFACT_ID}
        if target_type is FeedbackTargetType.artifact
        else {
            "artifact_id": _ARTIFACT_ID,
            "artifact_version_id": _VERSION_ID,
        }
    )
    return CreateUserFeedbackRequest(
        expected_version_number=1,
        target_type=target_type,
        target_id=target_id,
        target_locator=locator,
        category=FeedbackCategory.correction,
        summary="Correct this summary",
        requested_change="Recompute from the pinned document parse",
    )


def test_whole_summary_feedback_reuses_complete_document_provenance_read() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    artifacts = _PublishedSummaryArtifacts(_published_summary_version(summary))
    summaries = PaperSummaryReadService(artifacts, document_parses=_DocumentParses())
    authority = FeedbackTargetAuthority(
        artifacts,
        paper_summary_reader=summaries,
    )

    for target_type in (
        FeedbackTargetType.artifact,
        FeedbackTargetType.artifact_version,
    ):
        asyncio.run(
            authority.validate(
                version_id=_VERSION_ID,
                artifact_id=_ARTIFACT_ID,
                artifact_kind="paper_summary",
                session_id=_SESSION_ID,
                request=_whole_summary_feedback(target_type=target_type),
            )
        )


def test_whole_summary_feedback_fails_closed_without_document_parse_reader() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    artifacts = _PublishedSummaryArtifacts(_published_summary_version(summary))
    authority = FeedbackTargetAuthority(
        artifacts,
        paper_summary_reader=PaperSummaryReadService(artifacts),
    )

    with pytest.raises(SecurityProblem) as exc_info:
        asyncio.run(
            authority.validate(
                version_id=_VERSION_ID,
                artifact_id=_ARTIFACT_ID,
                artifact_kind="paper_summary",
                session_id=_SESSION_ID,
                request=_whole_summary_feedback(
                    target_type=FeedbackTargetType.artifact_version
                ),
            )
        )

    assert exc_info.value.code == "FEEDBACK_TARGET_INVALID"


def test_document_image_summary_returns_its_authorized_source() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    version = _published_summary_version(summary)
    image = _document_input_record(
        input_type=ResearchInputType.image,
        mime_type="image/tiff",
        filename="transit-study.tiff",
    )
    read_service = PaperSummaryReadService(
        _PublishedSummaryArtifacts(version),
        research_input_resolver=_research_input_by_identity(_ResearchInputs(image)),
        document_parses=_DocumentParses(),
    )

    source = asyncio.run(
        read_service.get_document_source(
            version_id=_VERSION_ID,
            session_id=_SESSION_ID,
        )
    )

    assert source.research_input is not None
    assert source.research_input.id == image.id
    assert source.research_input.type is ResearchInputType.image


def test_document_source_rejects_document_parse_provenance_drift() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    version = _published_summary_version(summary).model_copy(update={"evidence": ()})
    pdf = _document_input_record(
        input_type=ResearchInputType.pdf,
        mime_type="application/pdf",
        filename="transit-study.pdf",
    )
    read_service = PaperSummaryReadService(
        _PublishedSummaryArtifacts(version),
        research_input_resolver=_research_input_by_identity(_ResearchInputs(pdf)),
        document_parses=_DocumentParses(),
    )

    with pytest.raises(SecurityProblem) as exc_info:
        asyncio.run(
            read_service.get_document_source(
                version_id=_VERSION_ID,
                session_id=_SESSION_ID,
            )
        )

    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"


def test_summary_read_rejects_frozen_parse_identity_drift() -> None:
    execution = DocumentSummaryService(_Model()).execute(_request())
    summary = execution.admission.summary
    assert summary is not None
    payload = summary.model_dump(mode="json")
    drifted_hash = "sha256:" + "e" * 64
    payload["input_versions"]["document_parses"][0]["canonical_output_hash"] = (
        drifted_hash
    )
    payload["producer"]["input_versions"]["document_parses"][0][
        "canonical_output_hash"
    ] = drifted_hash
    output_hash = compute_paper_summary_output_hash(payload)
    payload["output_hash"] = output_hash
    payload["producer"]["output_hash"] = output_hash
    drifted = PaperSummaryArtifactContent.model_validate(payload)
    read_service = PaperSummaryReadService(
        _PublishedSummaryArtifacts(_published_summary_version(drifted)),
        document_parses=_DocumentParses(),
    )

    with pytest.raises(SecurityProblem) as exc_info:
        asyncio.run(
            read_service.get_summary(
                version_id=_VERSION_ID,
                session_id=_SESSION_ID,
            )
        )

    assert exc_info.value.code == "PROVENANCE_SCOPE_VIOLATION"


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
