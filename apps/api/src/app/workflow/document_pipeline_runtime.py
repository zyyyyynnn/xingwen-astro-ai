"""Run-bound DocumentParse-to-PaperSummary execution and publication preparation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactVersionModel,
    ResearchArtifactModel,
    ResearchInputBindingModel,
    ResearchInputContentModel,
    ResearchInputModel,
    ResearchRunModel,
    RunDecisionModel,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.paper_summary import (
    PaperSummaryArtifactContent,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import DocumentParseInput
from app.services.content_storage import ContentStorage
from app.services.document_parse_store import (
    DocumentParseRepository,
    DocumentParseService,
    PersistDocumentParseRequest,
)
from app.services.document_parsing import DocumentParsingService
from app.services.document_summary import (
    DocumentSummaryService,
    ExecuteDocumentSummaryRequest,
)
from app.services.model_execution import ModelExecutionError, ModelExecutionPort
from app.workflow.publisher import (
    ArtifactAdmissionContext,
    ArtifactEvidenceBinding,
    ArtifactPublication,
    ArtifactSourceSnapshotBinding,
    ProducerExecutionRequest,
    ProducerExecutionStore,
    PublicationAdmissionError,
    admit_artifact_candidate,
    normalize_producer_parameters,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.canonicalize import canonical_paper_id, normalize_title
from services.paper_pipeline.constants import SUMMARY_PARAMETERS_VERSION

_SUPPORTED_MIME_TYPES = frozenset(
    {"application/pdf", "text/markdown", "text/x-markdown", "text/plain"}
)
_SUMMARY_PARAMETERS = {"temperature": 0, "max_output_tokens": 8192}


class DocumentPipelineInputError(ValueError):
    """The current Run has no usable bound document input."""


class DocumentSummaryAdmissionError(ValueError):
    """The model response did not pass PaperSummary admission."""


@dataclass(frozen=True, slots=True)
class BoundDocumentInput:
    id: UUID
    project_id: UUID
    source_type: str
    content_hash: str
    filename: str | None
    mime_type: str


@dataclass(frozen=True, slots=True)
class _ArtifactTarget:
    artifact_id: UUID
    publication_key: str
    supersedes_version_id: UUID | None


class DocumentPipelineRuntime:
    """Execute every supported document explicitly bound to one ResearchRun."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        content_storage: ContentStorage,
        model_port: ModelExecutionPort,
        model_name: str,
        model_revision: str,
    ) -> None:
        self._session_factory = session_factory
        self._parsing = DocumentParsingService(content_storage)
        self._parse_store = DocumentParseService(
            DocumentParseRepository(session_factory), content_storage
        )
        self._summaries = DocumentSummaryService(model_port)
        self._producers = ProducerExecutionStore(session_factory)
        self._model_name = model_name
        self._model_revision = model_revision

    def require_bound_documents(
        self, *, run_id: UUID, project_id: UUID
    ) -> tuple[BoundDocumentInput, ...]:
        """Return the immutable, supported inputs owned and bound to this Run."""

        with self._session_factory() as session:
            lineage_run_ids = self._lineage_run_ids(
                session, run_id=run_id, project_id=project_id
            )
            supplemental_ids = {
                UUID(value)
                for values in session.scalars(
                    select(RunDecisionModel.input_ids).where(
                        RunDecisionModel.project_id == project_id,
                        RunDecisionModel.child_run_id.in_(lineage_run_ids),
                    )
                )
                for value in values
            }
            bound_ids = set(
                session.scalars(
                    select(ResearchInputBindingModel.input_id).where(
                        ResearchInputBindingModel.run_id.in_(lineage_run_ids),
                        ResearchInputBindingModel.project_id == project_id,
                    )
                )
            )
            input_ids = bound_ids | supplemental_ids
            rows = tuple(
                session.execute(
                    select(ResearchInputModel, ResearchInputContentModel)
                    .join(
                        ResearchInputContentModel,
                        (ResearchInputContentModel.project_id == ResearchInputModel.project_id)
                        & (
                            ResearchInputContentModel.content_hash
                            == ResearchInputModel.content_hash
                        ),
                    )
                    .where(
                        ResearchInputModel.id.in_(input_ids),
                        ResearchInputModel.project_id == project_id,
                        ResearchInputModel.status == "accepted",
                        (
                            ResearchInputModel.expires_at.is_(None)
                            | (ResearchInputModel.expires_at > datetime.now(UTC))
                        ),
                    )
                    .order_by(
                        ResearchInputModel.created_at.asc(),
                        ResearchInputModel.id.asc(),
                    )
                )
            )
        documents = tuple(
            BoundDocumentInput(
                id=input_row.id,
                project_id=input_row.project_id,
                source_type=input_row.source_type,
                content_hash=input_row.content_hash,
                filename=input_row.filename,
                mime_type=content.mime_type.casefold().split(";", 1)[0].strip(),
            )
            for input_row, content in rows
            if content.mime_type.casefold().split(";", 1)[0].strip()
            in _SUPPORTED_MIME_TYPES
        )
        if not documents:
            raise DocumentPipelineInputError(
                "ResearchRun has no supported PDF, Markdown, or plain-text input"
            )
        return documents

    @staticmethod
    def _lineage_run_ids(
        session: Session, *, run_id: UUID, project_id: UUID
    ) -> tuple[UUID, ...]:
        lineage: list[UUID] = []
        current_id: UUID | None = run_id
        while current_id is not None:
            if current_id in lineage or len(lineage) >= 32:
                raise DocumentPipelineInputError("ResearchRun lineage is invalid")
            row = session.scalar(
                select(ResearchRunModel).where(
                    ResearchRunModel.id == current_id,
                    ResearchRunModel.project_id == project_id,
                )
            )
            if row is None:
                raise DocumentPipelineInputError("ResearchRun lineage is incomplete")
            lineage.append(row.id)
            current_id = row.parent_run_id
        return tuple(lineage)

    async def prepare_publications(
        self,
        *,
        run_id: UUID,
        project_id: UUID,
        research_goal: str,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> tuple[ArtifactPublication, ...]:
        if step_key != "summarizing_papers":
            raise ValueError("Document Pipeline can only publish from summarizing_papers")
        documents = self.require_bound_documents(run_id=run_id, project_id=project_id)
        publications: list[ArtifactPublication] = []
        for document in documents:
            publications.append(
                await self._prepare_document_publication(
                    document=document,
                    run_id=run_id,
                    project_id=project_id,
                    research_goal=research_goal,
                    step_key=step_key,
                    attempt=attempt,
                    lease=lease,
                )
            )
        return tuple(publications)

    async def _prepare_document_publication(
        self,
        *,
        document: BoundDocumentInput,
        run_id: UUID,
        project_id: UUID,
        research_goal: str,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> ArtifactPublication:
        parse_input = DocumentParseInput(
            research_input_id=str(document.id),
            content_hash=document.content_hash,
            source_type=document.source_type,
            mime_type=document.mime_type,
            filename=document.filename,
        )
        parse_input_hash = compute_canonical_payload_hash(
            parse_input.model_dump(
                mode="json", exclude_none=True, exclude={"input_bytes"}
            )
        )
        parse_execution = self._producers.start_producer_execution(
            ProducerExecutionRequest(
                run_id=run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key=(
                    f"document-parse:{document.id}:attempt:{attempt.attempt_number}"
                ),
                producer_type="algorithm",
                producer_name="scientific_document_parser",
                producer_version="1.0.0",
                input_hash=parse_input_hash,
                parameters={
                    "mime_type": document.mime_type,
                    "source_type": document.source_type,
                },
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )
        try:
            candidate = await self._parsing.parse(parse_input)
        except Exception:
            self._producers.finish_producer_execution(
                parse_execution.id,
                status="failed",
                error_code="DOCUMENT_PARSE_FAILED",
            )
            raise
        self._producers.finish_producer_execution(
            parse_execution.id,
            status="completed",
            output_hash=candidate.canonical_output_hash,
        )
        parse_record = await self._parse_store.persist(
            PersistDocumentParseRequest(
                project_id=project_id,
                run_id=run_id,
                run_step_id=attempt.run_step_id,
                producer_execution_id=parse_execution.id,
                parse_input_hash=parse_input_hash,
                candidate=candidate,
            )
        )

        source_snapshot = PaperSummarySourceSnapshotReference(
            source_snapshot_id=str(parse_record.source_snapshot_id),
            source_id=f"research_input:{document.id}",
            source_version=document.content_hash,
            content_hash=document.content_hash,
        )
        paper_title = _document_title(document)
        paper = PaperSummaryPaperMetadata(
            paper_id=canonical_paper_id(
                doi=None,
                arxiv_id=None,
                normalized_title=normalize_title(paper_title),
                year=None,
                normalized_authors=(),
                source_id=source_snapshot.source_id,
                source_record_id=str(document.id),
            ),
            title=paper_title,
        )
        summary_request = ExecuteDocumentSummaryRequest(
            document_parse=candidate,
            document_parse_id=str(parse_record.id),
            source_snapshot=source_snapshot,
            paper=paper,
            source_id=source_snapshot.source_id,
            source_record_id=document.filename or str(document.id),
            research_goal=research_goal,
            provider="qwen",
            model=self._model_name,
            model_revision=self._model_revision,
            parameters=dict(_SUMMARY_PARAMETERS),
            run_id=str(run_id),
        )
        prepared = self._summaries.prepare(summary_request)
        prompt = prepared.model_request
        summary_execution = self._producers.start_producer_execution(
            ProducerExecutionRequest(
                run_id=run_id,
                step_key=step_key,
                attempt_id=attempt.attempt_id,
                idempotency_key=(
                    f"paper-summary:{document.id}:attempt:{attempt.attempt_number}"
                ),
                producer_type="model",
                producer_name="paper_summary",
                producer_version="3.0.0",
                input_hash=prepared.input_hash,
                parameters=normalize_producer_parameters(
                    summary_request.parameters,
                    parameters_version=SUMMARY_PARAMETERS_VERSION,
                ),
                model_provider=summary_request.provider,
                model_name=summary_request.model,
                prompt_name=prompt.prompt_name,
                prompt_version=prompt.prompt_version,
                prompt_hash=prompt.prompt_hash,
            ),
            token=lease.token,
            generation=lease.generation,
            expected_status=attempt.run_status,
            expected_revision=attempt.run_revision,
        )
        try:
            executed = await asyncio.to_thread(
                self._summaries.execute_prepared,
                prepared,
                producer_execution_id=str(summary_execution.id),
            )
        except Exception as exc:
            error_code = (
                exc.code
                if isinstance(exc, ModelExecutionError)
                else "PAPER_SUMMARY_EXECUTION_FAILED"
            )
            self._producers.finish_producer_execution(
                summary_execution.id,
                status="failed",
                error_code=error_code,
            )
            raise
        summary = executed.admission.summary
        if summary is None or executed.admission.producer.status != "completed":
            error_code = (
                executed.admission.producer.error_code
                or "PAPER_SUMMARY_ADMISSION_REJECTED"
            )
            self._producers.finish_producer_execution(
                summary_execution.id,
                status="rejected",
                error_code=error_code,
            )
            raise DocumentSummaryAdmissionError(error_code)
        try:
            admitted = _admit_summary(
                summary,
                project_id=project_id,
                persisted_snapshot_id=parse_record.source_snapshot_id,
            )
        except Exception:
            self._producers.finish_producer_execution(
                summary_execution.id,
                status="rejected",
                error_code="PAPER_SUMMARY_PUBLICATION_REJECTED",
            )
            raise
        self._producers.finish_producer_execution(
            summary_execution.id,
            status="completed",
            output_hash=admitted.content_hash,
            token_usage=(
                executed.token_usage.model_dump(mode="json")
                if executed.token_usage is not None
                else None
            ),
            latency_ms=executed.latency_ms,
        )
        target = self._ensure_artifact_target(
            project_id=project_id,
            document=document,
            summary=summary,
            step_key=step_key,
        )
        return ArtifactPublication(
            artifact_id=target.artifact_id,
            publication_key=target.publication_key,
            producer_execution_id=summary_execution.id,
            candidate=admitted,
            source_mode="live",
            supersedes_version_id=target.supersedes_version_id,
        )

    def _ensure_artifact_target(
        self,
        *,
        project_id: UUID,
        document: BoundDocumentInput,
        summary: PaperSummaryArtifactContent,
        step_key: str,
    ) -> _ArtifactTarget:
        logical_key = f"paper_summary.{document.id}"
        artifact_id = uuid5(NAMESPACE_URL, f"xingwen:{project_id}:{logical_key}")
        publication_key = str(
            uuid5(
                NAMESPACE_URL,
                f"xingwen:{project_id}:{step_key}:{logical_key}:{summary.input_hash}",
            )
        )
        with self._session_factory() as session, session.begin():
            artifact = session.get(ResearchArtifactModel, artifact_id)
            if artifact is None:
                artifact = ResearchArtifactModel(
                    id=artifact_id,
                    project_id=project_id,
                    kind="paper_summary",
                    title=f"{summary.paper.title} 摘要"[:240],
                    logical_key=logical_key,
                )
                session.add(artifact)
                session.flush()
            elif (
                artifact.project_id != project_id
                or artifact.kind != "paper_summary"
                or artifact.logical_key != logical_key
            ):
                raise PublicationAdmissionError(
                    "PaperSummary ResearchArtifact identity was reused with another meaning"
                )
            existing = session.scalar(
                select(ArtifactVersionModel).where(
                    ArtifactVersionModel.artifact_id == artifact.id,
                    ArtifactVersionModel.publication_key == publication_key,
                )
            )
            supersedes = (
                existing.supersedes_version_id
                if existing is not None
                else artifact.latest_version_id
            )
            return _ArtifactTarget(
                artifact_id=artifact.id,
                publication_key=publication_key,
                supersedes_version_id=supersedes,
            )


def _admit_summary(
    summary: PaperSummaryArtifactContent,
    *,
    project_id: UUID,
    persisted_snapshot_id: UUID,
):
    snapshot_id = str(persisted_snapshot_id)
    evidence_bindings = tuple(
        ArtifactEvidenceBinding(
            target_type="paper_summary",
            target_id=summary.summary_id,
            pipeline_evidence_id=evidence.evidence_id,
            pipeline_source_snapshot_id=evidence.source_snapshot_id,
            persisted_evidence_id=str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        f"xingwen:{project_id}:{summary.input_hash}:"
                        f"evidence:{evidence.evidence_id}"
                    ),
                )
            ),
            persisted_source_snapshot_id=snapshot_id,
        )
        for evidence in summary.evidence
    )
    return admit_artifact_candidate(
        summary,
        schema_version=summary.schema_version,
        source_snapshot_ids=tuple(
            item.source_snapshot_id for item in summary.input_versions.source_snapshots
        ),
        evidence_ids=summary.evidence_ids,
        evidence_validator=_summary_evidence_validator,
        domain_validator=_summary_domain_validator,
        quality_validator=_summary_quality_validator,
        source_snapshot_bindings=(
            ArtifactSourceSnapshotBinding(
                pipeline_source_snapshot_id=snapshot_id,
                persisted_source_snapshot_id=snapshot_id,
            ),
        ),
        evidence_bindings=evidence_bindings,
    )


