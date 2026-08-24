"""Independent, projection-based Publisher admission for Data Artifact candidates."""

from __future__ import annotations

from typing import Protocol

from pydantic import ValidationError

from app.schemas.data_artifacts import (
    CrossmatchArtifactAuthority,
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_context_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
)

from .projection import (
    DataArtifactDomainProjection,
    derive_data_artifact_domain_projection,
)


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
        (
            DatasetArtifactCandidate,
            FieldDictionaryArtifactCandidate,
            SourceCollectionArtifactCandidate,
        ),
    ):
        raise ValueError("unsupported Data Artifact candidate type")
    return candidate


def _revalidate(candidate: Candidate) -> Candidate:
    return type(candidate).model_validate(candidate.model_dump(mode="json"))


def _publication_input(candidate: Candidate) -> DataArtifactBuildInput:
    snapshot = getattr(candidate, "_artifact_publication_context", None)
    if snapshot is None or not hasattr(snapshot, "input_json"):
        raise ValueError(
            "candidate lacks its immutable Data Artifact admission snapshot"
        )
    try:
        input_value = DataArtifactBuildInput.model_validate_json(snapshot.input_json)
    except ValidationError as exc:
        raise ValueError(
            "immutable Data Artifact admission snapshot is invalid"
        ) from exc
    if (
        snapshot.input_hash != input_value.input_hash
        or input_value.input_hash != candidate.input_hash
    ):
        raise ValueError("candidate input hash disagrees with its admission snapshot")
    expected_context_hash = compute_data_artifact_context_hash(
        input_value, input_json=snapshot.input_json
    )
    if snapshot.context_hash != expected_context_hash:
        raise ValueError("candidate admission context commitment is invalid")
    return input_value


