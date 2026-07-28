"""D-03 PaperSummary model-output, Evidence, and Artifact content contracts."""

from __future__ import annotations

from copy import deepcopy
from enum import StrEnum
import re
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PrivateAttr,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .manifest import ContentHash, Identifier, SemanticVersion
from .paper_collection import PaperBenchmarkReference


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
_UNSAFE_HTML = re.compile(r"<\s*/?\s*[a-z][^>]*>", re.IGNORECASE)
_ARTIFACT_PUBLICATION_SEAL = object()


def _validate_safe_text(value: str) -> str:
    if _UNSAFE_HTML.search(value) or any(
        ord(character) < 32 and character not in "\t\n\r" for character in value
    ):
        raise ValueError("unsafe markup or control characters are forbidden")
    return value


NonEmptyString = Annotated[
    str, Field(min_length=1, max_length=4000), AfterValidator(_validate_safe_text)
]
ShortString = Annotated[
    str, Field(min_length=1, max_length=512), AfterValidator(_validate_safe_text)
]
PaperMetadataField = Literal[
    "source_record_id",
    "title",
    "authors",
    "year",
    "doi",
    "arxiv_id",
    "url",
]


class PaperSummarySupportStatus(StrEnum):
    supported = "supported"
    unsupported = "unsupported"
    unverifiable = "unverifiable"


class PaperSummaryAdmissionStatus(StrEnum):
    accepted = "accepted"
    rejected = "rejected"


class PaperSummaryFailureStage(StrEnum):
    json = "json"
    schema = "schema"


class PaperSummaryStatementCandidate(BaseModel):
    model_config = MODEL_CONFIG

    statement_id: Identifier
    text: NonEmptyString
    evidence_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_evidence_ids(self) -> Self:
        _require_unique(self.evidence_ids, "statement evidence id")
        return self


