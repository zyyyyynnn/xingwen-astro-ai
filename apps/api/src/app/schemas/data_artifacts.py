"""Contracts for data-artifact mapping and publication."""

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
from .core import Identifier as RuntimeIdentifier
from .core import JsonValue, UtcDateTime
from .data_artifact_identity import (
    compute_dataset_candidate_id,
    compute_dataset_canonical_content_hash,
    compute_dataset_lineage_hash,
)
from .data_artifact_primitives import DatabaseCellLocator, ManifestPins
from .data_artifact_seal import (
    DataArtifactAdmissionSnapshot,
    DataArtifactPublicationSeal,
    data_artifact_candidate_is_sealed,
)
from .crossmatch import (
    CrossmatchEvidence,
    CrossmatchResult,
    CrossmatchSide,
    CrossmatchSourceInput,
    EntityLevel,
    compute_crossmatch_record_logical_key,
)
from .enums import SourceMode
from .evidence import SourceSnapshotRecord
from .manifest import (
    CanonicalFieldId,
    ContentHash,
    DataType,
    FieldDefinition,
    Identifier,
    NullReason,
    ObjectType,
    QuantityKind,
    SemanticVersion,
)
from .scientific_document import DocumentLocator, DocumentParseQuality
from .source_acquisition import DataSourceDataLevel, DataSourceCompletion
from .source_table import SourceTableAdmission


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveDecimal = Annotated[Decimal, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]
RawScalar = str | int | float | Decimal | bool


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
    source_table_admission_mismatch = "SOURCE_TABLE_ADMISSION_MISMATCH"


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
    collection_semantics: Literal["span_absolute_or_relative_max_magnitude"]
    relative_denominator_floor: PositiveDecimal


class DecimalCapacity(BaseModel):
    model_config = MODEL_CONFIG

    max_input_text_length: int = Field(gt=0)
    max_significant_digits: int = Field(gt=0)
    max_adjusted_exponent: int = Field(gt=0)
    max_fractional_scale: int = Field(gt=0)
    max_plain_string_length: int = Field(gt=0)


