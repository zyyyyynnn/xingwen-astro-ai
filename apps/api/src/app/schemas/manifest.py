"""Versioned Case and Field Manifest schemas for the C-01 data contract.

This module deliberately contains only declarative metadata, stable hashing,
and static validation.  Fetching, matching, conversion, and quality evaluation
belong to later C-module issues.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
SEMANTIC_VERSION_PATTERN = r"^[1-9]\d*\.\d+\.\d+$"
CONTENT_HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
IDENTIFIER_PATTERN = r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$"
FIELD_ID_PATTERN = r"^(?:planet|star|system)\.[a-z][a-z0-9_]*$"

NonEmptyString = Annotated[str, Field(min_length=1)]
SemanticVersion = Annotated[str, Field(pattern=SEMANTIC_VERSION_PATTERN)]
ContentHash = Annotated[str, Field(pattern=CONTENT_HASH_PATTERN)]
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]
CanonicalFieldId = Annotated[str, Field(pattern=FIELD_ID_PATTERN)]


class DataType(StrEnum):
    """Canonical scalar types supported by the frozen case."""

    string = "string"
    integer = "integer"
    number = "number"


class ObjectType(StrEnum):
    """Objects represented by the exoplanet/host-star case."""

    planet = "planet"
    star = "star"
    system = "system"


class QuantityKind(StrEnum):
    """Physical dimensions used for static compatibility checks only."""

    none = "none"
    angle = "angle"
    time = "time"
    length = "length"
    mass = "mass"
    temperature = "temperature"
    logarithmic_abundance = "logarithmic_abundance"


class NullReason(StrEnum):
    """Controlled reasons for a nullable scientific value."""

    not_in_source = "not_in_source"
    not_measured = "not_measured"
    not_applicable = "not_applicable"
    unresolved_conflict = "unresolved_conflict"
    below_detection_limit = "below_detection_limit"


class UncertaintyMode(StrEnum):
    """How source uncertainty columns are declared, not evaluated."""

    not_applicable = "not_applicable"
    asymmetric_source_errors = "asymmetric_source_errors"


class ConflictResolutionStrategy(StrEnum):
    """The only C-01 selection declaration approved for this case."""

    prefer_source_priority_preserve_all = "prefer_source_priority_preserve_all"


class QualityMetricInput(StrEnum):
    """Future quality dimensions to which a field contributes."""

    completeness = "completeness"
    missingness = "missingness"
    conflict = "conflict"
    unit_consistency = "unit_consistency"
    evidence_coverage = "evidence_coverage"
    crossmatch_coverage = "crossmatch_coverage"


class MaintainerDefinition(BaseModel):
    """Ownership metadata for a manifest release."""

    model_config = MODEL_CONFIG

    module: Literal["C"]
    role: Literal["data_pipeline"]


class SourceColumnContractReference(BaseModel):
    """Immutable reference to the evidence-backed source-column adjudication."""

    model_config = MODEL_CONFIG

    snapshot_id: Identifier
    snapshot_version: SemanticVersion
    path: NonEmptyString
    content_hash: ContentHash


class SourceDefinition(BaseModel):
    """An approved source table declaration; it performs no I/O."""

    model_config = MODEL_CONFIG

    source_id: Identifier
    provider_source_id: Identifier
    provider: NonEmptyString
    name: NonEmptyString
    source_table: NonEmptyString
    documentation_url: HttpUrl
    declaration_mode: Literal["metadata_only"] = "metadata_only"
    approved_columns: tuple[NonEmptyString, ...] = Field(min_length=1)
    row_key_fields: tuple[NonEmptyString, ...] = Field(min_length=1)
    reference_columns: tuple[NonEmptyString, ...]
    provenance_columns: tuple[NonEmptyString, ...]
    column_contract: SourceColumnContractReference

    @model_validator(mode="after")
    def validate_source_column_contract(self) -> Self:
        expected_source_id = f"{self.provider_source_id}.{self.source_table}"
        if self.source_id != expected_source_id:
            raise ValueError(
                f"table source id {self.source_id} does not match provider/table "
                f"mapping {expected_source_id}"
            )

        _require_unique(self.approved_columns, "approved source column")
        _require_unique(self.row_key_fields, "source row key field")
        _require_unique(self.reference_columns, "source reference column")
        _require_unique(self.provenance_columns, "source provenance column")

        approved = set(self.approved_columns)
        role_columns = {
            "row key": set(self.row_key_fields),
            "reference": set(self.reference_columns),
            "provenance": set(self.provenance_columns),
        }
        for role, columns in role_columns.items():
            unknown = sorted(columns - approved)
            if unknown:
                raise ValueError(
                    f"{role} columns are not approved for {self.source_id}: {unknown}"
                )
        return self


class UnitDefinition(BaseModel):
    """A canonical or source unit registered by identifier."""

    model_config = MODEL_CONFIG

    unit_id: Identifier
    label: NonEmptyString
    symbol: str
    quantity_kind: QuantityKind


class UnitConversionRule(BaseModel):
    """A versioned conversion declaration without conversion code."""

    model_config = MODEL_CONFIG

    rule_id: Identifier
    rule_version: SemanticVersion
    source_unit: Identifier | None = None
    target_unit: Identifier | None = None
    declaration_mode: Literal["declaration_only"] = "declaration_only"

    @model_validator(mode="after")
    def require_a_complete_specific_pair(self) -> Self:
        if (self.source_unit is None) != (self.target_unit is None):
            raise ValueError("conversion rule unit pair must be both present or both absent")
        return self


class EvidenceLocatorRule(BaseModel):
    """Required provenance coordinates for a future source value."""

    model_config = MODEL_CONFIG

    rule_id: Identifier
    rule_version: SemanticVersion
    locator_type: Literal["database_cell"]
    required_components: tuple[NonEmptyString, ...] = Field(min_length=1)
    source_reference_when_available: bool = True

    @model_validator(mode="after")
    def reject_duplicate_components(self) -> Self:
        if len(self.required_components) != len(set(self.required_components)):
            raise ValueError("duplicate evidence locator component")
        return self


class NullPolicy(BaseModel):
    """Nullability semantics for one canonical field."""

    model_config = MODEL_CONFIG

    reason_required_when_null: bool
    allowed_reasons: tuple[NullReason, ...]


class LimitFlagMapping(BaseModel):
    """Source flag meanings for a bounded value."""

    model_config = MODEL_CONFIG

    measured: int = 0
    lower_limit: int = 1
    upper_limit: int = -1

    @model_validator(mode="after")
    def require_distinct_flags(self) -> Self:
        values = (self.measured, self.lower_limit, self.upper_limit)
        if len(set(values)) != len(values):
            raise ValueError("limit flag values must be distinct")
        return self


class LimitPolicy(BaseModel):
    """Whether the field can carry upper or lower limit semantics."""

    model_config = MODEL_CONFIG

    rule_version: SemanticVersion
    lower_limit_supported: bool
    upper_limit_supported: bool


class UncertaintyPolicy(BaseModel):
    """Versioned declaration for preserving source uncertainties."""

    model_config = MODEL_CONFIG

    rule_version: SemanticVersion
    mode: UncertaintyMode
    preserve_asymmetric_errors: bool

    @model_validator(mode="after")
    def align_mode_and_preservation(self) -> Self:
        expected = self.mode == UncertaintyMode.asymmetric_source_errors
        if self.preserve_asymmetric_errors is not expected:
            raise ValueError("uncertainty mode and preservation flag disagree")
        return self


class SourceAlias(BaseModel):
    """A source column mapped to one canonical field."""

    model_config = MODEL_CONFIG

    source_id: Identifier
    source_table: NonEmptyString
    raw_field: NonEmptyString
    source_unit: Identifier
    conversion_rule_id: Identifier
    priority: Annotated[int, Field(ge=1)]
    row_key_fields: tuple[NonEmptyString, ...] = Field(min_length=1)
    positive_error_field: NonEmptyString | None = None
    negative_error_field: NonEmptyString | None = None
    limit_field: NonEmptyString | None = None
    limit_flags: LimitFlagMapping | None = None
    reference_field: NonEmptyString | None = None
    provenance_field: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_companion_columns(self) -> Self:
        if (self.positive_error_field is None) != (self.negative_error_field is None):
            raise ValueError("positive and negative error fields must be declared together")
        if (self.limit_field is None) != (self.limit_flags is None):
            raise ValueError("limit field and limit flag mapping must be declared together")
        if len(self.row_key_fields) != len(set(self.row_key_fields)):
            raise ValueError("duplicate row key field")
        return self

    def declared_source_columns(self) -> tuple[str, ...]:
        """Return every raw, row-key, and companion source column."""

        optional_columns = (
            self.positive_error_field,
            self.negative_error_field,
            self.limit_field,
            self.reference_field,
            self.provenance_field,
        )
        return (
            self.raw_field,
            *self.row_key_fields,
            *(column for column in optional_columns if column is not None),
        )


class FieldDefinition(BaseModel):
    """The complete C-01 contract for one canonical field."""

    model_config = MODEL_CONFIG

    field_id: CanonicalFieldId
    meaning_zh: NonEmptyString
    label_en: NonEmptyString
    description: NonEmptyString
    object_type: ObjectType
    data_type: DataType
    canonical_unit: Identifier
    source_aliases: tuple[SourceAlias, ...] = Field(min_length=1)
    source_priority: tuple[Identifier, ...] = Field(min_length=1)
    conflict_resolution_strategy: ConflictResolutionStrategy
    conflict_resolution_rule_version: SemanticVersion
    required: bool
    nullable: bool
    null_policy: NullPolicy
    limit_policy: LimitPolicy
    uncertainty_policy: UncertaintyPolicy
    object_identity_key: bool
    crossmatch_key: bool
    crossmatch_rule_version: SemanticVersion | None = None
    evidence_locator_rule_id: Identifier
    transformation_rule_version: SemanticVersion
    quality_metric_inputs: tuple[QualityMetricInput, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_field_policy_consistency(self) -> Self:
        if len(self.source_priority) != len(set(self.source_priority)):
            raise ValueError(f"duplicate source priority for {self.field_id}")
        if len(self.quality_metric_inputs) != len(set(self.quality_metric_inputs)):
            raise ValueError(f"duplicate quality metric input for {self.field_id}")

        if self.nullable:
            if not self.null_policy.reason_required_when_null:
                raise ValueError(f"nullable field {self.field_id} must require a null reason")
            if not self.null_policy.allowed_reasons:
                raise ValueError(f"nullable field {self.field_id} must allow a null reason")
        elif self.null_policy.reason_required_when_null or self.null_policy.allowed_reasons:
            raise ValueError(f"non-nullable field {self.field_id} cannot define null reasons")

        if self.crossmatch_key != (self.crossmatch_rule_version is not None):
            raise ValueError(
                f"crossmatch field {self.field_id} must declare exactly one rule version"
            )

        aliases_with_limits = [alias for alias in self.source_aliases if alias.limit_field]
        supports_limits = (
            self.limit_policy.lower_limit_supported
            or self.limit_policy.upper_limit_supported
        )
        if supports_limits != bool(aliases_with_limits):
            raise ValueError(f"limit policy and source aliases disagree for {self.field_id}")

        aliases_with_errors = [
            alias for alias in self.source_aliases if alias.positive_error_field
        ]
        if self.data_type not in (DataType.integer, DataType.number) and (
            aliases_with_errors or supports_limits
        ):
            raise ValueError(
                f"non-numeric field {self.field_id} cannot declare measurement "
                "uncertainty or limits"
            )
        has_source_errors = (
            self.uncertainty_policy.mode == UncertaintyMode.asymmetric_source_errors
        )
        if has_source_errors != bool(aliases_with_errors):
            raise ValueError(f"uncertainty policy and source aliases disagree for {self.field_id}")

        return self

    def source_aliases_for(self, source_id: str) -> tuple[SourceAlias, ...]:
        """Return aliases belonging to one declared source."""

        return tuple(alias for alias in self.source_aliases if alias.source_id == source_id)


class FieldManifestPayload(BaseModel):
    """Canonical payload for a versioned field fact source."""

    model_config = MODEL_CONFIG

    manifest_id: Identifier
    case_id: Identifier
    name: NonEmptyString
    description: NonEmptyString
    schema_version: SemanticVersion
    manifest_version: SemanticVersion
    created_at: date
    maintained_by: MaintainerDefinition
    sources: tuple[SourceDefinition, ...] = Field(min_length=1)
    units: tuple[UnitDefinition, ...] = Field(min_length=1)
    conversion_rules: tuple[UnitConversionRule, ...] = Field(min_length=1)
    evidence_locator_rules: tuple[EvidenceLocatorRule, ...] = Field(min_length=1)
    fields: tuple[FieldDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry_references(self) -> Self:
        source_by_id = _unique_registry(self.sources, "source_id", "source id")
        source_table_keys: set[tuple[str, str]] = set()
        for source in self.sources:
            source_table_key = (source.provider, source.source_table)
            if source_table_key in source_table_keys:
                raise ValueError(f"duplicate source table: {source_table_key}")
            source_table_keys.add(source_table_key)

        unit_by_id = _unique_registry(self.units, "unit_id", "unit id")
        conversion_by_id = _unique_registry(
            self.conversion_rules, "rule_id", "conversion rule id"
        )
        evidence_by_id = _unique_registry(
            self.evidence_locator_rules, "rule_id", "evidence locator rule id"
        )
        field_by_id = _unique_registry(self.fields, "field_id", "canonical field id")

        alias_owners: dict[tuple[str, str, str], str] = {}
        used_reference_columns = {source.source_id: set() for source in self.sources}
        used_provenance_columns = {source.source_id: set() for source in self.sources}
        for field in self.fields:
            canonical_unit = unit_by_id.get(field.canonical_unit)
            if canonical_unit is None:
                raise ValueError(
                    f"unregistered canonical unit {field.canonical_unit} for {field.field_id}"
                )
            if field.evidence_locator_rule_id not in evidence_by_id:
                raise ValueError(
                    f"unregistered evidence locator rule "
                    f"{field.evidence_locator_rule_id} for {field.field_id}"
                )

            alias_source_ids = {alias.source_id for alias in field.source_aliases}
            if set(field.source_priority) != alias_source_ids:
                raise ValueError(
                    f"source priority must list every and only aliased source for {field.field_id}"
                )

            priorities_by_source: dict[str, set[int]] = {}
            for alias in field.source_aliases:
                if alias.raw_field in field_by_id:
                    raise ValueError(
                        f"source alias must not use canonical field id: {alias.raw_field}"
                    )
                source = source_by_id.get(alias.source_id)
                if source is None:
                    raise ValueError(
                        f"unregistered source {alias.source_id} for {field.field_id}"
                    )
                if alias.source_table != source.source_table:
                    raise ValueError(
                        f"source table mismatch for {alias.source_id} on {field.field_id}"
                    )

                unapproved_columns = sorted(
                    set(alias.declared_source_columns())
                    - set(source.approved_columns)
                )
                if unapproved_columns:
                    raise ValueError(
                        f"not an approved source column for {alias.source_id}: "
                        f"{unapproved_columns}"
                    )
                if alias.row_key_fields != source.row_key_fields:
                    raise ValueError(
                        f"row key fields do not match {alias.source_id}: "
                        f"expected {source.row_key_fields}"
                    )
                if (
                    alias.reference_field is not None
                    and alias.reference_field not in source.reference_columns
                ):
                    raise ValueError(
                        f"not an approved reference column for {alias.source_id}: "
                        f"{alias.reference_field}"
                    )
                if (
                    alias.provenance_field is not None
                    and alias.provenance_field not in source.provenance_columns
                ):
                    raise ValueError(
                        f"not an approved provenance column for {alias.source_id}: "
                        f"{alias.provenance_field}"
                    )
                if alias.reference_field is not None:
                    used_reference_columns[alias.source_id].add(alias.reference_field)
                if alias.provenance_field is not None:
                    used_provenance_columns[alias.source_id].add(alias.provenance_field)

                alias_key = (alias.source_id, alias.source_table, alias.raw_field)
                previous_owner = alias_owners.get(alias_key)
                if previous_owner is not None:
                    raise ValueError(
                        f"duplicate source alias {alias_key}: "
                        f"{previous_owner} and {field.field_id}"
                    )
                alias_owners[alias_key] = field.field_id

                source_priorities = priorities_by_source.setdefault(alias.source_id, set())
                if alias.priority in source_priorities:
                    raise ValueError(
                        f"duplicate alias priority {alias.priority} for "
                        f"{field.field_id} in {alias.source_id}"
                    )
                source_priorities.add(alias.priority)

                source_unit = unit_by_id.get(alias.source_unit)
                if source_unit is None:
                    raise ValueError(
                        f"unregistered source unit {alias.source_unit} for {field.field_id}"
                    )
                if source_unit.quantity_kind != canonical_unit.quantity_kind:
                    raise ValueError(
                        f"incompatible unit quantity kinds for {field.field_id}: "
                        f"{alias.source_unit} -> {field.canonical_unit}"
                    )

                conversion = conversion_by_id.get(alias.conversion_rule_id)
                if conversion is None:
                    raise ValueError(
                        f"unregistered conversion rule {alias.conversion_rule_id} "
                        f"for {field.field_id}"
                    )
                _validate_conversion_declaration(
                    conversion=conversion,
                    source_unit=alias.source_unit,
                    target_unit=field.canonical_unit,
                    field_id=field.field_id,
                )

        for source in self.sources:
            if used_reference_columns[source.source_id] != set(
                source.reference_columns
            ):
                raise ValueError(
                    f"reference column declarations disagree for {source.source_id}"
                )
            if used_provenance_columns[source.source_id] != set(
                source.provenance_columns
            ):
                raise ValueError(
                    f"provenance column declarations disagree for {source.source_id}"
                )

        if not field_by_id:
            raise ValueError("field manifest must contain at least one field")
        return self

    def field_by_id(self, field_id: str) -> FieldDefinition:
        """Return a canonical field definition or raise a useful lookup error."""

        for field in self.fields:
            if field.field_id == field_id:
                return field
        raise KeyError(field_id)


class FieldManifest(FieldManifestPayload):
    """Published Field Manifest with a verified canonical content hash."""

    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        _validate_content_hash(self)
        return self


class ManifestReference(BaseModel):
    """Immutable reference from a Case Manifest to a Field Manifest."""

    model_config = MODEL_CONFIG

    manifest_id: Identifier
    manifest_version: SemanticVersion
    content_hash: ContentHash


class TargetObjectDefinition(BaseModel):
    """Identity and declared crossmatch inputs for a case object."""

    model_config = MODEL_CONFIG

    object_type: ObjectType
    role: NonEmptyString
    identity_fields: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    crossmatch_fields: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    evidence_locator_rule_id: Identifier

    @model_validator(mode="after")
    def reject_duplicate_field_references(self) -> Self:
        if len(self.identity_fields) != len(set(self.identity_fields)):
            raise ValueError(f"duplicate identity field for {self.object_type}")
        if len(self.crossmatch_fields) != len(set(self.crossmatch_fields)):
            raise ValueError(f"duplicate crossmatch field for {self.object_type}")
        return self


class CaseManifestPayload(BaseModel):
    """Canonical payload for the fixed exoplanet/host-star research case."""

    model_config = MODEL_CONFIG

    case_id: Identifier
    name: NonEmptyString
    description: NonEmptyString
    schema_version: SemanticVersion
    manifest_version: SemanticVersion
    created_at: date
    maintained_by: MaintainerDefinition
    target_objects: tuple[TargetObjectDefinition, ...] = Field(min_length=1)
    default_requested_fields: tuple[CanonicalFieldId, ...] = Field(min_length=1)
    allowed_source_ids: tuple[Identifier, ...] = Field(min_length=1)
    field_manifest: ManifestReference
    minimum_evidence_locator_components: tuple[NonEmptyString, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_case_uniqueness(self) -> Self:
        object_types = [target.object_type for target in self.target_objects]
        if len(object_types) != len(set(object_types)):
            raise ValueError("duplicate target object type")
        _require_unique(self.default_requested_fields, "default requested field")
        _require_unique(self.allowed_source_ids, "allowed source id")
        _require_unique(
            self.minimum_evidence_locator_components,
            "minimum evidence locator component",
        )
        return self


class CaseManifest(CaseManifestPayload):
    """Published Case Manifest with a verified canonical content hash."""

    content_hash: ContentHash

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        _validate_content_hash(self)
        return self


class ManifestBundle(BaseModel):
    """Cross-file validation and canonical requested-field lookup."""

    model_config = MODEL_CONFIG

    case_manifest: CaseManifest
    field_manifest: FieldManifest

    @model_validator(mode="after")
    def validate_cross_manifest_references(self) -> Self:
        case = self.case_manifest
        fields = self.field_manifest
        reference = case.field_manifest

        if case.case_id != fields.case_id:
            raise ValueError("case and field manifest case_id values do not match")
        if reference.manifest_id != fields.manifest_id:
            raise ValueError("field manifest id does not match the case reference")
        if reference.manifest_version != fields.manifest_version:
            raise ValueError("field manifest version does not match the case reference")
        if reference.content_hash != fields.content_hash:
            raise ValueError("field manifest hash does not match the case reference")

        source_by_id = {source.source_id: source for source in fields.sources}
        provider_source_ids = {
            source.provider_source_id for source in fields.sources
        }
        unknown_providers = set(case.allowed_source_ids) - provider_source_ids
        if unknown_providers:
            raise ValueError(
                "case references unsupported provider sources: "
                f"{sorted(unknown_providers)}"
            )

        used_source_ids = {
            alias.source_id
            for field in fields.fields
            for alias in field.source_aliases
        }
        unauthorized_source_ids = {
            source_id
            for source_id in used_source_ids
            if source_by_id[source_id].provider_source_id
            not in case.allowed_source_ids
        }
        if unauthorized_source_ids:
            raise ValueError(
                "field aliases use source ids not allowed by the case: "
                f"{sorted(unauthorized_source_ids)}"
            )

        field_by_id = {field.field_id: field for field in fields.fields}
        self.validate_requested_fields(case.default_requested_fields)
        evidence_rule_ids = {
            rule.rule_id for rule in fields.evidence_locator_rules
        }
        evidence_rule_by_id = {
            rule.rule_id: rule for rule in fields.evidence_locator_rules
        }

        for target in case.target_objects:
            if target.evidence_locator_rule_id not in evidence_rule_ids:
                raise ValueError(
                    f"target {target.object_type} references an unknown evidence rule"
                )
            for field_id in target.identity_fields:
                field = field_by_id.get(field_id)
                if field is None or not field.object_identity_key:
                    raise ValueError(
                        f"target identity field is not declared as an identity key: {field_id}"
                    )
            for field_id in target.crossmatch_fields:
                field = field_by_id.get(field_id)
                if field is None or not field.crossmatch_key:
                    raise ValueError(
                        f"target crossmatch field is not declared as a crossmatch key: {field_id}"
                    )

            rule = evidence_rule_by_id[target.evidence_locator_rule_id]
            missing_components = set(case.minimum_evidence_locator_components) - set(
                rule.required_components
            )
            if missing_components:
                raise ValueError(
                    f"evidence rule omits required components: {sorted(missing_components)}"
                )

        return self

    def resolve_source_scope(
        self,
        provider_source_ids: Sequence[str],
    ) -> tuple[str, ...]:
        """Resolve API provider-level source scope to existing table source ids."""

        values = tuple(provider_source_ids)
        if not values:
            raise ValueError("source_scope must contain at least one provider source")
        if len(values) != len(set(values)):
            raise ValueError("source_scope must not contain duplicate provider sources")

        unsupported = sorted(set(values) - set(self.case_manifest.allowed_source_ids))
        if unsupported:
            raise ValueError(f"unsupported provider source(s): {unsupported}")

        selected = set(values)
        return tuple(
            source.source_id
            for source in self.field_manifest.sources
            if source.provider_source_id in selected
        )

    def validate_requested_fields(self, requested_fields: Sequence[str]) -> tuple[str, ...]:
        """Validate ResearchContract.requested_fields against canonical ids."""

        values = tuple(requested_fields)
        if not values:
            raise ValueError("requested_fields must contain at least one field")
        if len(values) != len(set(values)):
            raise ValueError("requested_fields must not contain duplicates")

        supported = {field.field_id for field in self.field_manifest.fields}
        unsupported = sorted(set(values) - supported)
        if unsupported:
            raise ValueError(f"unsupported requested field(s): {unsupported}")
        return values


def compute_content_hash(value: BaseModel | Mapping[str, Any]) -> str:
    """Compute the C-01 canonical SHA-256 hash, excluding ``content_hash``."""

    if isinstance(value, BaseModel):
        raw_payload = value.model_dump(mode="json", exclude={"content_hash"})
    else:
        raw_payload = dict(value)
        raw_payload.pop("content_hash", None)

    if isinstance(value, FieldManifestPayload) or "fields" in raw_payload:
        payload_model = FieldManifestPayload.model_validate(raw_payload)
    elif isinstance(value, CaseManifestPayload) or "target_objects" in raw_payload:
        payload_model = CaseManifestPayload.model_validate(raw_payload)
    else:
        raise TypeError("content hash input must be a Case or Field Manifest payload")

    payload = payload_model.model_dump(mode="json", exclude_none=True)

    canonical_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical_json.encode('utf-8')).hexdigest()}"


def load_manifest_bundle(
    case_manifest_path: str | Path,
    field_manifest_path: str | Path,
) -> ManifestBundle:
    """Load and fully validate one pinned Case/Field Manifest pair."""

    field_manifest = FieldManifest.model_validate_json(
        Path(field_manifest_path).read_text(encoding="utf-8")
    )
    case_manifest = CaseManifest.model_validate_json(
        Path(case_manifest_path).read_text(encoding="utf-8")
    )
    return ManifestBundle(
        case_manifest=case_manifest,
        field_manifest=field_manifest,
    )


def _unique_registry(
    values: Sequence[BaseModel],
    attribute: str,
    label: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        key = str(getattr(value, attribute))
        if key in result:
            raise ValueError(f"duplicate {label}: {key}")
        result[key] = value
    return result


def _require_unique(values: Sequence[Any], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {label}")


def _validate_conversion_declaration(
    *,
    conversion: UnitConversionRule,
    source_unit: str,
    target_unit: str,
    field_id: str,
) -> None:
    if conversion.source_unit is None and conversion.target_unit is None:
        if source_unit != target_unit:
            raise ValueError(
                f"identity conversion cannot map {source_unit} to {target_unit} "
                f"for {field_id}"
            )
        return
    if (conversion.source_unit, conversion.target_unit) != (source_unit, target_unit):
        raise ValueError(
            f"conversion rule {conversion.rule_id} does not declare "
            f"{source_unit} -> {target_unit} for {field_id}"
        )


def _validate_content_hash(manifest: BaseModel) -> None:
    expected = compute_content_hash(manifest)
    actual = str(getattr(manifest, "content_hash"))
    if actual != expected:
        raise ValueError(
            f"content_hash does not match canonical content: expected {expected}"
        )
