"""Publisher admission validators for sealed C-04 Artifact candidates."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_output_hash,
)
from app.schemas.manifest import DataType
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from .policy import load_mapping_rule_set, load_unit_conversion_catalog


Candidate = DatasetArtifactCandidate | FieldDictionaryArtifactCandidate | SourceCollectionArtifactCandidate


class AdmissionContext(Protocol):
    candidate: Candidate
    source_snapshot_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]


def _candidate(context: AdmissionContext) -> Candidate:
    candidate = context.candidate
    if not isinstance(candidate, (DatasetArtifactCandidate, FieldDictionaryArtifactCandidate, SourceCollectionArtifactCandidate)):
        raise ValueError("unsupported C-04 Artifact candidate type")
    return candidate


def _revalidate(candidate: Candidate) -> Candidate:
    return type(candidate).model_validate(candidate.model_dump(mode="json"))


def _publication_context(candidate: Candidate) -> DataArtifactBuildInput:
    context = getattr(candidate, "_artifact_publication_context", None)
    if not isinstance(context, DataArtifactBuildInput):
        raise ValueError("candidate lacks its original typed C-04 admission context")
    if context.input_hash != candidate.input_hash:
        raise ValueError("candidate input hash disagrees with its admission context")
    return context


def _replay_candidate(candidate: Candidate) -> Candidate:
    """Rebuild the candidate from frozen raw inputs and compare exact typed content."""

    fingerprint = compute_data_artifact_output_hash(candidate)
    if fingerprint != candidate.output_hash:
        raise ValueError("candidate output hash mismatch")
    cached = getattr(candidate, "_artifact_publication_replay_cache", None)
    if (
        isinstance(cached, tuple)
        and len(cached) == 2
        and cached[0] == fingerprint
        and isinstance(
            cached[1],
            (
                DatasetArtifactCandidate,
                FieldDictionaryArtifactCandidate,
                SourceCollectionArtifactCandidate,
            ),
        )
    ):
        return cached[1]

    # Import locally so the package-level public entrypoint can attach the same
    # frozen C-08 checks and process-local admission context without a cycle.
    from services.data_pipeline.data_artifacts import build_data_artifact_candidates

    replayed = build_data_artifact_candidates(_publication_context(candidate))
    expected: Candidate
    if isinstance(candidate, DatasetArtifactCandidate):
        expected = replayed.dataset
    elif isinstance(candidate, FieldDictionaryArtifactCandidate):
        expected = replayed.field_dictionary
    else:
        expected = replayed.source_collection

    candidate_payload = candidate.model_dump(mode="json", exclude_none=True)
    expected_payload = expected.model_dump(mode="json", exclude_none=True)
    if candidate_payload != expected_payload:
        raise ValueError(
            "candidate content does not match deterministic replay from its typed input"
        )
    object.__setattr__(
        candidate,
        "_artifact_publication_replay_cache",
        (fingerprint, expected),
    )
    return expected


def _revalidate_and_replay(candidate: Candidate) -> Candidate:
    revalidated = _revalidate(candidate)
    _replay_candidate(candidate)
    return revalidated


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
    producer = candidate.producer
    if (
        producer.producer_name != rule_set.producer_name
        or producer.producer_version != rule_set.producer_version
        or producer.mapping_rule_set_id != rule_set.rule_set_id
        or producer.mapping_rule_set_version != rule_set.version
        or producer.mapping_rule_set_content_hash != rule_set.content_hash
        or producer.conversion_catalog_id != catalog.catalog_id
        or producer.conversion_catalog_version != catalog.version
        or producer.conversion_catalog_content_hash != catalog.content_hash
    ):
        raise ValueError("candidate producer is not bound to frozen policies")


def _numeric_collection_agrees(values: list[Decimal], rule_set) -> bool:
    if len(values) <= 1:
        return True
    comparison = rule_set.numeric_comparison
    minimum = min(values)
    maximum = max(values)
    difference = maximum - minimum
    relative = difference / max(
        abs(maximum),
        abs(minimum),
        comparison.relative_denominator_floor,
    )
    compare = (
        (lambda value, threshold: value <= threshold)
        if comparison.threshold_inclusive
        else (lambda value, threshold: value < threshold)
    )
    return difference == 0 or compare(
        difference, comparison.absolute_tolerance
    ) or compare(relative, comparison.relative_tolerance)


def validate_data_artifact_evidence(context: AdmissionContext) -> None:
    candidate = _revalidate_and_replay(_candidate(context))
    if tuple(context.source_snapshot_ids) != candidate.source_snapshot_ids:
        raise ValueError("SourceSnapshot references disagree with candidate")
    if tuple(context.evidence_ids) != candidate.evidence_ids:
        raise ValueError("Evidence references disagree with candidate")
    if isinstance(candidate, DatasetArtifactCandidate):
        evidence_by_id = {item.evidence_id: item for item in candidate.transformation_evidence}
        source_values = {item.source_value_id: item for item in candidate.source_values}
        if len(evidence_by_id) != len(candidate.transformation_evidence):
            raise ValueError("duplicate transformation Evidence")
        if len(source_values) != len(candidate.source_values):
            raise ValueError("duplicate source value")
        for evidence in evidence_by_id.values():
            source_value = source_values.get(evidence.source_value_id)
            if source_value is None or evidence.locator != source_value.evidence_locator:
                raise ValueError("transformation Evidence is not bound to its source value")
            if evidence.evidence_id not in candidate.evidence_ids:
                raise ValueError("transformation Evidence is absent from candidate references")


def validate_data_artifact_domain(context: AdmissionContext) -> None:
    candidate = _revalidate_and_replay(_candidate(context))
    _validate_frozen_bindings(candidate)
    if candidate.output_hash != compute_data_artifact_output_hash(candidate):
        raise ValueError("candidate output hash mismatch")
    if isinstance(candidate, DatasetArtifactCandidate):
        if candidate.row_count != len(candidate.rows) or candidate.field_count != len(candidate.columns):
            raise ValueError("Dataset dimensions disagree with content")
        source_values_by_id = {
            item.source_value_id: item for item in candidate.source_values
        }
        source_ids = set(source_values_by_id)
        evidence_ids = {item.evidence_id for item in candidate.transformation_evidence}
        definitions = {column.field.field_id: column.field for column in candidate.columns}
        rule_set = load_mapping_rule_set()
        for row in candidate.rows:
            allowed = rule_set.entity_projection_policy.allowed_for(row.entity_level)
            expected_projection = tuple(
                field_id
                for field_id in candidate.requested_fields
                if definitions[field_id].object_type in allowed
            )
            if (
                row.projection_policy_version
                != rule_set.entity_projection_policy.version
                or row.projected_field_ids != expected_projection
            ):
                raise ValueError("Dataset row violates frozen entity projection policy")
            for field in row.fields:
                if not set(field.candidate_source_value_ids) <= source_ids:
                    raise ValueError("Dataset cell refers to an unknown source value")
                if not set(field.transformation_evidence_ids) <= evidence_ids:
                    raise ValueError("Dataset cell refers to unknown Evidence")
                values = [
                    source_values_by_id[source_value_id]
                    for source_value_id in field.candidate_source_value_ids
                    if source_values_by_id[source_value_id].canonical_value is not None
                ]
                definition = definitions[field.canonical_field_id]
                if definition.data_type in {DataType.integer, DataType.number}:
                    agrees = _numeric_collection_agrees(
                        [Decimal(item.canonical_value) for item in values],
                        rule_set,
                    )
                else:
                    agrees = len({item.canonical_value for item in values}) <= 1
                if agrees == bool(getattr(field, "conflict_ids", ())):
                    raise ValueError("Dataset conflict registry hides or invents a conflict")
                for conflict_id in getattr(field, "conflict_ids", ()):
                    conflict = next(
                        item
                        for item in candidate.conflicts
                        if item.conflict_id == conflict_id
                    )
                    if definition.data_type in {DataType.integer, DataType.number}:
                        numbers = [Decimal(item.canonical_value) for item in values]
                        expected_denominator = max(
                            *(abs(value) for value in numbers),
                            rule_set.numeric_comparison.relative_denominator_floor,
                        )
                        if conflict.relative_denominator != expected_denominator:
                            raise ValueError(
                                "Dataset conflict relative denominator is not frozen"
                            )
        if any(
            conflict.comparison_policy_version
            != rule_set.conflict_comparison_policy_version
            for conflict in candidate.conflicts
        ):
            raise ValueError("Dataset conflict policy version is not frozen")
        frozen_fields = {
            item.field_id: item for item in load_frozen_manifest_bundle().field_manifest.fields
        }
        if tuple(
            frozen_fields[field_id] for field_id in candidate.requested_fields
        ) != tuple(column.field for column in candidate.columns):
            raise ValueError("Dataset columns are not frozen Field Manifest definitions")
    elif isinstance(candidate, FieldDictionaryArtifactCandidate):
        frozen_fields = {
            item.field_id: item for item in load_frozen_manifest_bundle().field_manifest.fields
        }
        if tuple(
            frozen_fields[field_id] for field_id in candidate.requested_fields
        ) != candidate.field_definitions:
            raise ValueError("FieldDictionary definitions are not repository-frozen")


def validate_data_artifact_quality_prerequisites(context: AdmissionContext) -> None:
    candidate = _revalidate_and_replay(_candidate(context))
    if candidate.quality_evaluation_status != "not_evaluated":
        raise ValueError("C-04 must not evaluate C-05 quality")
    if isinstance(candidate, DatasetArtifactCandidate) and not candidate.quality_metric_input_declarations:
        raise ValueError("Dataset must declare its downstream quality inputs")


__all__ = [
    "validate_data_artifact_domain",
    "validate_data_artifact_evidence",
    "validate_data_artifact_quality_prerequisites",
]
