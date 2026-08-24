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
    compute_crossmatch_record_logical_key,
    compute_crossmatch_content_hash,
)
from app.schemas.data_artifact_identity import derive_canonical_row_identity
from app.schemas.data_artifacts import (
    AlignmentStatus,
    CrossmatchArtifactAuthority,
    CrossmatchDataArtifactAuthority,
    DataArtifactBuildInput,
    DataArtifactAuthority,
    DataArtifactErrorCode,
    DataArtifactProducer,
    DatabaseCellLocator,
    DatasetRow,
    DeclaredNullValue,
    DocumentObservationLocator,
    DocumentResearchInputOrigin,
    DocumentSourceCollectionMember,
    FieldConflictRecord,
    FieldSelectionRecord,
    LimitStatus,
    LimitValue,
    MappedCanonicalValue,
    RawSourceRecordReference,
    SelectionStatus,
    SourceTableArtifactAuthority,
    SourceTableCanonicalRowIdentity,
    SourceTableDataArtifactAuthority,
    SourceTableRowAuthority,
    SourceTableSourceCollectionMember,
    SourceValueCandidate,
    StructuredDatabaseOrigin,
    StructuredSourceCollectionMember,
    TransformationEvidence,
    TypedDocumentObservation,
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

from .conversion import (
    convert_decimal_value,
    decimal_from_source,
    resolve_conversion_rule,
    serialize_decimal,
)
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
    crossmatch_sources: tuple[StructuredSourceCollectionMember, ...]
    source_table_sources: tuple[SourceTableSourceCollectionMember, ...]
    supplemental_document_sources: tuple[DocumentSourceCollectionMember, ...]
    producer: DataArtifactProducer
    authority: DataArtifactAuthority
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
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
    row_count = (
        len(input_value.authority.crossmatch_result.records)
        if isinstance(input_value.authority, CrossmatchDataArtifactAuthority)
        else len(input_value.authority.source_table_admission.rows)
    )
    if row_count > capacity.max_rows:
        raise DataArtifactError(
            DataArtifactErrorCode.capacity_exceeded, "row capacity exceeded"
        )
    if len(requested) * row_count > capacity.max_total_cell_outcomes:
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
    fields = {field.field_id: field for field in manifest.fields}
    if isinstance(input_value.authority, SourceTableDataArtifactAuthority):
        admission = input_value.authority.source_table_admission
        if admission.manifest_pins != input_value.manifest_pins:
            raise DataArtifactError(
                DataArtifactErrorCode.manifest_pin_mismatch,
                "SourceTable admission is not bound to the Data Artifact Manifest pins",
            )
        if (
            admission.mapping_rule_set_id != input_value.mapping_rule_set.rule_set_id
            or admission.mapping_rule_set_version
            != input_value.mapping_rule_set.version
            or admission.mapping_rule_set_content_hash
            != input_value.mapping_rule_set.content_hash
            or admission.conversion_catalog_id
            != input_value.conversion_catalog.catalog_id
            or admission.conversion_catalog_version
            != input_value.conversion_catalog.version
            or admission.conversion_catalog_content_hash
            != input_value.conversion_catalog.content_hash
        ):
            raise DataArtifactError(
                DataArtifactErrorCode.source_table_admission_mismatch,
                "SourceTable admission is not bound to the frozen mapping/conversion policies",
            )
        column_by_field = {
            column.canonical_field_id: column for column in admission.columns
        }
        if not requested <= set(column_by_field):
            raise DataArtifactError(
                DataArtifactErrorCode.unsupported_requested_field,
                "requested fields are not all admitted SourceTable columns",
            )
        for field_id in requested:
            column = column_by_field[field_id]
            field = fields[field_id]
            aliases = tuple(
                alias
                for alias in field.source_aliases_for(admission.source_id)
                if alias.raw_field == column.raw_field
            )
            if len(aliases) != 1 or (
                aliases[0].conversion_rule_id != column.conversion_rule_id
                or aliases[0].source_unit != column.source_unit
                or field.canonical_unit != column.canonical_unit
            ):
                raise DataArtifactError(
                    DataArtifactErrorCode.source_table_admission_mismatch,
                    "SourceTable column conversion binding disagrees with the Manifest",
                )
    return bundle, tuple(fields[field_id] for field_id in input_value.requested_fields)


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
    if isinstance(input_value.authority, SourceTableDataArtifactAuthority):
        admission = input_value.authority.source_table_admission
        if (
            admission.source_result_status != "complete"
            or admission.overall_status.value != "pass"
        ):
            raise DataArtifactError(
                DataArtifactErrorCode.source_table_admission_mismatch,
                "only a complete, passing SourceTableAdmission can build a Dataset",
            )
        cells_by_row: dict[str, list[Any]] = {row.row_id: [] for row in admission.rows}
        for cell in admission.cells:
            cells_by_row.setdefault(cell.row_id, []).append(cell)
        for row_id, cells in cells_by_row.items():
            payload = {cell.locator.raw_field: cell.raw_value for cell in cells}
            if any(
                record_hash
                != compute_raw_data_record_hash(
                    source_id=admission.source_id,
                    row_key=row_key,
                    payload=payload,
                )
                for row_key, record_hash in {
                    cell.locator.row_key: cell.locator.raw_record_content_hash
                    for cell in cells
                }.items()
            ):
                raise DataArtifactError(
                    DataArtifactErrorCode.source_record_hash_mismatch,
                    "SourceTable cell locators do not bind their admitted raw record",
                )
        return

    if not isinstance(input_value.authority, CrossmatchDataArtifactAuthority):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "Crossmatch runtime validation requires Crossmatch authority",
        )
    authority = input_value.authority
    result = authority.crossmatch_result
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
            authority.left_acquisition,
            result.left_source_snapshot,
            result.left_source_mode,
            result.left_data_level,
            result.left_completion,
        ),
        (
            authority.right_acquisition,
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
        for acquisition in (authority.left_acquisition, authority.right_acquisition)
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
    if isinstance(input_value.authority, SourceTableDataArtifactAuthority):
        return
    if not isinstance(input_value.authority, CrossmatchDataArtifactAuthority):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "Crossmatch handoff validation requires Crossmatch authority",
        )
    result = input_value.authority.crossmatch_result
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
    return compute_crossmatch_record_logical_key(record)


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


