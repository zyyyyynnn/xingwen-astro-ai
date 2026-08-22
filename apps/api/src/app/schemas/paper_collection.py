"""Typed content contract for collected-paper artifacts.

This is a pipeline contract, not an HTTP resource or ArtifactVersion publisher.
The API publisher places a validated ``PaperCollection`` in an
ArtifactVersion envelope without translating it into a second domain model.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Annotated, Any, Literal, Self
import unicodedata

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .core import Identifier as CoreIdentifier
from .enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
    UpstreamFailureClass,
)
from .evidence import SourceSnapshotRecord
from .manifest import ContentHash, Identifier, SemanticVersion
from .persistence import PersistedUuid


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[str, Field(min_length=1)]
_WHITESPACE = re.compile(r"\s+")


def normalize_paper_query_text(value: str) -> str:
    """Canonical Unicode NFKC whitespace-collapsed casefolded text normalizer."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value)).strip().casefold()


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("value must not be blank")
    return value


NonBlankString = Annotated[
    str,
    Field(min_length=1),
    AfterValidator(_reject_blank),
]
Score = Annotated[float, Field(ge=0.0, le=1.0)]


class PaperBenchmarkReference(BaseModel):
    model_config = MODEL_CONFIG

    benchmark_id: Identifier
    schema_version: SemanticVersion
    benchmark_version: SemanticVersion
    scientific_payload_hash: ContentHash
    content_hash: ContentHash
    scenario_id: Identifier


class PaperQueryPagination(BaseModel):
    model_config = MODEL_CONFIG

    page_size: int = Field(gt=0, le=100)
    max_pages: int = Field(gt=0, le=100)
    candidate_limit: int = Field(gt=0, le=100)


class NormalizedPaperQuery(BaseModel):
    model_config = MODEL_CONFIG

    query_id: Identifier
    normalization_rule_version: SemanticVersion
    original_keywords: tuple[NonEmptyString, ...] = Field(min_length=1)
    normalized_keywords: tuple[NonEmptyString, ...] = Field(min_length=1)
    original_query_string: NonEmptyString
    normalized_query_string: NonEmptyString
    year_from: int = Field(ge=1900, le=2100)
    year_to: int = Field(ge=1900, le=2100)
    source_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_parameters: dict[Identifier, dict[str, Any]]
    pagination: PaperQueryPagination
    sort_strategy: NonEmptyString
    query_hash: ContentHash

    @model_validator(mode="after")
    def validate_normalized_query(self) -> Self:
        if self.year_from > self.year_to:
            raise ValueError("query year_from must not exceed year_to")
        if tuple(sorted(set(self.normalized_keywords))) != self.normalized_keywords:
            raise ValueError("normalized_keywords must be unique and sorted")
        expected_keywords = tuple(
            sorted({
                normalize_paper_query_text(keyword)
                for keyword in self.original_keywords
            })
        )
        if self.normalized_keywords != expected_keywords:
            raise ValueError(
                "normalized_keywords does not match normalized original_keywords"
            )
        if self.normalized_query_string != normalize_paper_query_text(
            self.original_query_string
        ):
            raise ValueError(
                "normalized_query_string does not match normalized original_query_string"
            )
        if tuple(sorted(set(self.source_ids))) != self.source_ids:
            raise ValueError("source_ids must be unique and sorted")
        expected_hash = compute_normalized_query_hash(self)
        if self.query_hash != expected_hash:
            raise ValueError(
                f"query_hash does not match normalized query: {expected_hash}"
            )
        expected_id = f"query.{expected_hash.removeprefix('sha256:')[:24]}"
        if self.query_id != expected_id:
            raise ValueError(f"query_id does not match normalized query: {expected_id}")
        return self


