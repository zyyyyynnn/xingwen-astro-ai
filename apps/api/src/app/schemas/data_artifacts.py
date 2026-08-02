"""C-04 versioned mapping and publisher-ready data Artifact contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    field_validator,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .crossmatch import (
    CrossmatchResult,
    CrossmatchSide,
    CrossmatchSourceInput,
    EntityLevel,
)
from .enums import SourceMode
from .manifest import (
    CanonicalFieldId,
    ContentHash,
    DataType,
    FieldDefinition,
    Identifier,
    NullReason,
    QuantityKind,
    SemanticVersion,
)
from .source_acquisition import DataSourceDataLevel, DataSourceCompletion


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
RawScalar = str | int | float | Decimal | bool

_ARTIFACT_PUBLICATION_SEAL = object()


class DataArtifactErrorCode(StrEnum):
    unsupported_requested_field = "UNSUPPORTED_REQUESTED_FIELD"
    unknown_source_field = "UNKNOWN_SOURCE_FIELD"
    source_record_reference_not_found = "SOURCE_RECORD_REFERENCE_NOT_FOUND"
    source_record_hash_mismatch = "SOURCE_RECORD_HASH_MISMATCH"
    snapshot_mismatch = "SNAPSHOT_MISMATCH"
    crossmatch_result_mismatch = "CROSSMATCH_RESULT_MISMATCH"
    manifest_pin_mismatch = "MANIFEST_PIN_MISMATCH"
    mapping_rule_mismatch = "MAPPING_RULE_MISMATCH"
    conversion_catalog_mismatch = "CONVERSION_CATALOG_MISMATCH"
    unknown_conversion_rule = "UNKNOWN_CONVERSION_RULE"
    incompatible_unit = "INCOMPATIBLE_UNIT"
    quantity_kind_mismatch = "QUANTITY_KIND_MISMATCH"
    invalid_numeric_value = "INVALID_NUMERIC_VALUE"
    non_finite_numeric_value = "NON_FINITE_NUMERIC_VALUE"
    invalid_uncertainty = "INVALID_UNCERTAINTY"
    unknown_limit_flag = "UNKNOWN_LIMIT_FLAG"
    limit_without_value = "LIMIT_WITHOUT_VALUE"
    invalid_null_reason = "INVALID_NULL_REASON"
    non_nullable_unresolved_field = "NON_NULLABLE_UNRESOLVED_FIELD"
    duplicate_source_value = "DUPLICATE_SOURCE_VALUE"
    duplicate_evidence = "DUPLICATE_EVIDENCE"
    conflict_selection_inconsistency = "CONFLICT_SELECTION_INCONSISTENCY"
    candidate_hash_mismatch = "CANDIDATE_HASH_MISMATCH"
    capacity_exceeded = "CAPACITY_EXCEEDED"
    publication_admission_not_sealed = "PUBLICATION_ADMISSION_NOT_SEALED"
    input_hash_mismatch = "INPUT_HASH_MISMATCH"


class UncertaintyStatus(StrEnum):
    complete = "complete"
    partial = "partial"
    missing = "missing"
    not_applicable = "not_applicable"


class LimitStatus(StrEnum):
    measured = "measured"
    lower_limit = "lower_limit"
    upper_limit = "upper_limit"
    not_applicable = "not_applicable"


class SelectionStatus(StrEnum):
    selected = "selected"
    unselected = "unselected"
    conflict = "conflict"


class AlignmentStatus(StrEnum):
    accepted = "accepted"
    review_required = "review_required"
    rejected = "rejected"
    conflict = "conflict"
    unmatched = "unmatched"
    inconclusive = "inconclusive"


class QualityEvaluationStatus(StrEnum):
    not_evaluated = "not_evaluated"


class DataArtifactCapacity(BaseModel):
    model_config = MODEL_CONFIG

    max_rows: int = Field(gt=0)
    max_requested_fields: int = Field(gt=0)
    max_source_values_per_field: int = Field(gt=0)
    max_transformation_evidence: int = Field(gt=0)
    max_conflict_candidates: int = Field(gt=0)
    max_total_cell_outcomes: int = Field(gt=0)


class NumericComparisonPolicy(BaseModel):
    model_config = MODEL_CONFIG

    absolute_tolerance: NonNegativeDecimal
    relative_tolerance: NonNegativeDecimal
    threshold_inclusive: bool = True


class MappingRuleSet(BaseModel):
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
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    source_selection_policy_version: SemanticVersion
    conflict_comparison_policy_version: SemanticVersion
    null_derivation_policy_version: SemanticVersion
    uncertainty_policy_implementation_version: SemanticVersion
    limit_policy_implementation_version: SemanticVersion
    numeric_normalization_serialization_version: SemanticVersion
    canonical_ordering_policy: Literal["field_manifest_then_stable_identity"]
    same_source_conflict_policy: Literal["preserve_conflict_no_scientific_winner"]
    unresolved_identity_policy: Literal["preserve_unresolved_rows"]
    non_nullable_missing_policy: Literal["fail_admission"]
    numeric_comparison: NumericComparisonPolicy
    capacity: DataArtifactCapacity
    created_at: date
    maintained_by: NonEmptyString

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        _validate_content_hash(self)
        return self


class ConversionConstantsProvenance(BaseModel):
    model_config = MODEL_CONFIG

    title: NonEmptyString
    authority: NonEmptyString
    source_url: NonEmptyString
    resolution_date: date
    note: NonEmptyString


class UnitConversionImplementation(BaseModel):
    model_config = MODEL_CONFIG

    rule_id: Identifier
    rule_version: SemanticVersion
    source_unit: Identifier | None = None
    target_unit: Identifier | None = None
    quantity_kind: QuantityKind
    factor: PositiveDecimal
    factor_numerator: PositiveDecimal
    factor_denominator: PositiveDecimal

    @model_validator(mode="after")
    def validate_factor(self) -> Self:
        if self.rule_id == "unit.identity.v1":
            if self.source_unit is not None or self.target_unit is not None:
                raise ValueError("identity implementation must not freeze a unit pair")
            if self.factor != Decimal(1):
                raise ValueError("identity implementation factor must be one")
        elif self.source_unit is None or self.target_unit is None:
            raise ValueError("specific conversion implementation requires a unit pair")
        return self


class UnitConversionCatalog(BaseModel):
    model_config = MODEL_CONFIG

    catalog_id: Identifier
    schema_version: SemanticVersion
    version: SemanticVersion
    content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash
    numeric_implementation_version: SemanticVersion
    precision_digits: int = Field(ge=18, le=50)
    rounding_mode: Literal["ROUND_HALF_EVEN"]
    serialization_policy: Literal["plain_decimal_string_no_exponent"]
    rules: tuple[UnitConversionImplementation, ...] = Field(min_length=1)
    constants_provenance: ConversionConstantsProvenance
    maintained_by: NonEmptyString
    created_at: date

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("conversion catalog contains duplicate rule ID")
        with localcontext() as context:
            context.prec = self.precision_digits
            context.rounding = ROUND_HALF_EVEN
            for rule in self.rules:
                if rule.factor != rule.factor_numerator / rule.factor_denominator:
                    raise ValueError(
                        "conversion factor does not match frozen numerator/denominator"
                    )
        _validate_content_hash(self)
        return self


class ManifestPins(BaseModel):
    model_config = MODEL_CONFIG

    case_manifest_id: Identifier
    case_manifest_version: SemanticVersion
    case_manifest_content_hash: ContentHash
    field_manifest_id: Identifier
    field_manifest_version: SemanticVersion
    field_manifest_content_hash: ContentHash


class DataArtifactProducer(BaseModel):
    model_config = MODEL_CONFIG

    producer_type: Literal["algorithm"] = "algorithm"
    producer_name: NonEmptyString
    producer_version: SemanticVersion
    mapping_rule_set_id: Identifier
    mapping_rule_set_version: SemanticVersion
    mapping_rule_set_content_hash: ContentHash
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash


class SourceCellLocator(BaseModel):
    model_config = MODEL_CONFIG

    side: CrossmatchSide
    source_snapshot_id: Identifier
    source_snapshot_content_hash: ContentHash
    source_id: Identifier
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    raw_record_content_hash: ContentHash
    raw_field: NonEmptyString


class UncertaintyValue(BaseModel):
    model_config = MODEL_CONFIG

    status: UncertaintyStatus
    source_positive: Decimal | None = None
    source_negative: Decimal | None = None
    canonical_positive: Decimal | None = None
    canonical_negative: Decimal | None = None
    positive_locator: SourceCellLocator | None = None
    negative_locator: SourceCellLocator | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        source_count = sum(v is not None for v in (self.source_positive, self.source_negative))
        canonical_count = sum(
            v is not None for v in (self.canonical_positive, self.canonical_negative)
        )
        expected = {
            0: UncertaintyStatus.missing,
            1: UncertaintyStatus.partial,
            2: UncertaintyStatus.complete,
        }[source_count]
        if self.status is UncertaintyStatus.not_applicable:
            if source_count or canonical_count or self.positive_locator or self.negative_locator:
                raise ValueError("not-applicable uncertainty cannot carry values")
        elif self.status is not expected or source_count != canonical_count:
            raise ValueError("uncertainty status does not match retained values")
        return self


class LimitValue(BaseModel):
    model_config = MODEL_CONFIG

    status: LimitStatus
    raw_flag: int | None = None
    locator: SourceCellLocator | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is LimitStatus.not_applicable:
            if self.raw_flag is not None or self.locator is not None:
                raise ValueError("not-applicable limit cannot carry a flag")
        elif self.raw_flag is None or self.locator is None:
            raise ValueError("applicable limit requires raw flag and locator")
        return self


class SourceValueCandidate(BaseModel):
    model_config = MODEL_CONFIG

    source_value_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_id: Identifier
    source_table: NonEmptyString
    source_snapshot_id: Identifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    raw_record_row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...]
    raw_record_content_hash: ContentHash
    raw_field: NonEmptyString
    raw_value: RawScalar | None
    source_unit: Identifier
    canonical_value: str | None
    canonical_unit: Identifier
    alias_priority: int = Field(gt=0)
    source_priority: int = Field(gt=0)
    transformation_rule_version: SemanticVersion
    conversion_rule_id: Identifier
    conversion_rule_version: SemanticVersion
    reference_field: NonEmptyString | None = None
    reference_value: RawScalar | None = None
    provenance_field: NonEmptyString | None = None
    provenance_value: RawScalar | None = None
    uncertainty: UncertaintyValue
    limit: LimitValue
    null_status: NullReason | None = None
    evidence_locator: SourceCellLocator
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if (self.canonical_value is None) != (self.null_status is not None):
            raise ValueError("source null status must exactly describe an unmapped raw value")
        if self.raw_value is None and self.canonical_value is not None:
            raise ValueError("null source value cannot carry a canonical value")
        _validate_content_hash(self)
        return self


class TransformationEvidence(BaseModel):
    model_config = MODEL_CONFIG

    evidence_id: Identifier
    target_candidate_kind: Literal["dataset"] = "dataset"
    dataset_row_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_value_id: Identifier
    locator: SourceCellLocator
    raw_value: RawScalar | None
    source_unit: Identifier
    canonical_value: str | None
    canonical_unit: Identifier
    conversion_rule_id: Identifier
    conversion_rule_version: SemanticVersion
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash
    transformation_rule_version: SemanticVersion
    uncertainty_locators: tuple[SourceCellLocator, ...]
    limit_locator: SourceCellLocator | None = None
    reference_locator: SourceCellLocator | None = None
    provenance_locator: SourceCellLocator | None = None
    crossmatch_result_id: Identifier
    crossmatch_result_content_hash: ContentHash
    crossmatch_logical_key: ContentHash
    crossmatch_evidence_ids: tuple[Identifier, ...]
    selection_status: SelectionStatus
    selection_reason: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        _validate_content_hash(self)
        return self


class FieldSelectionRecord(BaseModel):
    model_config = MODEL_CONFIG

    selection_id: Identifier
    canonical_field_id: CanonicalFieldId
    selected_source_value_id: Identifier | None
    candidate_source_value_ids: tuple[Identifier, ...]
    strategy: Literal["prefer_source_priority_preserve_all"]
    reason: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if len(self.candidate_source_value_ids) != len(set(self.candidate_source_value_ids)):
            raise ValueError("selection contains duplicate source value ID")
        if self.selected_source_value_id is not None and self.selected_source_value_id not in self.candidate_source_value_ids:
            raise ValueError("selection winner must be a retained candidate")
        _validate_content_hash(self)
        return self


class FieldConflictRecord(BaseModel):
    model_config = MODEL_CONFIG

    conflict_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_value_ids: tuple[Identifier, ...] = Field(min_length=2)
    conflict_scope: Literal["same_source", "cross_source", "identity_unresolved"]
    reason: NonEmptyString
    absolute_difference: Decimal | None = None
    relative_difference: Decimal | None = None
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if len(self.source_value_ids) != len(set(self.source_value_ids)):
            raise ValueError("conflict contains duplicate source value ID")
        _validate_content_hash(self)
        return self


class MappedCanonicalValue(BaseModel):
    model_config = MODEL_CONFIG

    status: Literal["mapped"] = "mapped"
    canonical_field_id: CanonicalFieldId
    canonical_value: str
    canonical_unit: Identifier
    selected_source_value_id: Identifier
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[Identifier, ...]
    selection_id: Identifier
    conflict_ids: tuple[Identifier, ...]


class DeclaredNullValue(BaseModel):
    model_config = MODEL_CONFIG

    status: Literal["declared_null"] = "declared_null"
    canonical_field_id: CanonicalFieldId
    reason: NullReason
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[Identifier, ...]


class UnresolvedCanonicalValue(BaseModel):
    model_config = MODEL_CONFIG

    status: Literal["unresolved"] = "unresolved"
    canonical_field_id: CanonicalFieldId
    reason: NonEmptyString
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[Identifier, ...]
    conflict_ids: tuple[Identifier, ...]


CanonicalValueOutcome = Annotated[
    MappedCanonicalValue | DeclaredNullValue | UnresolvedCanonicalValue,
    Field(discriminator="status"),
]


class DatasetColumn(BaseModel):
    model_config = MODEL_CONFIG

    field: FieldDefinition


class DatasetRow(BaseModel):
    model_config = MODEL_CONFIG

    row_id: Identifier
    crossmatch_record_type: NonEmptyString
    crossmatch_logical_key: ContentHash
    entity_level: EntityLevel
    alignment_status: AlignmentStatus
    source_member_ids: tuple[Identifier, ...]
    fields: tuple[CanonicalValueOutcome, ...]
    conflict_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        _validate_content_hash(self)
        return self


class _PublisherReadyCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: tuple[object, int] | None = PrivateAttr(default=None)

    def __artifact_publication_is_admitted__(self) -> bool:
        seal = self._artifact_publication_seal
        return bool(
            isinstance(seal, tuple)
            and len(seal) == 2
            and seal[0] is _ARTIFACT_PUBLICATION_SEAL
            and seal[1] == id(self)
        )


class DatasetArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["dataset"] = "dataset"
    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    crossmatch_result_id: Identifier
    crossmatch_input_hash: ContentHash
    crossmatch_output_hash: ContentHash
    crossmatch_content_hash: ContentHash
    requested_fields: tuple[CanonicalFieldId, ...]
    columns: tuple[DatasetColumn, ...]
    rows: tuple[DatasetRow, ...]
    source_values: tuple[SourceValueCandidate, ...]
    transformation_evidence: tuple[TransformationEvidence, ...]
    selections: tuple[FieldSelectionRecord, ...]
    conflicts: tuple[FieldConflictRecord, ...]
    row_count: int = Field(ge=0)
    field_count: int = Field(ge=0)
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    mapping_rule_set_id: Identifier
    mapping_rule_set_version: SemanticVersion
    mapping_rule_set_content_hash: ContentHash
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash
    quality_evaluation_status: Literal["not_evaluated"] = "not_evaluated"
    quality_metric_input_declarations: tuple[NonEmptyString, ...]
    quality_constraints_reference: NonEmptyString | None = None
    producer: DataArtifactProducer
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.row_count != len(self.rows) or self.field_count != len(self.columns):
            raise ValueError("Dataset candidate row/field count mismatch")
        if self.requested_fields != tuple(c.field.field_id for c in self.columns):
            raise ValueError("Dataset columns must exactly project requested fields")
        _require_unique(self.source_values, "source_value_id", "source value")
        _require_unique(self.transformation_evidence, "evidence_id", "transformation Evidence")
        _require_unique(self.selections, "selection_id", "selection")
        _require_unique(self.conflicts, "conflict_id", "conflict")
        source_values = {item.source_value_id: item for item in self.source_values}
        evidence = {item.evidence_id: item for item in self.transformation_evidence}
        selections = {item.selection_id: item for item in self.selections}
        conflicts = {item.conflict_id: item for item in self.conflicts}
        expected_evidence_ids = {
            *evidence,
            *(crossmatch_id for item in evidence.values() for crossmatch_id in item.crossmatch_evidence_ids),
        }
        if expected_evidence_ids != set(self.evidence_ids):
            raise ValueError("Dataset Evidence references must be the exact retained set")
        if not {item.source_snapshot_id for item in self.source_values} <= set(self.source_snapshot_ids):
            raise ValueError("Dataset source values refer to an undeclared SourceSnapshot")
        fields = {column.field.field_id: column.field for column in self.columns}
        for item in evidence.values():
            source_value = source_values.get(item.source_value_id)
            if source_value is None or item.locator != source_value.evidence_locator:
                raise ValueError("transformation Evidence must resolve to its source value")
        for row in self.rows:
            row_evidence = {
                evidence_id for outcome in row.fields for evidence_id in outcome.transformation_evidence_ids
            }
            row_conflicts = {conflict_id for outcome in row.fields for conflict_id in getattr(outcome, "conflict_ids", ())}
            if set(row.evidence_ids) != row_evidence or set(row.conflict_ids) != row_conflicts:
                raise ValueError("Dataset row reference registries are not exact")
            if tuple(outcome.canonical_field_id for outcome in row.fields) != self.requested_fields:
                raise ValueError("Dataset row fields do not match the requested projection")
            for outcome in row.fields:
                definition = fields[outcome.canonical_field_id]
                if not set(outcome.candidate_source_value_ids) <= source_values.keys():
                    raise ValueError("Dataset outcome refers to an unknown source value")
                if not set(outcome.transformation_evidence_ids) <= evidence.keys():
                    raise ValueError("Dataset outcome refers to unknown transformation Evidence")
                if isinstance(outcome, MappedCanonicalValue):
                    selection = selections.get(outcome.selection_id)
                    if selection is None or not set(outcome.conflict_ids) <= conflicts.keys():
                        raise ValueError("mapped outcome has a dangling selection/conflict reference")
                    if outcome.selected_source_value_id not in outcome.candidate_source_value_ids:
                        raise ValueError("mapped outcome winner is not a retained source value")
                    if (
                        selection.selected_source_value_id != outcome.selected_source_value_id
                        or selection.candidate_source_value_ids != outcome.candidate_source_value_ids
                    ):
                        raise ValueError("mapped outcome disagrees with its selection record")
                    selected = source_values[outcome.selected_source_value_id]
                    if (
                        selected.canonical_value != outcome.canonical_value
                        or selected.canonical_unit != outcome.canonical_unit
                    ):
                        raise ValueError("mapped outcome disagrees with its selected source value")
                elif isinstance(outcome, DeclaredNullValue):
                    if not definition.nullable or outcome.reason not in definition.null_policy.allowed_reasons:
                        raise ValueError("declared null is not authorized by the Field Manifest")
                outcome_evidence = [evidence[item] for item in outcome.transformation_evidence_ids]
                if any(
                    item.dataset_row_id != row.row_id
                    or item.canonical_field_id != outcome.canonical_field_id
                    for item in outcome_evidence
                ):
                    raise ValueError("Dataset outcome Evidence is bound to another row/field")
                if {item.source_value_id for item in outcome_evidence} != set(outcome.candidate_source_value_ids):
                    raise ValueError("Dataset outcome source values and Evidence are not one-to-one")
        referenced_selections = {
            outcome.selection_id
            for row in self.rows
            for outcome in row.fields
            if isinstance(outcome, MappedCanonicalValue)
        }
        if referenced_selections != selections.keys():
            raise ValueError("Dataset selection registry contains unreferenced records")
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class FieldDictionaryArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["field_dictionary"] = "field_dictionary"
    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    requested_fields: tuple[CanonicalFieldId, ...]
    field_definitions: tuple[FieldDefinition, ...]
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    mapping_rule_set_id: Identifier
    mapping_rule_set_version: SemanticVersion
    mapping_rule_set_content_hash: ContentHash
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash
    quality_evaluation_status: Literal["not_evaluated"] = "not_evaluated"
    producer: DataArtifactProducer
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.requested_fields != tuple(field.field_id for field in self.field_definitions):
            raise ValueError("FieldDictionary must exactly project requested fields")
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class SourceCollectionArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["source_collection"] = "source_collection"
    schema_version: Literal["1.0.0"] = "1.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    source_modes: tuple[SourceMode, ...]
    data_levels: tuple[DataSourceDataLevel, ...]
    completions: tuple[DataSourceCompletion, ...]
    raw_record_references: tuple[SourceCellLocator, ...]
    source_value_ids: tuple[Identifier, ...]
    crossmatch_result_id: Identifier
    crossmatch_content_hash: ContentHash
    alignment_record_keys: tuple[ContentHash, ...]
    conflict_record_keys: tuple[ContentHash, ...]
    review_required_record_keys: tuple[ContentHash, ...]
    inconclusive_record_keys: tuple[ContentHash, ...]
    license_notes: tuple[NonEmptyString, ...]
    mapping_rule_set_id: Identifier
    mapping_rule_set_version: SemanticVersion
    mapping_rule_set_content_hash: ContentHash
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash
    quality_evaluation_status: Literal["not_evaluated"] = "not_evaluated"
    producer: DataArtifactProducer
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if len(self.source_snapshot_ids) != 2 or len(set(self.source_snapshot_ids)) != 2:
            raise ValueError("SourceCollection requires two independent SourceSnapshots")
        for values, label in (
            (self.evidence_ids, "Evidence"),
            (self.source_value_ids, "source value"),
            (self.alignment_record_keys, "alignment record key"),
            (self.conflict_record_keys, "conflict record key"),
            (self.review_required_record_keys, "review-required record key"),
            (self.inconclusive_record_keys, "inconclusive record key"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"SourceCollection contains duplicate {label}")
        if len(self.raw_record_references) != len(set(self.raw_record_references)):
            raise ValueError("SourceCollection contains duplicate raw-cell locator")
        if not (
            set(self.conflict_record_keys)
            | set(self.review_required_record_keys)
            | set(self.inconclusive_record_keys)
        ) <= set(self.alignment_record_keys):
            raise ValueError("SourceCollection status keys must resolve to alignment records")
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class DataArtifactBuildInput(BaseModel):
    model_config = MODEL_CONFIG

    manifest_pins: ManifestPins
    requested_fields: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    left_acquisition: CrossmatchSourceInput
    right_acquisition: CrossmatchSourceInput
    crossmatch_result: CrossmatchResult
    mapping_rule_set: MappingRuleSet
    conversion_catalog: UnitConversionCatalog
    producer_version: SemanticVersion
    quality_constraints_reference: NonEmptyString | None = None
    input_hash: ContentHash

    @field_validator("requested_fields")
    @classmethod
    def canonicalize_requested_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_input(self) -> Self:
        if len(self.requested_fields) != len(set(self.requested_fields)):
            raise ValueError("requested fields must be unique")
        result = self.crossmatch_result
        pins = self.manifest_pins
        expected_pins = (
            pins.case_manifest_id,
            pins.case_manifest_version,
            pins.case_manifest_content_hash,
            pins.field_manifest_id,
            pins.field_manifest_version,
            pins.field_manifest_content_hash,
        )
        result_pins = (
            result.case_manifest_id,
            result.case_manifest_version,
            result.case_manifest_content_hash,
            result.field_manifest_id,
            result.field_manifest_version,
            result.field_manifest_content_hash,
        )
        rule_pins = (
            self.mapping_rule_set.case_manifest_id,
            self.mapping_rule_set.case_manifest_version,
            self.mapping_rule_set.case_manifest_content_hash,
            self.mapping_rule_set.field_manifest_id,
            self.mapping_rule_set.field_manifest_version,
            self.mapping_rule_set.field_manifest_content_hash,
        )
        if result_pins != expected_pins or rule_pins != expected_pins:
            raise ValueError("Manifest pins disagree across C-04 inputs")
        if (
            self.conversion_catalog.field_manifest_id != pins.field_manifest_id
            or self.conversion_catalog.field_manifest_version
            != pins.field_manifest_version
            or self.conversion_catalog.field_manifest_content_hash
            != pins.field_manifest_content_hash
        ):
            raise ValueError("conversion catalog disagrees with Field Manifest pin")
        for side, acquisition, snapshot, source_mode, data_level, completion in (
            (
                CrossmatchSide.left,
                self.left_acquisition,
                result.left_source_snapshot,
                result.left_source_mode,
                result.left_data_level,
                result.left_completion,
            ),
            (
                CrossmatchSide.right,
                self.right_acquisition,
                result.right_source_snapshot,
                result.right_source_mode,
                result.right_data_level,
                result.right_completion,
            ),
        ):
            if (
                acquisition.snapshot != snapshot
                or acquisition.source_mode is not source_mode
                or acquisition.data_level is not data_level
                or acquisition.completion != completion
            ):
                raise ValueError(f"{side.value} acquisition disagrees with CrossmatchResult")
            referenced = {
                (
                    candidate.source_record.row_key,
                    candidate.source_record.record_content_hash,
                )
                for candidate in result.candidates
                if candidate.side is side
            }
            acquired = {(record.row_key, record.content_hash) for record in acquisition.records}
            if referenced != acquired:
                raise ValueError(
                    f"{side.value} acquisition records disagree with CrossmatchResult"
                )
        expected = compute_data_artifact_input_hash(self)
        if self.input_hash != expected:
            raise ValueError(f"input_hash does not match build input: {expected}")
        return self


class DataArtifactBuildResult(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    schema_version: Literal["1.0.0"] = "1.0.0"
    dataset: DatasetArtifactCandidate
    field_dictionary: FieldDictionaryArtifactCandidate
    source_collection: SourceCollectionArtifactCandidate
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        _validate_output_hash(self)
        return self


def compute_data_artifact_content_hash(value: BaseModel | dict[str, Any]) -> str:
    payload = _model_or_dict(value)
    payload.pop("content_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_data_artifact_output_hash(value: BaseModel | dict[str, Any]) -> str:
    payload = _model_or_dict(value)
    payload.pop("candidate_id", None)
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def compute_data_artifact_input_hash(value: DataArtifactBuildInput | dict[str, Any]) -> str:
    payload = _model_or_dict(value)
    payload.pop("input_hash", None)
    if "requested_fields" in payload:
        payload["requested_fields"] = sorted(payload["requested_fields"])
    return compute_canonical_payload_hash(payload)


def compute_data_artifact_candidate_id(kind: str, output_hash: str) -> str:
    identity = compute_canonical_payload_hash(output_hash).removeprefix("sha256:")
    return f"candidate.{kind}.{identity[:24]}"


def _seal_data_artifact_candidate(
    value: DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | SourceCollectionArtifactCandidate,
):
    object.__setattr__(
        value,
        "_artifact_publication_seal",
        (_ARTIFACT_PUBLICATION_SEAL, id(value)),
    )
    return value


def _model_or_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    return (
        deepcopy(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else _drop_none(deepcopy(value))
    )


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_drop_none(item) for item in value)
    return value


def _validate_content_hash(value: BaseModel) -> None:
    expected = compute_data_artifact_content_hash(value)
    if getattr(value, "content_hash") != expected:
        raise ValueError(f"content_hash does not match canonical payload: {expected}")


def _validate_output_hash(value: BaseModel) -> None:
    expected = compute_data_artifact_output_hash(value)
    if getattr(value, "output_hash") != expected:
        raise ValueError(f"output_hash does not match canonical payload: {expected}")


def _validate_candidate_id(value: BaseModel) -> None:
    expected = compute_data_artifact_candidate_id(
        getattr(value, "kind"),
        getattr(value, "output_hash"),
    )
    if getattr(value, "candidate_id") != expected:
        raise ValueError(f"candidate_id does not match output identity: {expected}")


def _require_unique(values: tuple[BaseModel, ...], attribute: str, label: str) -> None:
    identities = [getattr(value, attribute) for value in values]
    if len(identities) != len(set(identities)):
        raise ValueError(f"candidate contains duplicate {label}")


__all__ = [
    "AlignmentStatus",
    "CanonicalValueOutcome",
    "DataArtifactBuildInput",
    "DataArtifactBuildResult",
    "DataArtifactCapacity",
    "DataArtifactErrorCode",
    "DatasetArtifactCandidate",
    "DeclaredNullValue",
    "FieldDictionaryArtifactCandidate",
    "LimitStatus",
    "MappedCanonicalValue",
    "MappingRuleSet",
    "SourceCollectionArtifactCandidate",
    "UnitConversionCatalog",
    "UnitConversionImplementation",
    "UnresolvedCanonicalValue",
    "compute_data_artifact_content_hash",
    "compute_data_artifact_candidate_id",
    "compute_data_artifact_input_hash",
    "compute_data_artifact_output_hash",
]
