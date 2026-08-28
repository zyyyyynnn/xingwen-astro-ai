"""Paper search and summary step services for Research Runs."""

from __future__ import annotations


from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    SourceMode,
    UpstreamFailureClass,
)
from app.schemas.paper_collection import PaperCollectionCandidate
from app.schemas.paper_summary import (
    PaperSummaryAdmissionStatus,
    PaperSummaryEvidenceCandidate,
    PaperSummaryEvidenceLocator,
    PaperSummaryPaperMetadata,
    PaperSummarySourceSnapshotReference,
)
from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.scientific_document import DocumentParseQuality
from app.services.artifacts import ArtifactReadService
from app.services.paper_collections import PaperCollectionReadService
from app.services.document_summary import ExecuteDocumentSummaryRequest
from app.services.document_summary_chunks import ChunkedDocumentSummaryService
from app.services.paper_candidate_inputs import PaperCandidateInputReadService
from app.workflow.document_parse_execution import (
    DocumentInputSource,
    DocumentParseExecutionService,
)
from app.workflow.publisher import admit_artifact_candidate
from app.workflow.step_publication import (
    PreparedStep,
    RunStepContext,
    StepModelCaller,
    StepPublicationFactory,
    step_uuid,
)
from app.workflow.store import AttemptHandle, LeaseGrant
from services.paper_pipeline.errors import PaperSearchExecutionError
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.mapper import build_paper_search_input
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


def _summary_parameters_hash(
    parameters: dict[str, float | int],
) -> str:
    """Mirror the PaperSummary pipeline's governed parameter-hash identity."""
    from services.paper_pipeline.constants import SUMMARY_PARAMETERS_VERSION

    return compute_canonical_payload_hash(
        {
            "parameters_version": SUMMARY_PARAMETERS_VERSION,
            "parameters": dict(parameters),
        }
    )