class PaperSearchInput(BaseModel):
    """Typed scientific input contract for live contract-driven paper search."""

    model_config = MODEL_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    contract_id: CoreIdentifier
    contract_version: int = Field(ge=1)
    contract_content_hash: ContentHash
    keywords: tuple[NonEmptyString, ...] = Field(min_length=1)
    year_from: int = Field(ge=1900, le=2100)
    year_to: int = Field(ge=1900, le=2100)
    source_ids: tuple[Identifier, ...] = Field(min_length=1)
    candidate_limit: int = Field(gt=0, le=100)
    selection_limit: int = Field(gt=0, le=100)
    stable_ordering: Literal[
        "source_relevance_then_canonical_tie_breaker"
    ] = "source_relevance_then_canonical_tie_breaker"
    content_scope: Literal["bibliographic_metadata"] = "bibliographic_metadata"
    access_policy: Literal[
        "metadata_url_only_requires_independent_access_evidence"
    ] = "metadata_url_only_requires_independent_access_evidence"
    source_policy_version: SemanticVersion = "1.0.0"
    producer_name: NonEmptyString = "xingwen.paper_collection"
    producer_version: SemanticVersion = "1.0.0"
    input_hash: ContentHash

    @model_validator(mode="after")
    def validate_paper_search_input(self) -> Self:
        if self.selection_limit > self.candidate_limit:
            raise ValueError("selection_limit must not exceed candidate_limit")
        if self.year_from > self.year_to:
            raise ValueError("year_from must not exceed year_to")
        if tuple(sorted(set(self.source_ids))) != self.source_ids:
            raise ValueError("source_ids must be unique and sorted")
        expected_hash = compute_paper_search_input_hash(self)
        if self.input_hash != expected_hash:
            raise ValueError(
                f"input_hash does not match PaperSearchInput: {expected_hash}"
            )
        return self


def compute_paper_search_input_hash(
    value: PaperSearchInput | dict[str, Any],
) -> str:
    if isinstance(value, BaseModel):
        payload = deepcopy(
            value.model_dump(
                mode="json",
                exclude_none=True,
            )
        )
    else:
        payload = {
            key: deepcopy(item)
            for key, item in value.items()
            if item is not None
        }

    payload.pop("input_hash", None)
    return compute_canonical_payload_hash(payload)


class PaperCollectionRules(BaseModel):
    model_config = MODEL_CONFIG

    adapter_name: NonEmptyString
    adapter_version: SemanticVersion
    query_normalization_version: SemanticVersion
    canonicalization_version: SemanticVersion
    dedupe_version: SemanticVersion
    ranking_version: SemanticVersion
    selection_version: SemanticVersion
    retry_policy_version: SemanticVersion
    source_policy_version: SemanticVersion
    selection_limit: int = Field(gt=0, le=100)


class PaperSourcePage(BaseModel):
    model_config = MODEL_CONFIG

    page_number: int = Field(gt=0)
    offset: int = Field(ge=0)
    requested_rows: int = Field(gt=0, le=100)
    returned_rows: int = Field(ge=0)
    total_results: int | None = Field(default=None, ge=0)
    attempt_count: int = Field(gt=0)
    status_code: int = Field(ge=100, le=599)
    retrieved_at: AwareDatetime
    request_hash: ContentHash
    response_hash: ContentHash
    rate_limit_metadata: dict[str, str | int | None] = Field(default_factory=dict)


