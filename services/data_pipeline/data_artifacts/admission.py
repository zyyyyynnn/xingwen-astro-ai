"""Independent Publisher admission validators for C-04 candidates.

This module deliberately never calls the production candidate assembler.  It
reparses the immutable build snapshot and proves the public candidate against
raw acquisition records and frozen manifests.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_context_hash,
    compute_data_artifact_output_hash,
)
from app.schemas.manifest import DataType
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from .policy import load_mapping_rule_set, load_unit_conversion_catalog


Candidate = (
    DatasetArtifactCandidate
    | FieldDictionaryArtifactCandidate
    | SourceCollectionArtifactCandidate
)


class AdmissionContext(Protocol):
    candidate: Candidate
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _candidate(context: AdmissionContext) -> Candidate:
    candidate = context.candidate
    if not isinstance(
        candidate,
        (DatasetArtifactCandidate, FieldDictionaryArtifactCandidate, SourceCollectionArtifactCandidate),
    ):
        raise ValueError("unsupported C-04 Artifact candidate type")
    return candidate


def _revalidate(candidate: Candidate) -> Candidate:
    return type(candidate).model_validate(candidate.model_dump(mode="json"))


def _publication_context(candidate: Candidate) -> DataArtifactBuildInput:
    snapshot = getattr(candidate, "_artifact_publication_context", None)
    if snapshot is None or not hasattr(snapshot, "input_json"):
        raise ValueError("candidate lacks its immutable C-04 admission snapshot")
    try:
        input_value = DataArtifactBuildInput.model_validate_json(snapshot.input_json)
    except Exception as exc:
        raise ValueError("immutable C-04 admission snapshot is invalid") from exc
    if input_value.input_hash != candidate.input_hash:
        raise ValueError("candidate input hash disagrees with its admission snapshot")
    if snapshot.context_hash != compute_data_artifact_context_hash(
        input_value, input_json=snapshot.input_json
    ):
        raise ValueError("candidate admission context commitment is invalid")
    return input_value


def _validate_frozen_bindings(candidate: Candidate) -> None:
    rule_set = load_mapping_rule_set()
    catalog = load_unit_conversion_catalog()
    bundle = load_frozen_manifest_bundle()
    pins = candidate.manifest_pins
    expected_pins = (
        bundle.case_manifest.case_id,
        bundle.case_manifest.manifest_version,
        bundle.case_manifest.content_hash,
        bundle.field_manifest.manifest_id,
        bundle.field_manifest.manifest_version,
        bundle.field_manifest.content_hash,
    )
    actual_pins = (
        pins.case_manifest_id,
        pins.case_manifest_version,
        pins.case_manifest_content_hash,
        pins.field_manifest_id,
        pins.field_manifest_version,
        pins.field_manifest_content_hash,
    )
    if actual_pins != expected_pins:
        raise ValueError("candidate Manifest pins are not repository-frozen")
    if (
        candidate.mapping_rule_set_id,
        candidate.mapping_rule_set_version,
        candidate.mapping_rule_set_content_hash,
    ) != (rule_set.rule_set_id, rule_set.version, rule_set.content_hash):
        raise ValueError("candidate MappingRuleSet binding is not repository-frozen")
    if (
        candidate.conversion_catalog_id,
        candidate.conversion_catalog_version,
        candidate.conversion_catalog_content_hash,
    ) != (catalog.catalog_id, catalog.version, catalog.content_hash):
        raise ValueError("candidate UnitConversionCatalog binding is not repository-frozen")


def _numeric_collection_agrees(values: list[Decimal], rule_set) -> bool:
    if len(values) <= 1:
        return True
    comparison = rule_set.numeric_comparison
    minimum, maximum = min(values), max(values)
    difference = maximum - minimum
    relative = difference / max(
        abs(maximum), abs(minimum), comparison.relative_denominator_floor
    )
    compare = (
        (lambda value, threshold: value <= threshold)
        if comparison.threshold_inclusive
        else (lambda value, threshold: value < threshold)
    )
    return difference == 0 or compare(difference, comparison.absolute_tolerance) or compare(
        relative, comparison.relative_tolerance
    )


def _independent_dataset(candidate: DatasetArtifactCandidate, input_value: DataArtifactBuildInput) -> None:
    from .pipeline import (
        _canonical_value,
        _limit,
        _record_key,
        _record_members,
        _stable_id,
        _uncertainty,
    )

    _validate_frozen_bindings(candidate)
    bundle = load_frozen_manifest_bundle()
    fields = {field.field_id: field for field in bundle.field_manifest.fields}
    if tuple(fields[field_id] for field_id in candidate.requested_fields) != tuple(
        column.field for column in candidate.columns
    ):
        raise ValueError("Dataset columns are not an exact frozen Manifest projection")
    conversion_versions = {
        rule.rule_id: rule.rule_version for rule in bundle.field_manifest.conversion_rules
    }
    candidates_by_id = {
        item.candidate_id: item for item in input_value.crossmatch_result.candidates
    }
    entity_by_source_value_id: dict[str, object] = {}
    for record in input_value.crossmatch_result.records:
        row_id = _stable_id("dataset_row", _record_key(record))
        for candidate_id in _record_members(record):
            entity = candidates_by_id[candidate_id]
            for field in fields.values():
                for alias in field.source_aliases_for(entity.source_record.source_id):
                    entity_by_source_value_id[
                        _stable_id(
                            "source_value",
                            {
                                "row_id": row_id,
                                "candidate_id": entity.candidate_id,
                                "field_id": field.field_id,
                                "raw_field": alias.raw_field,
                            },
                        )
                    ] = entity
    raw_records = {
        (record.source_id, record.row_key): record
        for acquisition in (input_value.left_acquisition, input_value.right_acquisition)
        for record in acquisition.records
    }
    source_values = {item.source_value_id: item for item in candidate.source_values}
    for value in source_values.values():
        entity = entity_by_source_value_id.get(value.source_value_id)
        raw = raw_records.get((value.source_id, value.raw_record_row_key))
        if entity is None or raw is None:
            raise ValueError("SourceValue does not resolve to an acquired C-08 record")
        if raw.content_hash != value.raw_record_content_hash:
            raise ValueError("SourceValue raw record hash disagrees with acquisition")
        field = fields.get(value.canonical_field_id)
        if field is None:
            raise ValueError("SourceValue uses a field outside the frozen Manifest")
        aliases = tuple(
            alias
            for alias in field.source_aliases_for(value.source_id)
            if alias.raw_field == value.raw_field and alias.source_table == value.source_table
        )
        if len(aliases) != 1:
            raise ValueError("SourceValue does not resolve to one frozen source alias")
        alias = aliases[0]
        expected_priority = field.source_priority.index(value.source_id) + 1
        if value.source_priority != expected_priority or value.alias_priority != alias.priority:
            raise ValueError("SourceValue priority disagrees with frozen Manifest")
        raw_value = raw.payload.get(alias.raw_field)
        if raw_value != value.raw_value:
            raise ValueError("SourceValue raw payload disagrees with acquisition")
        normalized_identity = next(
            (
                identity.normalized_value
                for identity in entity.identity_values
                if field.object_identity_key
                and identity.field_id == field.field_id
                and identity.locator.raw_field == alias.raw_field
            ),
            None,
        )
        expected_canonical = None
        if raw_value is not None:
            expected_canonical = normalized_identity or _canonical_value(
                raw_value,
                field,
                alias,
                input_value,
                bundle,
                conversion_versions,
            )
        if field.data_type is DataType.string and expected_canonical == "":
            expected_canonical = None
        if value.canonical_value != expected_canonical:
            raise ValueError("SourceValue canonical value disagrees with independent conversion")
        if value.source_unit != alias.source_unit or value.canonical_unit != field.canonical_unit:
            raise ValueError("SourceValue unit binding disagrees with frozen Manifest")
        expected_uncertainty = _uncertainty(
            raw, entity, field, alias, input_value, bundle, conversion_versions
        )
        expected_limit = _limit(raw, entity, alias, raw_value)
        if value.uncertainty != expected_uncertainty or value.limit != expected_limit:
            raise ValueError("SourceValue uncertainty or limit is not independently derived")
        if value.reference_value != (
            raw.payload.get(alias.reference_field) if alias.reference_field else None
        ) or value.provenance_value != (
            raw.payload.get(alias.provenance_field) if alias.provenance_field else None
        ):
            raise ValueError("SourceValue reference/provenance disagrees with raw payload")

    rule_set = load_mapping_rule_set()
    definitions = {column.field.field_id: column.field for column in candidate.columns}
    for row in candidate.rows:
        allowed = rule_set.entity_projection_policy.allowed_for(row.entity_level)
        expected_projection = tuple(
            field_id
            for field_id in candidate.requested_fields
            if definitions[field_id].object_type in allowed
        )
        if row.projected_field_ids != expected_projection:
            raise ValueError("Dataset row violates frozen entity projection policy")
        for outcome in row.fields:
            values = [
                source_values[item]
                for item in outcome.candidate_source_value_ids
                if item in source_values and source_values[item].canonical_value is not None
            ]
            field = definitions[outcome.canonical_field_id]
            if field.data_type in {DataType.integer, DataType.number}:
                agrees = _numeric_collection_agrees(
                    [Decimal(item.canonical_value) for item in values], rule_set
                )
            else:
                agrees = len({item.canonical_value for item in values}) <= 1
            if agrees == bool(getattr(outcome, "conflict_ids", ())):
                raise ValueError("Dataset conflict registry is not independently derived")

    expected_canonical_hash = compute_data_artifact_canonical_content_hash(candidate)
    if candidate.canonical_content_hash != expected_canonical_hash:
        raise ValueError("Dataset canonical content hash is invalid")
    if candidate.output_hash != compute_data_artifact_output_hash(candidate):
        raise ValueError("candidate output hash mismatch")


def _independent_source_collection(
    candidate: SourceCollectionArtifactCandidate, input_value: DataArtifactBuildInput
) -> None:
    _validate_frozen_bindings(candidate)
    expected = {
        acquisition.snapshot.source_id: {
            (
                record.source_id,
                acquisition.snapshot.snapshot_id,
                acquisition.snapshot.content_hash,
                acquisition.snapshot.query_hash,
                record.row_key,
                record.content_hash,
            )
            for record in acquisition.records
        }
        for acquisition in (input_value.left_acquisition, input_value.right_acquisition)
    }
    actual = {
        member.source_id: {
            (
                reference.source_id,
                reference.source_snapshot_id,
                reference.source_snapshot_content_hash,
                reference.query_hash,
                reference.row_key,
                reference.raw_record_content_hash,
            )
            for reference in member.raw_record_references
        }
        for member in candidate.members
    }
    if actual != expected:
        raise ValueError("SourceCollection record registry is not an exact acquisition set")
    if candidate.output_hash != compute_data_artifact_output_hash(candidate):
        raise ValueError("candidate output hash mismatch")


def validate_data_artifact_candidates_against_input(
    bundle: DataArtifactBuildResult | Candidate,
    input_value: DataArtifactBuildInput,
) -> None:
    """Independent pre-seal admission used by both builder and Publisher."""

    if isinstance(bundle, DataArtifactBuildResult):
        candidates = (bundle.dataset, bundle.field_dictionary, bundle.source_collection)
    else:
        candidates = (bundle,)
    for candidate in candidates:
        _revalidate(candidate)
        if isinstance(candidate, DatasetArtifactCandidate):
            _independent_dataset(candidate, input_value)
        elif isinstance(candidate, FieldDictionaryArtifactCandidate):
            _validate_frozen_bindings(candidate)
            frozen = load_frozen_manifest_bundle().field_manifest
            expected = tuple(
                item for item in frozen.fields if item.field_id in candidate.requested_fields
            )
            if candidate.field_definitions != expected:
                raise ValueError("FieldDictionary is not an exact Manifest projection")
        else:
            _independent_source_collection(candidate, input_value)


def _independent_validate(candidate: Candidate) -> Candidate:
    input_value = _publication_context(candidate)
    validate_data_artifact_candidates_against_input(candidate, input_value)
    return _revalidate(candidate)


def validate_data_artifact_evidence(context: AdmissionContext) -> None:
    candidate = _independent_validate(_candidate(context))
    if tuple(context.source_snapshot_ids) != candidate.source_snapshot_ids:
        raise ValueError("SourceSnapshot references disagree with candidate")
    if tuple(context.evidence_ids) != candidate.evidence_ids:
        raise ValueError("Evidence references disagree with candidate")


def validate_data_artifact_domain(context: AdmissionContext) -> None:
    candidate = _independent_validate(_candidate(context))
    if isinstance(candidate, DatasetArtifactCandidate):
        if candidate.row_count != len(candidate.rows) or candidate.field_count != len(candidate.columns):
            raise ValueError("Dataset dimensions disagree with content")


def validate_data_artifact_quality_prerequisites(context: AdmissionContext) -> None:
    candidate = _independent_validate(_candidate(context))
    if candidate.quality_evaluation_status != "not_evaluated":
        raise ValueError("C-04 must not evaluate C-05 quality")
    if isinstance(candidate, DatasetArtifactCandidate) and not candidate.quality_metric_input_declarations:
        raise ValueError("Dataset must declare its downstream quality inputs")


__all__ = [
    "validate_data_artifact_candidates_against_input",
    "validate_data_artifact_domain",
    "validate_data_artifact_evidence",
    "validate_data_artifact_quality_prerequisites",
]