def _locator(candidate: EntityCandidate, raw_field: str) -> DatabaseCellLocator:
    reference = candidate.source_record
    return DatabaseCellLocator(
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
    locators: list[DatabaseCellLocator | None] = []
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
        "source_snapshot_id": candidate.source_record.source_snapshot_id,
        "source_snapshot_content_hash": candidate.source_record.source_snapshot_content_hash,
        "query_hash": candidate.source_record.query_hash,
        "raw_value": raw_value,
        "source_unit": alias.source_unit,
        "canonical_value": canonical,
        "canonical_unit": field.canonical_unit,
        "alias_priority": alias.priority,
        "source_priority": source_priority,
        "transformation_rule_version": field.transformation_rule_version,
        "conversion_rule_id": alias.conversion_rule_id,
        "conversion_rule_version": conversion_versions[alias.conversion_rule_id],
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
        "origin": {
            "kind": "structured_database",
            "source_table": alias.source_table,
            "raw_record_row_key": candidate.source_record.row_key,
            "raw_record_content_hash": candidate.source_record.record_content_hash,
            "raw_field": alias.raw_field,
            "reference_field": alias.reference_field,
            "reference_value": raw_record.payload.get(alias.reference_field)
            if alias.reference_field
            else None,
            "provenance_field": alias.provenance_field,
            "provenance_value": raw_record.payload.get(alias.provenance_field)
            if alias.provenance_field
            else None,
        },
    }
    return _hashed(SourceValueCandidate, payload)


def _document_uncertainty(
    observation: TypedDocumentObservation,
    *,
    field: FieldDefinition,
    quantity_kind: str,
    conversion_rule,
    input_value: DataArtifactBuildInput,
) -> UncertaintyValue:
    values = (
        observation.uncertainty_positive_raw,
        observation.uncertainty_negative_raw,
    )
    canonical_values = tuple(
        convert_decimal_value(
            value,
            rule_id=conversion_rule.rule_id,
            rule_version=conversion_rule.rule_version,
            source_unit=observation.source_unit,
            target_unit=field.canonical_unit,
            quantity_kind=quantity_kind,
            catalog=input_value.conversion_catalog,
        )
        if value is not None
        else None
        for value in values
    )
    count = sum(item is not None for item in values)
    status = (
        UncertaintyStatus.missing,
        UncertaintyStatus.partial,
        UncertaintyStatus.complete,
    )[count]
    return UncertaintyValue(
        status=status,
        source_positive=values[0],
        source_negative=values[1],
        canonical_positive=canonical_values[0],
        canonical_negative=canonical_values[1],
    )


