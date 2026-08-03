"""Public, immutable schemas for the C-05 data-quality handoff.

This module is the Pydantic authoring source for quality results.  Pipeline
admission state and Publisher closures intentionally live under
``services.data_pipeline.data_quality`` and are not exported here.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._hashing import compute_canonical_payload_hash
from .core import (
    ContentHash,
    Identifier,
    NonEmptyString,
    ResearchContract,
    SemanticVersion,
)
from .data_artifacts import (
    AlignmentStatus,
    CanonicalRowIdentity,
    DataArtifactBuildInput,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    ManifestPins,
    SourceCollectionArtifactCandidate,
)
from .crossmatch import EntityLevel


MODEL_CONFIG = ConfigDict(
    extra="forbid",
    frozen=True,
    allow_inf_nan=False,
)


class QualityMetricStatus(StrEnum):
    determinate = "determinate"
    insufficient = "insufficient"
    not_applicable = "not_applicable"


class QualityMetricScope(StrEnum):
    field = "field"
    row = "row"
    dataset = "dataset"


class QualityGateStatus(StrEnum):
    pass_ = "pass"
    fail = "fail"
    insufficient = "insufficient"


class QualityErrorCode(StrEnum):
    QUALITY_INPUT_INVALID = "QUALITY_INPUT_INVALID"
    QUALITY_C04_CANDIDATE_MISMATCH = "QUALITY_C04_CANDIDATE_MISMATCH"
    QUALITY_CROSSMATCH_METRICS_MISMATCH = "QUALITY_CROSSMATCH_METRICS_MISMATCH"
    QUALITY_RESEARCH_CONTRACT_MISMATCH = "QUALITY_RESEARCH_CONTRACT_MISMATCH"
    QUALITY_RULE_SET_MISMATCH = "QUALITY_RULE_SET_MISMATCH"
    QUALITY_METRIC_FORMULA_INVALID = "QUALITY_METRIC_FORMULA_INVALID"
    QUALITY_METRIC_REFERENCE_INVALID = "QUALITY_METRIC_REFERENCE_INVALID"
    QUALITY_EVIDENCE_GAP = "QUALITY_EVIDENCE_GAP"
    QUALITY_SOURCE_SCOPE_INSUFFICIENT = "QUALITY_SOURCE_SCOPE_INSUFFICIENT"
    QUALITY_CONSTRAINT_FAILED = "QUALITY_CONSTRAINT_FAILED"
    QUALITY_CONSTRAINT_INSUFFICIENT = "QUALITY_CONSTRAINT_INSUFFICIENT"
    QUALITY_RESULT_HASH_MISMATCH = "QUALITY_RESULT_HASH_MISMATCH"
    QUALITY_ADMISSION_NOT_SEALED = "QUALITY_ADMISSION_NOT_SEALED"
    QUALITY_CAPACITY_EXCEEDED = "QUALITY_CAPACITY_EXCEEDED"


class QualityFailureStage(StrEnum):
    input_validation = "input_validation"
    c04_validation = "c04_validation"
    crossmatch_validation = "crossmatch_validation"
    contract_validation = "contract_validation"
    rule_validation = "rule_validation"
    metric_validation = "metric_validation"
    evidence_validation = "evidence_validation"
    capacity_preflight = "capacity_preflight"
    admission_validation = "admission_validation"


class QualityMetricId(StrEnum):
    field_completeness = "field_completeness"
    field_missingness = "field_missingness"
    field_unresolved_rate = "field_unresolved_rate"
    field_provenance_coverage = "field_provenance_coverage"
    field_evidence_coverage = "field_evidence_coverage"
    field_unit_consistency = "field_unit_consistency"
    field_conflict_rate = "field_conflict_rate"
    row_completeness = "row_completeness"
    row_missingness = "row_missingness"
    row_unresolved_rate = "row_unresolved_rate"
    row_provenance_coverage = "row_provenance_coverage"
    row_evidence_coverage = "row_evidence_coverage"
    row_unit_consistency = "row_unit_consistency"
    row_conflict_rate = "row_conflict_rate"
    dataset_completeness = "dataset_completeness"
    dataset_missingness = "dataset_missingness"
    dataset_unresolved_rate = "dataset_unresolved_rate"
    dataset_provenance_coverage = "dataset_provenance_coverage"
    dataset_evidence_coverage = "dataset_evidence_coverage"
    dataset_unit_consistency = "dataset_unit_consistency"
    dataset_cross_source_conflict_rate = "dataset_cross_source_conflict_rate"
    dataset_same_source_conflict_rate = "dataset_same_source_conflict_rate"
    object_match_coverage = "object_match_coverage"
    low_confidence_edge_rate = "low_confidence_edge_rate"
    review_required_record_rate = "review_required_record_rate"
    inconclusive_record_rate = "inconclusive_record_rate"
    source_scope_completeness = "source_scope_completeness"
    validation_integrity = "validation_integrity"


class QualityFormulaDefinition(BaseModel):
    model_config = MODEL_CONFIG

    formula_id: Identifier
    metric_id: QualityMetricId
    version: SemanticVersion
    numerator_definition: NonEmptyString
    denominator_definition: NonEmptyString
    applicability: Literal["projected_field_ids_only", "dataset_scope", "row_scope"]
    incomplete_source_policy: Literal["insufficient", "not_applicable"]
    empty_denominator_policy: Literal["not_applicable", "insufficient"]


class QualityGateBinding(BaseModel):
    model_config = MODEL_CONFIG

    constraint_id: Identifier
    contract_path: NonEmptyString
    metric_id: QualityMetricId | None = None
    operator: Literal["gte", "equals"]
    rule_binding_version: SemanticVersion
    input_locator: NonEmptyString


class QualityCapacityPolicy(BaseModel):
    model_config = MODEL_CONFIG

    max_rows: int = Field(gt=0, le=100_000)
    max_fields: int = Field(gt=0, le=100_000)
    max_cells: int = Field(gt=0, le=10_000_000)
    max_source_values: int = Field(gt=0, le=10_000_000)
    max_evidence: int = Field(gt=0, le=10_000_000)
    max_conflict_references: int = Field(gt=0, le=10_000_000)
    max_crossmatch_edges: int = Field(gt=0, le=10_000_000)
    max_metric_records: int = Field(gt=0, le=1_000_000)
    max_diagnostic_references: int = Field(gt=0, le=100_000)


class QualityAggregateScorePolicy(BaseModel):
    model_config = MODEL_CONFIG

    enabled: Literal[False] = False
    weights: tuple[()] = ()
    score: None = None


class DataQualityRuleSet(BaseModel):
    """Frozen C-05 rules and all upstream identities they bind."""

    model_config = MODEL_CONFIG

    rule_set_id: Identifier
    schema_version: SemanticVersion
    version: SemanticVersion
    content_hash: ContentHash
    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    data_artifact_input_schema_version: SemanticVersion
    data_artifact_candidate_schema_version: SemanticVersion
    crossmatch_schema_version: SemanticVersion
    crossmatch_rule_set_id: Identifier
    crossmatch_rule_set_version: SemanticVersion
    crossmatch_rule_set_content_hash: ContentHash
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    precision_digits: int = Field(gt=0, le=64)
    rounding_mode: Literal["ROUND_HALF_EVEN"]
    ratio_serialization: Literal["plain_decimal_string_no_exponent"]
    applicability_policy: Literal["projected_field_ids_only"]
    incomplete_source_policy: Literal["insufficient"]
    empty_denominator_policy: Literal["not_applicable", "insufficient"]
    formula_registry: tuple[QualityFormulaDefinition, ...] = Field(min_length=1)
    gate_bindings: tuple[QualityGateBinding, ...] = Field(min_length=1)
    publisher_gate_policy: Literal["pass_only"]
    aggregate_score_policy: QualityAggregateScorePolicy
    capacity: QualityCapacityPolicy
    created_at: date
    maintained_by: NonEmptyString

    @model_validator(mode="after")
    def validate_rule_set(self) -> DataQualityRuleSet:
        formula_ids = tuple(item.formula_id for item in self.formula_registry)
        metric_ids = tuple(item.metric_id for item in self.formula_registry)
        binding_ids = tuple(item.constraint_id for item in self.gate_bindings)
        if len(formula_ids) != len(set(formula_ids)):
            raise ValueError("quality RuleSet contains duplicate formula_id")
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("quality RuleSet contains duplicate metric_id")
        if len(binding_ids) != len(set(binding_ids)):
            raise ValueError("quality RuleSet contains duplicate constraint_id")
        if {item.metric_id for item in self.gate_bindings if item.metric_id} - set(metric_ids):
            raise ValueError("quality gate binds an unregistered metric")
        if self.aggregate_score_policy.enabled is not False:
            raise ValueError("C-05 v1 aggregate score must remain disabled")
        expected = compute_quality_rule_set_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"quality RuleSet content_hash mismatch: {expected}")
        return self


class QualityMetricResult(BaseModel):
    model_config = MODEL_CONFIG

    metric_id: QualityMetricId
    scope: QualityMetricScope
    target_id: Identifier
    status: QualityMetricStatus
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: Decimal | None = None
    formula_id: Identifier
    formula_version: SemanticVersion
    threshold: Decimal | None = None
    threshold_source: NonEmptyString | None = None
    input_locator: NonEmptyString

    @model_validator(mode="after")
    def validate_ratio(self) -> QualityMetricResult:
        if any(
            value is not None and ("e" in str(value).lower())
            for value in (self.value, self.threshold)
        ):
            raise ValueError("quality metric Decimal values must use plain serialization")
        if self.numerator > self.denominator:
            raise ValueError("quality metric numerator must not exceed denominator")
        if self.status is QualityMetricStatus.determinate:
            if self.denominator <= 0 or self.value is None:
                raise ValueError("determinate quality metric requires denominator and value")
            with localcontext() as context:
                context.prec = 28
                context.rounding = ROUND_HALF_EVEN
                expected = Decimal(self.numerator) / Decimal(self.denominator)
            if self.value != expected:
                raise ValueError("quality metric value is not recomputable from counts")
        elif self.value is not None:
            raise ValueError("non-determinate quality metric must not carry a value")
        elif self.status is QualityMetricStatus.not_applicable and (
            self.numerator != 0 or self.denominator != 0
        ):
            raise ValueError("not-applicable quality metric must have an empty denominator")
        return self


class QualityCount(BaseModel):
    model_config = MODEL_CONFIG

    key: NonEmptyString
    count: int = Field(ge=0)


class QualityManifestFieldReference(BaseModel):
    model_config = MODEL_CONFIG

    field_id: Identifier
    manifest_id: Identifier
    manifest_version: SemanticVersion
    manifest_content_hash: ContentHash


class FieldQualityResult(BaseModel):
    model_config = MODEL_CONFIG

    field_id: Identifier
    field_manifest_reference: QualityManifestFieldReference
    applicable_row_count: int = Field(ge=0)
    mapped_count: int = Field(ge=0)
    declared_null_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    null_reason_distribution: tuple[QualityCount, ...] = ()
    completeness: QualityMetricResult
    missingness: QualityMetricResult
    unresolved_rate: QualityMetricResult
    provenance_coverage: QualityMetricResult
    evidence_coverage: QualityMetricResult
    unit_consistency: QualityMetricResult
    same_source_conflict_rate: QualityMetricResult
    cross_source_conflict_rate: QualityMetricResult
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    row_ids: tuple[Identifier, ...]
    rule_references: tuple[Identifier, ...]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_counts_and_hash(self) -> FieldQualityResult:
        if self.mapped_count + self.declared_null_count + self.unresolved_count != self.applicable_row_count:
            raise ValueError("field quality outcome counts do not close")
        if self.field_manifest_reference.field_id != self.field_id:
            raise ValueError("field manifest reference disagrees with field_id")
        expected = compute_quality_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"field quality content_hash mismatch: {expected}")
        return self


class RowQualityResult(BaseModel):
    model_config = MODEL_CONFIG

    row_id: Identifier
    canonical_row_identity: CanonicalRowIdentity
    entity_level: EntityLevel
    alignment_status: AlignmentStatus
    applicable_field_count: int = Field(ge=0)
    mapped_count: int = Field(ge=0)
    declared_null_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    completeness: QualityMetricResult
    missingness: QualityMetricResult
    unresolved_rate: QualityMetricResult
    provenance_coverage: QualityMetricResult
    evidence_coverage: QualityMetricResult
    unit_consistency: QualityMetricResult
    conflict_rate: QualityMetricResult
    low_confidence: QualityMetricResult
    review_required: QualityMetricResult
    inconclusive: QualityMetricResult
    field_ids: tuple[Identifier, ...]
    conflict_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    crossmatch_logical_key: ContentHash
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_counts_and_hash(self) -> RowQualityResult:
        if self.mapped_count + self.declared_null_count + self.unresolved_count != self.applicable_field_count:
            raise ValueError("row quality outcome counts do not close")
        expected = compute_quality_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"row quality content_hash mismatch: {expected}")
        return self


class DatasetQualityResult(BaseModel):
    model_config = MODEL_CONFIG

    row_count: int = Field(ge=0)
    field_count: int = Field(ge=0)
    applicable_cell_count: int = Field(ge=0)
    mapped_count: int = Field(ge=0)
    declared_null_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    null_reason_distribution: tuple[QualityCount, ...] = ()
    completeness: QualityMetricResult
    missingness: QualityMetricResult
    unresolved_rate: QualityMetricResult
    provenance_coverage: QualityMetricResult
    evidence_coverage: QualityMetricResult
    unit_consistency: QualityMetricResult
    same_source_conflict_rate: QualityMetricResult
    cross_source_conflict_rate: QualityMetricResult
    object_match_coverage: QualityMetricResult
    low_confidence_edge_rate: QualityMetricResult
    review_required_record_rate: QualityMetricResult
    inconclusive_record_rate: QualityMetricResult
    source_scope_completeness: QualityMetricResult
    validation_integrity: QualityMetricResult
    field_result_ids: tuple[Identifier, ...]
    row_result_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    raw_status_distribution: tuple[QualityCount, ...]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_counts_and_hash(self) -> DatasetQualityResult:
        if self.mapped_count + self.declared_null_count + self.unresolved_count != self.applicable_cell_count:
            raise ValueError("dataset quality outcome counts do not close")
        expected = compute_quality_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"dataset quality content_hash mismatch: {expected}")
        return self


class QualityConstraintResult(BaseModel):
    model_config = MODEL_CONFIG

    constraint_id: Identifier
    source_field: NonEmptyString
    metric_id: QualityMetricId | None
    observed_status: QualityMetricStatus | Literal["not_checked"]
    observed_value: Decimal | None
    threshold: Decimal | None
    operator: Literal["gte", "equals"]
    result: QualityGateStatus
    rule_binding_version: SemanticVersion
    input_locator: NonEmptyString


class ResearchContractQualityGate(BaseModel):
    model_config = MODEL_CONFIG

    overall_status: QualityGateStatus
    checks: tuple[QualityConstraintResult, ...]
    rule_binding_version: SemanticVersion
    input_locator: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> ResearchContractQualityGate:
        expected = compute_quality_content_hash(self)
        if self.content_hash != expected:
            raise ValueError(f"quality gate content_hash mismatch: {expected}")
        return self


class QualityArtifactReference(BaseModel):
    model_config = MODEL_CONFIG

    kind: NonEmptyString
    candidate_id: Identifier
    input_hash: ContentHash
    output_hash: ContentHash
    canonical_content_hash: ContentHash | None = None
    lineage_hash: ContentHash | None = None


class QualityInputReferences(BaseModel):
    model_config = MODEL_CONFIG

    c04_input_hash: ContentHash
    candidates: tuple[QualityArtifactReference, ...] = Field(min_length=3, max_length=3)
    crossmatch_result_id: Identifier
    crossmatch_input_hash: ContentHash
    crossmatch_output_hash: ContentHash
    crossmatch_content_hash: ContentHash
    research_contract_id: Identifier
    research_contract_version: int = Field(ge=1)
    research_contract_content_hash: ContentHash
    quality_rule_set_id: Identifier
    quality_rule_set_version: SemanticVersion
    quality_rule_set_content_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate_kinds(self) -> QualityInputReferences:
        if tuple(item.kind for item in self.candidates) != (
            "dataset",
            "field_dictionary",
            "source_collection",
        ):
            raise ValueError("quality input references must use canonical C-04 candidate order")
        return self


class QualityProducerReference(BaseModel):
    model_config = MODEL_CONFIG

    producer_type: Literal["algorithm"] = "algorithm"
    producer_name: NonEmptyString
    producer_version: SemanticVersion


class DataQualityEvaluationInput(BaseModel):
    """Canonical public input to the C-05 evaluator."""

    model_config = MODEL_CONFIG

    data_artifact_input: DataArtifactBuildInput
    dataset_candidate: DatasetArtifactCandidate
    field_dictionary_candidate: FieldDictionaryArtifactCandidate
    source_collection_candidate: SourceCollectionArtifactCandidate
    research_contract: ResearchContract
    quality_rule_set: DataQualityRuleSet
    input_hash: ContentHash

    @model_validator(mode="after")
    def validate_input_hash(self) -> DataQualityEvaluationInput:
        expected = compute_data_quality_input_hash(self)
        if self.input_hash != expected:
            raise ValueError(f"quality input_hash mismatch: {expected}")
        return self


class DataQualityEvaluationResult(BaseModel):
    """Typed C-05 result; it is not a Core ``ArtifactKind``."""

    model_config = MODEL_CONFIG

    kind: Literal["data_quality"] = "data_quality"
    schema_version: SemanticVersion
    result_id: Identifier
    input_references: QualityInputReferences
    quality_rule_set_reference: QualityArtifactReference
    research_contract_reference: QualityArtifactReference
    field_results: tuple[FieldQualityResult, ...]
    row_results: tuple[RowQualityResult, ...]
    dataset_result: DatasetQualityResult
    contract_gate: ResearchContractQualityGate
    aggregate_score: Decimal | None
    aggregate_score_policy: QualityAggregateScorePolicy
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    producer: QualityProducerReference
    input_hash: ContentHash
    output_hash: ContentHash
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_result_hashes(self) -> DataQualityEvaluationResult:
        if self.aggregate_score_policy.enabled is not False or self.aggregate_score is not None:
            raise ValueError("C-05 v1 aggregate score must be disabled and null")
        expected_output = compute_quality_output_hash(self)
        if self.output_hash != expected_output:
            raise ValueError(f"quality output_hash mismatch: {expected_output}")
        expected_content = compute_quality_content_hash(self)
        if self.content_hash != expected_content:
            raise ValueError(f"quality content_hash mismatch: {expected_content}")
        return self


class DataQualityEvaluationRejected(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["data_quality_rejected"] = "data_quality_rejected"
    schema_version: SemanticVersion
    failure_stage: QualityFailureStage
    error_code: QualityErrorCode
    message: NonEmptyString
    input_hash: ContentHash | None = None
    rule_set_reference: QualityArtifactReference | None = None
    field_results: tuple[()] = ()
    row_results: tuple[()] = ()
    dataset_result: None = None
    output_hash: ContentHash
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_rejection_hashes(self) -> DataQualityEvaluationRejected:
        expected_output = compute_quality_output_hash(self)
        if self.output_hash != expected_output:
            raise ValueError(f"rejected quality output_hash mismatch: {expected_output}")
        expected_content = compute_quality_content_hash(self)
        if self.content_hash != expected_content:
            raise ValueError(f"rejected quality content_hash mismatch: {expected_content}")
        return self


DataQualityEvaluationOutcome = Annotated[
    DataQualityEvaluationResult | DataQualityEvaluationRejected,
    Field(discriminator="kind"),
]


def _payload(value: BaseModel | dict[str, Any], *, exclude: set[str] | None = None) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", exclude_none=True, exclude=exclude or set())
    result = dict(value)
    for key in exclude or set():
        result.pop(key, None)
    return _drop_none(result)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_drop_none(item) for item in value)
    return value


def compute_quality_rule_set_content_hash(value: DataQualityRuleSet | dict[str, Any]) -> str:
    return compute_canonical_payload_hash(_payload(value, exclude={"content_hash"}))


def compute_data_quality_input_hash(
    value: DataQualityEvaluationInput | dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(_payload(value, exclude={"input_hash"}))


def compute_quality_output_hash(
    value: DataQualityEvaluationResult | DataQualityEvaluationRejected | dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(
        _payload(value, exclude={"output_hash", "content_hash"})
    )


def compute_quality_content_hash(
    value: BaseModel | dict[str, Any],
) -> str:
    return compute_canonical_payload_hash(_payload(value, exclude={"content_hash"}))


def compute_data_quality_result_id(input_hash: ContentHash, rule_set_content_hash: ContentHash) -> str:
    identity = compute_canonical_payload_hash(
        {"kind": "data_quality", "input_hash": input_hash, "rule_set_content_hash": rule_set_content_hash}
    )
    return f"quality.{identity.removeprefix('sha256:')[:24]}"


__all__ = [
    "DataQualityEvaluationInput",
    "DataQualityEvaluationOutcome",
    "DataQualityEvaluationRejected",
    "DataQualityEvaluationResult",
    "DataQualityRuleSet",
    "DatasetQualityResult",
    "FieldQualityResult",
    "QualityAggregateScorePolicy",
    "QualityArtifactReference",
    "QualityCapacityPolicy",
    "QualityConstraintResult",
    "QualityErrorCode",
    "QualityFailureStage",
    "QualityFormulaDefinition",
    "QualityGateBinding",
    "QualityGateStatus",
    "QualityInputReferences",
    "QualityManifestFieldReference",
    "QualityMetricId",
    "QualityMetricResult",
    "QualityMetricScope",
    "QualityMetricStatus",
    "QualityProducerReference",
    "QualityCount",
    "ResearchContractQualityGate",
    "RowQualityResult",
    "compute_data_quality_input_hash",
    "compute_data_quality_result_id",
    "compute_quality_content_hash",
    "compute_quality_output_hash",
    "compute_quality_rule_set_content_hash",
]
