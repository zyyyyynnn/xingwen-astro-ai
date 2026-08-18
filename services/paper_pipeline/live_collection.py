"""Contract-driven live paper acquisition through the reusable search components.

This is the production counterpart of the benchmark runner: the query comes
from the confirmed ResearchContract's paper search scope instead of a frozen
benchmark scenario, and the resulting collection carries no benchmark
reference or recall metrics. The canonicalize/dedupe/rank components and the
source adapters are shared with the benchmark path.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import PaperSearchScope
from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
)
from app.schemas.paper_collection import (
    PaperCollection,
    PaperCollectionAcquisitionRun,
    PaperCollectionMetrics,
    PaperCollectionPayload,
    PaperCollectionRules,
    PaperSourceExecution,
    ProducerExecution,
    compute_paper_collection_input_hash,
    compute_paper_collection_output_hash,
)

from .canonicalize import CandidateDraft, canonicalize_record
from .constants import (
    CANONICALIZATION_VERSION,
    DEDUPE_VERSION,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    QUERY_NORMALIZATION_VERSION,
    RANKING_VERSION,
    RETRY_POLICY_VERSION,
    SELECTION_VERSION,
    SOURCE_POLICY_VERSION,
)
from .dedupe import group_duplicates
from .query import normalize_live_query
from .ranking import rank_and_select
from .sources.base import PaperSourceAdapter, SourceFailure
from .sources.crossref import CrossrefAdapter


Clock = Callable[[], datetime]

# Governed Crossref acquisition boundary shared with the frozen source policy.
CROSSREF_LICENSE_NOTE = (
    "Metadata may be retrieved publicly; linked content remains governed by "
    "the publisher or repository license. Crossref supplies deposited "
    "metadata and links, not a general entitlement to article full text."
)


class LivePaperCollectionRunner:
    """Run one contract-scoped live paper acquisition."""

    def __init__(
        self,
        *,
        adapter: PaperSourceAdapter | None = None,
        timeout_seconds: float = 15.0,
        clock: Clock | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.adapter = adapter or CrossrefAdapter(
            license_note=CROSSREF_LICENSE_NOTE,
            timeout_seconds=timeout_seconds,
            clock=self.clock,
        )

    def prepare_execution(
        self,
        *,
        scope: PaperSearchScope,
        page_size: int = 20,
    ) -> tuple[object, PaperCollectionRules, str]:
        if not scope.keywords:
            raise ValueError("live paper search requires contract keywords")
        if not scope.source_ids:
            raise ValueError("live paper search requires contract source ids")
        query = normalize_live_query(
            keywords=scope.keywords,
            year_from=scope.year_from,
            year_to=scope.year_to,
            source_ids=tuple(scope.source_ids),
            page_size=page_size,
            candidate_limit=scope.max_candidates,
        )
        rules = PaperCollectionRules(
            adapter_name=self.adapter.adapter_name,
            adapter_version=self.adapter.adapter_version,
            query_normalization_version=QUERY_NORMALIZATION_VERSION,
            canonicalization_version=CANONICALIZATION_VERSION,
            dedupe_version=DEDUPE_VERSION,
            ranking_version=RANKING_VERSION,
            selection_version=SELECTION_VERSION,
            retry_policy_version=RETRY_POLICY_VERSION,
            source_policy_version=SOURCE_POLICY_VERSION,
            selection_limit=scope.max_candidates,
        )
        return query, rules, compute_paper_collection_input_hash(None, query, rules)

    @property
    def producer_identity(self) -> tuple[str, str]:
        return PRODUCER_NAME, PRODUCER_VERSION

    def run(
        self,
        *,
        scope: PaperSearchScope,
        source_mode: SourceMode = SourceMode.live,
        data_level: PaperDataLevel = PaperDataLevel.live_result,
        page_size: int = 20,
        run_id: str | None = None,
    ) -> PaperCollection:
        started_at = self._now()
        query, rules, input_hash = self.prepare_execution(
            scope=scope, page_size=page_size
        )

        source_executions: list[PaperSourceExecution] = []
        snapshots = []
        source_records: list = []
        source_started_at = self._now()
        request_parameters_hash = compute_canonical_payload_hash(
            {
                "query_hash": query.query_hash,
                "source_id": self.adapter.source_id,
                "parameters": query.source_parameters[self.adapter.source_id],
                "pagination": query.pagination.model_dump(mode="json"),
            }
        )
        try:
            result = self.adapter.search(
                query, source_mode=source_mode, data_level=data_level
            )
        except SourceFailure as failure:
            source_finished_at = self._now()
            source_executions.append(
                PaperSourceExecution(
                    source_id=self.adapter.source_id,
                    source_mode=source_mode,
                    data_level=data_level,
                    status=PaperSourceExecutionStatus.failed,
                    query_hash=query.query_hash,
                    request_parameters_hash=request_parameters_hash,
                    pagination=query.pagination,
                    started_at=source_started_at,
                    finished_at=source_finished_at,
                    pages=(),
                    source_snapshot_id=None,
                    candidate_count=0,
                    retry_count=max(failure.attempt_count - 1, 0),
                    failure_class=failure.classification,
                    failure_code=failure.code,
                )
            )
        else:
            source_finished_at = self._now()
            snapshots.append(result.snapshot)
            source_records.extend(result.records)
            source_executions.append(
                PaperSourceExecution(
                    source_id=self.adapter.source_id,
                    source_mode=source_mode,
                    data_level=data_level,
                    status=PaperSourceExecutionStatus.completed,
                    query_hash=query.query_hash,
                    request_parameters_hash=request_parameters_hash,
                    pagination=query.pagination,
                    started_at=source_started_at,
                    finished_at=source_finished_at,
                    pages=result.pages,
                    source_snapshot_id=result.snapshot.snapshot_id,
                    candidate_count=len(result.records),
                    retry_count=result.retry_count,
                )
            )

        drafts = _canonicalize_records(source_records, snapshots)
        dedupe = group_duplicates(drafts)
        candidates = rank_and_select(
            drafts,
            dedupe,
            normalized_keywords=query.normalized_keywords,
            normalized_query=query.normalized_query_string,
            year_from=query.year_from,
            year_to=query.year_to,
            selection_limit=scope.max_candidates,
        )
        selected_paper_ids = tuple(
            sorted(
                {
                    candidate.canonical_paper_id
                    for candidate in candidates
                    if candidate.selected
                }
            )
        )
        failure_count = sum(
            execution.status is PaperSourceExecutionStatus.failed
            for execution in source_executions
        )
        successful_count = len(source_executions) - failure_count
        if successful_count == 0:
            acquisition_status = "failed"
        elif failure_count:
            acquisition_status = "partial"
        else:
            acquisition_status = "completed"
        finished_at = self._now()
        fingerprint = compute_canonical_payload_hash(
            {
                "input_hash": input_hash,
                "source_executions": [
                    _stable_source_execution_payload(execution)
                    for execution in source_executions
                ],
            }
        )
        acquisition_id = f"acquisition.{fingerprint.removeprefix('sha256:')[:24]}"
        producer_id_hash = compute_canonical_payload_hash(
            {"input_hash": input_hash, "acquisition_id": acquisition_id}
        )
        producer_status = (
            ProducerExecutionStatus.failed
            if acquisition_status == "failed"
            else ProducerExecutionStatus.completed
        )
        error_code = next(
            (
                execution.failure_code
                for execution in source_executions
                if execution.failure_code
            ),
            None,
        )
        latency_ms = max(
            0, int((finished_at - started_at).total_seconds() * 1_000)
        )
        producer = ProducerExecution(
            execution_id=f"producer.{producer_id_hash.removeprefix('sha256:')[:24]}",
            run_id=run_id,
            producer_name=PRODUCER_NAME,
            producer_version=PRODUCER_VERSION,
            parameters_hash=compute_canonical_payload_hash(
                rules.model_dump(mode="json", exclude_none=True)
            ),
            input_hash=input_hash,
            output_hash=None,
            status=producer_status,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            error_code=(
                error_code if producer_status is ProducerExecutionStatus.failed else None
            ),
        )
        duplicate_count = len(candidates) - len(dedupe.groups)
        duplicate_rate = duplicate_count / len(candidates) if candidates else 0.0
        metrics = PaperCollectionMetrics(
            source_execution_count=len(source_executions),
            source_failure_count=failure_count,
            source_empty_result_count=sum(
                execution.status is PaperSourceExecutionStatus.completed
                and execution.candidate_count == 0
                for execution in source_executions
            ),
            candidate_count=len(candidates),
            duplicate_candidate_count=duplicate_count,
            duplicate_rate=round(duplicate_rate, 6),
            selected_count=len(selected_paper_ids),
        )
        payload = PaperCollectionPayload(
            benchmark=None,
            query=query,
            acquisition_run=PaperCollectionAcquisitionRun(
                acquisition_id=acquisition_id,
                status=acquisition_status,
                started_at=started_at,
                finished_at=finished_at,
                candidate_count=len(candidates),
                duplicate_group_count=len(dedupe.groups),
                selected_count=len(selected_paper_ids),
                source_failure_count=failure_count,
            ),
            source_executions=tuple(source_executions),
            source_snapshots=tuple(snapshots),
            source_snapshot_ids=tuple(
                sorted(snapshot.snapshot_id for snapshot in snapshots)
            ),
            candidates=candidates,
            duplicate_groups=dedupe.groups,
            potential_duplicates=dedupe.potential_duplicates,
            selected_paper_ids=selected_paper_ids,
            dedupe_rule=(
                "doi_exact > arxiv_exact > title_year_author_match; "
                "uncertainty retained"
            ),
            ranking_rule=(
                "deterministic lexical relevance with canonical final tie-breaker"
            ),
            rules=rules,
            producer=producer,
            input_hash=input_hash,
            metrics=metrics,
        )
        output_hash = compute_paper_collection_output_hash(payload)
        final_payload = payload.model_dump(mode="json", exclude_none=False)
        final_payload["producer"]["output_hash"] = output_hash
        final_payload["output_hash"] = output_hash
        return PaperCollection.model_validate(final_payload)

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("pipeline clock must return timezone-aware datetime")
        return value


def _canonicalize_records(
    records: list, snapshots: list
) -> tuple[CandidateDraft, ...]:
    if not records:
        return ()
    snapshot_id_by_source = {
        snapshot.source_id: snapshot.snapshot_id for snapshot in snapshots
    }
    ordered = sorted(
        records,
        key=lambda record: compute_canonical_payload_hash(record.hash_payload()),
    )
    occurrences: dict[str, int] = {}
    drafts: list[CandidateDraft] = []
    for record in ordered:
        record_key = compute_canonical_payload_hash(record.hash_payload())
        occurrence = occurrences.get(record_key, 0)
        occurrences[record_key] = occurrence + 1
        drafts.append(
            canonicalize_record(
                record,
                snapshot_id=snapshot_id_by_source[record.source_id],
                occurrence_index=occurrence,
            )
        )
    return tuple(drafts)


def _stable_source_execution_payload(
    execution: PaperSourceExecution,
) -> dict[str, object]:
    payload = execution.model_dump(mode="json", exclude_none=True)
    payload.pop("started_at", None)
    payload.pop("finished_at", None)
    for page in payload.get("pages", []):
        page.pop("retrieved_at", None)
    return payload


__all__ = ["CROSSREF_LICENSE_NOTE", "LivePaperCollectionRunner"]