class PaperSourceExecution(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    source_mode: SourceMode
    data_level: PaperDataLevel
    status: PaperSourceExecutionStatus
    query_hash: ContentHash
    request_parameters_hash: ContentHash
    pagination: PaperQueryPagination
    started_at: AwareDatetime
    finished_at: AwareDatetime
    pages: tuple[PaperSourcePage, ...] = ()
    source_snapshot_id: Identifier | None = None
    candidate_count: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    failure_class: UpstreamFailureClass | None = None
    failure_code: str | None = None
    # Cached-run audit context (PaperCollection API read boundary): why this cached snapshot
    # applies to the current query, and how the live attempt failed. All three
    # fields are required for cached executions so a cached result is always
    # fully auditable, and forbidden otherwise.
    cache_applicability: NonBlankString | None = None
    live_failure_class: UpstreamFailureClass | None = None
    live_failure_code: NonBlankString | None = None

    @model_validator(mode="after")
    def validate_status_details(self) -> Self:
        if self.status is PaperSourceExecutionStatus.completed:
            if self.failure_class or self.failure_code:
                raise ValueError("completed source execution must not contain failure")
            if self.source_snapshot_id is None:
                raise ValueError(
                    "completed source execution requires SourceSnapshotRecord"
                )
        else:
            if self.failure_class is None or not self.failure_code:
                raise ValueError("failed source execution requires classified failure")
            if self.source_snapshot_id is not None:
                raise ValueError(
                    "failed source execution must not claim SourceSnapshotRecord"
                )
        if (
            self.source_mode is SourceMode.live
            and self.data_level is not PaperDataLevel.live_result
        ):
            raise ValueError("live source_mode requires live_result data level")
        if (
            self.source_mode is SourceMode.cached
            and self.data_level is not PaperDataLevel.real_run_cache
        ):
            raise ValueError("cached source_mode requires real_run_cache data level")
        if self.source_mode is SourceMode.fixture and self.data_level not in {
            PaperDataLevel.fixture,
            PaperDataLevel.recorded_response,
            PaperDataLevel.benchmark,
            PaperDataLevel.manual_review,
        }:
            raise ValueError(
                "fixture source_mode requires a non-live test/review data level"
            )
        if self.source_mode is SourceMode.cached:
            if self.cache_applicability is None:
                raise ValueError("cached source execution requires cache_applicability")
            if self.live_failure_class is None or not self.live_failure_code:
                raise ValueError(
                    "cached source execution requires live_failure_class and live_failure_code"
                )
        elif (
            self.cache_applicability is not None
            or self.live_failure_class is not None
            or self.live_failure_code is not None
        ):
            raise ValueError(
                "cache audit fields are only allowed for cached source_mode"
            )
        return self


class RawPaperCandidate(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    source_record_id: NonEmptyString
    source_snapshot_id: Identifier
    title: NonEmptyString
    authors: tuple[NonEmptyString, ...] = ()
    year: int | None = Field(default=None, ge=1900, le=2100)
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    abstract: Annotated[str, Field(min_length=1, max_length=16000)] | None = None
    record_hash: ContentHash
    # Record-level provenance label for synthetic demo/test records; a live
    # acquisition never sets it. Reviewers must be able to tell synthetic
    # review material from real bibliographic records per candidate.
    synthetic_note: NonEmptyString | None = None


class PaperCandidateConflict(BaseModel):
    model_config = MODEL_CONFIG

    field: Literal["doi", "arxiv_id", "title", "year", "authors"]
    related_candidate_id: Identifier
    classification: Literal["conflict", "uncertain_match"]
    detail: NonEmptyString


class PaperCollectionCandidate(BaseModel):
    model_config = MODEL_CONFIG

    candidate_id: Identifier
    raw: RawPaperCandidate
    canonical_paper_id: Identifier
    canonical_identity_basis: Literal[
        "doi", "arxiv_id", "title_year_authors", "source_record"
    ]
    title: NonEmptyString
    normalized_title: NonEmptyString
    authors: tuple[NonEmptyString, ...] = ()
    normalized_authors: tuple[str, ...] = ()
    year: int | None = Field(default=None, ge=1900, le=2100)
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    duplicate_group_id: Identifier
    dedupe_evidence: tuple[NonEmptyString, ...] = ()
    conflicts: tuple[PaperCandidateConflict, ...] = ()
    relevance_score: Score
    ranking_key: NonEmptyString
    selected: bool
    selection_reason: str | None = None
    exclusion_reason: str | None = None
    ranking_rule_version: SemanticVersion
    selection_rule_version: SemanticVersion

    @model_validator(mode="after")
    def validate_selection_reason(self) -> Self:
        if self.selected:
            if not self.selection_reason or self.exclusion_reason:
                raise ValueError("selected candidate requires only selection_reason")
        elif not self.exclusion_reason or self.selection_reason:
            raise ValueError("excluded candidate requires only exclusion_reason")
        return self


class PaperDuplicateGroup(BaseModel):
    model_config = MODEL_CONFIG

    duplicate_group_id: Identifier
    canonical_paper_id: Identifier
    candidate_ids: tuple[Identifier, ...] = Field(min_length=1)
    match_basis: tuple[NonEmptyString, ...] = Field(min_length=1)
    conflicts: tuple[PaperCandidateConflict, ...] = ()


class PaperPotentialDuplicate(BaseModel):
    model_config = MODEL_CONFIG

    candidate_ids: tuple[Identifier, Identifier]
    basis: Literal["title_year"]
    reason: NonEmptyString


class PaperCollectionMetrics(BaseModel):
    model_config = MODEL_CONFIG

    source_execution_count: int = Field(ge=0)
    source_failure_count: int = Field(ge=0)
    source_empty_result_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    duplicate_candidate_count: int = Field(ge=0)
    duplicate_rate: Score
    selected_count: int = Field(ge=0)
    # Benchmark recall is only defined when the collection was produced by a
    # frozen benchmark scenario; a contract-driven live collection has no
    # expected-paper set and must leave all three fields null.
    expected_candidate_count: int | None = Field(default=None, ge=0)
    recalled_expected_candidate_count: int | None = Field(default=None, ge=0)
    candidate_recall: Score | None = None

    @model_validator(mode="after")
    def validate_metric_bounds(self) -> Self:
        if self.source_failure_count > self.source_execution_count:
            raise ValueError("source failures cannot exceed source executions")
        if self.source_empty_result_count > self.source_execution_count:
            raise ValueError("empty results cannot exceed source executions")
        if self.duplicate_candidate_count > self.candidate_count:
            raise ValueError("duplicate candidates cannot exceed candidates")
        if self.selected_count > self.candidate_count:
            raise ValueError("selected candidates cannot exceed candidates")
        if (self.expected_candidate_count is None) != (
            self.recalled_expected_candidate_count is None
        ):
            raise ValueError(
                "benchmark recall fields must be present or absent together"
            )
        if (
            self.recalled_expected_candidate_count is not None
            and self.expected_candidate_count is not None
            and self.recalled_expected_candidate_count > self.expected_candidate_count
        ):
            raise ValueError("recalled candidates cannot exceed expected candidates")
        if (
            self.expected_candidate_count is None
            and self.candidate_recall is not None
        ):
            raise ValueError(
                "candidate recall must be unavailable without a benchmark"
            )
        if (
            self.expected_candidate_count is not None
            and self.recalled_expected_candidate_count is not None
            and self.candidate_recall is None
        ):
            raise ValueError("candidate recall is required for a non-empty benchmark")
        return self


class PaperCollectionAcquisitionRun(BaseModel):
    """Pipeline-local acquisition execution, never a ResearchRun state owner."""

    model_config = MODEL_CONFIG

    acquisition_id: Identifier
    status: Literal["completed", "partial", "failed"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    candidate_count: int = Field(ge=0)
    duplicate_group_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    source_failure_count: int = Field(ge=0)


class ProducerExecution(BaseModel):
    model_config = MODEL_CONFIG

    execution_id: Identifier
    run_id: PersistedUuid | None = None
    step_key: Literal["searching_papers"] = "searching_papers"
    producer_type: Literal["algorithm"] = "algorithm"
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    parameters_hash: ContentHash
    input_hash: ContentHash
    output_hash: ContentHash | None = None
    status: ProducerExecutionStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: int = Field(ge=0)
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_error(self) -> Self:
        if self.status is ProducerExecutionStatus.failed and not self.error_code:
            raise ValueError("failed ProducerExecution requires error_code")
        if self.status is ProducerExecutionStatus.completed and self.error_code:
            raise ValueError("completed ProducerExecution must not contain error_code")
        return self


class PaperCollectionPayload(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["paper_collection"] = "paper_collection"
    schema_version: Literal["3.0.0"] = "3.0.0"
    benchmark: PaperBenchmarkReference | None = None
    search_input: PaperSearchInput | None = None
    query: NormalizedPaperQuery
    acquisition_run: PaperCollectionAcquisitionRun
    source_executions: tuple[PaperSourceExecution, ...] = Field(min_length=1)
    source_snapshots: tuple[SourceSnapshotRecord, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...] = ()
    candidates: tuple[PaperCollectionCandidate, ...] = ()
    duplicate_groups: tuple[PaperDuplicateGroup, ...] = ()
    potential_duplicates: tuple[PaperPotentialDuplicate, ...] = ()
    selected_paper_ids: tuple[Identifier, ...] = ()
    dedupe_rule: NonEmptyString
    ranking_rule: NonEmptyString
    rules: PaperCollectionRules
    producer: ProducerExecution
    input_hash: ContentHash
    metrics: PaperCollectionMetrics

    @model_validator(mode="after")
    def validate_collection_integrity(self) -> Self:
        if self.benchmark is not None and self.search_input is not None:
            raise ValueError(
                "PaperCollection cannot carry both benchmark and search_input"
            )
        if self.benchmark is None and self.search_input is None:
            raise ValueError(
                "PaperCollection requires either benchmark or search_input"
            )

        if self.search_input is not None:
            if self.search_input.keywords != self.query.original_keywords:
                raise ValueError(
                    "PaperSearchInput keywords do not match normalized query"
                )
            if self.search_input.year_from != self.query.year_from:
                raise ValueError(
                    "PaperSearchInput year_from does not match normalized query"
                )
            if self.search_input.year_to != self.query.year_to:
                raise ValueError(
                    "PaperSearchInput year_to does not match normalized query"
                )
            if self.query.original_query_string != " ".join(self.search_input.keywords):
                raise ValueError(
                    "PaperSearchInput original query string is inconsistent"
                )
            if self.search_input.source_ids != self.query.source_ids:
                raise ValueError(
                    "PaperSearchInput source_ids do not match normalized query"
                )
            if (
                self.search_input.candidate_limit
                != self.query.pagination.candidate_limit
            ):
                raise ValueError(
                    "PaperSearchInput candidate_limit does not match query pagination"
                )
            if self.search_input.stable_ordering != self.query.sort_strategy:
                raise ValueError(
                    "PaperSearchInput stable_ordering does not match query sort strategy"
                )
            if self.search_input.selection_limit != self.rules.selection_limit:
                raise ValueError(
                    "PaperSearchInput selection_limit does not match collection rules"
                )
            if (
                self.search_input.source_policy_version
                != self.rules.source_policy_version
            ):
                raise ValueError(
                    "PaperSearchInput source_policy_version does not match collection rules"
                )
            if (
                self.search_input.producer_name != self.producer.producer_name
                or self.search_input.producer_version
                != self.producer.producer_version
            ):
                raise ValueError(
                    "PaperSearchInput producer identity does not match ProducerExecution"
                )

        if (
            self.query.normalization_rule_version
            != self.rules.query_normalization_version
        ):
            raise ValueError(
                "query normalization rule version does not match collection rules"
            )
        if tuple(sorted(self.query.source_parameters.keys())) != self.query.source_ids:
            raise ValueError(
                "query source_parameters registry does not match query source_ids"
            )

        candidate_by_id = _unique_by(self.candidates, "candidate_id", "candidate")
        group_by_id = _unique_by(
            self.duplicate_groups, "duplicate_group_id", "duplicate group"
        )
        snapshot_by_id = _unique_by(
            self.source_snapshots, "snapshot_id", "SourceSnapshotRecord"
        )
        _unique_by(self.source_executions, "source_id", "source execution")

        execution_source_ids = tuple(
            sorted(execution.source_id for execution in self.source_executions)
        )
        if execution_source_ids != self.query.source_ids:
            raise ValueError(
                "source executions do not match normalized query sources"
            )

        execution_snapshot_ids = {
            execution.source_snapshot_id
            for execution in self.source_executions
            if execution.source_snapshot_id is not None
        }
        if execution_snapshot_ids != set(self.source_snapshot_ids):
            raise ValueError(
                "collection source_snapshot_ids does not match execution snapshots"
            )

        if self.source_snapshot_ids != tuple(sorted(snapshot_by_id)):
            raise ValueError(
                "source_snapshot_ids must equal sorted SourceSnapshotRecord ids"
            )

        grouped_candidate_ids: list[str] = []
        for group in self.duplicate_groups:
            if tuple(sorted(group.candidate_ids)) != group.candidate_ids:
                raise ValueError("duplicate group candidate ids must be sorted")
            for candidate_id in group.candidate_ids:
                if candidate_id not in candidate_by_id:
                    raise ValueError(
                        f"unknown duplicate group candidate: {candidate_id}"
                    )
                candidate = candidate_by_id[candidate_id]
                if candidate.duplicate_group_id != group.duplicate_group_id:
                    raise ValueError("candidate duplicate group reference mismatch")
            grouped_candidate_ids.extend(group.candidate_ids)
        if sorted(grouped_candidate_ids) != sorted(candidate_by_id):
            raise ValueError(
                "every candidate must belong to exactly one duplicate group"
            )

        execution_by_source = {
            execution.source_id: execution
            for execution in self.source_executions
        }
        for candidate in self.candidates:
            if candidate.raw.source_snapshot_id not in snapshot_by_id:
                raise ValueError(
                    f"candidate lacks SourceSnapshotRecord: {candidate.candidate_id}"
                )
            if candidate.duplicate_group_id not in group_by_id:
                raise ValueError(
                    f"candidate has unknown duplicate group: {candidate.candidate_id}"
                )
            if candidate.raw.source_id not in execution_by_source:
                raise ValueError(
                    f"candidate has unknown source_id: {candidate.raw.source_id}"
                )
            c_execution = execution_by_source[candidate.raw.source_id]
            if c_execution.status is not PaperSourceExecutionStatus.completed:
                raise ValueError(
                    f"candidate belongs to non-completed execution: {candidate.candidate_id}"
                )
            if candidate.raw.source_snapshot_id != c_execution.source_snapshot_id:
                raise ValueError(
                    f"candidate source_snapshot_id does not match execution snapshot: {candidate.candidate_id}"
                )
            if candidate.ranking_rule_version != self.rules.ranking_version:
                raise ValueError(
                    f"candidate ranking_rule_version does not match collection rules: {candidate.candidate_id}"
                )
            if candidate.selection_rule_version != self.rules.selection_version:
                raise ValueError(
                    f"candidate selection_rule_version does not match collection rules: {candidate.candidate_id}"
                )

        selected_ids = tuple(
            sorted(
                {
                    candidate.canonical_paper_id
                    for candidate in self.candidates
                    if candidate.selected
                }
            )
        )
        if self.selected_paper_ids != selected_ids:
            raise ValueError("selected_paper_ids do not match selected candidates")

        for execution in self.source_executions:
            expected_req_hash = compute_paper_source_request_parameters_hash(
                self.query, execution.source_id
            )
            if execution.request_parameters_hash != expected_req_hash:
                raise ValueError(
                    "source execution request_parameters_hash does not match normalized query"
                )
            if execution.query_hash != self.query.query_hash:
                raise ValueError(
                    "source execution query_hash does not match normalized query"
                )
            if execution.pagination != self.query.pagination:
                raise ValueError(
                    "source execution pagination does not match normalized query"
                )
            actual_count = sum(
                candidate.raw.source_id == execution.source_id
                for candidate in self.candidates
            )
            if execution.candidate_count != actual_count:
                raise ValueError(
                    f"source execution candidate_count is inconsistent for {execution.source_id}"
                )
            if (
                execution.source_snapshot_id
                and execution.source_snapshot_id not in snapshot_by_id
            ):
                raise ValueError("source execution has unknown SourceSnapshotRecord")
            if execution.source_snapshot_id:
                snapshot = snapshot_by_id[execution.source_snapshot_id]
                if snapshot.source_id != execution.source_id:
                    raise ValueError(
                        "SourceSnapshot source_id does not match source execution"
                    )
                if snapshot.query_hash != execution.query_hash:
                    raise ValueError(
                        "SourceSnapshot query_hash does not match source execution"
                    )
                if snapshot.request_metadata.get("adapter_name") != self.rules.adapter_name:
                    raise ValueError(
                        "SourceSnapshot adapter_name does not match collection rules"
                    )
                if (
                    snapshot.request_metadata.get("adapter_version")
                    != self.rules.adapter_version
                ):
                    raise ValueError(
                        "SourceSnapshot adapter_version does not match collection rules"
                    )
            if (
                execution.source_mode is SourceMode.cached
                and execution.source_snapshot_id
            ):
                snapshot = snapshot_by_id[execution.source_snapshot_id]
                required_origin = {"origin_run_id", "origin_artifact_version_id"}
                if not required_origin.issubset(snapshot.request_metadata):
                    raise ValueError(
                        "cached source requires real origin Run and ArtifactVersion"
                    )
                if not snapshot.cache_version or not snapshot.cache_version.strip():
                    raise ValueError("cached source snapshot requires cache_version")

        if self.benchmark is None and self.metrics.expected_candidate_count is not None:
            raise ValueError(
                "benchmark recall metrics require the frozen benchmark reference"
            )
        expected_input_hash = compute_paper_collection_input_hash(
            self.benchmark,
            self.query,
            self.rules,
            search_input=self.search_input,
        )
        if (
            self.input_hash != expected_input_hash
            or self.producer.input_hash != expected_input_hash
        ):
            raise ValueError("PaperCollection input hash is inconsistent")

        expected_parameters_hash = compute_canonical_payload_hash(
            self.rules.model_dump(mode="json", exclude_none=True)
        )
        if self.producer.parameters_hash != expected_parameters_hash:
            raise ValueError(
                "ProducerExecution parameters_hash does not match collection rules"
            )

        failure_count = sum(
            execution.status is PaperSourceExecutionStatus.failed
            for execution in self.source_executions
        )
        successful_count = sum(
            execution.status is PaperSourceExecutionStatus.completed
            for execution in self.source_executions
        )
        if successful_count == 0:
            expected_acquisition_status = "failed"
        elif failure_count > 0:
            expected_acquisition_status = "partial"
        else:
            expected_acquisition_status = "completed"

        if self.acquisition_run.status != expected_acquisition_status:
            raise ValueError(
                "acquisition_run status is inconsistent with source executions"
            )

        if self.acquisition_run.status == "failed":
            if self.producer.status is not ProducerExecutionStatus.failed:
                raise ValueError(
                    "ProducerExecution status must be failed when acquisition fails"
                )
            allowed_failure_codes = {
                execution.failure_code
                for execution in self.source_executions
                if execution.failure_code
            }
            if self.producer.error_code not in allowed_failure_codes:
                raise ValueError(
                    "ProducerExecution error_code must match failed source execution"
                )
        else:
            if self.producer.status is not ProducerExecutionStatus.completed:
                raise ValueError(
                    "ProducerExecution status must be completed for successful acquisition"
                )

        empty_count = sum(
            execution.status is PaperSourceExecutionStatus.completed
            and execution.candidate_count == 0
            for execution in self.source_executions
        )
        duplicate_count = len(self.candidates) - len(self.duplicate_groups)
        if self.metrics.source_execution_count != len(self.source_executions):
            raise ValueError("source execution metric is inconsistent")
        if self.metrics.source_failure_count != failure_count:
            raise ValueError("source failure metric is inconsistent")
        if self.metrics.source_empty_result_count != empty_count:
            raise ValueError("source empty-result metric is inconsistent")
        if self.metrics.candidate_count != len(self.candidates):
            raise ValueError("candidate metric is inconsistent")
        if self.metrics.duplicate_candidate_count != duplicate_count:
            raise ValueError("duplicate metric is inconsistent")
        expected_duplicate_rate = (
            round(duplicate_count / len(self.candidates), 6)
            if self.candidates
            else 0.0
        )
        if self.metrics.duplicate_rate != expected_duplicate_rate:
            raise ValueError("duplicate_rate metric is inconsistent")
        if self.metrics.selected_count != len(self.selected_paper_ids):
            raise ValueError("selected metric is inconsistent")
        if self.acquisition_run.candidate_count != len(self.candidates):
            raise ValueError("acquisition candidate count is inconsistent")
        if self.acquisition_run.duplicate_group_count != len(self.duplicate_groups):
            raise ValueError("acquisition duplicate group count is inconsistent")
        if self.acquisition_run.selected_count != len(self.selected_paper_ids):
            raise ValueError("acquisition selected count is inconsistent")
        if self.acquisition_run.source_failure_count != failure_count:
            raise ValueError("acquisition source failure count is inconsistent")
        return self


class PaperCollection(PaperCollectionPayload):
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_output_hash(self) -> Self:
        expected = compute_paper_collection_output_hash(self)
        if self.output_hash != expected:
            raise ValueError(f"output_hash does not match PaperCollection: {expected}")
        if self.producer.output_hash != expected:
            raise ValueError("ProducerExecution output_hash does not match collection")
        return self


def compute_normalized_query_hash(value: NormalizedPaperQuery | dict[str, Any]) -> str:
    payload = _model_or_dict(value)
    for field in (
        "query_id",
        "query_hash",
        "original_keywords",
        "original_query_string",
    ):
        payload.pop(field, None)
    return compute_canonical_payload_hash(payload)


def compute_paper_source_request_parameters_hash(
    query: NormalizedPaperQuery | dict[str, Any],
    source_id: str,
) -> str:
    query_payload = _model_or_dict(query)
    source_parameters = query_payload.get("source_parameters", {}).get(source_id, {})
    payload = {
        "query_hash": query_payload["query_hash"],
        "source_id": source_id,
        "parameters": source_parameters,
        "pagination": query_payload["pagination"],
    }
    return compute_canonical_payload_hash(payload)


def compute_paper_collection_input_hash(
    benchmark: PaperBenchmarkReference | None,
    query: NormalizedPaperQuery,
    rules: PaperCollectionRules,
    *,
    search_input: PaperSearchInput | None = None,
) -> str:
    if benchmark is not None and search_input is not None:
        raise ValueError(
            "cannot compute input hash with both benchmark and search_input"
        )
    if benchmark is None and search_input is None:
        raise ValueError(
            "input hash requires either benchmark or search_input"
        )
    payload: dict[str, Any] = {
        "query_hash": query.query_hash,
        "rules": rules.model_dump(mode="json", exclude_none=True),
    }
    if benchmark is not None:
        payload["benchmark"] = benchmark.model_dump(mode="json", exclude_none=True)
    if search_input is not None:
        payload["search_input"] = search_input.input_hash
    return compute_canonical_payload_hash(payload)


def compute_paper_collection_output_hash(
    value: PaperCollectionPayload | PaperCollection | dict[str, Any],
) -> str:
    """Hash stable scientific content while excluding retrieval wall-clock fields."""

    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    producer = payload.get("producer", {})
    if isinstance(producer, dict):
        for field in (
            "run_id",
            "output_hash",
            "started_at",
            "finished_at",
            "latency_ms",
        ):
            producer.pop(field, None)
    acquisition = payload.get("acquisition_run", {})
    if isinstance(acquisition, dict):
        acquisition.pop("started_at", None)
        acquisition.pop("finished_at", None)
    for snapshot in payload.get("source_snapshots", []):
        if isinstance(snapshot, dict):
            snapshot.pop("retrieved_at", None)
    for execution in payload.get("source_executions", []):
        if not isinstance(execution, dict):
            continue
        execution.pop("started_at", None)
        execution.pop("finished_at", None)
        for page in execution.get("pages", []):
            if isinstance(page, dict):
                page.pop("retrieved_at", None)
    return compute_canonical_payload_hash(payload)


def _model_or_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return deepcopy(value.model_dump(mode="json", exclude_none=True))
    return deepcopy(value)


def _unique_by(items: tuple[Any, ...], field: str, label: str) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for item in items:
        item_id = getattr(item, field)
        if item_id in registry:
            raise ValueError(f"duplicate {label} id: {item_id}")
        registry[item_id] = item
    return registry


__all__ = [
    "NormalizedPaperQuery",
    "PaperBenchmarkReference",
    "PaperCollection",
    "PaperCollectionAcquisitionRun",
    "PaperCollectionCandidate",
    "PaperCollectionMetrics",
    "PaperCollectionPayload",
    "PaperCollectionRules",
    "PaperDuplicateGroup",
    "PaperPotentialDuplicate",
    "PaperQueryPagination",
    "PaperSearchInput",
    "PaperSourceExecution",
    "PaperSourcePage",
    "ProducerExecution",
    "RawPaperCandidate",
    "compute_normalized_query_hash",
    "compute_paper_collection_input_hash",
    "compute_paper_collection_output_hash",
    "compute_paper_search_input_hash",
    "compute_paper_source_request_parameters_hash",
    "normalize_paper_query_text",
]