def _document_source_value(
    *,
    row_id: str,
    observation: TypedDocumentObservation,
    field: FieldDefinition,
    structured_priority_count: int,
    input_value: DataArtifactBuildInput,
    quantity_kind: str,
) -> SourceValueCandidate:
    """Project one admitted typed document observation into a Dataset source value."""

    conversion_rule = resolve_conversion_rule(
        source_unit=observation.source_unit,
        target_unit=field.canonical_unit,
        quantity_kind=quantity_kind,
        catalog=input_value.conversion_catalog,
    )
    canonical: str | None = None
    if observation.parsed_scalar is not None:
        canonical = serialize_decimal(
            convert_decimal_value(
                observation.parsed_scalar,
                rule_id=conversion_rule.rule_id,
                rule_version=conversion_rule.rule_version,
                source_unit=observation.source_unit,
                target_unit=field.canonical_unit,
                quantity_kind=quantity_kind,
                catalog=input_value.conversion_catalog,
            ),
            capacity=input_value.conversion_catalog.decimal_capacity,
        )
    locator = DocumentObservationLocator(
        source_snapshot_id=str(observation.pipeline_source_snapshot.snapshot_id),
        source_snapshot_content_hash=observation.pipeline_source_snapshot.content_hash,
        source_id=observation.pipeline_source_snapshot.source_id,
        query_hash=observation.pipeline_source_snapshot.query_hash,
        research_input_id=str(observation.research_input_id),
        document_parse_id=str(observation.document_parse_id),
        raw_candidate_id=observation.raw_candidate_id,
        parse_quality=observation.parse_quality,
        document_locator=observation.document_locator,
    )
    source_value_id = _stable_id(
        "source_value.document",
        {
            "row_id": row_id,
            "observation_id": observation.observation_id,
            "field_id": field.field_id,
        },
    )
    payload = {
        "source_value_id": source_value_id,
        "canonical_field_id": field.field_id,
        "source_id": f"research_input:{observation.research_input_id}",
        "source_snapshot_id": str(observation.pipeline_source_snapshot.snapshot_id),
        "source_snapshot_content_hash": observation.pipeline_source_snapshot.content_hash,
        "query_hash": observation.pipeline_source_snapshot.query_hash,
        "raw_value": observation.raw_value,
        "source_unit": observation.source_unit,
        "canonical_value": canonical,
        "canonical_unit": field.canonical_unit,
        "alias_priority": 1,
        "source_priority": structured_priority_count + 1,
        "transformation_rule_version": field.transformation_rule_version,
        "conversion_rule_id": conversion_rule.rule_id,
        "conversion_rule_version": conversion_rule.rule_version,
        "uncertainty": _document_uncertainty(
            observation,
            field=field,
            quantity_kind=quantity_kind,
            conversion_rule=conversion_rule,
            input_value=input_value,
        ).model_dump(mode="json"),
        "limit": LimitValue(status=observation.limit_status).model_dump(mode="json"),
        "null_status": observation.null_status,
        "evidence_locator": locator.model_dump(mode="json"),
        "origin": {
            "kind": "document_research_input",
            "research_input_id": str(observation.research_input_id),
            "research_input_content_hash": observation.research_input_content_hash,
            "document_parse_id": str(observation.document_parse_id),
            "persisted_source_snapshot_id": str(
                observation.persisted_source_snapshot_id
            ),
            "pipeline_source_snapshot_id": str(
                observation.pipeline_source_snapshot.snapshot_id
            ),
            "pipeline_source_snapshot_content_hash": (
                observation.pipeline_source_snapshot.content_hash
            ),
            "raw_candidate_id": observation.raw_candidate_id,
            "observation_id": observation.observation_id,
            "parse_quality": observation.parse_quality.value,
            "document_locator": observation.document_locator.model_dump(mode="json"),
        },
    }
    return _hashed(SourceValueCandidate, payload)


def _replace_raw_field(
    locator: DatabaseCellLocator, raw_field: str
) -> DatabaseCellLocator:
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
    if not isinstance(input_value.authority, CrossmatchDataArtifactAuthority):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "Crossmatch Evidence derivation requires Crossmatch authority",
        )
    result = input_value.authority.crossmatch_result
    origin = source_value.origin
    structured = isinstance(origin, StructuredDatabaseOrigin)
    reference_field = origin.reference_field if structured else None
    reference_value = origin.reference_value if structured else None
    provenance_field = origin.provenance_field if structured else None
    provenance_value = origin.provenance_value if structured else None
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
        "reference_field": reference_field,
        "reference_value": reference_value,
        "reference_locator": _replace_raw_field(
            source_value.evidence_locator,
            reference_field,  # type: ignore[arg-type]
        ).model_dump(mode="json")
        if reference_field is not None
        else None,
        "provenance_field": provenance_field,
        "provenance_value": provenance_value,
        "provenance_locator": _replace_raw_field(
            source_value.evidence_locator,
            provenance_field,  # type: ignore[arg-type]
        ).model_dump(mode="json")
        if provenance_field is not None
        else None,
        "authority": {
            "authority_kind": "crossmatch",
            "result_id": result.result_id,
            "result_content_hash": result.content_hash,
            "logical_key": logical_key,
            "evidence_ids": tuple(getattr(record, "evidence_ids", ())),
        },
        "selection_status": status,
        "selection_reason": reason,
    }
    return _hashed(TransformationEvidence, payload)