class PaperSummaryModelOutput(BaseModel):
    """The complete JSON shape accepted before Evidence validation."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    research_goal: PaperSummaryStatementCandidate | None
    method: PaperSummaryStatementCandidate | None
    dataset: PaperSummaryStatementCandidate | None
    findings: tuple[PaperSummaryStatementCandidate, ...]
    limitations: tuple[PaperSummaryStatementCandidate, ...]
    future_work: tuple[PaperSummaryStatementCandidate, ...]
    evidence_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_statement_registry(self) -> Self:
        statements = self.statements()
        _require_unique(
            tuple(statement.statement_id for statement in statements),
            "summary statement id",
        )
        expected_evidence_ids = tuple(
            sorted({evidence_id for item in statements for evidence_id in item.evidence_ids})
        )
        if self.evidence_ids != expected_evidence_ids:
            raise ValueError("evidence_ids must equal the sorted statement Evidence union")
        return self

    def statements(self) -> tuple[PaperSummaryStatementCandidate, ...]:
        singular = tuple(
            item
            for item in (self.research_goal, self.method, self.dataset)
            if item is not None
        )
        return singular + self.findings + self.limitations + self.future_work


class PaperSummaryEvidenceLocator(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["paper_text", "paper_metadata"]
    source_url: HttpUrl
    section: ShortString | None = None
    paragraph: int | None = Field(default=None, ge=1)
    text_range: ShortString | None = None
    metadata_field: PaperMetadataField | None = None

    @model_validator(mode="after")
    def validate_locator_shape(self) -> Self:
        if self.kind == "paper_text":
            if not self.section or not self.text_range or self.metadata_field:
                raise ValueError("paper_text locator requires section and text_range")
        elif not self.metadata_field or any(
            value is not None for value in (self.section, self.paragraph, self.text_range)
        ):
            raise ValueError("paper_metadata locator requires only metadata_field")
        return self


class PaperSummaryEvidenceCandidate(BaseModel):
    """Caller-supplied, bounded Evidence input; source excerpt is never published."""

    model_config = MODEL_CONFIG

    evidence_id: Identifier
    paper_id: Identifier
    candidate_id: Identifier
    source_id: Identifier
    source_record_id: ShortString
    source_snapshot_id: Identifier
    claimed_source_version: ShortString | None = None
    locator: PaperSummaryEvidenceLocator
    quote_or_value: NonEmptyString
    accessible_excerpt: Annotated[str, Field(min_length=1, max_length=16000)] | None = Field(
        default=None, repr=False
    )


class PaperSummarySourceSnapshotReference(BaseModel):
    model_config = MODEL_CONFIG

    source_snapshot_id: Identifier
    source_id: Identifier
    source_version: ShortString
    content_hash: ContentHash


class PaperSummaryInputVersions(BaseModel):
    model_config = MODEL_CONFIG

    paper_collection_version_id: Identifier
    paper_collection_schema_version: SemanticVersion
    paper_collection_output_hash: ContentHash
    source_snapshots: tuple[PaperSummarySourceSnapshotReference, ...]

    @model_validator(mode="after")
    def validate_snapshot_versions(self) -> Self:
        _require_unique(
            tuple(item.source_snapshot_id for item in self.source_snapshots),
            "input SourceSnapshot version",
        )
        return self


class PaperSummaryEvidence(BaseModel):
    model_config = MODEL_CONFIG

    evidence_id: Identifier
    paper_id: Identifier
    candidate_id: Identifier
    source_id: Identifier
    source_record_id: ShortString
    source_snapshot_id: Identifier
    source_snapshot_version: ShortString
    source_snapshot_content_hash: ContentHash
    locator: PaperSummaryEvidenceLocator
    quote_or_value: NonEmptyString
    status: PaperSummarySupportStatus
    validation_code: Identifier


class PaperSummarySourceConflict(BaseModel):
    model_config = MODEL_CONFIG

    conflict_id: Identifier
    evidence_id: Identifier
    source_snapshot_id: Identifier
    claimed_source_version: ShortString
    source_snapshot_version: ShortString
    resolution: Literal["source_snapshot_version_retained"] = (
        "source_snapshot_version_retained"
    )


class PaperSummaryStatement(BaseModel):
    model_config = MODEL_CONFIG

    statement_id: Identifier
    text: NonEmptyString
    evidence_ids: tuple[Identifier, ...]
    status: PaperSummarySupportStatus
    validation_code: Identifier

    @model_validator(mode="after")
    def validate_support_state(self) -> Self:
        _require_unique(self.evidence_ids, "summary statement evidence id")
        if self.status is PaperSummarySupportStatus.supported and not self.evidence_ids:
            raise ValueError("supported summary statement requires Evidence")
        return self


class PaperSummaryProducerExecution(BaseModel):
    model_config = MODEL_CONFIG

    execution_id: Identifier
    run_id: Identifier | None = None
    step_key: Literal["summarizing_papers"] = "summarizing_papers"
    producer_type: Literal["model"] = "model"
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    model_name: ShortString
    prompt_name: Identifier
    prompt_version: ShortString
    prompt_hash: ContentHash
    parameters_version: SemanticVersion
    parameters_hash: ContentHash
    input_versions: PaperSummaryInputVersions
    input_hash: ContentHash
    model_response_hash: ContentHash
    output_hash: ContentHash | None = None
    status: Literal["completed", "rejected"]
    started_at: AwareDatetime
    finished_at: AwareDatetime
    latency_ms: int = Field(ge=0)
    error_code: Identifier | None = None

    @model_validator(mode="after")
    def validate_terminal_state(self) -> Self:
        if self.status == "completed":
            if self.output_hash is None or self.error_code is not None:
                raise ValueError("completed summary execution requires only output_hash")
        elif self.output_hash is not None or self.error_code is None:
            raise ValueError("rejected summary execution requires only error_code")
        return self


class PaperSummaryArtifactContent(BaseModel):
    """Publisher-ready D-03 content used directly by the v2 Artifact discriminator."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: object | None = PrivateAttr(default=None)

    kind: Literal["paper_summary"]
    schema_version: Literal["1.0.0"]
    summary_id: Identifier
    paper_id: Identifier
    benchmark: PaperBenchmarkReference
    input_versions: PaperSummaryInputVersions
    research_goal: PaperSummaryStatement | None
    method: PaperSummaryStatement | None
    dataset: PaperSummaryStatement | None
    findings: tuple[PaperSummaryStatement, ...]
    limitations: tuple[PaperSummaryStatement, ...]
    future_work: tuple[PaperSummaryStatement, ...]
    evidence_ids: tuple[Identifier, ...]
    evidence: tuple[PaperSummaryEvidence, ...]
    source_conflicts: tuple[PaperSummarySourceConflict, ...]
    producer: PaperSummaryProducerExecution
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_summary_integrity(self) -> Self:
        statements = self.statements()
        _require_unique(
            tuple(statement.statement_id for statement in statements),
            "summary statement id",
        )
        expected_evidence_ids = tuple(
            sorted({evidence_id for item in statements for evidence_id in item.evidence_ids})
        )
        if self.evidence_ids != expected_evidence_ids:
            raise ValueError("evidence_ids must equal the sorted statement Evidence union")
        evidence_by_id = _unique_registry(self.evidence, "evidence_id", "summary Evidence")
        conflict_by_id = _unique_registry(
            self.source_conflicts, "conflict_id", "source conflict"
        )
        if any(
            conflict.evidence_id not in evidence_by_id
            for conflict in conflict_by_id.values()
        ):
            raise ValueError("source conflict must reference retained Evidence")
        snapshots = {
            item.source_snapshot_id: item for item in self.input_versions.source_snapshots
        }
        for evidence in self.evidence:
            snapshot = snapshots.get(evidence.source_snapshot_id)
            if snapshot is None:
                raise ValueError("Evidence must reference an input SourceSnapshot version")
            if (
                evidence.source_id != snapshot.source_id
                or evidence.source_snapshot_version != snapshot.source_version
                or evidence.source_snapshot_content_hash != snapshot.content_hash
            ):
                raise ValueError("Evidence SourceSnapshot version does not match input")
        for statement in statements:
            if statement.status is not PaperSummarySupportStatus.supported:
                continue
            retained = [evidence_by_id.get(item) for item in statement.evidence_ids]
            if not retained or any(
                item is None or item.status is not PaperSummarySupportStatus.supported
                for item in retained
            ):
                raise ValueError("supported statement requires fully supported Evidence")
        if self.producer.status != "completed":
            raise ValueError("published PaperSummary requires completed ProducerExecution")
        if self.input_versions != self.producer.input_versions:
            raise ValueError("ProducerExecution input versions do not match summary")
        if self.input_hash != self.producer.input_hash:
            raise ValueError("ProducerExecution input_hash does not match summary")
        expected_output_hash = compute_paper_summary_output_hash(self)
        if self.output_hash != expected_output_hash:
            raise ValueError(f"output_hash does not match PaperSummary: {expected_output_hash}")
        if self.producer.output_hash != expected_output_hash:
            raise ValueError("ProducerExecution output_hash does not match summary")
        return self

    def statements(self) -> tuple[PaperSummaryStatement, ...]:
        singular = tuple(
            item
            for item in (self.research_goal, self.method, self.dataset)
            if item is not None
        )
        return singular + self.findings + self.limitations + self.future_work

    def __artifact_publication_is_admitted__(self) -> bool:
        return self._artifact_publication_seal is _ARTIFACT_PUBLICATION_SEAL


