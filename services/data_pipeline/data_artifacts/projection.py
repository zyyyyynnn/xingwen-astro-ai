"""Single Data Artifact domain projection derived from canonical frozen inputs.

The projection is the only owner of scientific derivation. Candidate assembly
serializes it, while independent admission derives a fresh projection and
compares the complete public domain surface before a publication seal exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConflictGroup,
    CrossmatchRecord,
    CrossmatchEvidence,
    EntityCandidate,
    UnpairedRecord,
    compute_crossmatch_content_hash,
)
from app.schemas.data_artifact_identity import derive_canonical_row_identity
from app.schemas.data_artifacts import (
    AlignmentStatus,
    DataArtifactBuildInput,
    DataArtifactErrorCode,
    DataArtifactProducer,
    DatasetRow,
    DeclaredNullValue,
    FieldConflictRecord,
    FieldSelectionRecord,
    LimitStatus,
    LimitValue,
    MappedCanonicalValue,
    RawSourceRecordReference,
    SelectionStatus,
    SourceCellLocator,
    SourceCollectionMember,
    SourceValueCandidate,
    TransformationEvidence,
    UncertaintyStatus,
    UncertaintyValue,
    UnresolvedCanonicalValue,
    compute_data_artifact_content_hash,
    compute_data_artifact_input_hash,
    compute_raw_record_reference_registry_hash,
)
from app.schemas.manifest import DataType, FieldDefinition, NullReason, QuantityKind
from app.schemas.source_acquisition import (
    RawDataSourceRecord,
    compute_raw_data_record_hash,
)
from services.data_pipeline.crossmatch.policy import (
    load_crossmatch_rule_set,
    load_crossmatch_source_policy,
    load_entity_alias_catalog,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from .conversion import convert_decimal_value, decimal_from_source, serialize_decimal
from .errors import DataArtifactError
from .policy import load_mapping_rule_set, load_unit_conversion_catalog


@dataclass(frozen=True, slots=True)
class DataArtifactDomainProjection:
    """Complete process-local expectation for all three Data Artifact candidates."""

    input_value: DataArtifactBuildInput
    fields: tuple[FieldDefinition, ...]
    rows: tuple[DatasetRow, ...]
    source_values: tuple[SourceValueCandidate, ...]
    transformation_evidence: tuple[TransformationEvidence, ...]
    selections: tuple[FieldSelectionRecord, ...]
    conflicts: tuple[FieldConflictRecord, ...]
    source_members: tuple[SourceCollectionMember, ...]
    producer: DataArtifactProducer
    source_snapshot_ids: tuple[str, ...]
    crossmatch_evidence: tuple[CrossmatchEvidence, ...]
    crossmatch_evidence_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    alignment_record_keys: tuple[str, ...]
    conflict_record_keys: tuple[str, ...]
    review_required_record_keys: tuple[str, ...]
    inconclusive_record_keys: tuple[str, ...]
    quality_metric_input_declarations: tuple[str, ...]


def _stable_id(prefix: str, payload: object) -> str:
    digest = compute_canonical_payload_hash(payload).removeprefix("sha256:")
    return f"{prefix}.{digest[:24]}"


def _hashed(model_type, payload: dict[str, Any]):
    payload["content_hash"] = compute_data_artifact_content_hash(payload)
    return model_type.model_validate(payload)


def _quantity_kind(field: FieldDefinition, bundle) -> str:
    units = {unit.unit_id: unit for unit in bundle.field_manifest.units}
    unit = units.get(field.canonical_unit)
    return (unit.quantity_kind if unit is not None else QuantityKind.none).value


def validate_policy_bindings(input_value: DataArtifactBuildInput):
    bundle = load_frozen_manifest_bundle()
    case = bundle.case_manifest
    manifest = bundle.field_manifest
    pins = input_value.manifest_pins
    actual = (
        case.case_id,
        case.manifest_version,
        case.content_hash,
        manifest.manifest_id,
        manifest.manifest_version,
        manifest.content_hash,
    )
    expected = (
        pins.case_manifest_id,
        pins.case_manifest_version,
        pins.case_manifest_content_hash,
        pins.field_manifest_id,
        pins.field_manifest_version,
        pins.field_manifest_content_hash,
    )
    if actual != expected:
        raise DataArtifactError(
            DataArtifactErrorCode.manifest_pin_mismatch,
            "frozen manifests disagree with the Data Artifact input pins",
        )
    if input_value.mapping_rule_set != load_mapping_rule_set():
        raise DataArtifactError(
            DataArtifactErrorCode.mapping_rule_mismatch,
            "caller MappingRuleSet is not the repository-frozen execution policy",
        )
    if input_value.conversion_catalog != load_unit_conversion_catalog():
        raise DataArtifactError(
            DataArtifactErrorCode.conversion_catalog_mismatch,
            "caller UnitConversionCatalog is not the repository-frozen execution policy",
        )

    fields_by_id = {field.field_id: field for field in manifest.fields}
    requested = set(input_value.requested_fields)
    unknown = requested - fields_by_id.keys()
    if unknown:
        raise DataArtifactError(
            DataArtifactErrorCode.unsupported_requested_field,
            f"requested fields are not canonical Field Manifest IDs: {sorted(unknown)}",
        )
    capacity = input_value.mapping_rule_set.capacity
    if len(requested) > capacity.max_requested_fields:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded, "field capacity exceeded"
        )
    if len(input_value.crossmatch_result.records) > capacity.max_rows:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded, "row capacity exceeded"
        )
    if (
        len(requested) * len(input_value.crossmatch_result.records)
        > capacity.max_total_cell_outcomes
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded, "cell capacity exceeded"
        )
    if input_value.producer_version != input_value.mapping_rule_set.producer_version:
        raise DataArtifactError(
            DataArtifactErrorCode.mapping_rule_mismatch,
            "requested producer version disagrees with the frozen MappingRuleSet",
        )

    declarations = {rule.rule_id: rule for rule in manifest.conversion_rules}
    implementations = {
        rule.rule_id: rule for rule in input_value.conversion_catalog.rules
    }
    if implementations.keys() != declarations.keys():
        raise DataArtifactError(
            DataArtifactErrorCode.conversion_catalog_mismatch,
            "conversion implementation set must exactly match Manifest declarations",
        )
    for field in fields_by_id.values():
        for alias in field.source_aliases:
            declared = declarations.get(alias.conversion_rule_id)
            implemented = implementations.get(alias.conversion_rule_id)
            if declared is None or implemented is None:
                raise DataArtifactError(
                    DataArtifactErrorCode.unknown_conversion_rule,
                    f"conversion rule {alias.conversion_rule_id} is not frozen end-to-end",
                )
            if declared.rule_version != implemented.rule_version:
                raise DataArtifactError(
                    DataArtifactErrorCode.conversion_catalog_mismatch,
                    "conversion declaration and implementation versions disagree",
                )
            expected_kind = (
                QuantityKind.none
                if implemented.rule_id == "unit.identity"
                else QuantityKind(_quantity_kind(field, bundle))
            )
            if implemented.quantity_kind is not expected_kind:
                raise DataArtifactError(
                    DataArtifactErrorCode.conversion_catalog_mismatch,
                    "conversion declaration and implementation quantity kinds disagree",
                )
            if declared.source_unit is not None and (
                declared.source_unit != implemented.source_unit
                or declared.target_unit != implemented.target_unit
            ):
                raise DataArtifactError(
                    DataArtifactErrorCode.conversion_catalog_mismatch,
                    "conversion declaration and implementation unit pairs disagree",
                )
    return bundle, tuple(
        field for field in manifest.fields if field.field_id in requested
    )


def validate_runtime_input_integrity(input_value: DataArtifactBuildInput) -> None:
    if input_value.input_hash != compute_data_artifact_input_hash(input_value):
        raise DataArtifactError(
            DataArtifactErrorCode.input_hash_mismatch,
            "Data Artifact input hash does not match the supplied typed input",
        )
    for policy, label in (
        (input_value.mapping_rule_set, "MappingRuleSet"),
        (input_value.conversion_catalog, "UnitConversionCatalog"),
    ):
        if policy.content_hash != compute_data_artifact_content_hash(policy):
            code = (
                DataArtifactErrorCode.mapping_rule_mismatch
                if label == "MappingRuleSet"
                else DataArtifactErrorCode.conversion_catalog_mismatch
            )
            raise DataArtifactError(code, f"{label} content hash is invalid")
    result = input_value.crossmatch_result
    if (
        result.content_hash != compute_crossmatch_content_hash(result)
        or result.output_hash != result.content_hash
        or result.result_id
        != f"crossmatch.{result.content_hash.removeprefix('sha256:')[:24]}"
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "CrossmatchResult hash or stable identity is invalid",
        )
    for acquisition, snapshot, mode, level, completion in (
        (
            input_value.left_acquisition,
            result.left_source_snapshot,
            result.left_source_mode,
            result.left_data_level,
            result.left_completion,
        ),
        (
            input_value.right_acquisition,
            result.right_source_snapshot,
            result.right_source_mode,
            result.right_data_level,
            result.right_completion,
        ),
    ):
        if acquisition.snapshot != snapshot:
            raise DataArtifactError(
                DataArtifactErrorCode.snapshot_mismatch,
                "acquisition SourceSnapshot disagrees with CrossmatchResult",
            )
        if (
            acquisition.source_mode is not mode
            or acquisition.data_level is not level
            or acquisition.completion != completion
        ):
            raise DataArtifactError(
                DataArtifactErrorCode.crossmatch_result_mismatch,
                "acquisition execution scope disagrees with CrossmatchResult",
            )
    acquired = {
        (record.source_id, record.row_key): record
        for acquisition in (input_value.left_acquisition, input_value.right_acquisition)
        for record in acquisition.records
    }
    if any(
        record.content_hash
        != compute_raw_data_record_hash(
            source_id=record.source_id, row_key=record.row_key, payload=record.payload
        )
        for record in acquired.values()
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.source_record_hash_mismatch,
            "acquisition raw-record content hash is invalid",
        )
    referenced: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for candidate in result.candidates:
        reference = candidate.source_record
        key = (reference.source_id, reference.row_key)
        record = acquired.get(key)
        if record is None:
            raise DataArtifactError(
                DataArtifactErrorCode.source_record_reference_not_found,
                "CrossmatchResult refers to an unavailable acquisition record",
            )
        if record.content_hash != reference.record_content_hash:
            raise DataArtifactError(
                DataArtifactErrorCode.source_record_hash_mismatch,
                "CrossmatchResult raw-record hash disagrees with acquisition",
            )
        referenced.add(key)
    if referenced != acquired.keys():
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "acquisition includes records outside the frozen Crossmatch input",
        )


def validate_frozen_crossmatch_handoff(input_value: DataArtifactBuildInput) -> None:
    result = input_value.crossmatch_result
    context = result.admission_context
    rule_set = load_crossmatch_rule_set()
    aliases = load_entity_alias_catalog()
    sources = load_crossmatch_source_policy()
    if (context.rule_set, context.alias_catalog, context.source_policy) != (
        rule_set,
        aliases,
        sources,
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "CrossmatchResult is not bound to the repository-frozen Cross-source Entity Alignment policies",
        )
    expected = (
        rule_set.rule_set_id,
        rule_set.version,
        rule_set.content_hash,
        aliases.catalog_id,
        aliases.version,
        aliases.content_hash,
        rule_set.producer_name,
        rule_set.producer_version,
    )
    actual = (
        result.rule_set_id,
        result.rule_set_version,
        result.rule_set_content_hash,
        result.alias_catalog_id,
        result.alias_catalog_version,
        result.alias_catalog_content_hash,
        result.producer_execution.producer_name,
        result.producer_execution.producer_version,
    )
    if actual != expected:
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "CrossmatchResult execution bindings are not repository-frozen",
        )


def _record_key(record: CrossmatchRecord) -> str:
    if isinstance(record, UnpairedRecord):
        return compute_canonical_payload_hash(
            {"record_type": record.record_type, "candidate_id": record.candidate_id}
        )
    return record.logical_match_key


def _record_members(record: CrossmatchRecord) -> tuple[str, ...]:
    if isinstance(record, UnpairedRecord):
        return (record.candidate_id,)
    return tuple(sorted((*record.left_candidate_ids, *record.right_candidate_ids)))


def _alignment_status(record: CrossmatchRecord) -> AlignmentStatus:
    if isinstance(record, UnpairedRecord):
        return AlignmentStatus(record.decision.value)
    if record.adjudication is AdjudicationDecision.accepted:
        return AlignmentStatus.accepted
    if record.adjudication is AdjudicationDecision.rejected:
        return AlignmentStatus.rejected
    if record.adjudication is AdjudicationDecision.keep_unresolved:
        return (
            AlignmentStatus.conflict
            if isinstance(record, ConflictGroup)
            else AlignmentStatus.review_required
        )
    if isinstance(record, ConflictGroup):
        return AlignmentStatus.conflict
    return AlignmentStatus(record.decision.value)


def _locator(candidate: EntityCandidate, raw_field: str) -> SourceCellLocator:
    reference = candidate.source_record
    return SourceCellLocator(
        source_role=candidate.side.value,
        source_snapshot_id=reference.source_snapshot_id,
        source_snapshot_content_hash=reference.source_snapshot_content_hash,
        source_id=reference.source_id,
        query_hash=reference.query_hash,
        row_key=reference.row_key,
        raw_record_content_hash=reference.record_content_hash,
        raw_field=raw_field,
    )


def canonicalize_source_value(
    raw: object,
    field: FieldDefinition,
    alias,
    conversion_catalog,
    bundle,
    conversion_versions: dict[str, str],
) -> str:
    if field.data_type is DataType.string:
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            raise DataArtifactError(
                DataArtifactErrorCode.invalid_numeric_value,
                f"{field.field_id} requires a stable source string/integer scalar",
            )
        return str(raw).strip()
    numeric = convert_decimal_value(
        raw,
        rule_id=alias.conversion_rule_id,
        rule_version=conversion_versions[alias.conversion_rule_id],
        source_unit=alias.source_unit,
        target_unit=field.canonical_unit,
        quantity_kind=_quantity_kind(field, bundle),
        catalog=conversion_catalog,
    )
    if field.data_type is DataType.integer and numeric != numeric.to_integral_value():
        raise DataArtifactError(
            DataArtifactErrorCode.invalid_numeric_value,
            f"{field.field_id} requires an integral canonical value",
        )
    return serialize_decimal(numeric, capacity=conversion_catalog.decimal_capacity)


def _uncertainty(
    record: RawDataSourceRecord,
    candidate: EntityCandidate,
    field: FieldDefinition,
    alias,
    input_value: DataArtifactBuildInput,
    bundle,
    conversion_versions: dict[str, str] | None = None,
) -> UncertaintyValue:
    if alias.positive_error_field is None:
        return UncertaintyValue(status=UncertaintyStatus.not_applicable)
    if conversion_versions is None:
        conversion_versions = {
            rule.rule_id: rule.rule_version
            for rule in bundle.field_manifest.conversion_rules
        }
    source_values: list[Decimal | None] = []
    canonical_values: list[Decimal | None] = []
    locators: list[SourceCellLocator | None] = []
    for name in (alias.positive_error_field, alias.negative_error_field):
        raw = record.payload.get(name)
        locator = _locator(candidate, name) if name in record.payload else None
        if raw is None:
            source_values.append(None)
            canonical_values.append(None)
            locators.append(locator)
            continue
        try:
            source_values.append(
                decimal_from_source(
                    raw, capacity=input_value.conversion_catalog.decimal_capacity
                )
            )
            canonical_values.append(
                convert_decimal_value(
                    raw,
                    rule_id=alias.conversion_rule_id,
                    rule_version=conversion_versions[alias.conversion_rule_id],
                    source_unit=alias.source_unit,
                    target_unit=field.canonical_unit,
                    quantity_kind=_quantity_kind(field, bundle),
                    catalog=input_value.conversion_catalog,
                )
            )
            locators.append(locator)
        except DataArtifactError as exc:
            raise DataArtifactError(
                DataArtifactErrorCode.invalid_uncertainty,
                "source uncertainty is not a valid finite numeric scalar",
                cause=exc,
            ) from exc
    count = sum(item is not None for item in source_values)
    status = (
        UncertaintyStatus.missing,
        UncertaintyStatus.partial,
        UncertaintyStatus.complete,
    )[count]
    return UncertaintyValue(
        status=status,
        source_positive=source_values[0],
        source_negative=source_values[1],
        canonical_positive=canonical_values[0],
        canonical_negative=canonical_values[1],
        positive_locator=locators[0],
        negative_locator=locators[1],
    )


def _limit(
    record: RawDataSourceRecord,
    candidate: EntityCandidate,
    alias,
    raw_value: object,
) -> LimitValue:
    if alias.limit_field is None:
        return LimitValue(status=LimitStatus.not_applicable)
    flag = record.payload.get(alias.limit_field)
    if flag is None:
        if raw_value is None:
            return LimitValue(status=LimitStatus.not_applicable)
        raise DataArtifactError(
            DataArtifactErrorCode.unknown_limit_flag,
            f"declared limit flag {alias.limit_field} is missing",
        )
    if isinstance(flag, bool) or not isinstance(flag, int):
        raise DataArtifactError(
            DataArtifactErrorCode.unknown_limit_flag, "limit flag must be an integer"
        )
    if raw_value is None:
        raise DataArtifactError(
            DataArtifactErrorCode.limit_without_value,
            "limit flag cannot exist without a value",
        )
    flags = alias.limit_flags
    statuses = {
        flags.measured: LimitStatus.measured,
        flags.lower_limit: LimitStatus.lower_limit,
        flags.upper_limit: LimitStatus.upper_limit,
    }
    if flag not in statuses:
        raise DataArtifactError(
            DataArtifactErrorCode.unknown_limit_flag,
            "limit flag is not declared by the Field Manifest",
        )
    return LimitValue(
        status=statuses[flag],
        raw_flag=flag,
        locator=_locator(candidate, alias.limit_field),
    )


def _source_value(
    *,
    row_id: str,
    candidate: EntityCandidate,
    raw_record: RawDataSourceRecord,
    field: FieldDefinition,
    alias,
    source_priority: int,
    input_value: DataArtifactBuildInput,
    bundle,
    conversion_versions: dict[str, str],
) -> SourceValueCandidate:
    raw_value = raw_record.payload.get(alias.raw_field)
    normalized_identity = next(
        (
            value.normalized_value
            for value in candidate.identity_values
            if field.object_identity_key
            and value.field_id == field.field_id
            and value.locator.raw_field == alias.raw_field
        ),
        None,
    )
    canonical = None
    if raw_value is not None:
        canonical = normalized_identity or canonicalize_source_value(
            raw_value,
            field,
            alias,
            input_value.conversion_catalog,
            bundle,
            conversion_versions,
        )
    if field.data_type is DataType.string and canonical == "":
        canonical = None
    locator = _locator(candidate, alias.raw_field)
    source_value_id = _stable_id(
        "source_value",
        {
            "row_id": row_id,
            "candidate_id": candidate.candidate_id,
            "field_id": field.field_id,
            "raw_field": alias.raw_field,
        },
    )
    payload = {
        "source_value_id": source_value_id,
        "canonical_field_id": field.field_id,
        "source_id": candidate.source_record.source_id,
        "source_table": alias.source_table,
        "source_snapshot_id": candidate.source_record.source_snapshot_id,
        "source_snapshot_content_hash": candidate.source_record.source_snapshot_content_hash,
        "query_hash": candidate.source_record.query_hash,
        "raw_record_row_key": candidate.source_record.row_key,
        "raw_record_content_hash": candidate.source_record.record_content_hash,
        "raw_field": alias.raw_field,
        "raw_value": raw_value,
        "source_unit": alias.source_unit,
        "canonical_value": canonical,
        "canonical_unit": field.canonical_unit,
        "alias_priority": alias.priority,
        "source_priority": source_priority,
        "transformation_rule_version": field.transformation_rule_version,
        "conversion_rule_id": alias.conversion_rule_id,
        "conversion_rule_version": conversion_versions[alias.conversion_rule_id],
        "reference_field": alias.reference_field,
        "reference_value": raw_record.payload.get(alias.reference_field)
        if alias.reference_field
        else None,
        "provenance_field": alias.provenance_field,
        "provenance_value": raw_record.payload.get(alias.provenance_field)
        if alias.provenance_field
        else None,
        "uncertainty": _uncertainty(
            raw_record,
            candidate,
            field,
            alias,
            input_value,
            bundle,
            conversion_versions,
        ).model_dump(mode="json"),
        "limit": _limit(raw_record, candidate, alias, raw_value).model_dump(
            mode="json"
        ),
        "null_status": NullReason.not_measured if raw_value is None else None,
        "evidence_locator": locator.model_dump(mode="json"),
    }
    return _hashed(SourceValueCandidate, payload)


def _replace_raw_field(locator: SourceCellLocator, raw_field: str) -> SourceCellLocator:
    return locator.model_copy(update={"raw_field": raw_field})


def _build_evidence(
    source_value: SourceValueCandidate,
    *,
    row_id: str,
    logical_key: str,
    record: CrossmatchRecord,
    input_value: DataArtifactBuildInput,
    status: SelectionStatus,
    reason: str,
) -> TransformationEvidence:
    result = input_value.crossmatch_result
    uncertainty_locators = tuple(
        locator
        for locator in (
            source_value.uncertainty.positive_locator,
            source_value.uncertainty.negative_locator,
        )
        if locator is not None
    )
    payload = {
        "evidence_id": _stable_id(
            "evidence.transformation",
            {"row_id": row_id, "source_value_id": source_value.source_value_id},
        ),
        "target_candidate_kind": "dataset",
        "dataset_row_id": row_id,
        "canonical_field_id": source_value.canonical_field_id,
        "source_value_id": source_value.source_value_id,
        "locator": source_value.evidence_locator.model_dump(mode="json"),
        "raw_value": source_value.raw_value,
        "source_unit": source_value.source_unit,
        "canonical_value": source_value.canonical_value,
        "canonical_unit": source_value.canonical_unit,
        "conversion_rule_id": source_value.conversion_rule_id,
        "conversion_rule_version": source_value.conversion_rule_version,
        "conversion_catalog_id": input_value.conversion_catalog.catalog_id,
        "conversion_catalog_version": input_value.conversion_catalog.version,
        "conversion_catalog_content_hash": input_value.conversion_catalog.content_hash,
        "transformation_rule_version": source_value.transformation_rule_version,
        "uncertainty": source_value.uncertainty.model_dump(mode="json"),
        "limit": source_value.limit.model_dump(mode="json"),
        "uncertainty_locators": [
            locator.model_dump(mode="json") for locator in uncertainty_locators
        ],
        "limit_locator": source_value.limit.locator.model_dump(mode="json")
        if source_value.limit.locator is not None
        else None,
        "reference_field": source_value.reference_field,
        "reference_value": source_value.reference_value,
        "reference_locator": _replace_raw_field(
            source_value.evidence_locator, source_value.reference_field
        ).model_dump(mode="json")
        if source_value.reference_field is not None
        else None,
        "provenance_field": source_value.provenance_field,
        "provenance_value": source_value.provenance_value,
        "provenance_locator": _replace_raw_field(
            source_value.evidence_locator, source_value.provenance_field
        ).model_dump(mode="json")
        if source_value.provenance_field is not None
        else None,
        "crossmatch_result_id": result.result_id,
        "crossmatch_result_content_hash": result.content_hash,
        "crossmatch_logical_key": logical_key,
        "crossmatch_evidence_ids": tuple(getattr(record, "evidence_ids", ())),
        "selection_status": status,
        "selection_reason": reason,
    }
    return _hashed(TransformationEvidence, payload)


def numeric_values_agree(left: Decimal, right: Decimal, rule_set) -> bool:
    difference = abs(left - right)
    if difference == 0:
        return True
    comparison = rule_set.numeric_comparison
    denominator = max(abs(left), abs(right), comparison.relative_denominator_floor)
    relative = difference / denominator
    compare = (
        (lambda value, threshold: value <= threshold)
        if comparison.threshold_inclusive
        else (lambda value, threshold: value < threshold)
    )
    return compare(difference, comparison.absolute_tolerance) or compare(
        relative, comparison.relative_tolerance
    )


def derive_field_conflicts(
    field: FieldDefinition,
    non_null_values: list[SourceValueCandidate] | tuple[SourceValueCandidate, ...],
    rule_set,
    *,
    row_id: str = "dataset_row.unit",
) -> tuple[FieldConflictRecord, ...]:
    if len(non_null_values) <= 1:
        return ()
    if len(non_null_values) > rule_set.capacity.max_conflict_candidates:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded,
            "conflict-candidate capacity exceeded",
        )
    numeric = field.data_type in {DataType.integer, DataType.number}
    absolute = relative = denominator = None
    if numeric:
        numbers = [Decimal(item.canonical_value) for item in non_null_values]
        minimum, maximum = min(numbers), max(numbers)
        absolute = maximum - minimum
        denominator = max(
            abs(maximum),
            abs(minimum),
            rule_set.numeric_comparison.relative_denominator_floor,
        )
        relative = absolute / denominator
        agrees = numeric_values_agree(minimum, maximum, rule_set)
    else:
        first = non_null_values[0].canonical_value
        agrees = all(item.canonical_value == first for item in non_null_values[1:])
    if agrees:
        return ()
    source_value_ids = tuple(sorted(item.source_value_id for item in non_null_values))
    payload = {
        "conflict_id": _stable_id(
            "conflict.field", {"field": field.field_id, "ids": source_value_ids}
        ),
        "dataset_row_id": row_id,
        "canonical_field_id": field.field_id,
        "source_value_ids": source_value_ids,
        "conflict_scope": "same_source"
        if len({item.source_id for item in non_null_values}) == 1
        else "cross_source",
        "reason": "distinct canonical values are retained; source priority selects display only",
        "comparison_policy_version": rule_set.conflict_comparison_policy_version,
        "absolute_difference": serialize_decimal(absolute)
        if absolute is not None
        else None,
        "relative_denominator": serialize_decimal(denominator)
        if denominator is not None
        else None,
        "relative_difference": serialize_decimal(relative)
        if relative is not None
        else None,
    }
    # Decimal inputs must be normalized through the persisted model before the
    # canonical hash is computed. Hashing the pre-validation strings makes
    # values such as scientific notation commit to a different payload than
    # the Decimal serialization validated by ``FieldConflictRecord``.
    normalized_source = {
        **payload,
        "absolute_difference": absolute,
        "relative_denominator": denominator,
        "relative_difference": relative,
    }
    normalized = FieldConflictRecord.model_construct(
        **normalized_source,
        content_hash="sha256:" + "0" * 64,
    ).model_dump(mode="json")
    normalized["content_hash"] = compute_data_artifact_content_hash(normalized)
    return (FieldConflictRecord.model_validate(normalized),)


def _source_members(
    input_value: DataArtifactBuildInput,
) -> tuple[SourceCollectionMember, ...]:
    members: list[SourceCollectionMember] = []
    for side, acquisition in (
        ("left", input_value.left_acquisition),
        ("right", input_value.right_acquisition),
    ):
        snapshot = acquisition.snapshot
        references = tuple(
            sorted(
                (
                    RawSourceRecordReference(
                        source_id=record.source_id,
                        source_snapshot_id=snapshot.snapshot_id,
                        source_snapshot_content_hash=snapshot.content_hash,
                        query_hash=snapshot.query_hash,
                        row_key=record.row_key,
                        raw_record_content_hash=record.content_hash,
                    )
                    for record in acquisition.records
                ),
                key=lambda item: (
                    item.source_id,
                    item.row_key,
                    item.raw_record_content_hash,
                ),
            )
        )
        members.append(
            SourceCollectionMember(
                side=side,
                source_snapshot=snapshot,
                source_id=snapshot.source_id,
                source_snapshot_id=snapshot.snapshot_id,
                source_snapshot_content_hash=snapshot.content_hash,
                query_hash=snapshot.query_hash,
                source_mode=acquisition.source_mode,
                data_level=acquisition.data_level,
                completion=acquisition.completion,
                license_note=snapshot.license_note,
                raw_record_references=references,
                raw_record_count=len(references),
                raw_record_reference_registry_hash=compute_raw_record_reference_registry_hash(
                    references
                ),
            )
        )
    return tuple(members)


def derive_data_artifact_domain_projection(
    input_value: DataArtifactBuildInput,
) -> DataArtifactDomainProjection:
    """Derive the complete expected Data Artifact domain from canonical frozen inputs."""

    validate_runtime_input_integrity(input_value)
    validate_frozen_crossmatch_handoff(input_value)
    bundle, fields = validate_policy_bindings(input_value)
    result = input_value.crossmatch_result
    conversion_versions = {
        rule.rule_id: rule.rule_version
        for rule in bundle.field_manifest.conversion_rules
    }
    source_priorities = {
        field.field_id: {
            source_id: priority
            for priority, source_id in enumerate(field.source_priority, start=1)
        }
        for field in fields
    }
    candidate_by_id = {
        candidate.candidate_id: candidate for candidate in result.candidates
    }
    raw_by_reference = {
        (record.source_id, record.row_key): record
        for acquisition in (input_value.left_acquisition, input_value.right_acquisition)
        for record in acquisition.records
    }

    all_source_values: list[SourceValueCandidate] = []
    all_evidence: list[TransformationEvidence] = []
    all_selections: list[FieldSelectionRecord] = []
    all_conflicts: list[FieldConflictRecord] = []
    rows: list[DatasetRow] = []
    for record in result.records:
        logical_key = _record_key(record)
        row_id = _stable_id("dataset_row", logical_key)
        member_ids = _record_members(record)
        members = tuple(candidate_by_id[candidate_id] for candidate_id in member_ids)
        alignment = _alignment_status(record)
        outcomes = []
        row_conflict_ids: list[str] = []
        row_evidence_ids: list[str] = []
        allowed_object_types = (
            input_value.mapping_rule_set.entity_projection_policy.allowed_for(
                record.entity_level
            )
        )
        for field in fields:
            if field.object_type not in allowed_object_types:
                continue
            applicable_members = tuple(
                member
                for member in members
                if field.source_aliases_for(member.source_record.source_id)
            )
            if not applicable_members:
                continue
            source_values: list[SourceValueCandidate] = []
            for member in applicable_members:
                source_id = member.source_record.source_id
                raw = raw_by_reference.get((source_id, member.source_record.row_key))
                if (
                    raw is None
                    or raw.content_hash != member.source_record.record_content_hash
                ):
                    raise DataArtifactError(
                        DataArtifactErrorCode.source_record_reference_not_found,
                        "Cross-source Entity Alignment source record reference is unavailable",
                    )
                for alias in field.source_aliases_for(source_id):
                    if alias.raw_field not in raw.payload:
                        continue
                    source_values.append(
                        _source_value(
                            row_id=row_id,
                            candidate=member,
                            raw_record=raw,
                            field=field,
                            alias=alias,
                            source_priority=source_priorities[field.field_id][
                                source_id
                            ],
                            input_value=input_value,
                            bundle=bundle,
                            conversion_versions=conversion_versions,
                        )
                    )
            source_values.sort(
                key=lambda item: (
                    item.source_priority,
                    item.alias_priority,
                    item.source_value_id,
                )
            )
            if (
                len(source_values)
                > input_value.mapping_rule_set.capacity.max_source_values_per_field
            ):
                raise DataArtifactError(
                    DataArtifactErrorCode.capacity_exceeded,
                    "source-value capacity exceeded",
                )
            non_null = [
                item for item in source_values if item.canonical_value is not None
            ]
            conflicts = derive_field_conflicts(
                field,
                non_null,
                input_value.mapping_rule_set,
                row_id=row_id,
            )
            selected = non_null[0] if non_null else None
            identity_unresolved = alignment in {
                AlignmentStatus.inconclusive,
                AlignmentStatus.review_required,
                AlignmentStatus.rejected,
                AlignmentStatus.conflict,
            }
            selection_reason = (
                f"crossmatch alignment remains {alignment.value}; no field winner is selected"
                if identity_unresolved
                else "highest declared source and alias priority; every candidate is retained"
            )
            selection = None
            if selected is not None and not identity_unresolved:
                selection = _hashed(
                    FieldSelectionRecord,
                    {
                        "selection_id": _stable_id(
                            "selection.field",
                            {"row_id": row_id, "field": field.field_id},
                        ),
                        "dataset_row_id": row_id,
                        "canonical_field_id": field.field_id,
                        "selected_source_value_id": selected.source_value_id,
                        "candidate_source_value_ids": tuple(
                            item.source_value_id for item in source_values
                        ),
                        "strategy": "prefer_source_priority_preserve_all",
                        "reason": selection_reason,
                    },
                )
            evidences = []
            for value in source_values:
                if identity_unresolved or conflicts:
                    status = SelectionStatus.conflict
                elif (
                    selected is not None
                    and value.source_value_id == selected.source_value_id
                ):
                    status = SelectionStatus.selected
                else:
                    status = SelectionStatus.unselected
                evidences.append(
                    _build_evidence(
                        value,
                        row_id=row_id,
                        logical_key=logical_key,
                        record=record,
                        input_value=input_value,
                        status=status,
                        reason=selection_reason,
                    )
                )
            evidence_ids = tuple(item.evidence_id for item in evidences)
            source_value_ids = tuple(item.source_value_id for item in source_values)
            conflict_ids = tuple(item.conflict_id for item in conflicts)
            if identity_unresolved:
                outcome = UnresolvedCanonicalValue(
                    canonical_field_id=field.field_id,
                    reason=f"crossmatch alignment remains {alignment.value}",
                    candidate_source_value_ids=source_value_ids,
                    transformation_evidence_ids=evidence_ids,
                    conflict_ids=conflict_ids,
                )
            elif selected is not None:
                outcome = MappedCanonicalValue(
                    canonical_field_id=field.field_id,
                    canonical_value=selected.canonical_value,
                    canonical_unit=field.canonical_unit,
                    selected_source_value_id=selected.source_value_id,
                    candidate_source_value_ids=source_value_ids,
                    transformation_evidence_ids=evidence_ids,
                    selection_id=selection.selection_id,
                    conflict_ids=conflict_ids,
                )
            elif field.nullable:
                outcome = DeclaredNullValue(
                    canonical_field_id=field.field_id,
                    reason=NullReason.not_measured
                    if source_values
                    else NullReason.not_in_source,
                    candidate_source_value_ids=source_value_ids,
                    transformation_evidence_ids=evidence_ids,
                )
            else:
                raise DataArtifactError(
                    DataArtifactErrorCode.non_nullable_unresolved_field,
                    f"non-nullable field {field.field_id} has no mapped source value",
                )
            outcomes.append(outcome)
            if (
                len(all_evidence) + len(evidences)
                > input_value.mapping_rule_set.capacity.max_transformation_evidence
            ):
                raise DataArtifactError(
                    DataArtifactErrorCode.capacity_exceeded,
                    "Evidence capacity exceeded",
                )
            all_source_values.extend(source_values)
            all_evidence.extend(evidences)
            if selection is not None:
                all_selections.append(selection)
            all_conflicts.extend(conflicts)
            row_conflict_ids.extend(conflict_ids)
            row_evidence_ids.extend(evidence_ids)
        rows.append(
            _hashed(
                DatasetRow,
                {
                    "row_id": row_id,
                    "crossmatch_record_type": record.record_type,
                    "crossmatch_logical_key": logical_key,
                    "entity_level": record.entity_level,
                    "canonical_row_identity": derive_canonical_row_identity(
                        record,
                        members,
                        alignment_status=alignment,
                    ),
                    "projection_policy_version": input_value.mapping_rule_set.entity_projection_policy.version,
                    "projected_field_ids": tuple(
                        item.canonical_field_id for item in outcomes
                    ),
                    "alignment_status": alignment,
                    "source_member_ids": member_ids,
                    "fields": [item.model_dump(mode="json") for item in outcomes],
                    "conflict_ids": tuple(sorted(set(row_conflict_ids))),
                    "evidence_ids": tuple(sorted(set(row_evidence_ids))),
                    "source_snapshot_ids": tuple(
                        sorted(
                            {
                                member.source_record.source_snapshot_id
                                for member in members
                            }
                        )
                    ),
                },
            )
        )

    producer = DataArtifactProducer(
        producer_name=input_value.mapping_rule_set.producer_name,
        producer_version=input_value.producer_version,
        mapping_rule_set_id=input_value.mapping_rule_set.rule_set_id,
        mapping_rule_set_version=input_value.mapping_rule_set.version,
        mapping_rule_set_content_hash=input_value.mapping_rule_set.content_hash,
        conversion_catalog_id=input_value.conversion_catalog.catalog_id,
        conversion_catalog_version=input_value.conversion_catalog.version,
        conversion_catalog_content_hash=input_value.conversion_catalog.content_hash,
    )
    source_snapshot_ids = tuple(
        sorted(
            (
                result.left_source_snapshot.snapshot_id,
                result.right_source_snapshot.snapshot_id,
            )
        )
    )
    crossmatch_evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for record in result.records
                for evidence_id in getattr(record, "evidence_ids", ())
            }
        )
    )
    crossmatch_evidence_by_id = {item.evidence_id: item for item in result.evidence}
    crossmatch_evidence = tuple(
        crossmatch_evidence_by_id[item] for item in crossmatch_evidence_ids
    )
    evidence_ids = tuple(
        sorted(
            {
                *(item.evidence_id for item in all_evidence),
                *crossmatch_evidence_ids,
            }
        )
    )
    return DataArtifactDomainProjection(
        input_value=input_value,
        fields=fields,
        rows=tuple(rows),
        source_values=tuple(all_source_values),
        transformation_evidence=tuple(all_evidence),
        selections=tuple(all_selections),
        conflicts=tuple(all_conflicts),
        source_members=_source_members(input_value),
        producer=producer,
        source_snapshot_ids=source_snapshot_ids,
        crossmatch_evidence=crossmatch_evidence,
        crossmatch_evidence_ids=crossmatch_evidence_ids,
        evidence_ids=evidence_ids,
        alignment_record_keys=tuple(_record_key(record) for record in result.records),
        conflict_record_keys=tuple(
            _record_key(record)
            for record in result.records
            if _alignment_status(record) is AlignmentStatus.conflict
        ),
        review_required_record_keys=tuple(
            _record_key(record)
            for record in result.records
            if _alignment_status(record) is AlignmentStatus.review_required
        ),
        inconclusive_record_keys=tuple(
            _record_key(record)
            for record in result.records
            if _alignment_status(record) is AlignmentStatus.inconclusive
        ),
        quality_metric_input_declarations=tuple(
            sorted(
                {
                    metric.value
                    for field in fields
                    for metric in field.quality_metric_inputs
                }
            )
        ),
    )


__all__ = [
    "DataArtifactDomainProjection",
    "derive_data_artifact_domain_projection",
    "derive_field_conflicts",
    "numeric_values_agree",
    "validate_frozen_crossmatch_handoff",
    "validate_policy_bindings",
    "validate_runtime_input_integrity",
]
