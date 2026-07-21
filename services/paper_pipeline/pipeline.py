"""Orchestrate D-02 acquisition without owning ResearchRun state or publishing."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
)
from app.schemas.evidence import SourceSnapshot
from app.schemas.paper_benchmark import BenchmarkPackage, BenchmarkSearchScenario
from app.schemas.paper_collection import (
    PaperBenchmarkReference,
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

from .benchmark import load_frozen_benchmark
from .canonicalize import (
    CandidateDraft,
    canonicalize_record,
    normalize_arxiv_id,
    normalize_doi,
    normalize_title,
)
from .constants import (
    CANONICALIZATION_VERSION,
    DEDUPE_VERSION,
    FROZEN_X00_MAIN_SHA,
    PRODUCER_NAME,
    PRODUCER_VERSION,
    QUERY_NORMALIZATION_VERSION,
    RANKING_VERSION,
    RETRY_POLICY_VERSION,
    SELECTION_VERSION,
    SOURCE_POLICY_VERSION,
)
from .dedupe import group_duplicates
from .query import normalize_benchmark_query
from .ranking import rank_and_select
from .sources.base import PaperSourceAdapter, RawSourceRecord, SourceFailure
from .sources.crossref import CrossrefAdapter


Clock = Callable[[], datetime]


class PaperCollectionPipeline:
    """Generate publisher-ready content while leaving publication to B-06."""

    def __init__(
        self,
        *,
        benchmark: BenchmarkPackage | None = None,
        adapter: PaperSourceAdapter | None = None,
        timeout_seconds: float = 15.0,
        clock: Clock | None = None,
    ) -> None:
        self.benchmark = benchmark or load_frozen_benchmark()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        crossref_policy = next(
            policy
            for policy in self.benchmark.source_policies
            if policy.source_id == "crossref"
        )
        self.adapter = adapter or CrossrefAdapter(
            license_note=(
                f"{crossref_policy.license_boundary} "
                f"{crossref_policy.full_text_boundary}"
            ),
            timeout_seconds=timeout_seconds,
            clock=self.clock,
        )

    def run(
        self,
        *,
        scenario_id: str,
        page_size: int = 20,
        selection_limit: int = 10,
        source_mode: SourceMode = SourceMode.live,
        data_level: PaperDataLevel = PaperDataLevel.live_result,
        run_id: str | None = None,
    ) -> PaperCollection:
        scenario = self._scenario(scenario_id)
        started_at = self._now()
        query = normalize_benchmark_query(
            scenario,
            source_ids=(self.adapter.source_id,),
            page_size=page_size,
        )
        benchmark_reference = PaperBenchmarkReference(
            benchmark_id=self.benchmark.benchmark_id,
            schema_version=self.benchmark.schema_version,
            benchmark_version=self.benchmark.benchmark_version,
            scientific_payload_hash=self.benchmark.scientific_payload_hash,
            content_hash=self.benchmark.content_hash,
            scenario_id=scenario.scenario_id,
            x00_main_sha=FROZEN_X00_MAIN_SHA,
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
            selection_limit=selection_limit,
        )
        input_hash = compute_paper_collection_input_hash(
            benchmark_reference, query, rules
        )

        source_executions: list[PaperSourceExecution] = []
        snapshots = []
        source_records: list[RawSourceRecord] = []
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
            selection_limit=selection_limit,
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
        recalled_count = _recalled_expected_count(
            candidates=drafts,
            scenario=scenario,
            benchmark=self.benchmark,
        )
        expected_count = len(set(scenario.expected_paper_ids))
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
                error_code
                if producer_status is ProducerExecutionStatus.failed
                else None
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
            expected_candidate_count=expected_count,
            recalled_expected_candidate_count=recalled_count,
            candidate_recall=round(recalled_count / expected_count, 6),
        )
        payload = PaperCollectionPayload(
            benchmark=benchmark_reference,
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

    def _scenario(self, scenario_id: str) -> BenchmarkSearchScenario:
        for scenario in self.benchmark.search_scenarios:
            if scenario.scenario_id == scenario_id:
                return scenario
        raise ValueError(f"unknown frozen benchmark scenario: {scenario_id}")

    def _now(self) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise ValueError("pipeline clock must return timezone-aware datetime")
        return value


def _canonicalize_records(
    records: list[RawSourceRecord], snapshots: list[SourceSnapshot]
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


def _recalled_expected_count(
    *,
    candidates: tuple[CandidateDraft, ...],
    scenario: BenchmarkSearchScenario,
    benchmark: BenchmarkPackage,
) -> int:
    expected_ids = set(scenario.expected_paper_ids)
    expected_papers = {
        paper.paper_id: paper
        for paper in benchmark.seed_papers
        if paper.paper_id in expected_ids
    }
    recalled: set[str] = set()
    for expected_id, paper in expected_papers.items():
        expected_doi = normalize_doi(paper.doi)
        expected_arxiv = normalize_arxiv_id(paper.arxiv_id)
        expected_title = normalize_title(paper.title)
        for candidate in candidates:
            if expected_doi and candidate.doi == expected_doi:
                recalled.add(expected_id)
                break
            if expected_arxiv and candidate.arxiv_id == expected_arxiv:
                recalled.add(expected_id)
                break
            if (
                candidate.normalized_title == expected_title
                and candidate.year == paper.year
            ):
                recalled.add(expected_id)
                break
    return len(recalled)


def _stable_source_execution_payload(
    execution: PaperSourceExecution,
) -> dict[str, object]:
    payload = execution.model_dump(mode="json", exclude_none=True)
    payload.pop("started_at", None)
    payload.pop("finished_at", None)
    for page in payload.get("pages", []):
        page.pop("retrieved_at", None)
    return payload