def _summary_evidence_validator(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, PaperSummaryArtifactContent):
        raise ValueError("PaperSummary evidence validator received another kind")
    if tuple(item.evidence_id for item in candidate.evidence) != tuple(
        sorted(candidate.evidence_ids)
    ):
        raise ValueError("PaperSummary Evidence registry is not canonical")
    if len(context.persisted_evidence_ids) != len(candidate.evidence_ids):
        raise ValueError("PaperSummary persisted Evidence closure is incomplete")


def _summary_domain_validator(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, PaperSummaryArtifactContent):
        raise ValueError("PaperSummary domain validator received another kind")
    if candidate.producer.input_hash != candidate.input_hash:
        raise ValueError("PaperSummary producer identity does not match the Artifact")
    if not candidate.input_versions.document_parses:
        raise ValueError("Live document summary requires a persisted DocumentParse")


def _summary_quality_validator(context: ArtifactAdmissionContext) -> None:
    candidate = context.candidate
    if not isinstance(candidate, PaperSummaryArtifactContent):
        raise ValueError("PaperSummary quality validator received another kind")
    if not candidate.statements():
        raise ValueError("PaperSummary must contain at least one admitted statement")


def _document_title(document: BoundDocumentInput) -> str:
    if document.filename:
        stem = PurePath(document.filename).stem.strip()
        if stem:
            return stem[:512]
    return f"研究文档 {str(document.id)[:8]}"


__all__ = [
    "BoundDocumentInput",
    "DocumentPipelineInputError",
    "DocumentPipelineRuntime",
    "DocumentSummaryAdmissionError",
]