def _validate_common(
    candidate: Candidate, projection: DataArtifactDomainProjection
) -> None:
    input_value = projection.input_value
    expected = (
        input_value.manifest_pins,
        projection.source_snapshot_ids,
        projection.authority,
        projection.evidence_ids,
        input_value.mapping_rule_set.rule_set_id,
        input_value.mapping_rule_set.version,
        input_value.mapping_rule_set.content_hash,
        input_value.conversion_catalog.catalog_id,
        input_value.conversion_catalog.version,
        input_value.conversion_catalog.content_hash,
        projection.producer,
        input_value.input_hash,
        "not_evaluated",
    )
    actual = (
        candidate.manifest_pins,
        candidate.source_snapshot_ids,
        candidate.authority,
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
    if actual != expected:
        raise ValueError(
            "candidate common bindings differ from the frozen domain projection"
        )


def _validate_identity(candidate: Candidate) -> None:
    if isinstance(candidate, DatasetArtifactCandidate):
        expected_canonical = compute_data_artifact_canonical_content_hash(candidate)
        if candidate.canonical_content_hash != expected_canonical:
            raise ValueError(
                "Dataset canonical_content_hash is not strictly recomputed"
            )
        expected_lineage = compute_data_artifact_lineage_hash(candidate)
        if candidate.lineage_hash != expected_lineage:
            raise ValueError("Dataset lineage_hash is not strictly recomputed")
        identity_hash = expected_canonical
    else:
        identity_hash = compute_data_artifact_output_hash(candidate)
    expected_output = compute_data_artifact_output_hash(candidate)
    if candidate.output_hash != expected_output:
        raise ValueError("candidate output_hash does not cover complete public content")
    expected_id = compute_data_artifact_candidate_id(
        candidate.kind,
        identity_hash,
        schema_version=candidate.schema_version,
    )
    if candidate.candidate_id != expected_id:
        raise ValueError("candidate_id does not match its strict identity projection")


def _validate_dataset(
    candidate: DatasetArtifactCandidate, projection: DataArtifactDomainProjection
) -> None:
    input_value = projection.input_value
    expected_columns = tuple(field for field in projection.fields)
    if candidate.requested_fields != tuple(
        field.field_id for field in projection.fields
    ):
        raise ValueError("Dataset requested fields differ from the domain projection")
    if tuple(column.field for column in candidate.columns) != expected_columns:
        raise ValueError(
            "Dataset columns differ from the frozen Field Manifest projection"
        )
    if candidate.rows != projection.rows:
        raise ValueError("Dataset rows differ from the complete domain projection")
    if candidate.source_values != projection.source_values:
        raise ValueError(
            "Dataset SourceValue set differs from the complete domain projection"
        )
    if candidate.transformation_evidence != projection.transformation_evidence:
        raise ValueError(
            "Dataset Evidence set differs from the complete domain projection"
        )
    if candidate.selections != projection.selections:
        raise ValueError(
            "Dataset selection set differs from the complete domain projection"
        )
    if candidate.conflicts != projection.conflicts:
        raise ValueError(
            "Dataset conflict set differs from the complete domain projection"
        )
    if candidate.row_count != len(projection.rows) or candidate.field_count != len(
        projection.fields
    ):
        raise ValueError("Dataset dimensions differ from the domain projection")
    if candidate.authority != projection.authority:
        raise ValueError("Dataset authority differs from the domain projection")
    if (
        candidate.quality_metric_input_declarations
        != projection.quality_metric_input_declarations
        or candidate.quality_constraints_reference
        != input_value.quality_constraints_reference
    ):
        raise ValueError(
            "Dataset quality declarations differ from the domain projection"
        )


def _validate_field_dictionary(
    candidate: FieldDictionaryArtifactCandidate,
    projection: DataArtifactDomainProjection,
) -> None:
    expected_fields = tuple(field.field_id for field in projection.fields)
    if (
        candidate.requested_fields != expected_fields
        or candidate.field_definitions != projection.fields
    ):
        raise ValueError(
            "FieldDictionary differs from the frozen Field Manifest projection"
        )


def _validate_source_collection(
    candidate: SourceCollectionArtifactCandidate,
    projection: DataArtifactDomainProjection,
) -> None:
    expected_authority = projection.authority
    if isinstance(expected_authority, CrossmatchArtifactAuthority):
        expected_status_keys = (
            expected_authority.alignment_record_keys,
            expected_authority.conflict_record_keys,
            expected_authority.review_required_record_keys,
            expected_authority.inconclusive_record_keys,
        )
    else:
        expected_status_keys = ((), (), (), ())
    expected = (
        projection.crossmatch_sources,
        projection.source_table_sources,
        projection.supplemental_document_sources,
        tuple(value.source_value_id for value in projection.source_values),
        expected_authority,
        *expected_status_keys,
    )
    actual_authority = candidate.authority
    if isinstance(actual_authority, CrossmatchArtifactAuthority):
        actual_status_keys = (
            actual_authority.alignment_record_keys,
            actual_authority.conflict_record_keys,
            actual_authority.review_required_record_keys,
            actual_authority.inconclusive_record_keys,
        )
    else:
        actual_status_keys = ((), (), (), ())
    actual = (
        candidate.crossmatch_sources,
        candidate.source_table_sources,
        candidate.supplemental_document_sources,
        candidate.source_value_ids,
        candidate.authority,
        *actual_status_keys,
    )
    if actual != expected:
        raise ValueError(
            "SourceCollection differs from the exact acquisition/domain projection"
        )


def validate_data_artifact_candidates_against_input(
    bundle: DataArtifactBuildResult | Candidate,
    input_value: DataArtifactBuildInput,
) -> None:
    """Derive a fresh expectation and prove every candidate before sealing."""

    projection = derive_data_artifact_domain_projection(input_value)
    candidates = (
        (bundle.dataset, bundle.field_dictionary, bundle.source_collection)
        if isinstance(bundle, DataArtifactBuildResult)
        else (bundle,)
    )
    for candidate in candidates:
        _validate_common(candidate, projection)
        if isinstance(candidate, DatasetArtifactCandidate):
            _validate_dataset(candidate, projection)
        elif isinstance(candidate, FieldDictionaryArtifactCandidate):
            _validate_field_dictionary(candidate, projection)
        elif isinstance(candidate, SourceCollectionArtifactCandidate):
            _validate_source_collection(candidate, projection)
        else:
            raise ValueError("unsupported Data Artifact candidate type")
        _validate_identity(candidate)
        _revalidate(candidate)


def _independent_validate(candidate: Candidate) -> Candidate:
    input_value = _publication_input(candidate)
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
    if isinstance(candidate, DatasetArtifactCandidate) and (
        candidate.row_count != len(candidate.rows)
        or candidate.field_count != len(candidate.columns)
    ):
        raise ValueError("Dataset dimensions disagree with content")


def validate_data_artifact_quality_prerequisites(context: AdmissionContext) -> None:
    candidate = _independent_validate(_candidate(context))
    if candidate.quality_evaluation_status != "not_evaluated":
        raise ValueError("Data Artifact must not evaluate data quality")
    if (
        isinstance(candidate, DatasetArtifactCandidate)
        and not candidate.quality_metric_input_declarations
    ):
        raise ValueError("Dataset must declare its downstream quality inputs")


__all__ = [
    "validate_data_artifact_candidates_against_input",
    "validate_data_artifact_domain",
    "validate_data_artifact_evidence",
    "validate_data_artifact_quality_prerequisites",
]
