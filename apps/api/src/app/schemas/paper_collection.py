"""Typed D-02 PaperCollection pipeline content contract.

This is a pipeline contract, not an HTTP resource or ArtifactVersion publisher.
The future B-06 publisher can place a validated ``PaperCollection`` in an
ArtifactVersion envelope without translating it into a second domain model.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .enums import (
    PaperDataLevel,
    PaperSourceExecutionStatus,
    ProducerExecutionStatus,
    SourceMode,
    UpstreamFailureClass,
)
from .evidence import SourceSnapshotRecord
from .manifest import ContentHash, Identifier, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[str, Field(min_length=1)]
Score = Annotated[float, Field(ge=0.0, le=1.0)]


class PaperBenchmarkReference(BaseModel):
    model_config = MODEL_CONFIG

    benchmark_id: Identifier
    schema_version: SemanticVersion
    benchmark_version: SemanticVersion
    scientific_payload_hash: ContentHash
    content_hash: ContentHash
    scenario_id: Identifier
    x00_main_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]


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
        if tuple(sorted(set(self.source_ids))) != self.source_ids:
            raise ValueError("source_ids must be unique and sorted")
        expected_hash = compute_normalized_query_hash(self)
        if self.query_hash != expected_hash:
            raise ValueError(f"query_hash does not match normalized query: {expected_hash}")
        expected_id = f"query.{expected_hash.removeprefix('sha256:')[:24]}"
        if self.query_id != expected_id:
            raise ValueError(f"query_id does not match normalized query: {expected_id}")
        return self


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

    @model_validator(mode="after")
    def validate_status_details(self) -> Self:
        if self.status is PaperSourceExecutionStatus.completed:
            if self.failure_class or self.failure_code:
                raise ValueError("completed source execution must not contain failure")
            if self.source_snapshot_id is None:
                raise ValueError("completed source execution requires SourceSnapshotRecord")
        else:
            if self.failure_class is None or not self.failure_code:
                raise ValueError("failed source execution requires classified failure")
            if self.source_snapshot_id is not None:
                raise ValueError("failed source execution must not claim SourceSnapshotRecord")
        if self.source_mode is SourceMode.live and self.data_level is not PaperDataLevel.live_result:
            raise ValueError("live source_mode requires live_result data level")
        if self.source_mode is SourceMode.cached and self.data_level is not PaperDataLevel.real_run_cache:
            raise ValueError("cached source_mode requires real_run_cache data level")
        if self.source_mode is SourceMode.fixture and self.data_level not in {
            PaperDataLevel.fixture,
            PaperDataLevel.recorded_response,
            PaperDataLevel.benchmark,
            PaperDataLevel.manual_review,
        }:
            raise ValueError("fixture source_mode requires a non-live test/review data level")
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
    record_hash: ContentHash


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
    canonical_identity_basis: Literal["doi", "arxiv_id", "title_year_authors", "source_record"]
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
    expected_candidate_count: int = Field(ge=0)
    recalled_expected_candidate_count: int = Field(ge=0)
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
        if self.recalled_expected_candidate_count > self.expected_candidate_count:
            raise ValueError("recalled candidates cannot exceed expected candidates")
        if self.expected_candidate_count == 0 and self.candidate_recall is not None:
            raise ValueError("candidate recall must be unavailable for an empty benchmark")
        if self.expected_candidate_count and self.candidate_recall is None:
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
    run_id: Identifier | None = None
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

    schema_version: Literal["1.0.0"] = "1.0.0"
    benchmark: PaperBenchmarkReference
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
        candidate_by_id = _unique_by(self.candidates, "candidate_id", "candidate")
        group_by_id = _unique_by(self.duplicate_groups, "duplicate_group_id", "duplicate group")
        snapshot_by_id = _unique_by(self.source_snapshots, "snapshot_id", "SourceSnapshotRecord")
        _unique_by(self.source_executions, "source_id", "source execution")

        if self.source_snapshot_ids != tuple(sorted(snapshot_by_id)):
            raise ValueError("source_snapshot_ids must equal sorted SourceSnapshotRecord ids")

        grouped_candidate_ids: list[str] = []
        for group in self.duplicate_groups:
            if tuple(sorted(group.candidate_ids)) != group.candidate_ids:
                raise ValueError("duplicate group candidate ids must be sorted")
            for candidate_id in group.candidate_ids:
                if candidate_id not in candidate_by_id:
                    raise ValueError(f"unknown duplicate group candidate: {candidate_id}")
                candidate = candidate_by_id[candidate_id]
                if candidate.duplicate_group_id != group.duplicate_group_id:
                    raise ValueError("candidate duplicate group reference mismatch")
            grouped_candidate_ids.extend(group.candidate_ids)
        if sorted(grouped_candidate_ids) != sorted(candidate_by_id):
            raise ValueError("every candidate must belong to exactly one duplicate group")

        for candidate in self.candidates:
            if candidate.raw.source_snapshot_id not in snapshot_by_id:
                raise ValueError(f"candidate lacks SourceSnapshotRecord: {candidate.candidate_id}")
            if candidate.duplicate_group_id not in group_by_id:
                raise ValueError(f"candidate has unknown duplicate group: {candidate.candidate_id}")

        selected_ids = tuple(
            sorted({candidate.canonical_paper_id for candidate in self.candidates if candidate.selected})
        )
        if self.selected_paper_ids != selected_ids:
            raise ValueError("selected_paper_ids do not match selected candidates")

        for execution in self.source_executions:
            if execution.source_snapshot_id and execution.source_snapshot_id not in snapshot_by_id:
                raise ValueError("source execution has unknown SourceSnapshotRecord")
            if execution.source_mode is SourceMode.cached and execution.source_snapshot_id:
                snapshot = snapshot_by_id[execution.source_snapshot_id]
                required_origin = {"origin_run_id", "origin_artifact_version_id"}
                if not required_origin.issubset(snapshot.request_metadata):
                    raise ValueError("cached source requires real origin Run and ArtifactVersion")

        expected_input_hash = compute_paper_collection_input_hash(
            self.benchmark, self.query, self.rules
        )
        if self.input_hash != expected_input_hash or self.producer.input_hash != expected_input_hash:
            raise ValueError("PaperCollection input hash is inconsistent")

        failure_count = sum(
            execution.status is PaperSourceExecutionStatus.failed
            for execution in self.source_executions
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


def compute_paper_collection_input_hash(
    benchmark: PaperBenchmarkReference,
    query: NormalizedPaperQuery,
    rules: PaperCollectionRules,
) -> str:
    return compute_canonical_payload_hash(
        {
            "benchmark": benchmark.model_dump(mode="json", exclude_none=True),
            "query_hash": query.query_hash,
            "rules": rules.model_dump(mode="json", exclude_none=True),
        }
    )


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
