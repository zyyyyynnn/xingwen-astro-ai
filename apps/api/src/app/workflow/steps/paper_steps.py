"""Paper search and summary step services for Research Runs."""

from __future__ import annotations

import asyncio

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel
from app.schemas.paper_collection import PaperCollectionCandidate
from app.schemas.paper_summary import (
    PaperSummaryAdmissionStatus,
    PaperSummaryEvidenceCandidate,
    PaperSummaryEvidenceLocator,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas.scientific_document import DocumentParseInput, DocumentParseQuality
from app.services.content_storage import ContentStorage
from app.services.document_parse_store import (
    DocumentParseService,
    PersistDocumentParseRequest,
)
from app.services.document_summary import ExecuteDocumentSummaryRequest
from app.services.document_summary_chunks import ChunkedDocumentSummaryService
from app.services.model_execution import ModelExecutionPort
from app.services.paper_candidate_inputs import PaperCandidateInputReadService
from app.services.scientific_document.ports import DocumentParserPort
from app.workflow.publisher import admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.constants import (
    SUMMARY_PRODUCER_NAME,
    SUMMARY_PRODUCER_VERSION,
)
from services.paper_pipeline.summary import (
    PaperSummaryPipeline,
    build_document_evidence_candidates,
    build_document_summary_input_identity,
)

#: Governed generation parameters shared by the paper summary model call.
MODEL_PARAMETERS: dict[str, float | int] = {"temperature": 0.6, "top_p": 0.8}


def _selected_candidate(
    collection,
) -> PaperCollectionCandidate:
    """Pick the summarized paper: first selected, non-synthetic candidate."""

    return next(
        candidate
        for candidate in collection.candidates
        if candidate.selected and candidate.raw.synthetic_note is None
    )


def _evidence_candidates(
    candidate: PaperCollectionCandidate,
) -> tuple[PaperSummaryEvidenceCandidate, ...]:
    """Anchor summary Evidence on the candidate's real bibliographic record."""

    if candidate.raw.url is None:
        raise ValueError("paper summary candidate must carry a source url")
    anchor = {
        "paper_id": candidate.canonical_paper_id,
        "candidate_id": candidate.candidate_id,
        "source_id": candidate.raw.source_id,
        "source_record_id": candidate.raw.source_record_id,
        "source_snapshot_id": candidate.raw.source_snapshot_id,
    }
    items: list[PaperSummaryEvidenceCandidate] = [
        PaperSummaryEvidenceCandidate(
            evidence_id="ev.title",
            locator=PaperSummaryEvidenceLocator(
                kind="paper_metadata",
                source_url=candidate.raw.url,
                metadata_field="title",
            ),
            quote_or_value=candidate.raw.title,
            **anchor,
        )
    ]
    if candidate.raw.year is not None:
        items.append(
            PaperSummaryEvidenceCandidate(
                evidence_id="ev.year",
                locator=PaperSummaryEvidenceLocator(
                    kind="paper_metadata",
                    source_url=candidate.raw.url,
                    metadata_field="year",
                ),
                quote_or_value=str(candidate.raw.year),
                **anchor,
            )
        )
    if candidate.raw.doi is not None:
        items.append(
            PaperSummaryEvidenceCandidate(
                evidence_id="ev.doi",
                locator=PaperSummaryEvidenceLocator(
                    kind="paper_metadata",
                    source_url=candidate.raw.url,
                    metadata_field="doi",
                ),
                quote_or_value=candidate.raw.doi,
                **anchor,
            )
        )
    return tuple(items)


class PaperStepService:
    """Search live literature and summarize the selected paper for one Run."""

    def __init__(
        self,
        *,
        publications: StepPublicationFactory,
        collection_runner: LivePaperCollectionRunner | None = None,
        paper_inputs: PaperCandidateInputReadService | None = None,
        content_storage: ContentStorage | None = None,
        document_parser: DocumentParserPort | None = None,
        document_parses: DocumentParseService | None = None,
    ) -> None:
        self._publications = publications
        self._collection_runner = collection_runner or LivePaperCollectionRunner()
        self._paper_inputs = paper_inputs
        self._content_storage = content_storage
        self._document_parser = document_parser
        self._document_parses = document_parses

    def search(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        _query, rules, input_hash = self._collection_runner.prepare_execution(
            scope=context.contract.paper_search_scope
        )
        producer_name, producer_version = self._collection_runner.producer_identity
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="paper_collection",
            producer_type="algorithm",
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=input_hash,
            parameters={"selection_limit": rules.selection_limit},
            attempt=attempt,
            lease=lease,
        )
        try:
            collection = self._collection_runner.run(
                scope=context.contract.paper_search_scope,
                source_mode=SourceMode.live,
                data_level=DataSourceDataLevel.live_result,
                run_id=str(context.run_id),
            )
        except Exception:
            self._publications.finish_producer(
                execution.id, status="failed", error_code="PAPER_COLLECTION_FAILED"
            )
            raise
        self._publications.ensure_source_snapshots(context, collection.source_snapshots)
        # The Publisher contract for PaperCollection admits SourceSnapshot
        # bindings only: literature Evidence rows are declared by the later
        # summarizing/reasoning steps, never by the search publication.
        source_bindings = self._publications.source_bindings(
            context, collection.source_snapshot_ids
        )
        admitted = admit_artifact_candidate(
            collection,
            schema_version=collection.schema_version,
            source_snapshot_ids=collection.source_snapshot_ids,
            evidence_ids=(),
            evidence_validator=lambda _context: None,
            domain_validator=lambda _context: None,
            quality_validator=lambda _context: None,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=(),
        )
        self._publications.finish_producer(
            execution.id, status="completed", output_hash=admitted.content_hash
        )
        publication = self._publications.publication(
            context,
            kind="paper_collection",
            candidate=admitted,
            producer_execution_id=execution.id,
        )
        context.paper_collection = collection
        return PreparedStep(
            publications=(publication,),
            activity_result_summary=f"已检索相关文献，入选 {len(collection.candidates)} 篇候选论文",
        )

    def summarize(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
        model_execution: ModelExecutionPort,
    ) -> PreparedStep:
        collection = context.paper_collection
        if collection is None:
            raise ValueError("paper_collection must be prepared first")
        collection_version_id = context.versions.get("paper_collection")
        if collection_version_id is None:
            raise ValueError("paper_collection must be published first")
        candidate = _selected_candidate(collection)
        full_text = (
            self._paper_inputs.accepted_research_input(
                session_id=context.session_id,
                project_id=str(context.project_id),
                paper_collection_version_id=str(collection_version_id),
                canonical_paper_id=candidate.canonical_paper_id,
            )
            if self._paper_inputs is not None
            else None
        )
        if full_text is not None:
            return self._summarize_document(
                context,
                step_key=step_key,
                attempt=attempt,
                lease=lease,
                model_caller=model_caller,
                model_execution=model_execution,
                candidate=candidate,
                research_input=full_text,
            )
        evidence_candidates = _evidence_candidates(candidate)
        model_response, response, execution_id = model_caller.execute_json(
            prompt_name="paper_summary",
            input_payload={
                "research_goal": context.contract.research_goal,
                "paper_payload": {
                    "paper_id": candidate.canonical_paper_id,
                    "title": candidate.raw.title,
                    "authors": list(candidate.raw.authors or ()),
                    "year": candidate.raw.year,
                    "doi": candidate.raw.doi,
                    "url": str(candidate.raw.url),
                    "paper_collection_version_id": str(collection_version_id),
                },
                "evidence_candidates": [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in evidence_candidates
                ],
            },
            parameters=MODEL_PARAMETERS,
            producer_name=SUMMARY_PRODUCER_NAME,
            producer_version=SUMMARY_PRODUCER_VERSION,
        )
        result = PaperSummaryPipeline().admit(
            paper_collection=collection,
            paper_collection_version_id=str(collection_version_id),
            paper_id=candidate.canonical_paper_id,
            model_response=model_response,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            evidence_candidates=evidence_candidates,
            execution_id=str(execution_id),
            run_id=str(context.run_id),
        )
        if (
            result.admission_status is not PaperSummaryAdmissionStatus.accepted
            or result.summary is None
        ):
            model_caller.reject(
                execution_id,
                input_hash=None,
                response=response,
                error_code=f"PAPER_SUMMARY_{result.failure_stage or 'REJECTED'}",
            )
            raise ValueError(f"论文总结未通过准入: {result.failure_stage}")
        summary = result.summary
        summary_version_id = step_uuid(
            str(context.run_id), "artifact-version:paper_summary"
        )
        source_bindings, evidence_bindings = self._publications.paper_summary_bindings(
            context, summary
        )
        admitted = admit_artifact_candidate(
            summary,
            schema_version=summary.schema_version,
            source_snapshot_ids=summary.source_snapshot_ids,
            evidence_ids=summary.evidence_ids,
            evidence_validator=lambda _context: None,
            domain_validator=lambda _context: None,
            quality_validator=lambda _context: None,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        model_caller.complete(
            execution_id,
            input_hash=summary.input_hash,
            output_hash=admitted.content_hash,
            response=response,
        )
        publication = self._publications.publication(
            context,
            kind="paper_summary",
            candidate=admitted,
            producer_execution_id=execution_id,
            version_id=summary_version_id,
        )
        context.paper_summary = summary
        return PreparedStep(
            publications=(publication,),
            activity_result_summary=f"已归纳《{summary.paper.title}》的核心科研发现与支持证据",
        )

    def _summarize_document(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
        model_execution: ModelExecutionPort,
        candidate: PaperCollectionCandidate,
        research_input: object,
    ) -> PreparedStep:
        if (
            self._content_storage is None
            or self._document_parser is None
            or self._document_parses is None
        ):
            raise ValueError("全文论文总结需要生产文档解析运行时")
        content_hash = str(getattr(research_input, "content_hash"))
        content = asyncio.run(self._content_storage.retrieve(content_hash))
        if content is None:
            raise ValueError("已绑定论文全文的不可变内容不存在")
        parse_input = DocumentParseInput(
            research_input_id=str(getattr(research_input, "id")),
            content_hash=content_hash,
            source_type=str(getattr(research_input, "source_type")),
            mime_type=str(getattr(research_input, "mime_type") or "application/pdf"),
            filename=getattr(research_input, "filename"),
            input_bytes=content,
        )
        profile = self._document_parser.profile
        parse_input_hash = compute_canonical_payload_hash(
            {
                "input": parse_input.model_dump(
                    mode="json", exclude_none=True, exclude={"input_bytes"}
                ),
                "profile": profile.model_dump(mode="json"),
            }
        )
        parse_execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key=f"document_parse:{candidate.canonical_paper_id}",
            producer_type="algorithm",
            producer_name="scientific-document-parser",
            producer_version=profile.parser_profile_version,
            input_hash=parse_input_hash,
            parameters={
                "parser_profile_id": profile.parser_profile_id,
                "routing_policy_id": profile.routing_policy_id,
            },
            parameters_hash=profile.configuration_hash,
            attempt=attempt,
            lease=lease,
        )
        try:
            document = self._document_parser.parse_document(parse_input)
        except Exception:
            self._publications.finish_producer(
                parse_execution.id,
                status="failed",
                error_code="DOCUMENT_PARSE_FAILED",
            )
            raise
        self._publications.finish_producer(
            parse_execution.id,
            status="completed",
            output_hash=document.canonical_output_hash,
        )
        parse_record = asyncio.run(
            self._document_parses.persist(
                PersistDocumentParseRequest(
                    project_id=context.project_id,
                    run_id=context.run_id,
                    run_step_id=attempt.run_step_id,
                    producer_execution_id=parse_execution.id,
                    parse_input_hash=parse_input_hash,
                    candidate=document,
                )
            )
        )
        if document.overall_quality is DocumentParseQuality.unsupported:
            raise ValueError("当前解析器无法可靠读取所选论文全文")

        snapshot = self._document_parses.source_snapshot(
            project_id=context.project_id,
            document_parse_id=parse_record.id,
        )
        snapshot_reference = PaperSummarySourceSnapshotReference(
            source_snapshot_id=str(snapshot.id),
            source_id=snapshot.source_id,
            source_version=snapshot.source_version,
            content_hash=snapshot.content_hash,
        )
        paper = PaperSummaryPaperMetadata(
            paper_id=candidate.canonical_paper_id,
            title=candidate.raw.title,
            authors=tuple(candidate.raw.authors or ()),
            year=candidate.raw.year,
        )
        evidence_candidates = build_document_evidence_candidates(
            document_parse=document,
            document_parse_id=str(parse_record.id),
            paper_id=paper.paper_id,
            source_id=snapshot.source_id,
            source_record_id=candidate.raw.source_record_id,
            source_snapshot_id=str(snapshot.id),
        )
        if not evidence_candidates:
            raise ValueError("论文全文没有可用于总结的可靠文本证据")
        prompt = model_caller.prompt("paper_summary")
        _, summary_input_hash, parameters_hash = build_document_summary_input_identity(
            document_parse=document,
            document_parse_id=str(parse_record.id),
            source_snapshot=snapshot_reference,
            paper=paper,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            evidence_candidates=evidence_candidates,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
        )
        summary_execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="document_paper_summary",
            producer_type="model",
            producer_name=SUMMARY_PRODUCER_NAME,
            producer_version=SUMMARY_PRODUCER_VERSION,
            input_hash=summary_input_hash,
            parameters={
                **MODEL_PARAMETERS,
                "resume_from_completed_children": True,
            },
            parameters_hash=parameters_hash,
            model_provider=model_caller.provider,
            requested_model=model_caller.requested_model,
            explicit_revision=model_caller.explicit_revision,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.content_hash,
            attempt=attempt,
            lease=lease,
        )
        request = ExecuteDocumentSummaryRequest(
            document_parse=document,
            document_parse_id=str(parse_record.id),
            source_snapshot=snapshot_reference,
            paper=paper,
            source_id=snapshot.source_id,
            source_record_id=candidate.raw.source_record_id,
            research_goal=context.contract.research_goal,
            provider=model_caller.provider,
            model=model_caller.requested_model,
            model_revision=model_caller.explicit_revision,
            parameters=MODEL_PARAMETERS,
            run_id=str(context.run_id),
            producer_execution_id=str(summary_execution.id),
        )
        try:
            result = ChunkedDocumentSummaryService(model_execution).execute(request)
        except Exception:
            self._publications.finish_producer(
                summary_execution.id,
                status="failed",
                error_code="DOCUMENT_SUMMARY_FAILED",
            )
            raise
        if (
            result.admission.admission_status
            is not PaperSummaryAdmissionStatus.accepted
            or result.admission.summary is None
        ):
            self._publications.finish_producer(
                summary_execution.id,
                status="rejected",
                output_hash=result.admission.producer.model_response_hash,
                response=result.model_response,
                error_code="DOCUMENT_SUMMARY_REJECTED",
            )
            raise ValueError("论文全文总结未通过证据准入")
        summary = result.admission.summary
        source_bindings, evidence_bindings = self._publications.paper_summary_bindings(
            context,
            summary,
            source_snapshots_are_persisted=True,
        )
        admitted = admit_artifact_candidate(
            summary,
            schema_version=summary.schema_version,
            source_snapshot_ids=summary.source_snapshot_ids,
            evidence_ids=summary.evidence_ids,
            evidence_validator=lambda _context: None,
            domain_validator=lambda _context: None,
            quality_validator=lambda _context: None,
            source_snapshot_bindings=source_bindings,
            evidence_bindings=evidence_bindings,
        )
        self._publications.finish_producer(
            summary_execution.id,
            status="completed",
            input_hash=summary.input_hash,
            output_hash=admitted.content_hash,
            response=result.model_response,
        )
        for evidence in summary.evidence:
            locator = evidence.locator.document_locator
            if locator is None:
                continue
            asyncio.run(
                self._document_parses.persist_locator(
                    project_id=context.project_id,
                    document_parse_id=parse_record.id,
                    source_snapshot_id=snapshot.id,
                    locator=locator,
                )
            )
        publication = self._publications.publication(
            context,
            kind="paper_summary",
            candidate=admitted,
            producer_execution_id=summary_execution.id,
            version_id=step_uuid(str(context.run_id), "artifact-version:paper_summary"),
        )
        context.paper_summary = summary
        return PreparedStep(
            publications=(publication,),
            activity_result_summary=(
                f"已从论文全文归纳《{summary.paper.title}》并保留逐段证据定位"
            ),
        )


__all__ = ["PaperStepService"]