def _source_table_source_value(
    *,
    row_id: str,
    cell,
    column,
    field: FieldDefinition,
    input_value: DataArtifactBuildInput,
) -> SourceValueCandidate:
    """Project an already-admitted SourceTable cell without re-conversion."""

    locator = cell.locator
    source_value_id = f"source_value.{cell.evidence_id}"
    payload = {
        "source_value_id": source_value_id,
        "canonical_field_id": field.field_id,
        "source_id": locator.source_id,
        "source_snapshot_id": locator.source_snapshot_id,
        "source_snapshot_content_hash": locator.source_snapshot_content_hash,
        "query_hash": locator.query_hash,
        "raw_value": cell.raw_value,
        "source_unit": column.source_unit,
        "canonical_value": cell.canonical_value,
        "canonical_unit": cell.canonical_unit,
        "alias_priority": 1,
        "source_priority": 1,
        "transformation_rule_version": field.transformation_rule_version,
        "conversion_rule_id": column.conversion_rule_id,
        "conversion_rule_version": column.conversion_rule_version,
        "uncertainty": UncertaintyValue(
            status=UncertaintyStatus.not_applicable
        ).model_dump(mode="json"),
        "limit": LimitValue(status=LimitStatus.not_applicable).model_dump(mode="json"),
        "null_status": NullReason.not_measured
        if cell.canonical_value is None
        else None,
        "evidence_locator": locator.model_dump(mode="json"),
        "origin": {
            "kind": "structured_database",
            "source_table": input_value.authority.source_table_admission.source_table,
            "raw_record_row_key": locator.row_key,
            "raw_record_content_hash": locator.raw_record_content_hash,
            "raw_field": locator.raw_field,
        },
    }
    return _hashed(SourceValueCandidate, payload)


def _source_table_evidence(
    source_value: SourceValueCandidate,
    *,
    row_id: str,
    input_value: DataArtifactBuildInput,
    status: SelectionStatus,
    reason: str,
) -> TransformationEvidence:
    locator = source_value.evidence_locator
    origin = source_value.origin
    if not isinstance(locator, DatabaseCellLocator) or not isinstance(
        origin, StructuredDatabaseOrigin
    ):
        raise DataArtifactError(
            DataArtifactErrorCode.source_table_admission_mismatch,
            "SourceTable transformation requires a structured database cell",
        )
    admission = input_value.authority.source_table_admission
    uncertainty_locators = tuple(
        item
        for item in (
            source_value.uncertainty.positive_locator,
            source_value.uncertainty.negative_locator,
        )
        if item is not None
    )
    payload = {
        "evidence_id": source_value.source_value_id.removeprefix("source_value."),
        "target_candidate_kind": "dataset",
        "dataset_row_id": row_id,
        "canonical_field_id": source_value.canonical_field_id,
        "source_value_id": source_value.source_value_id,
        "locator": locator.model_dump(mode="json"),
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
            item.model_dump(mode="json") for item in uncertainty_locators
        ],
        "limit_locator": source_value.limit.locator.model_dump(mode="json")
        if source_value.limit.locator is not None
        else None,
        "reference_field": origin.reference_field,
        "reference_value": origin.reference_value,
        "reference_locator": None,
        "provenance_field": origin.provenance_field,
        "provenance_value": origin.provenance_value,
        "provenance_locator": None,
        "authority": {
            "authority_kind": "source_table",
            "admission_id": admission.admission_id,
            "row_id": row_id,
        },
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


