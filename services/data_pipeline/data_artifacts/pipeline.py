"""Build deterministic, evidence-first C-04 data Artifact candidates."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.crossmatch import (
    AdjudicationDecision,
    ConflictGroup,
    CrossmatchRecord,
    EntityCandidate,
    UnpairedRecord,
    compute_crossmatch_content_hash,
)
from app.schemas.data_artifacts import (
    AlignmentStatus,
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DataArtifactErrorCode,
    DataArtifactProducer,
    DatasetArtifactCandidate,
    DatasetColumn,
    DatasetRow,
    DeclaredNullValue,
    FieldConflictRecord,
    FieldDictionaryArtifactCandidate,
    FieldSelectionRecord,
    LimitStatus,
    LimitValue,
    MappedCanonicalValue,
    SelectionStatus,
    RawSourceRecordReference,
    SourceCellLocator,
    SourceCollectionArtifactCandidate,
    SourceCollectionMember,
    SourceValueCandidate,
    TransformationEvidence,
    UncertaintyStatus,
    UncertaintyValue,
    UnresolvedCanonicalValue,
    _seal_data_artifact_candidate,
    compute_data_artifact_candidate_id,
    compute_data_artifact_content_hash,
    compute_data_artifact_input_hash,
    compute_data_artifact_output_hash,
    compute_raw_record_reference_registry_hash,
)
from app.schemas.manifest import DataType, FieldDefinition, NullReason, QuantityKind
from app.schemas.source_acquisition import RawDataSourceRecord, compute_raw_data_record_hash
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from .conversion import convert_decimal_value, decimal_from_source, serialize_decimal
from .errors import DataArtifactError
from .policy import load_mapping_rule_set, load_unit_conversion_catalog


def _stable_id(prefix: str, payload: object) -> str:
    digest = compute_canonical_payload_hash(payload).removeprefix("sha256:")
    return f"{prefix}.{digest[:24]}"


def _hashed(model_type, payload: dict[str, Any]):
    payload["content_hash"] = compute_data_artifact_content_hash(payload)
    return model_type.model_validate(payload)


def _candidate(model_type, payload: dict[str, Any]):
    payload.setdefault("schema_version", "1.0.0")
    payload.setdefault("quality_evaluation_status", "not_evaluated")
    output_hash = compute_data_artifact_output_hash(payload)
    payload["candidate_id"] = compute_data_artifact_candidate_id(payload["kind"], output_hash)
    payload["output_hash"] = output_hash
    return model_type.model_validate(payload)


def _validate_policy_bindings(input_value: DataArtifactBuildInput):
    bundle = load_frozen_manifest_bundle()
    case = bundle.case_manifest
    field_manifest = bundle.field_manifest
    pins = input_value.manifest_pins
    actual = (
        case.case_id,
        case.manifest_version,
        case.content_hash,
        field_manifest.manifest_id,
        field_manifest.manifest_version,
        field_manifest.content_hash,
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
            "frozen manifests disagree with the C-04 input pins",
        )

    frozen_rule_set = load_mapping_rule_set()
    if input_value.mapping_rule_set != frozen_rule_set:
        raise DataArtifactError(
            DataArtifactErrorCode.mapping_rule_mismatch,
            "caller MappingRuleSet is not the repository-frozen execution policy",
        )
    frozen_catalog = load_unit_conversion_catalog()
    if input_value.conversion_catalog != frozen_catalog:
        raise DataArtifactError(
            DataArtifactErrorCode.conversion_catalog_mismatch,
            "caller UnitConversionCatalog is not the repository-frozen execution policy",
        )

    fields_by_id = {field.field_id: field for field in field_manifest.fields}
    requested = set(input_value.requested_fields)
    unknown = requested - fields_by_id.keys()
    if unknown:
        raise DataArtifactError(
            DataArtifactErrorCode.unsupported_requested_field,
            f"requested fields are not canonical Field Manifest IDs: {sorted(unknown)}",
        )
    capacity = input_value.mapping_rule_set.capacity
    if len(requested) > capacity.max_requested_fields:
        raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "field capacity exceeded")
    if len(input_value.crossmatch_result.records) > capacity.max_rows:
        raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "row capacity exceeded")
    if len(requested) * len(input_value.crossmatch_result.records) > capacity.max_total_cell_outcomes:
        raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "cell capacity exceeded")
    if input_value.producer_version != input_value.mapping_rule_set.producer_version:
        raise DataArtifactError(
            DataArtifactErrorCode.mapping_rule_mismatch,
            "requested producer version disagrees with the frozen MappingRuleSet",
        )

    declarations = {rule.rule_id: rule for rule in field_manifest.conversion_rules}
    implementations = {rule.rule_id: rule for rule in input_value.conversion_catalog.rules}
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
            expected_quantity_kind = (
                QuantityKind.none
                if implemented.rule_id == "unit.identity.v1"
                else QuantityKind(_quantity_kind(field, bundle))
            )
            if implemented.quantity_kind is not expected_quantity_kind:
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
    ordered = tuple(field for field in field_manifest.fields if field.field_id in requested)
    return bundle, ordered


def _validate_runtime_input_integrity(input_value: DataArtifactBuildInput) -> None:
    if input_value.input_hash != compute_data_artifact_input_hash(input_value):
        raise DataArtifactError(
            DataArtifactErrorCode.input_hash_mismatch,
            "C-04 input hash does not match the supplied typed input",
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
    for acquisition, expected_snapshot, expected_mode, expected_level, expected_completion in (
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
        if acquisition.snapshot != expected_snapshot:
            raise DataArtifactError(
                DataArtifactErrorCode.snapshot_mismatch,
                "acquisition SourceSnapshot disagrees with CrossmatchResult",
            )
        if (
            acquisition.source_mode is not expected_mode
            or acquisition.data_level is not expected_level
            or acquisition.completion != expected_completion
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
            source_id=record.source_id,
            row_key=record.row_key,
            payload=record.payload,
        )
        for record in acquired.values()
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.source_record_hash_mismatch,
            "acquisition raw-record content hash is invalid",
        )
    referenced_keys: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
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
        referenced_keys.add(key)
    if referenced_keys != acquired.keys():
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "acquisition includes records outside the frozen Crossmatch input",
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
        return AlignmentStatus.conflict if isinstance(record, ConflictGroup) else AlignmentStatus.review_required
    if isinstance(record, ConflictGroup):
        return AlignmentStatus.conflict
    return AlignmentStatus(record.decision.value)


def _locator(candidate: EntityCandidate, raw_field: str) -> SourceCellLocator:
    ref = candidate.source_record
    return SourceCellLocator(
        side=candidate.side,
        source_snapshot_id=ref.source_snapshot_id,
        source_snapshot_content_hash=ref.source_snapshot_content_hash,
        source_id=ref.source_id,
        query_hash=ref.query_hash,
        row_key=ref.row_key,
        raw_record_content_hash=ref.record_content_hash,
        raw_field=raw_field,
    )


def _quantity_kind(field: FieldDefinition, bundle) -> str:
    units = {unit.unit_id: unit for unit in bundle.field_manifest.units}
    unit = units.get(field.canonical_unit)
    return (unit.quantity_kind if unit is not None else QuantityKind.none).value


def _canonical_value(
    raw: object,
    field: FieldDefinition,
    alias,
    input_value,
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
        catalog=input_value.conversion_catalog,
    )
    if field.data_type is DataType.integer and numeric != numeric.to_integral_value():
        raise DataArtifactError(
            DataArtifactErrorCode.invalid_numeric_value,
            f"{field.field_id} requires an integral canonical value",
        )
    return serialize_decimal(
        numeric,
        capacity=input_value.conversion_catalog.decimal_capacity,
    )


def _companion_decimal(
    raw: object,
    field,
    alias,
    input_value,
    bundle,
    conversion_versions: dict[str, str],
) -> Decimal:
    return convert_decimal_value(
        raw,
        rule_id=alias.conversion_rule_id,
        rule_version=conversion_versions[alias.conversion_rule_id],
        source_unit=alias.source_unit,
        target_unit=field.canonical_unit,
        quantity_kind=_quantity_kind(field, bundle),
        catalog=input_value.conversion_catalog,
    )


def _uncertainty(
    record,
    candidate,
    field,
    alias,
    input_value,
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
    values: list[Decimal | None] = []
    canonical: list[Decimal | None] = []
    locators: list[SourceCellLocator | None] = []
    for name in (alias.positive_error_field, alias.negative_error_field):
        raw = record.payload.get(name)
        locator = _locator(candidate, name) if name in record.payload else None
        if raw is None:
            values.append(None)
            canonical.append(None)
            locators.append(locator)
        else:
            try:
                value = decimal_from_source(
                    raw,
                    capacity=input_value.conversion_catalog.decimal_capacity,
                )
                converted = _companion_decimal(
                    raw,
                    field,
                    alias,
                    input_value,
                    bundle,
                    conversion_versions,
                )
            except DataArtifactError as exc:
                raise DataArtifactError(
                    DataArtifactErrorCode.invalid_uncertainty,
                    "source uncertainty is not a valid finite numeric scalar",
                    cause=exc,
                ) from exc
            values.append(value)
            canonical.append(converted)
            locators.append(locator)
    count = sum(value is not None for value in values)
    status = (UncertaintyStatus.missing, UncertaintyStatus.partial, UncertaintyStatus.complete)[count]
    return UncertaintyValue(
        status=status,
        source_positive=values[0],
        source_negative=values[1],
        canonical_positive=canonical[0],
        canonical_negative=canonical[1],
        positive_locator=locators[0],
        negative_locator=locators[1],
    )


def _limit(record, candidate, alias, raw_value: object) -> LimitValue:
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
        raise DataArtifactError(DataArtifactErrorCode.unknown_limit_flag, "limit flag must be an integer")
    if raw_value is None:
        raise DataArtifactError(DataArtifactErrorCode.limit_without_value, "limit flag cannot exist without a value")
    mapping = alias.limit_flags
    statuses = {
        mapping.measured: LimitStatus.measured,
        mapping.lower_limit: LimitStatus.lower_limit,
        mapping.upper_limit: LimitStatus.upper_limit,
    }
    if flag not in statuses:
        raise DataArtifactError(DataArtifactErrorCode.unknown_limit_flag, "limit flag is not declared by the Field Manifest")
    return LimitValue(status=statuses[flag], raw_flag=flag, locator=_locator(candidate, alias.limit_field))


def _source_value(
    *,
    row_id,
    candidate,
    raw_record,
    field,
    alias,
    source_priority,
    input_value,
    bundle,
    conversion_versions,
):
    raw_value = raw_record.payload.get(alias.raw_field)
    locator = _locator(candidate, alias.raw_field)
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
        canonical = normalized_identity or _canonical_value(
            raw_value,
            field,
            alias,
            input_value,
            bundle,
            conversion_versions,
        )
    if field.data_type is DataType.string and canonical == "":
        canonical = None
    source_value_id = _stable_id(
        "source_value",
        {"row_id": row_id, "candidate_id": candidate.candidate_id, "field_id": field.field_id, "raw_field": alias.raw_field},
    )
    reference_value = raw_record.payload.get(alias.reference_field) if alias.reference_field else None
    provenance_value = raw_record.payload.get(alias.provenance_field) if alias.provenance_field else None
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
        "reference_value": reference_value,
        "provenance_field": alias.provenance_field,
        "provenance_value": provenance_value,
        "uncertainty": _uncertainty(
            raw_record,
            candidate,
            field,
            alias,
            input_value,
            bundle,
            conversion_versions,
        ).model_dump(mode="json"),
        "limit": _limit(raw_record, candidate, alias, raw_value).model_dump(mode="json"),
        "null_status": NullReason.not_measured if raw_value is None else None,
        "evidence_locator": locator.model_dump(mode="json"),
    }
    return _hashed(SourceValueCandidate, payload)


def _distinct_locators(source_value: SourceValueCandidate) -> tuple[SourceCellLocator, ...]:
    values = (source_value.uncertainty.positive_locator, source_value.uncertainty.negative_locator)
    return tuple(value for value in values if value is not None)


def _build_evidence(source_value, *, row_id, logical_key, record, result, input_value, status, reason):
    evidence_id = _stable_id("evidence.transformation", {"row_id": row_id, "source_value_id": source_value.source_value_id})
    payload = {
        "evidence_id": evidence_id,
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
        "uncertainty_locators": [value.model_dump(mode="json") for value in _distinct_locators(source_value)],
        "limit_locator": None if source_value.limit.locator is None else source_value.limit.locator.model_dump(mode="json"),
        "reference_field": source_value.reference_field,
        "reference_value": source_value.reference_value,
        "reference_locator": None if source_value.reference_field is None else _replace_raw_field(source_value.evidence_locator, source_value.reference_field).model_dump(mode="json"),
        "provenance_field": source_value.provenance_field,
        "provenance_value": source_value.provenance_value,
        "provenance_locator": None if source_value.provenance_field is None else _replace_raw_field(source_value.evidence_locator, source_value.provenance_field).model_dump(mode="json"),
        "crossmatch_result_id": result.result_id,
        "crossmatch_result_content_hash": result.content_hash,
        "crossmatch_logical_key": logical_key,
        "crossmatch_evidence_ids": tuple(getattr(record, "evidence_ids", ())),
        "selection_status": status,
        "selection_reason": reason,
    }
    return _hashed(TransformationEvidence, payload)


def _replace_raw_field(locator: SourceCellLocator, raw_field: str) -> SourceCellLocator:
    return locator.model_copy(update={"raw_field": raw_field})


def _numeric_values_agree(left: Decimal, right: Decimal, rule_set) -> bool:
    difference = abs(left - right)
    if difference == 0:
        return True
    comparison = rule_set.numeric_comparison
    denominator = max(
        abs(left),
        abs(right),
        comparison.relative_denominator_floor,
    )
    relative = difference / denominator
    compare = (lambda value, threshold: value <= threshold) if comparison.threshold_inclusive else (lambda value, threshold: value < threshold)
    return compare(difference, comparison.absolute_tolerance) or compare(relative, comparison.relative_tolerance)


def _conflicts(field, non_null_values, rule_set, *, row_id="dataset_row.unit"):
    if len(non_null_values) <= 1:
        return ()
    if len(non_null_values) > rule_set.capacity.max_conflict_candidates:
        raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "conflict-candidate capacity exceeded")
    if field.data_type in {DataType.integer, DataType.number}:
        numbers = [Decimal(item.canonical_value) for item in non_null_values]
        minimum = min(numbers)
        maximum = max(numbers)
        difference = maximum - minimum
        comparison = rule_set.numeric_comparison
        denominator = max(
            abs(maximum),
            abs(minimum),
            comparison.relative_denominator_floor,
        )
        relative = difference / denominator
        compare = (
            (lambda value, threshold: value <= threshold)
            if comparison.threshold_inclusive
            else (lambda value, threshold: value < threshold)
        )
        agrees = difference == 0 or compare(
            difference, comparison.absolute_tolerance
        ) or compare(relative, comparison.relative_tolerance)
    else:
        first = non_null_values[0]
        agrees = all(first.canonical_value == item.canonical_value for item in non_null_values[1:])
    if agrees:
        return ()
    ids = tuple(sorted(item.source_value_id for item in non_null_values))
    sources = {item.source_id for item in non_null_values}
    numeric = field.data_type in {DataType.integer, DataType.number}
    absolute = relative = None
    if numeric:
        numbers = [Decimal(item.canonical_value) for item in non_null_values]
        absolute = max(numbers) - min(numbers)
        denominator = max(
            *(abs(value) for value in numbers),
            rule_set.numeric_comparison.relative_denominator_floor,
        )
        relative = absolute / denominator
    payload = {
        "conflict_id": _stable_id("conflict.field", {"field": field.field_id, "ids": ids}),
        "dataset_row_id": row_id,
        "canonical_field_id": field.field_id,
        "source_value_ids": ids,
        "conflict_scope": "same_source" if len(sources) == 1 else "cross_source",
        "reason": "distinct canonical values are retained; source priority selects display only",
        "comparison_policy_version": rule_set.conflict_comparison_policy_version,
        "absolute_difference": None if absolute is None else serialize_decimal(absolute),
        "relative_denominator": None if not numeric else serialize_decimal(denominator),
        "relative_difference": None if relative is None else serialize_decimal(relative),
    }
    return (_hashed(FieldConflictRecord, payload),)


def build_data_artifact_candidates(input: DataArtifactBuildInput) -> DataArtifactBuildResult:
    """Transform already-acquired, already-crossmatched inputs without external I/O."""

    _validate_runtime_input_integrity(input)
    bundle, fields = _validate_policy_bindings(input)
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
    result = input.crossmatch_result
    candidate_by_id = {candidate.candidate_id: candidate for candidate in result.candidates}
    raw_by_reference: dict[tuple[str, tuple[tuple[str, str], ...]], RawDataSourceRecord] = {}
    for acquisition in (input.left_acquisition, input.right_acquisition):
        for record in acquisition.records:
            raw_by_reference[(record.source_id, record.row_key)] = record

    all_source_values: list[SourceValueCandidate] = []
    all_evidence: list[TransformationEvidence] = []
    all_selections: list[FieldSelectionRecord] = []
    all_conflicts: list[FieldConflictRecord] = []
    rows: list[DatasetRow] = []
    for record in result.records:
        logical_key = _record_key(record)
        row_id = _stable_id("dataset_row", logical_key)
        member_ids = _record_members(record)
        members = tuple(candidate_by_id[item] for item in member_ids)
        alignment = _alignment_status(record)
        outcomes = []
        row_conflict_ids: list[str] = []
        row_evidence_ids: list[str] = []
        allowed_object_types = input.mapping_rule_set.entity_projection_policy.allowed_for(
            record.entity_level
        )
        for field in fields:
            if field.object_type not in allowed_object_types:
                continue
            source_values: list[SourceValueCandidate] = []
            for member in members:
                source_id = member.source_record.source_id
                raw = raw_by_reference.get((source_id, member.source_record.row_key))
                if raw is None or raw.content_hash != member.source_record.record_content_hash:
                    raise DataArtifactError(DataArtifactErrorCode.source_record_reference_not_found, "C-08 source record reference is unavailable")
                aliases = field.source_aliases_for(source_id)
                for alias in aliases:
                    if alias.raw_field not in raw.payload:
                        continue
                    priority = source_priorities[field.field_id][source_id]
                    source_values.append(
                        _source_value(
                            row_id=row_id,
                            candidate=member,
                            raw_record=raw,
                            field=field,
                            alias=alias,
                            source_priority=priority,
                            input_value=input,
                            bundle=bundle,
                            conversion_versions=conversion_versions,
                        )
                    )
            source_values.sort(key=lambda value: (value.source_priority, value.alias_priority, value.source_value_id))
            if len(source_values) > input.mapping_rule_set.capacity.max_source_values_per_field:
                raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "source-value capacity exceeded")
            non_null = [value for value in source_values if value.canonical_value is not None]
            conflicts = _conflicts(
                field,
                non_null,
                input.mapping_rule_set,
                row_id=row_id,
            )
            selected = non_null[0] if non_null else None
            identity_unresolved = alignment in {AlignmentStatus.review_required, AlignmentStatus.rejected, AlignmentStatus.conflict}
            selection_reason = (
                f"crossmatch alignment remains {alignment.value}; no field winner is selected"
                if identity_unresolved
                else "highest declared source and alias priority; every candidate is retained"
            )
            selection = None
            if selected is not None and not identity_unresolved:
                selection_payload = {
                    "selection_id": _stable_id("selection.field", {"row_id": row_id, "field": field.field_id}),
                    "dataset_row_id": row_id,
                    "canonical_field_id": field.field_id,
                    "selected_source_value_id": selected.source_value_id,
                    "candidate_source_value_ids": tuple(item.source_value_id for item in source_values),
                    "strategy": "prefer_source_priority_preserve_all",
                    "reason": selection_reason,
                }
                selection = _hashed(FieldSelectionRecord, selection_payload)
            evidences = []
            for value in source_values:
                if identity_unresolved or conflicts:
                    status = SelectionStatus.conflict
                elif selected is not None and value.source_value_id == selected.source_value_id:
                    status = SelectionStatus.selected
                else:
                    status = SelectionStatus.unselected
                evidences.append(
                    _build_evidence(
                        value,
                        row_id=row_id,
                        logical_key=logical_key,
                        record=record,
                        result=result,
                        input_value=input,
                        status=status,
                        reason=selection_reason,
                    )
                )
            evidence_ids = tuple(item.evidence_id for item in evidences)
            value_ids = tuple(item.source_value_id for item in source_values)
            conflict_ids = tuple(item.conflict_id for item in conflicts)
            if identity_unresolved:
                outcome = UnresolvedCanonicalValue(
                    canonical_field_id=field.field_id,
                    reason=f"crossmatch alignment remains {alignment.value}",
                    candidate_source_value_ids=value_ids,
                    transformation_evidence_ids=evidence_ids,
                    conflict_ids=conflict_ids,
                )
            elif selected is not None:
                outcome = MappedCanonicalValue(
                    canonical_field_id=field.field_id,
                    canonical_value=selected.canonical_value,
                    canonical_unit=field.canonical_unit,
                    selected_source_value_id=selected.source_value_id,
                    candidate_source_value_ids=value_ids,
                    transformation_evidence_ids=evidence_ids,
                    selection_id=selection.selection_id,
                    conflict_ids=conflict_ids,
                )
            elif field.nullable:
                outcome = DeclaredNullValue(
                    canonical_field_id=field.field_id,
                    reason=NullReason.not_measured if source_values else NullReason.not_in_source,
                    candidate_source_value_ids=value_ids,
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
                > input.mapping_rule_set.capacity.max_transformation_evidence
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
        row_payload = {
            "row_id": row_id,
            "crossmatch_record_type": record.record_type,
            "crossmatch_logical_key": logical_key,
            "entity_level": record.entity_level,
            "projection_policy_version": input.mapping_rule_set.entity_projection_policy.version,
            "projected_field_ids": tuple(item.canonical_field_id for item in outcomes),
            "alignment_status": alignment,
            "source_member_ids": member_ids,
            "fields": [item.model_dump(mode="json") for item in outcomes],
            "conflict_ids": tuple(sorted(set(row_conflict_ids))),
            "evidence_ids": tuple(sorted(set(row_evidence_ids))),
            "source_snapshot_ids": tuple(sorted({member.source_record.source_snapshot_id for member in members})),
        }
        rows.append(_hashed(DatasetRow, row_payload))

    if len(all_evidence) > input.mapping_rule_set.capacity.max_transformation_evidence:
        raise DataArtifactError(DataArtifactErrorCode.capacity_exceeded, "Evidence capacity exceeded")
    producer = DataArtifactProducer(
        producer_name=input.mapping_rule_set.producer_name,
        producer_version=input.producer_version,
        mapping_rule_set_id=input.mapping_rule_set.rule_set_id,
        mapping_rule_set_version=input.mapping_rule_set.version,
        mapping_rule_set_content_hash=input.mapping_rule_set.content_hash,
        conversion_catalog_id=input.conversion_catalog.catalog_id,
        conversion_catalog_version=input.conversion_catalog.version,
        conversion_catalog_content_hash=input.conversion_catalog.content_hash,
    )
    snapshot_ids = tuple(sorted((result.left_source_snapshot.snapshot_id, result.right_source_snapshot.snapshot_id)))
    crossmatch_evidence_ids = tuple(
        sorted(
            {
                evidence_id
                for record in result.records
                for evidence_id in getattr(record, "evidence_ids", ())
            }
        )
    )
    evidence_ids = tuple(sorted({*(item.evidence_id for item in all_evidence), *crossmatch_evidence_ids}))
    common = {
        "manifest_pins": input.manifest_pins.model_dump(mode="json"),
        "source_snapshot_ids": snapshot_ids,
        "evidence_ids": evidence_ids,
        "mapping_rule_set_id": input.mapping_rule_set.rule_set_id,
        "mapping_rule_set_version": input.mapping_rule_set.version,
        "mapping_rule_set_content_hash": input.mapping_rule_set.content_hash,
        "conversion_catalog_id": input.conversion_catalog.catalog_id,
        "conversion_catalog_version": input.conversion_catalog.version,
        "conversion_catalog_content_hash": input.conversion_catalog.content_hash,
        "producer": producer.model_dump(mode="json"),
        "input_hash": input.input_hash,
    }
    dataset = _candidate(
        DatasetArtifactCandidate,
        {
            "kind": "dataset",
            **common,
            "crossmatch_result_id": result.result_id,
            "crossmatch_input_hash": result.input_hash,
            "crossmatch_output_hash": result.output_hash,
            "crossmatch_content_hash": result.content_hash,
            "crossmatch_source_snapshot_ids": snapshot_ids,
            "crossmatch_evidence_ids": crossmatch_evidence_ids,
            "requested_fields": tuple(field.field_id for field in fields),
            "columns": [DatasetColumn(field=field).model_dump(mode="json") for field in fields],
            "rows": [row.model_dump(mode="json") for row in rows],
            "source_values": [value.model_dump(mode="json") for value in all_source_values],
            "transformation_evidence": [item.model_dump(mode="json") for item in all_evidence],
            "selections": [item.model_dump(mode="json") for item in all_selections],
            "conflicts": [item.model_dump(mode="json") for item in all_conflicts],
            "row_count": len(rows),
            "field_count": len(fields),
            "quality_metric_input_declarations": tuple(sorted({metric.value for field in fields for metric in field.quality_metric_inputs})),
            "quality_constraints_reference": input.quality_constraints_reference,
        },
    )
    field_dictionary = _candidate(
        FieldDictionaryArtifactCandidate,
        {
            "kind": "field_dictionary",
            **common,
            "requested_fields": tuple(field.field_id for field in fields),
            "field_definitions": [field.model_dump(mode="json") for field in fields],
        },
    )
    alignments = tuple(_record_key(record) for record in result.records)
    source_members = []
    for side, acquisition in (
        ("left", input.left_acquisition),
        ("right", input.right_acquisition),
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
        source_members.append(
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
                raw_record_reference_registry_hash=(
                    compute_raw_record_reference_registry_hash(references)
                ),
            )
        )
    source_collection = _candidate(
        SourceCollectionArtifactCandidate,
        {
            "kind": "source_collection",
            **common,
            "members": [member.model_dump(mode="json") for member in source_members],
            "source_value_ids": tuple(value.source_value_id for value in all_source_values),
            "crossmatch_result_id": result.result_id,
            "crossmatch_content_hash": result.content_hash,
            "alignment_record_keys": alignments,
            "conflict_record_keys": tuple(_record_key(record) for record in result.records if _alignment_status(record) is AlignmentStatus.conflict),
            "review_required_record_keys": tuple(_record_key(record) for record in result.records if _alignment_status(record) is AlignmentStatus.review_required),
            "inconclusive_record_keys": tuple(_record_key(record) for record in result.records if _alignment_status(record) is AlignmentStatus.inconclusive),
        },
    )
    hash_payload = {
        "schema_version": "1.0.0",
        "dataset": dataset.model_dump(mode="json"),
        "field_dictionary": field_dictionary.model_dump(mode="json"),
        "source_collection": source_collection.model_dump(mode="json"),
        "input_hash": input.input_hash,
    }
    payload = {
        "schema_version": "1.0.0",
        "dataset": dataset,
        "field_dictionary": field_dictionary,
        "source_collection": source_collection,
        "input_hash": input.input_hash,
        "output_hash": compute_data_artifact_output_hash(hash_payload),
    }
    for candidate in (dataset, field_dictionary, source_collection):
        _seal_data_artifact_candidate(candidate)
    return DataArtifactBuildResult.model_validate(payload)
