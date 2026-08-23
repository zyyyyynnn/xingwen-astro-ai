"""Leaf quality contracts shared by SourceTable admission and Data Quality."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .core import Identifier, NonEmptyString, SemanticVersion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class QualityMetricStatus(StrEnum):
    determinate = "determinate"
    insufficient = "insufficient"
    not_applicable = "not_applicable"


class QualityMetricScope(StrEnum):
    field = "field"
    row = "row"
    dataset = "dataset"


class QualityFormulaKind(StrEnum):
    ratio = "ratio"
    flag = "flag"


class QualityObservationId(StrEnum):
    field_mapped_count = "field.mapped_count"
    field_applicable_count = "field.applicable_count"
    field_declared_null_count = "field.declared_null_count"
    field_missing_count = "field.missing_count"
    field_unresolved_count = "field.unresolved_count"
    field_provenance_count = "field.provenance_count"
    field_evidence_count = "field.evidence_count"
    field_unit_consistent_assertion_count = "field.unit_consistent_assertion_count"
    field_unit_applicable_assertion_count = "field.unit_applicable_assertion_count"
    field_same_source_conflict_count = "field.same_source_conflict_count"
    field_cross_source_conflict_count = "field.cross_source_conflict_count"
    row_mapped_count = "row.mapped_count"
    row_applicable_field_count = "row.applicable_field_count"
    row_missing_count = "row.missing_count"
    row_unresolved_count = "row.unresolved_count"
    row_provenance_count = "row.provenance_count"
    row_evidence_count = "row.evidence_count"
    row_unit_consistent_assertion_count = "row.unit_consistent_assertion_count"
    row_unit_applicable_assertion_count = "row.unit_applicable_assertion_count"
    row_conflict_count = "row.conflict_count"
    row_low_confidence_flag = "row.low_confidence_flag"
    row_review_required_flag = "row.review_required_flag"
    row_inconclusive_flag = "row.inconclusive_flag"
    row_confidence_applicable_record_count = "row.confidence_applicable_record_count"
    row_adjudicable_record_count = "row.adjudicable_record_count"
    row_unpaired_record_count = "row.unpaired_record_count"
    dataset_mapped_count = "dataset.mapped_count"
    dataset_applicable_cell_count = "dataset.applicable_cell_count"
    dataset_missing_count = "dataset.missing_count"
    dataset_unresolved_count = "dataset.unresolved_count"
    dataset_provenance_count = "dataset.provenance_count"
    dataset_evidence_count = "dataset.evidence_count"
    dataset_evidence_applicable_count = "dataset.evidence_applicable_count"
    dataset_unit_consistent_assertion_count = "dataset.unit_consistent_assertion_count"
    dataset_unit_applicable_assertion_count = "dataset.unit_applicable_assertion_count"
    dataset_same_source_conflict_count = "dataset.same_source_conflict_count"
    dataset_cross_source_conflict_count = "dataset.cross_source_conflict_count"
    dataset_object_match_count = "dataset.object_match_count"
    dataset_object_candidate_count = "dataset.object_candidate_count"
    dataset_low_confidence_edge_count = "dataset.low_confidence_edge_count"
    dataset_candidate_edge_count = "dataset.candidate_edge_count"
    dataset_review_required_record_count = "dataset.review_required_record_count"
    dataset_adjudicable_record_count = "dataset.adjudicable_record_count"
    dataset_inconclusive_record_count = "dataset.inconclusive_record_count"
    dataset_crossmatch_record_count = "dataset.crossmatch_record_count"
    dataset_complete_source_count = "dataset.complete_source_count"
    dataset_required_source_count = "dataset.required_source_count"
    dataset_validation_pass_count = "dataset.validation_pass_count"
    dataset_validation_check_count = "dataset.validation_check_count"


class QualityGateStatus(StrEnum):
    pass_ = "pass"
    fail = "fail"
    insufficient = "insufficient"


class QualityMetricId(StrEnum):
    field_completeness = "field_completeness"
    field_missingness = "field_missingness"
    field_unresolved_rate = "field_unresolved_rate"
    field_provenance_coverage = "field_provenance_coverage"
    field_evidence_coverage = "field_evidence_coverage"
    field_unit_consistency = "field_unit_consistency"
    field_same_source_conflict_rate = "field_same_source_conflict_rate"
    field_cross_source_conflict_rate = "field_cross_source_conflict_rate"
    row_completeness = "row_completeness"
    row_missingness = "row_missingness"
    row_unresolved_rate = "row_unresolved_rate"
    row_provenance_coverage = "row_provenance_coverage"
    row_evidence_coverage = "row_evidence_coverage"
    row_unit_consistency = "row_unit_consistency"
    row_conflict_rate = "row_conflict_rate"
    row_low_confidence_flag = "row_low_confidence_flag"
    row_review_required_flag = "row_review_required_flag"
    row_inconclusive_flag = "row_inconclusive_flag"
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
    formula_scope: QualityMetricScope
    precision_digits: int = Field(gt=0, le=64)
    input_locator: NonEmptyString

    @model_validator(mode="after")
    def validate_ratio(self) -> QualityMetricResult:
        if self.formula_scope is not self.scope:
            raise ValueError("quality metric formula scope does not match result scope")
        if self.value is not None and "e" in str(self.value).lower():
            raise ValueError("quality metric Decimal values must use plain serialization")
        if self.numerator > self.denominator:
            raise ValueError("quality metric numerator must not exceed denominator")
        if self.status is QualityMetricStatus.determinate:
            if self.denominator <= 0 or self.value is None:
                raise ValueError("determinate quality metric requires denominator and value")
            with localcontext() as context:
                context.prec = self.precision_digits
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


class QualityConstraintResult(BaseModel):
    model_config = MODEL_CONFIG

    constraint_id: Identifier
    source_field: NonEmptyString
    metric_id: QualityMetricId | None
    observation_key: NonEmptyString
    observed_status: QualityMetricStatus | Literal["not_checked"]
    observed_value: Decimal | None
    threshold: Decimal | None
    operator: Literal["gte", "equals"]
    result: QualityGateStatus
    rule_binding_version: SemanticVersion
    input_locator: NonEmptyString


__all__ = [
    "QualityConstraintResult",
    "QualityFormulaKind",
    "QualityGateStatus",
    "QualityMetricId",
    "QualityMetricResult",
    "QualityMetricScope",
    "QualityMetricStatus",
    "QualityObservationId",
]