_RETRYABLE_SOURCE_FAILURES = frozenset(
    {
        UpstreamFailureClass.timeout,
        UpstreamFailureClass.rate_limited,
        UpstreamFailureClass.transport,
        UpstreamFailureClass.upstream_server,
        "timeout",
        "rate_limited",
        "transport",
        "upstream_server",
    }
)


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
    """Anchor summary Evidence on the candidate's acquired source record."""

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
    if candidate.raw.abstract is not None:
        quote = candidate.raw.abstract[:4000]
        items.append(
            PaperSummaryEvidenceCandidate(
                evidence_id="ev.abstract",
                locator=PaperSummaryEvidenceLocator(
                    kind="paper_text",
                    source_url=candidate.raw.url,
                    section="abstract",
                    text_range=f"0:{len(quote)}",
                ),
                quote_or_value=quote,
                accessible_excerpt=candidate.raw.abstract,
                **anchor,
            )
        )
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
        document_parse_execution: DocumentParseExecutionService | None = None,
    ) -> None:
        self._publications = publications
        self._collection_runner = collection_runner or LivePaperCollectionRunner()
        self._paper_inputs = paper_inputs
        self._document_parse_execution = document_parse_execution

    def search(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
    ) -> PreparedStep:
        search_input = build_paper_search_input(context.contract)
        _query, rules, input_hash = self._collection_runner.prepare_execution(
            search_input=search_input
        )
        rules_payload = rules.model_dump(mode="json", exclude_none=True)
        rules_hash = compute_canonical_payload_hash(rules_payload)
        producer_name, producer_version = self._collection_runner.producer_identity
        execution = self._publications.start_producer(
            context,
            step_key=step_key,
            operation_key="paper_collection",
            producer_type="algorithm",
            producer_name=producer_name,
            producer_version=producer_version,
            input_hash=input_hash,
            parameters=rules_payload,
            parameters_hash=rules_hash,
            attempt=attempt,
            lease=lease,
        )
        try:
            collection = self._collection_runner.run(
                search_input=search_input,
                source_mode=SourceMode.live,
                data_level=PaperDataLevel.live_result,
                run_id=str(context.run_id),
            )
        except Exception as exc:
            error_code = getattr(exc, "code", None) or "PAPER_COLLECTION_FAILED"
            self._publications.finish_producer(
                execution.id,
                status="failed",
                error_code=error_code,
            )
            raise

        if collection.acquisition_run.status == "failed":
            failed_execution = next(
                (
                    e
                    for e in collection.source_executions
                    if e.status is PaperSourceExecutionStatus.failed
                ),
                None,
            )
            retryable = (
                failed_execution.failure_class in _RETRYABLE_SOURCE_FAILURES
                if failed_execution and failed_execution.failure_class
                else False
            )
            error_code = (
                failed_execution.failure_code
                if failed_execution and failed_execution.failure_code
                else "PAPER_SOURCE_FAILED"
            )
            error = PaperSearchExecutionError(
                code=error_code,
                public_message=(
                    "文献数据源检索超时或限流，请稍后重试。"
                    if retryable
                    else "文献数据源检索遇到不可恢复的错误。"
                ),
                retryable=retryable,
                producer_status="failed",
            )
            self._publications.finish_producer(
                execution.id,
                status="failed",
                input_hash=collection.input_hash,
                error_code=error_code,
            )
            raise error

        if len(collection.candidates) == 0:
            error = PaperSearchExecutionError(
                code="PAPER_COLLECTION_EMPTY",
                public_message="论文检索已完成，但没有找到符合研究协议的候选文献。",
                retryable=False,
                producer_status="rejected",
            )
            self._publications.finish_producer(
                execution.id,
                status="rejected",
                input_hash=collection.input_hash,
                error_code="PAPER_COLLECTION_EMPTY",
            )
            raise error

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
            execution.id,
            status="completed",
            input_hash=collection.input_hash,
            output_hash=admitted.content_hash,
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
    ) -> PreparedStep:
        collection = context.paper_collection
        collection_version_id = context.versions.get("paper_collection")
        if collection is None and collection_version_id is not None:
            read = PaperCollectionReadService(
                ArtifactReadService(self._publications.factory)
            ).get_collection(
                version_id=str(collection_version_id),
                session_id=context.session_id,
            )
            collection = read.collection
            context.paper_collection = collection
        if collection is None:
            raise ValueError("paper_collection must be prepared first")
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
            parameters_hash=_summary_parameters_hash(MODEL_PARAMETERS),
        )
        result = PaperSummaryPipeline().admit(
            paper_collection=collection,
            paper_collection_version_id=str(collection_version_id),
            paper_id=candidate.canonical_paper_id,
            model_response=model_response,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            evidence_candidates=evidence_candidates,
            # Producer metadata requires lowercase dotted identifiers; a raw
            # UUID can start with a digit and would fail admission.
            execution_id=f"paper-summary-execution-{execution_id}",
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
        summary_title = summary.paper.title if summary.paper is not None else None
        return PreparedStep(
            publications=(publication,),
            activity_result_summary=(
                f"已归纳论文《{summary_title}》的核心科研发现与支持证据"
                if summary_title is not None
                else "已归纳所选论文的核心科研发现与支持证据"
            ),
        )

    def _summarize_document(
        self,
        context: RunStepContext,
        *,
        step_key: str,
        attempt: AttemptHandle,
        lease: LeaseGrant,
        model_caller: StepModelCaller,
        candidate: PaperCollectionCandidate,
        research_input: object,
    ) -> PreparedStep:
        if self._document_parse_execution is None:
            raise ValueError("全文论文总结需要生产文档解析运行时")
        parsed = self._document_parse_execution.execute(
            context,
            step_key=step_key,
            attempt=attempt,
            lease=lease,
            source=DocumentInputSource.from_record(research_input),
            operation_key=f"document_parse:paper:{candidate.canonical_paper_id}",
        )
        document = parsed.candidate
        parse_record = parsed.record
        if document.overall_quality is DocumentParseQuality.unsupported:
            raise ValueError("当前解析器无法可靠读取所选论文全文")

        snapshot = parsed.source_snapshot
        snapshot_reference = PaperSummarySourceSnapshotReference(
            source_snapshot_id=str(snapshot.id),
            source_id=snapshot.source_id,
            source_version=snapshot.source_version_or_etag or snapshot.content_hash,
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
        model_execution = model_caller.pin_resumable_port()
        model_identity = model_caller.identity
        _, summary_input_hash, parameters_hash = build_document_summary_input_identity(
            document_parse=document,
            document_parse_id=str(parse_record.id),
            source_snapshot=snapshot_reference,
            paper=paper,
            model_name=model_identity.requested_model,
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
            model_provider=model_identity.provider,
            requested_model=model_identity.requested_model,
            explicit_revision=model_identity.explicit_revision,
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
            provider=model_identity.provider,
            model=model_identity.requested_model,
            model_revision=model_identity.explicit_revision,
            parameters=MODEL_PARAMETERS,
            run_id=str(context.run_id),
            producer_execution_id=f"paper-summary-execution-{summary_execution.id}",
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
            self._document_parse_execution.persist_locator(
                project_id=context.project_id,
                document_parse_id=parse_record.id,
                source_snapshot_id=snapshot.id,
                locator=locator,
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
