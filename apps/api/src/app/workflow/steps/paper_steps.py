"""Paper search and summary step services for Research Runs."""

from __future__ import annotations

from app.schemas.enums import SourceMode
from app.schemas.source_acquisition import DataSourceDataLevel
from app.schemas.paper_collection import PaperCollectionCandidate
from app.schemas.paper_summary import (
    PaperSummaryAdmissionStatus,
    PaperSummaryEvidenceCandidate,
    PaperSummaryEvidenceLocator,
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
from services.paper_pipeline.live_collection import LivePaperCollectionRunner
from services.paper_pipeline.summary import PaperSummaryPipeline

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
    ) -> None:
        self._publications = publications
        self._collection_runner = collection_runner or LivePaperCollectionRunner()

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
    ) -> PreparedStep:
        collection = context.paper_collection
        if collection is None:
            raise ValueError("paper_collection must be prepared first")
        collection_version_id = context.versions.get("paper_collection")
        if collection_version_id is None:
            raise ValueError("paper_collection must be published first")
        candidate = _selected_candidate(collection)
        evidence_candidates = _evidence_candidates(candidate)
        prompt = model_caller.prompt("paper_summary")
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
        )
        result = PaperSummaryPipeline().admit(
            paper_collection=collection,
            paper_collection_version_id=str(collection_version_id),
            paper_id=candidate.canonical_paper_id,
            model_response=model_response,
            model_name=model_caller.requested_model,
            parameters=MODEL_PARAMETERS,
            evidence_candidates=evidence_candidates,
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
        source_bindings, evidence_bindings = (
            self._publications.paper_summary_bindings(context, summary)
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


__all__ = ["PaperStepService"]