class PaperSummaryAdmissionResult(BaseModel):
    model_config = MODEL_CONFIG

    admission_status: PaperSummaryAdmissionStatus
    failure_stage: PaperSummaryFailureStage | None = None
    summary: PaperSummaryArtifactContent | None = None
    producer: PaperSummaryProducerExecution

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.admission_status is PaperSummaryAdmissionStatus.accepted:
            if self.failure_stage is not None or self.summary is None:
                raise ValueError("accepted admission requires only a Summary")
        elif self.failure_stage is None or self.summary is not None:
            raise ValueError("rejected admission requires only a failure_stage")
        return self


class PaperSummaryBenchmarkEvaluationCase(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    benchmark_summary_id: Identifier
    admission: PaperSummaryAdmissionResult
    unsupported_statement_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        _require_unique(self.unsupported_statement_ids, "unsupported statement target")
        return self


class PaperSummaryBenchmarkCaseResult(BaseModel):
    model_config = MODEL_CONFIG

    case_id: Identifier
    benchmark_summary_id: Identifier
    schema_valid: bool
    core_item_count: int = Field(ge=0)
    supported_core_item_count: int = Field(ge=0)
    unsupported_expected: bool
    unsupported_blocked: bool
    input_hash: ContentHash
    model_response_hash: ContentHash
    output_hash: ContentHash | None = None


class PaperSummaryBenchmarkReport(BaseModel):
    model_config = MODEL_CONFIG

    report_version: Literal["1.0.0"] = "1.0.0"
    benchmark_id: Identifier
    benchmark_schema_version: SemanticVersion
    benchmark_version: SemanticVersion
    benchmark_scientific_payload_hash: ContentHash
    benchmark_content_hash: ContentHash
    prompt_name: Identifier
    prompt_version: ShortString
    prompt_hash: ContentHash
    model_name: ShortString
    parameters_version: SemanticVersion
    parameters_hash: ContentHash
    cases: tuple[PaperSummaryBenchmarkCaseResult, ...] = Field(min_length=1)
    schema_items_valid: int = Field(ge=0)
    schema_items_total: int = Field(ge=1)
    schema_pass_rate: float = Field(ge=0.0, le=1.0)
    evidence_items_supported: int = Field(ge=0)
    evidence_items_total: int = Field(ge=0)
    evidence_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    unsupported_items_blocked: int = Field(ge=0)
    unsupported_items_total: int = Field(ge=0)
    unsupported_block_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    human_review_sample_ids: tuple[Identifier, ...] = Field(min_length=1)
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_report_hash(self) -> Self:
        _require_unique(tuple(case.case_id for case in self.cases), "benchmark case id")
        _require_unique(self.human_review_sample_ids, "human review sample id")
        if self.schema_items_valid > self.schema_items_total:
            raise ValueError("schema pass numerator must not exceed denominator")
        if self.evidence_items_supported > self.evidence_items_total:
            raise ValueError("Evidence coverage numerator must not exceed denominator")
        if self.unsupported_items_blocked > self.unsupported_items_total:
            raise ValueError("unsupported block numerator must not exceed denominator")
        expected = compute_paper_summary_benchmark_output_hash(self)
        if self.output_hash != expected:
            raise ValueError(f"output_hash does not match benchmark report: {expected}")
        return self


def compute_paper_summary_output_hash(
    value: PaperSummaryArtifactContent | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    producer = payload.get("producer", {})
    if isinstance(producer, dict):
        for field in (
            "execution_id",
            "run_id",
            "output_hash",
            "started_at",
            "finished_at",
            "latency_ms",
        ):
            producer.pop(field, None)
    return compute_canonical_payload_hash(payload)


def _seal_paper_summary_for_publication(
    value: PaperSummaryArtifactContent,
) -> PaperSummaryArtifactContent:
    object.__setattr__(
        value,
        "_artifact_publication_seal",
        _ARTIFACT_PUBLICATION_SEAL,
    )
    return value


def compute_paper_summary_benchmark_output_hash(
    value: PaperSummaryBenchmarkReport | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def _model_or_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return deepcopy(value.model_dump(mode="json", exclude_none=True))
    return _drop_none(deepcopy(value))


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_none(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    return value


def _require_unique(values: tuple[Any, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _unique_registry(
    values: tuple[BaseModel, ...], attribute: str, label: str
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        key = str(getattr(value, attribute))
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = value
    return result