class EntityProjectionRule(BaseModel):
    model_config = MODEL_CONFIG

    entity_level: EntityLevel
    allowed_object_types: tuple[ObjectType, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_allowed_types(self) -> Self:
        if len(self.allowed_object_types) != len(set(self.allowed_object_types)):
            raise ValueError("entity projection rule contains duplicate object type")
        if self.allowed_object_types != tuple(
            sorted(self.allowed_object_types, key=lambda item: item.value)
        ):
            raise ValueError("entity projection object types must use canonical order")
        return self


class EntityProjectionPolicy(BaseModel):
    model_config = MODEL_CONFIG

    version: SemanticVersion
    system_context_policy: Literal["host_and_source_assertion_only_no_implicit_join"]
    rules: tuple[EntityProjectionRule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rules(self) -> Self:
        levels = tuple(rule.entity_level for rule in self.rules)
        if len(levels) != len(set(levels)) or set(levels) != set(EntityLevel):
            raise ValueError(
                "entity projection policy must define every row grain once"
            )
        if levels != tuple(sorted(levels, key=lambda item: item.value)):
            raise ValueError("entity projection rules must use canonical order")
        return self

    def allowed_for(self, entity_level: EntityLevel) -> frozenset[ObjectType]:
        return frozenset(
            next(
                rule.allowed_object_types
                for rule in self.rules
                if rule.entity_level is entity_level
            )
        )


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
    entity_projection_policy: EntityProjectionPolicy
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
        if self.rule_id == "unit.identity":
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
    zero_serialization_policy: Literal["canonical_unsigned_zero"]
    decimal_capacity: DecimalCapacity
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


class DocumentObservationLocator(BaseModel):
    """Locator for one admitted document observation bound to persisted provenance."""

    model_config = MODEL_CONFIG

    kind: Literal["document_observation"] = "document_observation"
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    source_id: RuntimeIdentifier
    query_hash: ContentHash
    research_input_id: RuntimeIdentifier
    document_parse_id: RuntimeIdentifier
    raw_candidate_id: Identifier
    parse_quality: DocumentParseQuality
    document_locator: DocumentLocator


DataValueLocator = Annotated[
    DatabaseCellLocator | DocumentObservationLocator,
    Field(discriminator="kind"),
]


class UncertaintyValue(BaseModel):
    model_config = MODEL_CONFIG

    status: UncertaintyStatus
    source_positive: Decimal | None = None
    source_negative: Decimal | None = None
    canonical_positive: Decimal | None = None
    canonical_negative: Decimal | None = None
    positive_locator: DatabaseCellLocator | None = None
    negative_locator: DatabaseCellLocator | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        source_count = sum(
            v is not None for v in (self.source_positive, self.source_negative)
        )
        canonical_count = sum(
            v is not None for v in (self.canonical_positive, self.canonical_negative)
        )
        expected = {
            0: UncertaintyStatus.missing,
            1: UncertaintyStatus.partial,
            2: UncertaintyStatus.complete,
        }[source_count]
        if self.status is UncertaintyStatus.not_applicable:
            if (
                source_count
                or canonical_count
                or self.positive_locator
                or self.negative_locator
            ):
                raise ValueError("not-applicable uncertainty cannot carry values")
        elif self.status is not expected or source_count != canonical_count:
            raise ValueError("uncertainty status does not match retained values")
        return self


class LimitValue(BaseModel):
    model_config = MODEL_CONFIG

    status: LimitStatus
    raw_flag: int | None = None
    locator: DatabaseCellLocator | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is LimitStatus.not_applicable:
            if self.raw_flag is not None or self.locator is not None:
                raise ValueError("not-applicable limit cannot carry a flag")
        elif self.locator is None:
            # Document observation limits carry semantic status without a
            # database flag cell; their provenance lives in evidence_locator.
            if self.raw_flag is not None:
                raise ValueError("document limit cannot carry a database flag")
        elif self.raw_flag is None or not isinstance(self.locator, DatabaseCellLocator):
            raise ValueError("applicable database limit requires flag and cell locator")
        return self


class StructuredDatabaseOrigin(BaseModel):
    """Structured left/right database provenance of one source value."""

    model_config = MODEL_CONFIG

    kind: Literal["structured_database"] = "structured_database"
    source_table: NonEmptyString
    raw_record_row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...]
    raw_record_content_hash: ContentHash
    raw_field: NonEmptyString
    reference_field: NonEmptyString | None = None
    reference_value: RawScalar | None = None
    provenance_field: NonEmptyString | None = None
    provenance_value: RawScalar | None = None


class DocumentResearchInputOrigin(BaseModel):
    """Admitted document observation provenance of one source value."""

    model_config = MODEL_CONFIG

    kind: Literal["document_research_input"] = "document_research_input"
    research_input_id: RuntimeIdentifier
    research_input_content_hash: ContentHash
    document_parse_id: RuntimeIdentifier
    persisted_source_snapshot_id: RuntimeIdentifier
    pipeline_source_snapshot_id: Identifier
    pipeline_source_snapshot_content_hash: ContentHash
    raw_candidate_id: Identifier
    observation_id: Identifier
    parse_quality: DocumentParseQuality
    document_locator: DocumentLocator


SourceValueOrigin = Annotated[
    StructuredDatabaseOrigin | DocumentResearchInputOrigin,
    Field(discriminator="kind"),
]


class SourceValueCandidate(BaseModel):
    model_config = MODEL_CONFIG

    source_value_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_id: RuntimeIdentifier
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    raw_value: RawScalar | None = None
    source_unit: Identifier
    canonical_value: str | None = None
    canonical_unit: Identifier
    alias_priority: int = Field(gt=0)
    source_priority: int = Field(gt=0)
    transformation_rule_version: SemanticVersion
    conversion_rule_id: Identifier
    conversion_rule_version: SemanticVersion
    uncertainty: UncertaintyValue
    limit: LimitValue
    null_status: NullReason | None = None
    evidence_locator: DataValueLocator
    origin: SourceValueOrigin
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_value(self) -> Self:
        if (self.canonical_value is None) != (self.null_status is not None):
            raise ValueError(
                "source null status must exactly describe an unmapped raw value"
            )
        if self.raw_value is None and self.canonical_value is not None:
            raise ValueError("null source value cannot carry a canonical value")
        locator_record = (
            self.evidence_locator.source_id,
            self.evidence_locator.source_snapshot_id,
            self.evidence_locator.source_snapshot_content_hash,
            self.evidence_locator.query_hash,
        )
        expected_record = (
            self.source_id,
            self.source_snapshot_id,
            self.source_snapshot_content_hash,
            self.query_hash,
        )
        if isinstance(self.origin, StructuredDatabaseOrigin):
            if not isinstance(self.evidence_locator, DatabaseCellLocator):
                raise ValueError(
                    "structured origin requires a database cell evidence locator"
                )
            if self.limit.status is not LimitStatus.not_applicable and (
                self.limit.raw_flag is None
                or self.limit.locator is None
                or not isinstance(self.limit.locator, DatabaseCellLocator)
            ):
                raise ValueError(
                    "structured applicable limit requires database flag and locator"
                )
            expected_record += (
                self.origin.raw_record_row_key,
                self.origin.raw_record_content_hash,
            )
            locator_record += (
                self.evidence_locator.row_key,
                self.evidence_locator.raw_record_content_hash,
            )
            if (
                locator_record != expected_record
                or self.evidence_locator.raw_field != self.origin.raw_field
            ):
                raise ValueError("source value locator disagrees with its raw record")
            companion_locators = tuple(
                locator
                for locator in (
                    self.uncertainty.positive_locator,
                    self.uncertainty.negative_locator,
                    self.limit.locator,
                )
                if locator is not None
            )
            if any(
                (
                    locator.source_id,
                    locator.source_snapshot_id,
                    locator.source_snapshot_content_hash,
                    locator.query_hash,
                    locator.row_key,
                    locator.raw_record_content_hash,
                )
                != expected_record
                for locator in companion_locators
            ):
                raise ValueError(
                    "source value companion locator refers to another record"
                )
            if self.origin.reference_field is None and (
                self.origin.reference_value is not None
            ):
                raise ValueError("source reference value requires a reference field")
            if self.origin.provenance_field is None and (
                self.origin.provenance_value is not None
            ):
                raise ValueError("source provenance value requires a provenance field")
        else:
            if not isinstance(self.evidence_locator, DocumentObservationLocator):
                raise ValueError(
                    "document origin requires a document observation evidence locator"
                )
            if self.limit.status is not LimitStatus.not_applicable and (
                self.limit.raw_flag is not None or self.limit.locator is not None
            ):
                raise ValueError(
                    "document limit must carry semantic status without database provenance"
                )
            if (
                locator_record != expected_record
                or self.source_snapshot_id != self.origin.pipeline_source_snapshot_id
                or self.source_snapshot_content_hash
                != self.origin.pipeline_source_snapshot_content_hash
                or self.evidence_locator.research_input_id
                != self.origin.research_input_id
                or self.evidence_locator.document_parse_id
                != self.origin.document_parse_id
                or self.evidence_locator.raw_candidate_id
                != self.origin.raw_candidate_id
                or self.evidence_locator.parse_quality is not self.origin.parse_quality
                or self.evidence_locator.document_locator
                != self.origin.document_locator
            ):
                raise ValueError(
                    "document source value locator disagrees with its observation"
                )
        _validate_content_hash(self)
        return self


class CrossmatchTransformationAuthority(BaseModel):
    """Crossmatch-only execution binding for one transformation Evidence."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["crossmatch"] = "crossmatch"
    result_id: Identifier
    result_content_hash: ContentHash
    logical_key: ContentHash
    evidence_ids: tuple[RuntimeIdentifier, ...]


class SourceTableTransformationAuthority(BaseModel):
    """SourceTable-only execution binding for one transformation Evidence."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["source_table"] = "source_table"
    admission_id: Identifier
    row_id: Identifier


TransformationAuthority = Annotated[
    CrossmatchTransformationAuthority | SourceTableTransformationAuthority,
    Field(discriminator="authority_kind"),
]


class TransformationEvidence(BaseModel):
    model_config = MODEL_CONFIG

    evidence_id: RuntimeIdentifier
    target_candidate_kind: Literal["dataset"] = "dataset"
    dataset_row_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_value_id: Identifier
    locator: DataValueLocator
    raw_value: RawScalar | None = None
    source_unit: Identifier
    canonical_value: str | None = None
    canonical_unit: Identifier
    conversion_rule_id: Identifier
    conversion_rule_version: SemanticVersion
    conversion_catalog_id: Identifier
    conversion_catalog_version: SemanticVersion
    conversion_catalog_content_hash: ContentHash
    transformation_rule_version: SemanticVersion
    uncertainty: UncertaintyValue
    limit: LimitValue
    uncertainty_locators: tuple[DatabaseCellLocator, ...]
    limit_locator: DatabaseCellLocator | None = None
    reference_field: NonEmptyString | None = None
    reference_value: RawScalar | None = None
    reference_locator: DatabaseCellLocator | None = None
    provenance_field: NonEmptyString | None = None
    provenance_value: RawScalar | None = None
    provenance_locator: DatabaseCellLocator | None = None
    authority: TransformationAuthority
    selection_status: SelectionStatus
    selection_reason: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if len(self.uncertainty_locators) != len(set(self.uncertainty_locators)):
            raise ValueError(
                "transformation Evidence contains duplicate uncertainty locator"
            )
        if isinstance(self.authority, CrossmatchTransformationAuthority):
            if len(self.authority.evidence_ids) != len(
                set(self.authority.evidence_ids)
            ):
                raise ValueError(
                    "transformation Evidence contains duplicate crossmatch Evidence"
                )
            if self.authority.evidence_ids != tuple(
                sorted(self.authority.evidence_ids)
            ):
                raise ValueError("crossmatch Evidence IDs must use canonical order")
        _validate_content_hash(self)
        return self


class FieldSelectionRecord(BaseModel):
    model_config = MODEL_CONFIG

    selection_id: Identifier
    dataset_row_id: Identifier
    canonical_field_id: CanonicalFieldId
    selected_source_value_id: Identifier | None = None
    candidate_source_value_ids: tuple[Identifier, ...]
    strategy: Literal["prefer_source_priority_preserve_all"]
    reason: NonEmptyString
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        if len(self.candidate_source_value_ids) != len(
            set(self.candidate_source_value_ids)
        ):
            raise ValueError("selection contains duplicate source value ID")
        if (
            self.selected_source_value_id is not None
            and self.selected_source_value_id not in self.candidate_source_value_ids
        ):
            raise ValueError("selection winner must be a retained candidate")
        _validate_content_hash(self)
        return self


class FieldConflictRecord(BaseModel):
    model_config = MODEL_CONFIG

    conflict_id: Identifier
    dataset_row_id: Identifier
    canonical_field_id: CanonicalFieldId
    source_value_ids: tuple[Identifier, ...] = Field(min_length=2)
    conflict_scope: Literal["same_source", "cross_source", "identity_unresolved"]
    reason: Literal[
        "distinct canonical values are retained; source priority selects display only"
    ]
    comparison_policy_version: SemanticVersion
    absolute_difference: Decimal | None = None
    relative_denominator: Decimal | None = None
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
    selected_source_value_id: Identifier | None = None
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[RuntimeIdentifier, ...]
    selection_id: Identifier
    conflict_ids: tuple[Identifier, ...]


class DeclaredNullValue(BaseModel):
    model_config = MODEL_CONFIG

    status: Literal["declared_null"] = "declared_null"
    canonical_field_id: CanonicalFieldId
    reason: NullReason
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[RuntimeIdentifier, ...]


class UnresolvedCanonicalValue(BaseModel):
    model_config = MODEL_CONFIG

    status: Literal["unresolved"] = "unresolved"
    canonical_field_id: CanonicalFieldId
    reason: NonEmptyString
    candidate_source_value_ids: tuple[Identifier, ...]
    transformation_evidence_ids: tuple[RuntimeIdentifier, ...]
    conflict_ids: tuple[Identifier, ...]


CanonicalValueOutcome = Annotated[
    MappedCanonicalValue | DeclaredNullValue | UnresolvedCanonicalValue,
    Field(discriminator="status"),
]


class DatasetColumn(BaseModel):
    model_config = MODEL_CONFIG

    field: FieldDefinition


class CanonicalEntityIdentityValue(BaseModel):
    model_config = MODEL_CONFIG

    field_id: CanonicalFieldId
    normalized_value: NonEmptyString
    normalization_rule_version: SemanticVersion


class CanonicalEntityIdentity(BaseModel):
    model_config = MODEL_CONFIG

    entity_level: EntityLevel
    identity_values: tuple[CanonicalEntityIdentityValue, ...] = Field(min_length=1)
    logical_assertion_key: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        field_ids = [value.field_id for value in self.identity_values]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("canonical entity identity fields must be unique")
        if (self.entity_level is EntityLevel.planet_assertion) != (
            self.logical_assertion_key is not None
        ):
            raise ValueError(
                "planet assertion identity alone requires a logical assertion key"
            )
        return self


class CanonicalRowIdentity(BaseModel):
    model_config = MODEL_CONFIG

    identity_version: Literal["1.0.0"] = "1.0.0"
    record_type: Literal["paired", "unpaired", "conflict_group"]
    entity_level: EntityLevel
    alignment_status: AlignmentStatus
    member_entities: tuple[CanonicalEntityIdentity, ...] = Field(min_length=1)
    conflict_code: Identifier | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if (self.record_type == "conflict_group") != (self.conflict_code is not None):
            raise ValueError(
                "conflict row identity alone requires a crossmatch conflict code"
            )
        return self


class SourceTableCanonicalRowIdentity(BaseModel):
    """Canonical identity derived from one admitted SourceTable row."""

    model_config = MODEL_CONFIG

    identity_kind: Literal["source_table"] = "source_table"
    identity_version: Literal["1.0.0"] = "1.0.0"
    entity_level: EntityLevel = EntityLevel.host_star
    identity_field_id: CanonicalFieldId
    canonical_identity: NonEmptyString


class CrossmatchRowAuthority(BaseModel):
    model_config = MODEL_CONFIG

    authority_kind: Literal["crossmatch"] = "crossmatch"
    record_type: Literal["paired", "unpaired", "conflict_group"]
    logical_key: ContentHash
    entity_level: EntityLevel
    canonical_row_identity: CanonicalRowIdentity
    alignment_status: AlignmentStatus
    source_member_ids: tuple[Identifier, ...]


class SourceTableRowAuthority(BaseModel):
    model_config = MODEL_CONFIG

    authority_kind: Literal["source_table"] = "source_table"
    admission_id: Identifier
    source_table_row_id: Identifier
    canonical_row_identity: SourceTableCanonicalRowIdentity


DatasetRowAuthority = Annotated[
    CrossmatchRowAuthority | SourceTableRowAuthority,
    Field(discriminator="authority_kind"),
]


class DatasetRow(BaseModel):
    model_config = MODEL_CONFIG

    row_id: Identifier
    row_authority: DatasetRowAuthority
    projection_policy_version: SemanticVersion
    projected_field_ids: tuple[CanonicalFieldId, ...]
    fields: tuple[CanonicalValueOutcome, ...]
    conflict_ids: tuple[Identifier, ...]
    evidence_ids: tuple[RuntimeIdentifier, ...]
    source_snapshot_ids: tuple[RuntimeIdentifier, ...]
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        for values, label in (
            (self.projected_field_ids, "projected field"),
            (self.conflict_ids, "conflict"),
            (self.evidence_ids, "Evidence"),
            (self.source_snapshot_ids, "SourceSnapshot"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Dataset row contains duplicate {label} reference")
        if self.projected_field_ids != tuple(
            outcome.canonical_field_id for outcome in self.fields
        ):
            raise ValueError("Dataset row projection does not match its field outcomes")
        if isinstance(self.row_authority, CrossmatchRowAuthority):
            if (
                self.row_authority.record_type
                != self.row_authority.canonical_row_identity.record_type
                or self.row_authority.entity_level
                is not self.row_authority.canonical_row_identity.entity_level
                or self.row_authority.alignment_status
                is not self.row_authority.canonical_row_identity.alignment_status
            ):
                raise ValueError(
                    "Dataset row fields disagree with its canonical row identity"
                )
        elif self.row_authority.source_table_row_id != self.row_id:
            raise ValueError("SourceTable row identity does not bind its row_id")
        _validate_content_hash(self)
        return self

    @property
    def entity_level(self) -> EntityLevel:
        return self.row_authority.canonical_row_identity.entity_level

    @property
    def canonical_row_identity(
        self,
    ) -> CanonicalRowIdentity | SourceTableCanonicalRowIdentity:
        return self.row_authority.canonical_row_identity


class _PublisherReadyCandidate(BaseModel):
    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True
    _artifact_publication_seal: DataArtifactPublicationSeal | None = PrivateAttr(
        default=None
    )
    _artifact_publication_context: DataArtifactAdmissionSnapshot | None = PrivateAttr(
        default=None
    )

    def __artifact_publication_is_admitted__(self) -> bool:
        return data_artifact_candidate_is_sealed(
            self,
            self._artifact_publication_seal,
            self._artifact_publication_context,
            public_payload_hash=compute_data_artifact_public_payload_hash(self),
        )


class CrossmatchArtifactAuthority(BaseModel):
    """Crossmatch-specific identity and Evidence authority for a candidate."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["crossmatch"] = "crossmatch"
    result_id: Identifier
    input_hash: ContentHash
    output_hash: ContentHash
    content_hash: ContentHash
    source_snapshot_ids: tuple[RuntimeIdentifier, ...]
    evidence: tuple[CrossmatchEvidence, ...]
    evidence_ids: tuple[RuntimeIdentifier, ...]
    alignment_record_keys: tuple[ContentHash, ...] = ()
    conflict_record_keys: tuple[ContentHash, ...] = ()
    review_required_record_keys: tuple[ContentHash, ...] = ()
    inconclusive_record_keys: tuple[ContentHash, ...] = ()

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if len(self.source_snapshot_ids) != 2:
            raise ValueError("Crossmatch authority requires exactly two snapshots")
        if self.source_snapshot_ids != tuple(sorted(self.source_snapshot_ids)):
            raise ValueError("Crossmatch authority snapshots must use canonical order")
        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        if len(evidence_by_id) != len(self.evidence):
            raise ValueError("Crossmatch authority contains duplicate Evidence")
        if self.evidence_ids != tuple(sorted(evidence_by_id)):
            raise ValueError("Crossmatch authority Evidence registry is not closed")
        return self


class SourceTableArtifactAuthority(BaseModel):
    """Compact SourceTable lineage binding for a public candidate."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["source_table"] = "source_table"
    admission_id: Identifier
    admission_output_hash: ContentHash
    source_id: Identifier
    source_table: NonEmptyString
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    evidence_ids: tuple[RuntimeIdentifier, ...]

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        if self.evidence_ids != tuple(sorted(set(self.evidence_ids))):
            raise ValueError("SourceTable authority Evidence registry is not canonical")
        return self


DataArtifactAuthority = Annotated[
    CrossmatchArtifactAuthority | SourceTableArtifactAuthority,
    Field(discriminator="authority_kind"),
]


class DatasetArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["dataset"] = "dataset"
    schema_version: Literal["4.0.0"] = "4.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    authority: DataArtifactAuthority
    requested_fields: tuple[CanonicalFieldId, ...]
    columns: tuple[DatasetColumn, ...]
    rows: tuple[DatasetRow, ...]
    source_values: tuple[SourceValueCandidate, ...]
    transformation_evidence: tuple[TransformationEvidence, ...]
    selections: tuple[FieldSelectionRecord, ...]
    conflicts: tuple[FieldConflictRecord, ...]
    row_count: int = Field(ge=0)
    field_count: int = Field(ge=0)
    source_snapshot_ids: tuple[RuntimeIdentifier, ...]
    evidence_ids: tuple[RuntimeIdentifier, ...]
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
    canonical_content_hash: ContentHash
    lineage_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_candidate(self) -> Self:
        if self.row_count != len(self.rows) or self.field_count != len(self.columns):
            raise ValueError("Dataset candidate row/field count mismatch")
        if self.requested_fields != tuple(c.field.field_id for c in self.columns):
            raise ValueError("Dataset columns must exactly project requested fields")
        _require_unique(self.source_values, "source_value_id", "source value")
        _require_unique(
            self.transformation_evidence, "evidence_id", "transformation Evidence"
        )
        _require_unique(self.selections, "selection_id", "selection")
        _require_unique(self.conflicts, "conflict_id", "conflict")
        for values, label in (
            (self.requested_fields, "requested field"),
            (self.source_snapshot_ids, "SourceSnapshot"),
            (self.evidence_ids, "Evidence"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Dataset contains duplicate {label} reference")
        if self.source_snapshot_ids != tuple(sorted(self.source_snapshot_ids)):
            raise ValueError("Dataset SourceSnapshot registry must use canonical order")
        if self.evidence_ids != tuple(sorted(self.evidence_ids)):
            raise ValueError("Dataset top-level references must use canonical order")
        source_values = {item.source_value_id: item for item in self.source_values}
        evidence = {item.evidence_id: item for item in self.transformation_evidence}
        if isinstance(self.authority, CrossmatchArtifactAuthority):
            if self.authority.source_snapshot_ids and not set(
                self.authority.source_snapshot_ids
            ) <= set(self.source_snapshot_ids):
                raise ValueError("Dataset authority snapshots are not registered")
        else:
            if self.authority.source_snapshot_id not in self.source_snapshot_ids:
                raise ValueError("Dataset SourceTable snapshot is not registered")
            for source_value in self.source_values:
                if not isinstance(source_value.origin, StructuredDatabaseOrigin):
                    raise ValueError(
                        "SourceTable Dataset values require structured database origin"
                    )
                locator = source_value.evidence_locator
                if (
                    not isinstance(locator, DatabaseCellLocator)
                    or locator.source_role != "single"
                ):
                    raise ValueError(
                        "SourceTable Dataset values require single-source cell locators"
                    )
                if (
                    source_value.source_id != self.authority.source_id
                    or source_value.source_snapshot_id
                    != self.authority.source_snapshot_id
                    or source_value.source_snapshot_content_hash
                    != self.authority.source_snapshot_content_hash
                    or locator.source_id != self.authority.source_id
                    or locator.source_snapshot_id != self.authority.source_snapshot_id
                    or locator.source_snapshot_content_hash
                    != self.authority.source_snapshot_content_hash
                    or source_value.origin.source_table != self.authority.source_table
                    or source_value.origin.raw_field != locator.raw_field
                ):
                    raise ValueError(
                        "SourceTable Dataset value disagrees with its compact authority"
                    )
            for row in self.rows:
                if not isinstance(row.row_authority, SourceTableRowAuthority):
                    raise ValueError(
                        "SourceTable Dataset requires SourceTable row authority"
                    )
                identity = row.row_authority.canonical_row_identity
                if row.row_authority.admission_id != self.authority.admission_id:
                    raise ValueError("SourceTable Dataset row authority is not bound")
        selections = {item.selection_id: item for item in self.selections}
        conflicts = {item.conflict_id: item for item in self.conflicts}
        expected_evidence_ids = set(evidence)
        if isinstance(self.authority, CrossmatchArtifactAuthority):
            expected_evidence_ids |= set(self.authority.evidence_ids)
        else:
            if self.authority.evidence_ids != self.evidence_ids:
                raise ValueError("SourceTable Dataset Evidence registry is not closed")
            expected_evidence_ids = set(evidence)
        if expected_evidence_ids != set(self.evidence_ids):
            raise ValueError(
                "Dataset Evidence references must be the exact retained set"
            )
        if isinstance(self.authority, CrossmatchArtifactAuthority) and not {
            crossmatch_id
            for item in evidence.values()
            for crossmatch_id in (
                item.authority.evidence_ids
                if isinstance(item.authority, CrossmatchTransformationAuthority)
                else ()
            )
        } <= set(self.authority.evidence_ids):
            raise ValueError(
                "transformation Evidence refers to undeclared crossmatch Evidence"
            )
        used_snapshot_ids = {
            *[item.source_snapshot_id for item in self.source_values],
            *[item.locator.source_snapshot_id for item in self.transformation_evidence],
            *[
                snapshot_id
                for row in self.rows
                for snapshot_id in row.source_snapshot_ids
            ],
        }
        if not used_snapshot_ids <= set(self.source_snapshot_ids):
            raise ValueError(
                "Dataset SourceSnapshot registry disagrees with retained values"
            )
        fields = {column.field.field_id: column.field for column in self.columns}

        def _structured_origin(item: SourceValueCandidate) -> StructuredDatabaseOrigin:
            return item.origin  # type: ignore[return-value]

        for item in evidence.values():
            source_value = source_values.get(item.source_value_id)
            if source_value is None:
                raise ValueError(
                    "transformation Evidence must resolve to its source value"
                )
            origin = _structured_origin(source_value)
            reference_field = (
                origin.reference_field
                if isinstance(origin, StructuredDatabaseOrigin)
                else None
            )
            reference_value = (
                origin.reference_value
                if isinstance(origin, StructuredDatabaseOrigin)
                else None
            )
            provenance_field = (
                origin.provenance_field
                if isinstance(origin, StructuredDatabaseOrigin)
                else None
            )
            provenance_value = (
                origin.provenance_value
                if isinstance(origin, StructuredDatabaseOrigin)
                else None
            )
            expected_evidence_binding = (
                source_value.canonical_field_id,
                source_value.evidence_locator,
                source_value.raw_value,
                source_value.source_unit,
                source_value.canonical_value,
                source_value.canonical_unit,
                source_value.conversion_rule_id,
                source_value.conversion_rule_version,
                source_value.transformation_rule_version,
                source_value.uncertainty,
                source_value.limit,
                reference_field,
                reference_value,
                provenance_field,
                provenance_value,
            )
            actual_evidence_binding = (
                item.canonical_field_id,
                item.locator,
                item.raw_value,
                item.source_unit,
                item.canonical_value,
                item.canonical_unit,
                item.conversion_rule_id,
                item.conversion_rule_version,
                item.transformation_rule_version,
                item.uncertainty,
                item.limit,
                item.reference_field,
                item.reference_value,
                item.provenance_field,
                item.provenance_value,
            )
            if actual_evidence_binding != expected_evidence_binding:
                raise ValueError(
                    "transformation Evidence values disagree with source value"
                )
            if item.uncertainty_locators != tuple(
                locator
                for locator in (
                    source_value.uncertainty.positive_locator,
                    source_value.uncertainty.negative_locator,
                )
                if locator is not None
            ):
                raise ValueError("transformation Evidence uncertainty locators drifted")
            if item.limit_locator != source_value.limit.locator:
                raise ValueError("transformation Evidence limit locator drifted")
            expected_reference_locator = (
                None
                if reference_field is None
                else source_value.evidence_locator.model_copy(  # type: ignore[union-attr]
                    update={"raw_field": reference_field}
                )
            )
            expected_provenance_locator = (
                None
                if provenance_field is None
                else source_value.evidence_locator.model_copy(  # type: ignore[union-attr]
                    update={"raw_field": provenance_field}
                )
            )
            if (
                item.reference_locator != expected_reference_locator
                or item.provenance_locator != expected_provenance_locator
            ):
                raise ValueError("transformation Evidence companion locators drifted")
            if (
                item.conversion_catalog_id != self.conversion_catalog_id
                or item.conversion_catalog_version != self.conversion_catalog_version
                or item.conversion_catalog_content_hash
                != self.conversion_catalog_content_hash
            ):
                raise ValueError("transformation Evidence execution bindings drifted")
            if isinstance(self.authority, CrossmatchArtifactAuthority):
                if not isinstance(item.authority, CrossmatchTransformationAuthority):
                    raise ValueError(
                        "Crossmatch Dataset requires Crossmatch Evidence authority"
                    )
                if (
                    item.authority.result_id != self.authority.result_id
                    or item.authority.result_content_hash != self.authority.content_hash
                ):
                    raise ValueError(
                        "transformation Evidence Crossmatch binding drifted"
                    )
            else:
                if not isinstance(item.authority, SourceTableTransformationAuthority):
                    raise ValueError(
                        "SourceTable Dataset requires SourceTable Evidence authority"
                    )
                if item.authority.admission_id != self.authority.admission_id:
                    raise ValueError(
                        "transformation Evidence SourceTable binding drifted"
                    )
        for row in self.rows:
            row_evidence = {
                evidence_id
                for outcome in row.fields
                for evidence_id in outcome.transformation_evidence_ids
            }
            row_conflicts = {
                conflict_id
                for outcome in row.fields
                for conflict_id in getattr(outcome, "conflict_ids", ())
            }
            if (
                set(row.evidence_ids) != row_evidence
                or set(row.conflict_ids) != row_conflicts
            ):
                raise ValueError("Dataset row reference registries are not exact")
            row_fields = tuple(outcome.canonical_field_id for outcome in row.fields)
            if (
                len(row_fields) != len(set(row_fields))
                or not set(row_fields) <= set(self.requested_fields)
                or row_fields
                != tuple(
                    field_id
                    for field_id in self.requested_fields
                    if field_id in row_fields
                )
            ):
                raise ValueError(
                    "Dataset row fields are not a canonical requested-field projection"
                )
            for outcome in row.fields:
                for values, label in (
                    (outcome.candidate_source_value_ids, "source value"),
                    (outcome.transformation_evidence_ids, "transformation Evidence"),
                    (getattr(outcome, "conflict_ids", ()), "conflict"),
                ):
                    if len(values) != len(set(values)):
                        raise ValueError(
                            f"Dataset outcome contains duplicate {label} reference"
                        )
                definition = fields[outcome.canonical_field_id]
                if not set(outcome.candidate_source_value_ids) <= source_values.keys():
                    raise ValueError(
                        "Dataset outcome refers to an unknown source value"
                    )
                if not set(outcome.transformation_evidence_ids) <= evidence.keys():
                    raise ValueError(
                        "Dataset outcome refers to unknown transformation Evidence"
                    )
                outcome_source_values = [
                    source_values[item] for item in outcome.candidate_source_value_ids
                ]
                if any(
                    item.canonical_field_id != outcome.canonical_field_id
                    for item in outcome_source_values
                ):
                    raise ValueError(
                        "Dataset outcome reuses a source value for another field"
                    )
                if isinstance(outcome, MappedCanonicalValue):
                    selection = selections.get(outcome.selection_id)
                    if (
                        selection is None
                        or not set(outcome.conflict_ids) <= conflicts.keys()
                    ):
                        raise ValueError(
                            "mapped outcome has a dangling selection/conflict reference"
                        )
                    if outcome.selected_source_value_id is not None:
                        if (
                            outcome.selected_source_value_id
                            not in outcome.candidate_source_value_ids
                        ):
                            raise ValueError(
                                "mapped outcome winner is not a retained source value"
                            )
                        expected_reason = (
                            "SourceTable admission retains the canonical source value"
                            if isinstance(self.authority, SourceTableArtifactAuthority)
                            else "highest declared source and alias priority; every candidate is retained"
                        )
                        selected = source_values[outcome.selected_source_value_id]
                        if (
                            selected.canonical_value != outcome.canonical_value
                            or selected.canonical_unit != outcome.canonical_unit
                        ):
                            raise ValueError(
                                "mapped outcome disagrees with its selected source value"
                            )
                    else:
                        # Document consensus: every candidate agrees and no
                        # candidate is promoted to a scientific winner.
                        expected_reason = (
                            "equal admitted document values form the canonical consensus; "
                            "no scientific winner is selected"
                        )
                        agreeing = all(
                            item.canonical_value == outcome.canonical_value
                            for item in outcome_source_values
                        )
                        structured_candidates = [
                            item
                            for item in outcome_source_values
                            if isinstance(item.origin, StructuredDatabaseOrigin)
                        ]
                        if (
                            not agreeing
                            or not outcome_source_values
                            or structured_candidates
                        ):
                            raise ValueError(
                                "document consensus requires equal document-only candidates"
                            )
                    if (
                        selection.selected_source_value_id
                        != outcome.selected_source_value_id
                        or selection.candidate_source_value_ids
                        != outcome.candidate_source_value_ids
                        or selection.dataset_row_id != row.row_id
                        or selection.canonical_field_id != outcome.canonical_field_id
                    ):
                        raise ValueError(
                            "mapped outcome disagrees with its selection record"
                        )
                    if selection.reason != expected_reason:
                        raise ValueError(
                            "mapped outcome selection reason is not frozen"
                        )
                elif isinstance(outcome, DeclaredNullValue):
                    if (
                        not definition.nullable
                        or outcome.reason not in definition.null_policy.allowed_reasons
                    ):
                        raise ValueError(
                            "declared null is not authorized by the Field Manifest"
                        )
                outcome_evidence = [
                    evidence[item] for item in outcome.transformation_evidence_ids
                ]
                if any(
                    item.dataset_row_id != row.row_id
                    or item.canonical_field_id != outcome.canonical_field_id
                    for item in outcome_evidence
                ):
                    raise ValueError(
                        "Dataset outcome Evidence is bound to another row/field"
                    )
                if {item.source_value_id for item in outcome_evidence} != set(
                    outcome.candidate_source_value_ids
                ):
                    raise ValueError(
                        "Dataset outcome source values and Evidence are not one-to-one"
                    )
                expected_statuses = {
                    item.source_value_id: (
                        SelectionStatus.conflict
                        if isinstance(outcome, UnresolvedCanonicalValue)
                        or bool(getattr(outcome, "conflict_ids", ()))
                        else SelectionStatus.selected
                        if isinstance(outcome, MappedCanonicalValue)
                        and item.source_value_id == outcome.selected_source_value_id
                        else SelectionStatus.unselected
                    )
                    for item in outcome_source_values
                }
                if any(
                    item.selection_status is not expected_statuses[item.source_value_id]
                    for item in outcome_evidence
                ):
                    raise ValueError("transformation Evidence selection status drifted")
                expected_reason = (
                    f"crossmatch alignment remains {row.row_authority.alignment_status.value}; no field winner is selected"
                    if isinstance(outcome, UnresolvedCanonicalValue)
                    and isinstance(row.row_authority, CrossmatchRowAuthority)
                    else "SourceTable admission retains the canonical source value"
                    if isinstance(outcome, UnresolvedCanonicalValue)
                    else (
                        "equal admitted document values form the canonical consensus; "
                        "no scientific winner is selected"
                    )
                    if isinstance(outcome, MappedCanonicalValue)
                    and outcome.selected_source_value_id is None
                    else "SourceTable admission retains the canonical source value"
                    if isinstance(self.authority, SourceTableArtifactAuthority)
                    and isinstance(outcome, MappedCanonicalValue)
                    else "highest declared source and alias priority; every candidate is retained"
                )
                if any(
                    item.selection_reason != expected_reason
                    for item in outcome_evidence
                ):
                    raise ValueError("transformation Evidence selection reason drifted")
                for conflict_id in getattr(outcome, "conflict_ids", ()):
                    conflict = conflicts[conflict_id]
                    non_null_ids = tuple(
                        sorted(
                            item.source_value_id
                            for item in outcome_source_values
                            if item.canonical_value is not None
                        )
                    )
                    if (
                        conflict.dataset_row_id != row.row_id
                        or conflict.canonical_field_id != outcome.canonical_field_id
                        or conflict.source_value_ids != non_null_ids
                    ):
                        raise ValueError(
                            "conflict candidate set disagrees with its outcome"
                        )
                    expected_scope = (
                        "same_source"
                        if len(
                            {
                                item.source_id
                                for item in outcome_source_values
                                if item.canonical_value is not None
                            }
                        )
                        == 1
                        else "cross_source"
                    )
                    if conflict.conflict_scope != expected_scope:
                        raise ValueError(
                            "conflict scope disagrees with candidate sources"
                        )
                    numeric_values = [
                        Decimal(item.canonical_value)
                        for item in outcome_source_values
                        if item.canonical_value is not None
                        and definition.data_type in {DataType.integer, DataType.number}
                    ]
                    if numeric_values:
                        absolute = max(numeric_values) - min(numeric_values)
                        if (
                            conflict.absolute_difference != absolute
                            or conflict.relative_denominator is None
                            or conflict.relative_denominator
                            < max(abs(value) for value in numeric_values)
                            or conflict.relative_difference
                            != absolute / conflict.relative_denominator
                        ):
                            raise ValueError(
                                "conflict numeric differences are not derived"
                            )
                    elif any(
                        value is not None
                        for value in (
                            conflict.absolute_difference,
                            conflict.relative_denominator,
                            conflict.relative_difference,
                        )
                    ):
                        raise ValueError(
                            "non-numeric conflict carries numeric differences"
                        )
        referenced_selections = {
            outcome.selection_id
            for row in self.rows
            for outcome in row.fields
            if isinstance(outcome, MappedCanonicalValue)
        }
        if referenced_selections != selections.keys():
            raise ValueError("Dataset selection registry contains unreferenced records")
        referenced_source_values = {
            source_value_id
            for row in self.rows
            for outcome in row.fields
            for source_value_id in outcome.candidate_source_value_ids
        }
        referenced_evidence = {
            evidence_id
            for row in self.rows
            for outcome in row.fields
            for evidence_id in outcome.transformation_evidence_ids
        }
        referenced_conflicts = {
            conflict_id
            for row in self.rows
            for outcome in row.fields
            for conflict_id in getattr(outcome, "conflict_ids", ())
        }
        if referenced_source_values != source_values.keys():
            raise ValueError("Dataset source value registry contains orphan records")
        if referenced_evidence != evidence.keys():
            raise ValueError(
                "Dataset transformation Evidence registry contains orphan records"
            )
        if referenced_conflicts != conflicts.keys():
            raise ValueError("Dataset conflict registry contains orphan records")
        expected_canonical_hash = compute_data_artifact_canonical_content_hash(self)
        if self.canonical_content_hash != expected_canonical_hash:
            raise ValueError(
                "canonical_content_hash does not match complete scientific semantics: "
                f"{expected_canonical_hash}"
            )
        expected_lineage_hash = compute_data_artifact_lineage_hash(self)
        if self.lineage_hash != expected_lineage_hash:
            raise ValueError(
                "lineage_hash does not match complete raw/input lineage: "
                f"{expected_lineage_hash}"
            )
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class FieldDictionaryArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["field_dictionary"] = "field_dictionary"
    schema_version: Literal["4.0.0"] = "4.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    authority: DataArtifactAuthority
    requested_fields: tuple[CanonicalFieldId, ...]
    field_definitions: tuple[FieldDefinition, ...]
    source_snapshot_ids: tuple[RuntimeIdentifier, ...]
    evidence_ids: tuple[RuntimeIdentifier, ...]
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
        if self.requested_fields != tuple(
            field.field_id for field in self.field_definitions
        ):
            raise ValueError("FieldDictionary must exactly project requested fields")
        for values, label in (
            (self.requested_fields, "requested field"),
            (self.source_snapshot_ids, "SourceSnapshot"),
            (self.evidence_ids, "Evidence"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    f"FieldDictionary contains duplicate {label} reference"
                )
        if self.source_snapshot_ids != tuple(sorted(self.source_snapshot_ids)):
            raise ValueError("FieldDictionary references must use canonical order")
        if self.evidence_ids != tuple(sorted(self.evidence_ids)):
            raise ValueError("FieldDictionary references must use canonical order")
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class RawSourceRecordReference(BaseModel):
    model_config = MODEL_CONFIG

    source_id: Identifier
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    row_key: tuple[tuple[NonEmptyString, NonEmptyString], ...] = Field(min_length=1)
    raw_record_content_hash: ContentHash


def compute_raw_record_reference_registry_hash(
    references: tuple[RawSourceRecordReference, ...] | list[RawSourceRecordReference],
) -> str:
    return compute_canonical_payload_hash(
        [reference.model_dump(mode="json") for reference in references]
    )


class StructuredSourceCollectionMember(BaseModel):
    model_config = MODEL_CONFIG

    member_kind: Literal["structured"] = "structured"
    side: CrossmatchSide
    source_snapshot: SourceSnapshotRecord
    source_id: Identifier
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    source_mode: SourceMode
    data_level: DataSourceDataLevel
    completion: DataSourceCompletion
    license_note: NonEmptyString
    raw_record_references: tuple[RawSourceRecordReference, ...]
    raw_record_count: int = Field(ge=0)
    raw_record_reference_registry_hash: ContentHash

    @model_validator(mode="after")
    def validate_member(self) -> Self:
        if (
            self.source_id != self.source_snapshot.source_id
            or self.source_snapshot_id != self.source_snapshot.snapshot_id
            or self.source_snapshot_content_hash != self.source_snapshot.content_hash
            or self.query_hash != self.source_snapshot.query_hash
            or self.license_note != self.source_snapshot.license_note
        ):
            raise ValueError(
                "SourceCollection member disagrees with its SourceSnapshot"
            )
        metadata = self.source_snapshot.request_metadata
        if metadata.get("source_mode") not in (
            None,
            self.source_mode.value,
        ) or metadata.get("data_level") not in (None, self.data_level.value):
            raise ValueError(
                "SourceCollection member execution scope disagrees with snapshot"
            )
        row_keys = [item.row_key for item in self.raw_record_references]
        record_hashes = [
            item.raw_record_content_hash for item in self.raw_record_references
        ]
        if self.raw_record_references != tuple(
            sorted(
                self.raw_record_references,
                key=lambda item: (
                    item.source_id,
                    item.row_key,
                    item.raw_record_content_hash,
                ),
            )
        ):
            raise ValueError(
                "SourceCollection raw record references must use canonical order"
            )
        if len(row_keys) != len(set(row_keys)):
            raise ValueError("SourceCollection member contains duplicate row key")
        if len(record_hashes) != len(set(record_hashes)):
            raise ValueError("SourceCollection member contains duplicate record hash")
        if (
            self.raw_record_count != len(self.raw_record_references)
            or self.raw_record_reference_registry_hash
            != compute_raw_record_reference_registry_hash(self.raw_record_references)
        ):
            raise ValueError("SourceCollection raw record registry binding drifted")
        expected_binding = (
            self.source_id,
            self.source_snapshot_id,
            self.source_snapshot_content_hash,
            self.query_hash,
        )
        if any(
            (
                item.source_id,
                item.source_snapshot_id,
                item.source_snapshot_content_hash,
                item.query_hash,
            )
            != expected_binding
            for item in self.raw_record_references
        ):
            raise ValueError("raw record reference disagrees with its source member")
        return self


class SourceTableSourceCollectionMember(BaseModel):
    """One persisted SourceTable and its compact raw-record registry."""

    model_config = MODEL_CONFIG

    member_kind: Literal["source_table"] = "source_table"
    source_snapshot: SourceSnapshotRecord
    admission_id: Identifier
    admission_output_hash: ContentHash
    source_id: Identifier
    source_table: NonEmptyString
    source_snapshot_id: RuntimeIdentifier
    source_snapshot_content_hash: ContentHash
    query_hash: ContentHash
    license_note: NonEmptyString
    raw_record_references: tuple[RawSourceRecordReference, ...]
    raw_record_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_member(self) -> Self:
        if (
            self.source_snapshot.snapshot_id != self.source_snapshot_id
            or self.source_snapshot.source_id != self.source_id
            or self.source_snapshot.content_hash != self.source_snapshot_content_hash
            or self.source_snapshot.query_hash != self.query_hash
            or self.license_note != self.source_snapshot.license_note
        ):
            raise ValueError("SourceTable member disagrees with its Snapshot")
        if self.raw_record_references != tuple(
            sorted(
                self.raw_record_references,
                key=lambda item: (
                    item.source_id,
                    item.row_key,
                    item.raw_record_content_hash,
                ),
            )
        ):
            raise ValueError(
                "SourceTable raw record references must use canonical order"
            )
        row_keys = tuple(item.row_key for item in self.raw_record_references)
        record_hashes = tuple(
            item.raw_record_content_hash for item in self.raw_record_references
        )
        if len(row_keys) != len(set(row_keys)):
            raise ValueError("SourceTable member contains duplicate row key")
        if len(record_hashes) != len(set(record_hashes)):
            raise ValueError("SourceTable member contains duplicate record hash")
        if self.raw_record_count != len(self.raw_record_references):
            raise ValueError("SourceTable raw record registry is not closed")
        expected_binding = (
            self.source_id,
            self.source_snapshot_id,
            self.source_snapshot_content_hash,
            self.query_hash,
        )
        if any(
            (
                item.source_id,
                item.source_snapshot_id,
                item.source_snapshot_content_hash,
                item.query_hash,
            )
            != expected_binding
            for item in self.raw_record_references
        ):
            raise ValueError("raw record reference disagrees with its source member")
        return self


class DataSourceSnapshotProjection(BaseModel):
    """Logical data-pipeline projection of one scientific source snapshot."""

    model_config = MODEL_CONFIG

    snapshot_id: Identifier
    source_id: RuntimeIdentifier
    source_type: NonEmptyString
    retrieved_at: UtcDateTime
    query: JsonValue
    query_hash: ContentHash
    source_version_or_etag: str | None = None
    content_hash: ContentHash
    license_note: NonEmptyString
    cache_version: Annotated[str, Field(min_length=1)] | None = None
    request_metadata: dict[str, JsonValue] = Field(default_factory=dict)


class DocumentSourceCollectionMember(BaseModel):
    """One admitted document research input retained as supplemental provenance."""

    model_config = MODEL_CONFIG

    member_kind: Literal["document"] = "document"
    source_class: Literal["document_research_input"]
    pipeline_source_snapshot: DataSourceSnapshotProjection
    pipeline_source_snapshot_id: Identifier
    pipeline_source_snapshot_content_hash: ContentHash
    persisted_source_snapshot_id: RuntimeIdentifier
    research_input_id: RuntimeIdentifier
    research_input_content_hash: ContentHash
    document_parse_ids: tuple[RuntimeIdentifier, ...] = Field(min_length=1)
    observation_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def validate_member(self) -> Self:
        if (
            self.pipeline_source_snapshot_id
            != self.pipeline_source_snapshot.snapshot_id
            or self.pipeline_source_snapshot_content_hash
            != self.pipeline_source_snapshot.content_hash
            or self.research_input_content_hash
            != self.pipeline_source_snapshot.content_hash
            or self.pipeline_source_snapshot.source_id
            != f"research_input:{self.research_input_id}"
            or not self.persisted_source_snapshot_id
            or len(self.document_parse_ids) != len(set(self.document_parse_ids))
            or len(self.observation_ids) != len(set(self.observation_ids))
            or not self.observation_ids
            or self.observation_ids != tuple(sorted(self.observation_ids))
        ):
            raise ValueError(
                "Document SourceCollection member disagrees with its projection"
            )
        return self


class SourceCollectionArtifactCandidate(_PublisherReadyCandidate):
    kind: Literal["source_collection"] = "source_collection"
    schema_version: Literal["4.0.0"] = "4.0.0"
    candidate_id: Identifier
    manifest_pins: ManifestPins
    authority: DataArtifactAuthority
    source_snapshot_ids: tuple[RuntimeIdentifier, ...]
    evidence_ids: tuple[RuntimeIdentifier, ...]
    crossmatch_sources: tuple[StructuredSourceCollectionMember, ...] = ()
    source_table_sources: tuple[SourceTableSourceCollectionMember, ...] = ()
    supplemental_document_sources: tuple[DocumentSourceCollectionMember, ...] = ()
    source_value_ids: tuple[Identifier, ...]
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
        structured_members = self.crossmatch_sources
        source_table_members = self.source_table_sources
        document_members = self.supplemental_document_sources
        if isinstance(self.authority, CrossmatchArtifactAuthority):
            if source_table_members or (
                len(structured_members) != 2
                or tuple(member.side for member in structured_members)
                != (CrossmatchSide.left, CrossmatchSide.right)
            ):
                raise ValueError(
                    "SourceCollection requires one canonical left/right structured pair"
                )
            source_ids = tuple(member.source_id for member in structured_members)
            snapshot_ids = tuple(
                member.source_snapshot_id for member in structured_members
            )
            if len(set(source_ids)) != 2 or len(set(snapshot_ids)) != 2:
                raise ValueError(
                    "SourceCollection requires two independent sources and snapshots"
                )
            if set(self.authority.source_snapshot_ids) != set(snapshot_ids):
                raise ValueError(
                    "SourceCollection Crossmatch snapshots must be the left/right pair"
                )
        else:
            if len(source_table_members) != 1 or structured_members or document_members:
                raise ValueError(
                    "SourceTable SourceCollection requires exactly one source-table member"
                )
            source_ids = (source_table_members[0].source_id,)
            snapshot_ids = (source_table_members[0].source_snapshot_id,)
            if (
                self.authority.source_snapshot_id != snapshot_ids[0]
                or self.authority.admission_id != source_table_members[0].admission_id
                or self.authority.admission_output_hash
                != source_table_members[0].admission_output_hash
            ):
                raise ValueError("SourceCollection SourceTable authority drifted")
        if document_members and any(
            member.pipeline_source_snapshot_id in snapshot_ids
            for member in document_members
        ):
            raise ValueError(
                "Document members must not reuse a crossmatch SourceSnapshot"
            )
        expected_snapshots = tuple(
            sorted(
                (
                    *snapshot_ids,
                    *(
                        member.pipeline_source_snapshot_id
                        for member in document_members
                    ),
                )
            )
        )
        if self.source_snapshot_ids != expected_snapshots:
            raise ValueError(
                "SourceCollection snapshot projection disagrees with members"
            )
        for values, label in (
            (self.evidence_ids, "Evidence"),
            (self.source_value_ids, "source value"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"SourceCollection contains duplicate {label}")
        if isinstance(self.authority, CrossmatchArtifactAuthority):
            status_sets = (
                set(self.authority.conflict_record_keys),
                set(self.authority.review_required_record_keys),
                set(self.authority.inconclusive_record_keys),
            )
            if not set().union(*status_sets) <= set(
                self.authority.alignment_record_keys
            ):
                raise ValueError(
                    "SourceCollection status keys must resolve to alignment records"
                )
            if any(
                left & right
                for index, left in enumerate(status_sets)
                for right in status_sets[index + 1 :]
            ):
                raise ValueError("SourceCollection status registries must be disjoint")
        _validate_output_hash(self)
        _validate_candidate_id(self)
        return self


class DocumentObservationAdmissionStatus(StrEnum):
    accepted = "accepted"
    review_required = "review_required"
    rejected = "rejected"


class DocumentObservationAdmissionCode(StrEnum):
    """Stable reason codes for document observation admission outcomes."""

    document_source_disabled = "DOCUMENT_SOURCE_DISABLED"
    document_source_capability_unsupported = "DOCUMENT_SOURCE_CAPABILITY_UNSUPPORTED"
    document_provenance_invalid = "DOCUMENT_PROVENANCE_INVALID"
    document_parse_unsupported = "DOCUMENT_PARSE_UNSUPPORTED"
    document_field_unresolved = "DOCUMENT_FIELD_UNRESOLVED"
    document_field_ambiguous = "DOCUMENT_FIELD_AMBIGUOUS"
    document_entity_unresolved = "DOCUMENT_ENTITY_UNRESOLVED"
    document_entity_ambiguous = "DOCUMENT_ENTITY_AMBIGUOUS"
    document_value_invalid = "DOCUMENT_VALUE_INVALID"
    document_unit_unresolved = "DOCUMENT_UNIT_UNRESOLVED"
    document_locator_invalid = "DOCUMENT_LOCATOR_INVALID"


class TypedDocumentObservation(BaseModel):
    """One admitted document observation entering the Data Artifact projection.

    This is the single place where raw document scalar semantics (symmetric /
    asymmetric uncertainty, upper/lower limits, explicit nulls) are parsed.
    Downstream projection must never reinterpret the free text.
    """

    model_config = MODEL_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    observation_id: Identifier
    raw_candidate_id: Identifier
    research_input_id: RuntimeIdentifier
    research_input_content_hash: ContentHash
    document_parse_id: RuntimeIdentifier
    persisted_source_snapshot_id: RuntimeIdentifier
    pipeline_source_snapshot: DataSourceSnapshotProjection
    document_locator: DocumentLocator
    parse_quality: DocumentParseQuality
    canonical_field_id: CanonicalFieldId
    crossmatch_logical_key: ContentHash
    raw_value: NonEmptyString | None = None
    raw_text: NonEmptyString | None = None
    parsed_scalar: Decimal | None = None
    source_unit: Identifier
    uncertainty_positive_raw: Decimal | None = None
    uncertainty_negative_raw: Decimal | None = None
    limit_status: LimitStatus = LimitStatus.not_applicable
    null_status: NullReason | None = None
    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.raw_value is None and self.raw_text is None:
            raise ValueError("document observation requires raw value or text")
        if self.null_status is None and self.parsed_scalar is None:
            raise ValueError("accepted document observation requires a parsed scalar")
        if self.null_status is not None and self.parsed_scalar is not None:
            raise ValueError("explicit-null document observation cannot carry a scalar")
        if self.null_status is not None and (
            self.uncertainty_positive_raw is not None
            or self.uncertainty_negative_raw is not None
        ):
            raise ValueError(
                "explicit-null document observation cannot carry uncertainty"
            )
        if not self.document_parse_id or not self.persisted_source_snapshot_id:
            raise ValueError("document observation requires persisted provenance IDs")
        if self.pipeline_source_snapshot.snapshot_id != self.pipeline_snapshot_id:
            raise ValueError(
                "document observation pipeline snapshot projection drifted"
            )
        if self.pipeline_source_snapshot.source_id != (
            f"research_input:{self.research_input_id}"
        ):
            raise ValueError(
                "document observation must bind its own research input source"
            )
        if (
            self.pipeline_source_snapshot.content_hash
            != self.research_input_content_hash
        ):
            raise ValueError(
                "document observation ResearchInput hash disagrees with its snapshot"
            )
        expected_hash = compute_canonical_payload_hash(
            self.model_dump(mode="json", exclude={"content_hash"})
        )
        if self.content_hash != expected_hash:
            raise ValueError(
                "document observation content_hash does not match canonical payload"
            )
        return self

    @property
    def pipeline_snapshot_id(self) -> str:
        return self.pipeline_source_snapshot.snapshot_id


class CrossmatchDataArtifactAuthority(BaseModel):
    """Existing Crossmatch-backed Data Artifact input authority."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["crossmatch"] = "crossmatch"
    left_acquisition: CrossmatchSourceInput
    right_acquisition: CrossmatchSourceInput
    crossmatch_result: CrossmatchResult
    document_observations: tuple[TypedDocumentObservation, ...] = ()


class SourceTableDataArtifactAuthority(BaseModel):
    """One persisted SourceSnapshot plus its admitted SourceTable."""

    model_config = MODEL_CONFIG

    authority_kind: Literal["source_table"] = "source_table"
    source_snapshot: SourceSnapshotRecord
    source_table_admission: SourceTableAdmission

    @model_validator(mode="after")
    def validate_authority(self) -> Self:
        admission = self.source_table_admission
        if (
            str(self.source_snapshot.snapshot_id) != str(admission.source_snapshot_id)
            or self.source_snapshot.source_id != admission.source_id
            or self.source_snapshot.content_hash
            != admission.source_snapshot_content_hash
            or self.source_snapshot.query_hash != admission.query_hash
            or self.source_snapshot.retrieved_at != admission.retrieved_at
        ):
            raise ValueError("SourceTable authority disagrees with its SourceSnapshot")
        return self


DataArtifactInputAuthority = Annotated[
    CrossmatchDataArtifactAuthority | SourceTableDataArtifactAuthority,
    Field(discriminator="authority_kind"),
]


class DataArtifactBuildInput(BaseModel):
    model_config = MODEL_CONFIG

    manifest_pins: ManifestPins
    requested_fields: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    authority: DataArtifactInputAuthority
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
        document_observations = (
            self.authority.document_observations
            if isinstance(self.authority, CrossmatchDataArtifactAuthority)
            else ()
        )
        observation_ids = [item.observation_id for item in document_observations]
        candidate_ids = [item.raw_candidate_id for item in document_observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("document observations must have unique observation_id")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("document observations must have unique raw_candidate_id")
        requested_fields = set(self.requested_fields)
        if any(
            item.canonical_field_id not in requested_fields
            for item in document_observations
        ):
            raise ValueError("document observation field is not requested")
        if isinstance(self.authority, CrossmatchDataArtifactAuthority):
            result = self.authority.crossmatch_result
            record_keys = {
                compute_crossmatch_record_logical_key(record)
                for record in result.records
            }
            if any(
                item.crossmatch_logical_key not in record_keys
                for item in document_observations
            ):
                raise ValueError(
                    "document observation references an unknown Crossmatch row"
                )
        else:
            admission = self.authority.source_table_admission
            if document_observations:
                raise ValueError(
                    "SourceTable authority cannot carry document observations"
                )
            admitted_fields = {
                column.canonical_field_id for column in admission.columns
            }
            if not set(self.requested_fields) <= admitted_fields:
                raise ValueError(
                    "SourceTable requested fields must be admitted canonical fields"
                )
        snapshot_bindings: dict[str, str] = {}
        snapshot_facts: dict[str, DataSourceSnapshotProjection] = {}
        for item in document_observations:
            pipeline_id = item.pipeline_snapshot_id
            persisted_id = str(item.persisted_source_snapshot_id)
            previous = snapshot_bindings.setdefault(pipeline_id, persisted_id)
            if previous != persisted_id:
                raise ValueError(
                    "one pipeline document snapshot must bind exactly one persisted snapshot"
                )
            previous_projection = snapshot_facts.setdefault(
                pipeline_id, item.pipeline_source_snapshot
            )
            if previous_projection != item.pipeline_source_snapshot:
                raise ValueError(
                    "document observations disagree about pipeline snapshot facts"
                )
        pins = self.manifest_pins
        expected_pins = (
            pins.case_manifest_id,
            pins.case_manifest_version,
            pins.case_manifest_content_hash,
            pins.field_manifest_id,
            pins.field_manifest_version,
            pins.field_manifest_content_hash,
        )
        rule_pins = (
            self.mapping_rule_set.case_manifest_id,
            self.mapping_rule_set.case_manifest_version,
            self.mapping_rule_set.case_manifest_content_hash,
            self.mapping_rule_set.field_manifest_id,
            self.mapping_rule_set.field_manifest_version,
            self.mapping_rule_set.field_manifest_content_hash,
        )
        if (
            self.conversion_catalog.field_manifest_id != pins.field_manifest_id
            or self.conversion_catalog.field_manifest_version
            != pins.field_manifest_version
            or self.conversion_catalog.field_manifest_content_hash
            != pins.field_manifest_content_hash
        ):
            raise ValueError("conversion catalog disagrees with Field Manifest pin")
        if rule_pins != expected_pins:
            raise ValueError("Manifest pins disagree across Data Artifact inputs")
        if isinstance(self.authority, SourceTableDataArtifactAuthority):
            pins = self.manifest_pins
            admission = self.authority.source_table_admission
            if admission.source_result_status != "complete":
                raise ValueError("SourceTable Data Artifact requires a complete source")
            if admission.overall_status.value != "pass":
                raise ValueError("SourceTable Data Artifact requires a passing source")
            if admission.manifest_pins != pins:
                raise ValueError("SourceTable admission disagrees with manifest pins")
            if (
                admission.mapping_rule_set_content_hash
                != self.mapping_rule_set.content_hash
                or admission.conversion_catalog_content_hash
                != self.conversion_catalog.content_hash
            ):
                raise ValueError(
                    "SourceTable admission disagrees with execution policies"
                )
            expected = compute_data_artifact_input_hash(self)
            if self.input_hash != expected:
                raise ValueError(f"input_hash does not match build input: {expected}")
            return self
        if not isinstance(self.authority, CrossmatchDataArtifactAuthority):
            raise ValueError("Crossmatch input authority is required for this branch")
        result = self.authority.crossmatch_result
        result_pins = (
            result.case_manifest_id,
            result.case_manifest_version,
            result.case_manifest_content_hash,
            result.field_manifest_id,
            result.field_manifest_version,
            result.field_manifest_content_hash,
        )
        if result_pins != expected_pins or rule_pins != expected_pins:
            raise ValueError("Manifest pins disagree across Data Artifact inputs")
        for side, acquisition, snapshot, source_mode, data_level, completion in (
            (
                CrossmatchSide.left,
                self.authority.left_acquisition,
                result.left_source_snapshot,
                result.left_source_mode,
                result.left_data_level,
                result.left_completion,
            ),
            (
                CrossmatchSide.right,
                self.authority.right_acquisition,
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
                raise ValueError(
                    f"{side.value} acquisition disagrees with CrossmatchResult"
                )
            referenced = {
                (
                    candidate.source_record.row_key,
                    candidate.source_record.record_content_hash,
                )
                for candidate in result.candidates
                if candidate.side is side
            }
            acquired = {
                (record.row_key, record.content_hash) for record in acquisition.records
            }
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

    schema_version: Literal["4.0.0"] = "4.0.0"
    dataset: DatasetArtifactCandidate
    field_dictionary: FieldDictionaryArtifactCandidate
    source_collection: SourceCollectionArtifactCandidate
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_hash(self) -> Self:
        candidates = (self.dataset, self.field_dictionary, self.source_collection)
        common_bindings = {
            (
                candidate.manifest_pins,
                candidate.source_snapshot_ids,
                candidate.authority.model_dump_json(),
                candidate.evidence_ids,
                candidate.mapping_rule_set_id,
                candidate.mapping_rule_set_version,
                candidate.mapping_rule_set_content_hash,
                candidate.conversion_catalog_id,
                candidate.conversion_catalog_version,
                candidate.conversion_catalog_content_hash,
                candidate.producer,
                candidate.input_hash,
                candidate.quality_evaluation_status,
            )
            for candidate in candidates
        }
        if len(common_bindings) != 1 or any(
            candidate.input_hash != self.input_hash for candidate in candidates
        ):
            raise ValueError("build candidates do not share exact common bindings")
        if self.dataset.requested_fields != self.field_dictionary.requested_fields:
            raise ValueError("Dataset and FieldDictionary requested fields drifted")
        if tuple(column.field for column in self.dataset.columns) != (
            self.field_dictionary.field_definitions
        ):
            raise ValueError("Dataset columns and FieldDictionary definitions drifted")
        if self.source_collection.source_value_ids != tuple(
            item.source_value_id for item in self.dataset.source_values
        ):
            raise ValueError("SourceCollection source values disagree with Dataset")
        if isinstance(self.dataset.authority, CrossmatchArtifactAuthority):
            if not isinstance(
                self.source_collection.authority, CrossmatchArtifactAuthority
            ):
                raise ValueError("Dataset and SourceCollection authority kinds drifted")
            dataset_authority = self.dataset.authority
            collection_authority = self.source_collection.authority
            if (
                collection_authority.result_id != dataset_authority.result_id
                or collection_authority.content_hash != dataset_authority.content_hash
            ):
                raise ValueError(
                    "Dataset and SourceCollection crossmatch identity drifted"
                )
            if set(collection_authority.alignment_record_keys) != {
                row.row_authority.logical_key
                for row in self.dataset.rows
                if isinstance(row.row_authority, CrossmatchRowAuthority)
            }:
                raise ValueError(
                    "SourceCollection alignments do not cover Dataset rows"
                )
        else:
            if not isinstance(
                self.source_collection.authority, SourceTableArtifactAuthority
            ):
                raise ValueError("Dataset and SourceCollection authority kinds drifted")
            if (
                self.source_collection.authority.admission_id
                != self.dataset.authority.admission_id
                or self.source_collection.authority.admission_output_hash
                != self.dataset.authority.admission_output_hash
                or self.source_collection.authority.source_id
                != self.dataset.authority.source_id
                or self.source_collection.authority.source_snapshot_id
                != self.dataset.authority.source_snapshot_id
            ):
                raise ValueError(
                    "Dataset and SourceCollection SourceTable identity drifted"
                )
            if any(
                not isinstance(row.row_authority, SourceTableRowAuthority)
                or row.row_authority.admission_id != self.dataset.authority.admission_id
                for row in self.dataset.rows
            ):
                raise ValueError("Dataset rows do not bind the admitted SourceTable")
        collection_records = {
            (
                reference.source_id,
                reference.source_snapshot_id,
                reference.source_snapshot_content_hash,
                reference.query_hash,
                reference.row_key,
                reference.raw_record_content_hash,
            )
            for member in self.source_collection.crossmatch_sources
            for reference in member.raw_record_references
        }
        collection_records.update(
            {
                (
                    reference.source_id,
                    reference.source_snapshot_id,
                    reference.source_snapshot_content_hash,
                    reference.query_hash,
                    reference.row_key,
                    reference.raw_record_content_hash,
                )
                for member in self.source_collection.source_table_sources
                for reference in member.raw_record_references
            }
        )
        dataset_records = {
            (
                value.source_id,
                value.source_snapshot_id,
                value.source_snapshot_content_hash,
                value.query_hash,
                value.origin.raw_record_row_key,  # type: ignore[union-attr]
                value.origin.raw_record_content_hash,  # type: ignore[union-attr]
            )
            for value in self.dataset.source_values
            if isinstance(value.origin, StructuredDatabaseOrigin)
        }
        if not dataset_records <= collection_records:
            raise ValueError("Dataset uses raw records absent from SourceCollection")
        document_members = self.source_collection.supplemental_document_sources
        for value in self.dataset.source_values:
            if not isinstance(value.origin, DocumentResearchInputOrigin):
                continue
            origin = value.origin
            if not any(
                member.research_input_id == origin.research_input_id
                and member.research_input_content_hash
                == origin.research_input_content_hash
                and member.persisted_source_snapshot_id
                == origin.persisted_source_snapshot_id
                and member.pipeline_source_snapshot_id
                == origin.pipeline_source_snapshot_id
                and member.pipeline_source_snapshot_content_hash
                == origin.pipeline_source_snapshot_content_hash
                and member.pipeline_source_snapshot.source_id == value.source_id
                and member.pipeline_source_snapshot.query_hash == value.query_hash
                and origin.document_parse_id in member.document_parse_ids
                and origin.observation_id in member.observation_ids
                for member in document_members
            ):
                raise ValueError(
                    "Dataset document provenance is absent from SourceCollection"
                )
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


def compute_data_artifact_public_payload_hash(value: BaseModel | dict[str, Any]) -> str:
    """Hash the complete public candidate payload, including identity fields."""

    return compute_canonical_payload_hash(_model_or_dict(value))


def compute_data_artifact_lineage_hash(value: BaseModel | dict[str, Any]) -> str:
    return compute_dataset_lineage_hash(value)


def compute_data_artifact_canonical_content_hash(
    value: DatasetArtifactCandidate | dict[str, Any],
) -> str:
    return compute_dataset_canonical_content_hash(value)


def compute_data_artifact_input_hash(
    value: DataArtifactBuildInput | dict[str, Any],
) -> str:
    payload = _model_or_dict(value)
    payload.pop("input_hash", None)
    if "requested_fields" in payload:
        payload["requested_fields"] = sorted(payload["requested_fields"])
    return compute_canonical_payload_hash(payload)


def compute_data_artifact_context_hash(
    value: DataArtifactBuildInput,
    *,
    input_json: str | None = None,
) -> str:
    """Commit to the canonical input and all frozen policy identities."""

    return compute_canonical_payload_hash(
        {
            "input_json": input_json or value.model_dump_json(),
            "manifest_pins": value.manifest_pins.model_dump(mode="json"),
            "mapping_rule_set": {
                "id": value.mapping_rule_set.rule_set_id,
                "version": value.mapping_rule_set.version,
                "content_hash": value.mapping_rule_set.content_hash,
            },
            "conversion_catalog": {
                "id": value.conversion_catalog.catalog_id,
                "version": value.conversion_catalog.version,
                "content_hash": value.conversion_catalog.content_hash,
            },
            "authority": value.authority.model_dump(mode="json"),
        }
    )


def compute_data_artifact_candidate_id(
    kind: str,
    identity_hash: str,
    *,
    schema_version: str = "4.0.0",
) -> str:
    return compute_dataset_candidate_id(kind, schema_version, identity_hash)


def _model_or_dict(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    payload = (
        deepcopy(value.model_dump(mode="json", exclude_none=True))
        if isinstance(value, BaseModel)
        else deepcopy(value)
    )
    # ``exclude_none`` does not recurse into free-form dictionaries such as a
    # source record payload.  Apply the canonical null-elision rule to both
    # model and dict inputs so hashing is representation-independent.
    return _drop_none(payload)


def _drop_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _drop_none(item) for key, item in value.items() if item is not None
        }
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
    canonical = getattr(value, "canonical_content_hash", None)
    identity_hash = canonical or getattr(value, "output_hash")
    expected = compute_data_artifact_candidate_id(
        getattr(value, "kind"),
        identity_hash,
        schema_version=getattr(value, "schema_version", "4.0.0"),
    )
    if getattr(value, "candidate_id") != expected:
        raise ValueError(f"candidate_id does not match canonical identity: {expected}")


def _require_unique(values: tuple[BaseModel, ...], attribute: str, label: str) -> None:
    identities = [getattr(value, attribute) for value in values]
    if len(identities) != len(set(identities)):
        raise ValueError(f"candidate contains duplicate {label}")


__all__ = [
    "AlignmentStatus",
    "CanonicalEntityIdentity",
    "CanonicalEntityIdentityValue",
    "CanonicalRowIdentity",
    "CanonicalValueOutcome",
    "DataArtifactBuildInput",
    "DataArtifactBuildResult",
    "DataArtifactAdmissionSnapshot",
    "DataArtifactCapacity",
    "DecimalCapacity",
    "DataArtifactErrorCode",
    "DatabaseCellLocator",
    "DataSourceSnapshotProjection",
    "DocumentObservationAdmissionCode",
    "DocumentObservationAdmissionStatus",
    "DocumentObservationLocator",
    "DocumentResearchInputOrigin",
    "DocumentSourceCollectionMember",
    "EntityProjectionPolicy",
    "EntityProjectionRule",
    "DatasetArtifactCandidate",
    "DeclaredNullValue",
    "FieldDictionaryArtifactCandidate",
    "LimitStatus",
    "LimitValue",
    "MappedCanonicalValue",
    "MappingRuleSet",
    "RawSourceRecordReference",
    "SourceCollectionArtifactCandidate",
    "SourceTableArtifactAuthority",
    "SourceTableCanonicalRowIdentity",
    "SourceTableDataArtifactAuthority",
    "SourceTableRowAuthority",
    "SourceTableSourceCollectionMember",
    "SourceTableTransformationAuthority",
    "SourceValueCandidate",
    "SourceValueOrigin",
    "StructuredDatabaseOrigin",
    "StructuredSourceCollectionMember",
    "TypedDocumentObservation",
    "UnitConversionCatalog",
    "UnitConversionImplementation",
    "UnresolvedCanonicalValue",
    "compute_data_artifact_content_hash",
    "compute_data_artifact_context_hash",
    "compute_data_artifact_canonical_content_hash",
    "compute_data_artifact_candidate_id",
    "compute_data_artifact_input_hash",
    "compute_data_artifact_lineage_hash",
    "compute_data_artifact_output_hash",
    "compute_data_artifact_public_payload_hash",
]