def _derive_source_table_domain_projection(
    input_value: DataArtifactBuildInput,
    *,
    fields: tuple[FieldDefinition, ...],
) -> DataArtifactDomainProjection:
    """Derive the canonical Data Artifact surface from one admitted source table."""

    authority_input = input_value.authority
    if not isinstance(authority_input, SourceTableDataArtifactAuthority):
        raise AssertionError("SourceTable projection requires SourceTable authority")
    admission = authority_input.source_table_admission
    columns_by_field = {
        column.canonical_field_id: column for column in admission.columns
    }
    cells_by_row_field = {
        (cell.row_id, cell.canonical_field_id): cell for cell in admission.cells
    }
    requested_fields = {field.field_id for field in fields}
    if not requested_fields <= set(columns_by_field):
        raise DataArtifactError(
            DataArtifactErrorCode.source_table_admission_mismatch,
            "SourceTable admission does not contain the requested projection",
        )
    manifest = load_frozen_manifest_bundle().field_manifest
    source = next(
        item for item in manifest.sources if item.source_id == admission.source_id
    )
    identity_raw_field = source.row_key_fields[0]
    identity_column = next(
        column for column in admission.columns if column.raw_field == identity_raw_field
    )

    source_values: list[SourceValueCandidate] = []
    transformation_evidence: list[TransformationEvidence] = []
    selections: list[FieldSelectionRecord] = []
    rows: list[DatasetRow] = []
    reason = "SourceTable admission retains the canonical source value"
    for admitted_row in admission.rows:
        row_id = admitted_row.row_id
        outcomes = []
        row_evidence_ids: list[str] = []
        for field in fields:
            column = columns_by_field[field.field_id]
            cell = cells_by_row_field.get((row_id, field.field_id))
            if cell is None:
                raise DataArtifactError(
                    DataArtifactErrorCode.source_table_admission_mismatch,
                    "SourceTable admission is missing a requested cell",
                )
            source_value = _source_table_source_value(
                row_id=row_id,
                cell=cell,
                column=column,
                field=field,
                input_value=input_value,
            )
            status = (
                SelectionStatus.selected
                if source_value.canonical_value is not None
                else SelectionStatus.unselected
            )
            evidence = _source_table_evidence(
                source_value,
                row_id=row_id,
                input_value=input_value,
                status=status,
                reason=reason,
            )
            source_values.append(source_value)
            transformation_evidence.append(evidence)
            row_evidence_ids.append(evidence.evidence_id)
            if source_value.canonical_value is None:
                outcome = DeclaredNullValue(
                    canonical_field_id=field.field_id,
                    reason=NullReason.not_measured,
                    candidate_source_value_ids=(source_value.source_value_id,),
                    transformation_evidence_ids=(evidence.evidence_id,),
                )
            else:
                selection = _hashed(
                    FieldSelectionRecord,
                    {
                        "selection_id": _stable_id(
                            "selection.field",
                            {"row_id": row_id, "field": field.field_id},
                        ),
                        "dataset_row_id": row_id,
                        "canonical_field_id": field.field_id,
                        "selected_source_value_id": source_value.source_value_id,
                        "candidate_source_value_ids": (source_value.source_value_id,),
                        "strategy": "prefer_source_priority_preserve_all",
                        "reason": reason,
                    },
                )
                selections.append(selection)
                outcome = MappedCanonicalValue(
                    canonical_field_id=field.field_id,
                    canonical_value=source_value.canonical_value,
                    canonical_unit=source_value.canonical_unit,
                    selected_source_value_id=source_value.source_value_id,
                    candidate_source_value_ids=(source_value.source_value_id,),
                    transformation_evidence_ids=(evidence.evidence_id,),
                    selection_id=selection.selection_id,
                    conflict_ids=(),
                )
            outcomes.append(outcome)
        rows.append(
            _hashed(
                DatasetRow,
                {
                    "row_id": row_id,
                    "row_authority": SourceTableRowAuthority(
                        admission_id=admission.admission_id,
                        source_table_row_id=row_id,
                        canonical_row_identity=SourceTableCanonicalRowIdentity(
                            identity_field_id=identity_column.canonical_field_id,
                            canonical_identity=admitted_row.canonical_identity,
                        ),
                    ).model_dump(mode="json"),
                    "projection_policy_version": input_value.mapping_rule_set.entity_projection_policy.version,
                    "projected_field_ids": tuple(
                        item.canonical_field_id for item in outcomes
                    ),
                    "fields": [item.model_dump(mode="json") for item in outcomes],
                    "conflict_ids": (),
                    "evidence_ids": tuple(sorted(row_evidence_ids)),
                    "source_snapshot_ids": (admission.source_snapshot_id,),
                },
            )
        )

    references_by_row: dict[tuple[tuple[str, str], ...], RawSourceRecordReference] = {}
    for cell in admission.cells:
        reference = RawSourceRecordReference(
            source_id=admission.source_id,
            source_snapshot_id=admission.source_snapshot_id,
            source_snapshot_content_hash=admission.source_snapshot_content_hash,
            query_hash=admission.query_hash,
            row_key=cell.locator.row_key,
            raw_record_content_hash=cell.locator.raw_record_content_hash,
        )
        previous = references_by_row.setdefault(reference.row_key, reference)
        if previous.raw_record_content_hash != reference.raw_record_content_hash:
            raise DataArtifactError(
                DataArtifactErrorCode.source_table_admission_mismatch,
                "SourceTable cells disagree about raw-record content identity",
            )
    raw_references = tuple(
        sorted(
            references_by_row.values(),
            key=lambda item: (
                item.source_id,
                item.row_key,
                item.raw_record_content_hash,
            ),
        )
    )
    source_snapshot = authority_input.source_snapshot
    source_member = SourceTableSourceCollectionMember(
        source_snapshot=source_snapshot,
        admission_id=admission.admission_id,
        admission_output_hash=admission.output_hash,
        source_id=admission.source_id,
        source_table=admission.source_table,
        source_snapshot_id=admission.source_snapshot_id,
        source_snapshot_content_hash=admission.source_snapshot_content_hash,
        query_hash=admission.query_hash,
        license_note=source_snapshot.license_note,
        raw_record_references=raw_references,
        raw_record_count=len(raw_references),
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
    evidence_ids = tuple(sorted(item.evidence_id for item in transformation_evidence))
    artifact_authority = SourceTableArtifactAuthority(
        admission_id=admission.admission_id,
        admission_output_hash=admission.output_hash,
        source_id=admission.source_id,
        source_table=admission.source_table,
        source_snapshot_id=admission.source_snapshot_id,
        source_snapshot_content_hash=admission.source_snapshot_content_hash,
        evidence_ids=evidence_ids,
    )
    return DataArtifactDomainProjection(
        input_value=input_value,
        fields=fields,
        rows=tuple(rows),
        source_values=tuple(source_values),
        transformation_evidence=tuple(transformation_evidence),
        selections=tuple(selections),
        conflicts=(),
        crossmatch_sources=(),
        source_table_sources=(source_member,),
        supplemental_document_sources=(),
        producer=producer,
        authority=artifact_authority,
        source_snapshot_ids=(admission.source_snapshot_id,),
        evidence_ids=evidence_ids,
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


def _source_members(
    input_value: DataArtifactBuildInput,
) -> tuple[StructuredSourceCollectionMember | SourceTableSourceCollectionMember, ...]:
    members: list[
        StructuredSourceCollectionMember | SourceTableSourceCollectionMember
    ] = []
    for side, acquisition in (
        ("left", input_value.authority.left_acquisition),
        ("right", input_value.authority.right_acquisition),
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
            StructuredSourceCollectionMember(
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


def _document_members(
    input_value: DataArtifactBuildInput,
) -> tuple[DocumentSourceCollectionMember, ...]:
    """Group admitted document observations into one supplemental member per input."""

    grouped: dict[str, list[TypedDocumentObservation]] = {}
    document_observations = (
        input_value.authority.document_observations
        if isinstance(input_value.authority, CrossmatchDataArtifactAuthority)
        else ()
    )
    for observation in document_observations:
        grouped.setdefault(str(observation.research_input_id), []).append(observation)
    members: list[DocumentSourceCollectionMember] = []
    for research_input_id in sorted(grouped):
        observations = sorted(
            grouped[research_input_id], key=lambda item: item.observation_id
        )
        snapshot = observations[0].pipeline_source_snapshot
        if any(item.pipeline_source_snapshot != snapshot for item in observations):
            raise DataArtifactError(
                DataArtifactErrorCode.snapshot_mismatch,
                "document observations disagree about their pipeline snapshot",
            )
        persisted_snapshot_id = str(observations[0].persisted_source_snapshot_id)
        research_input_content_hash = observations[0].research_input_content_hash
        if any(
            str(item.persisted_source_snapshot_id) != persisted_snapshot_id
            or item.research_input_content_hash != research_input_content_hash
            for item in observations
        ):
            raise DataArtifactError(
                DataArtifactErrorCode.snapshot_mismatch,
                "document observations disagree about persisted provenance",
            )
        members.append(
            DocumentSourceCollectionMember(
                source_class="document_research_input",
                pipeline_source_snapshot=snapshot,
                pipeline_source_snapshot_id=snapshot.snapshot_id,
                pipeline_source_snapshot_content_hash=snapshot.content_hash,
                persisted_source_snapshot_id=persisted_snapshot_id,
                research_input_id=research_input_id,
                research_input_content_hash=research_input_content_hash,
                document_parse_ids=tuple(
                    dict.fromkeys(str(item.document_parse_id) for item in observations)
                ),
                observation_ids=tuple(item.observation_id for item in observations),
            )
        )
    return tuple(members)


def derive_document_snapshot_bindings(
    input_value: DataArtifactBuildInput,
) -> dict[str, str]:
    """Derive the exact persisted snapshot binding from validated observations."""

    bindings: dict[str, str] = {}
    document_observations = (
        input_value.authority.document_observations
        if isinstance(input_value.authority, CrossmatchDataArtifactAuthority)
        else ()
    )
    for observation in sorted(
        document_observations,
        key=lambda item: (item.pipeline_snapshot_id, item.observation_id),
    ):
        pipeline_id = observation.pipeline_snapshot_id
        persisted_id = str(observation.persisted_source_snapshot_id)
        existing = bindings.setdefault(pipeline_id, persisted_id)
        if existing != persisted_id:
            raise DataArtifactError(
                DataArtifactErrorCode.snapshot_mismatch,
                "one pipeline document snapshot must bind exactly one persisted snapshot",
            )
    return {key: bindings[key] for key in sorted(bindings)}


def derive_data_artifact_domain_projection(
    input_value: DataArtifactBuildInput,
) -> DataArtifactDomainProjection:
    """Derive the complete expected Data Artifact domain from canonical frozen inputs."""

    validate_runtime_input_integrity(input_value)
    validate_frozen_crossmatch_handoff(input_value)
    bundle, fields = validate_policy_bindings(input_value)
    if isinstance(input_value.authority, SourceTableDataArtifactAuthority):
        return _derive_source_table_domain_projection(
            input_value,
            fields=fields,
        )
    if not isinstance(input_value.authority, CrossmatchDataArtifactAuthority):
        raise DataArtifactError(
            DataArtifactErrorCode.crossmatch_result_mismatch,
            "Crossmatch projection requires Crossmatch authority",
        )
    result = input_value.authority.crossmatch_result
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
        for acquisition in (
            input_value.authority.left_acquisition,
            input_value.authority.right_acquisition,
        )
        for record in acquisition.records
    }

    all_source_values: list[SourceValueCandidate] = []
    all_evidence: list[TransformationEvidence] = []
    all_selections: list[FieldSelectionRecord] = []
    all_conflicts: list[FieldConflictRecord] = []
    rows: list[DatasetRow] = []
    document_observations_by_key: dict[
        tuple[str, str], tuple[TypedDocumentObservation, ...]
    ] = {}
    document_observations = input_value.authority.document_observations
    for observation in document_observations:
        key = (observation.crossmatch_logical_key, observation.canonical_field_id)
        document_observations_by_key.setdefault(key, ())
        document_observations_by_key[key] = (
            *document_observations_by_key[key],
            observation,
        )
    document_snapshot_ids: set[str] = set()
    for record in result.records:
        logical_key = _record_key(record)
        row_id = _stable_id("dataset_row", logical_key)
        member_ids = _record_members(record)
        members = tuple(candidate_by_id[candidate_id] for candidate_id in member_ids)
        alignment = _alignment_status(record)
        outcomes = []
        row_conflict_ids: list[str] = []
        row_evidence_ids: list[str] = []
        row_document_snapshot_ids: set[str] = set()
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
            row_observations = document_observations_by_key.get(
                (logical_key, field.field_id), ()
            )
            if not applicable_members and not row_observations:
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
            structured_priority_count = len(field.source_priority)
            for observation in row_observations:
                source_values.append(
                    _document_source_value(
                        row_id=row_id,
                        observation=observation,
                        field=field,
                        structured_priority_count=structured_priority_count,
                        input_value=input_value,
                        quantity_kind=_quantity_kind(field, bundle),
                    )
                )
                document_snapshot_ids.add(
                    str(observation.pipeline_source_snapshot.snapshot_id)
                )
                row_document_snapshot_ids.add(
                    str(observation.pipeline_source_snapshot.snapshot_id)
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
            identity_unresolved = alignment in {
                AlignmentStatus.inconclusive,
                AlignmentStatus.review_required,
                AlignmentStatus.rejected,
                AlignmentStatus.conflict,
            }
            structured_non_null = [
                item
                for item in non_null
                if isinstance(item.origin, StructuredDatabaseOrigin)
            ]
            document_non_null = [
                item
                for item in non_null
                if isinstance(item.origin, DocumentResearchInputOrigin)
            ]
            selected = None
            consensus = False
            if structured_non_null:
                # Approved structured sources outrank supplemental documents.
                selected = structured_non_null[0]
            elif document_non_null and not identity_unresolved:
                distinct = {item.canonical_value for item in document_non_null}
                if len(distinct) == 1 and len(document_non_null) > 1:
                    # Equal document values form the canonical outcome together;
                    # no candidate is promoted to a scientific winner.
                    consensus = True
                elif len(distinct) == 1:
                    selected = document_non_null[0]
                # Conflicting document values without a structured winner keep
                # the field unresolved; the conflict record above is retained.
            identity_unresolved = identity_unresolved or (
                selected is None and not consensus and bool(document_non_null)
            )
            selection_reason = (
                f"crossmatch alignment remains {alignment.value}; no field winner is selected"
                if identity_unresolved
                else "equal admitted document values form the canonical consensus; "
                "no scientific winner is selected"
                if consensus
                else "highest declared source and alias priority; every candidate is retained"
            )
            selection = None
            if (selected is not None or consensus) and not identity_unresolved:
                selection = _hashed(
                    FieldSelectionRecord,
                    {
                        "selection_id": _stable_id(
                            "selection.field",
                            {"row_id": row_id, "field": field.field_id},
                        ),
                        "dataset_row_id": row_id,
                        "canonical_field_id": field.field_id,
                        "selected_source_value_id": selected.source_value_id
                        if selected is not None
                        else None,
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
                    reason=(
                        f"crossmatch alignment remains {alignment.value}"
                        if alignment
                        in {
                            AlignmentStatus.inconclusive,
                            AlignmentStatus.review_required,
                            AlignmentStatus.rejected,
                            AlignmentStatus.conflict,
                        }
                        else "admitted document values conflict without a structured winner"
                    ),
                    candidate_source_value_ids=source_value_ids,
                    transformation_evidence_ids=evidence_ids,
                    conflict_ids=conflict_ids,
                )
            elif consensus or selected is not None:
                outcome = MappedCanonicalValue(
                    canonical_field_id=field.field_id,
                    canonical_value=(
                        document_non_null[0].canonical_value
                        if consensus
                        else selected.canonical_value  # type: ignore[index,union-attr]
                    ),
                    canonical_unit=field.canonical_unit,
                    selected_source_value_id=(
                        selected.source_value_id if selected is not None else None
                    ),
                    candidate_source_value_ids=source_value_ids,
                    transformation_evidence_ids=evidence_ids,
                    selection_id=selection.selection_id,  # type: ignore[union-attr]
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
                    "row_authority": {
                        "authority_kind": "crossmatch",
                        "record_type": record.record_type,
                        "logical_key": logical_key,
                        "entity_level": record.entity_level.value,
                        "canonical_row_identity": derive_canonical_row_identity(
                            record,
                            members,
                            alignment_status=alignment,
                        ),
                        "alignment_status": alignment.value,
                        "source_member_ids": member_ids,
                    },
                    "projection_policy_version": input_value.mapping_rule_set.entity_projection_policy.version,
                    "projected_field_ids": tuple(
                        item.canonical_field_id for item in outcomes
                    ),
                    "fields": [item.model_dump(mode="json") for item in outcomes],
                    "conflict_ids": tuple(sorted(set(row_conflict_ids))),
                    "evidence_ids": tuple(sorted(set(row_evidence_ids))),
                    "source_snapshot_ids": tuple(
                        sorted(
                            {
                                member.source_record.source_snapshot_id
                                for member in members
                            }
                            | row_document_snapshot_ids
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
    crossmatch_snapshot_ids = tuple(
        sorted(
            (
                result.left_source_snapshot.snapshot_id,
                result.right_source_snapshot.snapshot_id,
            )
        )
    )
    source_snapshot_ids = tuple(
        sorted({*crossmatch_snapshot_ids, *document_snapshot_ids})
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
    artifact_authority = CrossmatchArtifactAuthority(
        result_id=result.result_id,
        input_hash=result.input_hash,
        output_hash=result.output_hash,
        content_hash=result.content_hash,
        source_snapshot_ids=crossmatch_snapshot_ids,
        evidence=crossmatch_evidence,
        evidence_ids=crossmatch_evidence_ids,
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
    )
    evidence_ids = tuple(
        sorted(
            {
                *(item.evidence_id for item in all_evidence),
                *crossmatch_evidence_ids,
            }
        )
    )
    source_members = _source_members(input_value)
    return DataArtifactDomainProjection(
        input_value=input_value,
        fields=fields,
        rows=tuple(rows),
        source_values=tuple(all_source_values),
        transformation_evidence=tuple(all_evidence),
        selections=tuple(all_selections),
        conflicts=tuple(all_conflicts),
        crossmatch_sources=tuple(
            item
            for item in source_members
            if isinstance(item, StructuredSourceCollectionMember)
        ),
        source_table_sources=tuple(
            item
            for item in source_members
            if isinstance(item, SourceTableSourceCollectionMember)
        ),
        supplemental_document_sources=_document_members(input_value),
        producer=producer,
        authority=artifact_authority,
        source_snapshot_ids=source_snapshot_ids,
        evidence_ids=evidence_ids,
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
    "derive_document_snapshot_bindings",
    "derive_data_artifact_domain_projection",
    "derive_field_conflicts",
    "numeric_values_agree",
    "validate_frozen_crossmatch_handoff",
    "validate_policy_bindings",
    "validate_runtime_input_integrity",
]
