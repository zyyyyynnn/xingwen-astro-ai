"""Serialize, independently admit, and seal Data Artifact domain projections."""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_core import PydanticSerializationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.data_artifacts import (
    DataArtifactAdmissionSnapshot,
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DataArtifactErrorCode,
    DatasetArtifactCandidate,
    DatasetColumn,
    FieldDictionaryArtifactCandidate,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_context_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
    compute_data_artifact_public_payload_hash,
)
from app.schemas.data_artifact_seal import seal_data_artifact_candidate

from .admission import validate_data_artifact_candidates_against_input
from .errors import DataArtifactError
from .projection import (
    DataArtifactDomainProjection,
    derive_data_artifact_domain_projection,
    validate_policy_bindings,
    validate_runtime_input_integrity,
)


def _candidate(model_type, payload: dict[str, Any]):
    payload.setdefault("schema_version", "2.0.0")
    payload.setdefault("quality_evaluation_status", "not_evaluated")
    normalized: dict[str, Any] = {}
    deferred = {
        "candidate_id",
        "output_hash",
        "canonical_content_hash",
        "lineage_hash",
    }
    for name, model_field in model_type.model_fields.items():
        if name in deferred or name not in payload:
            continue
        normalized[name] = TypeAdapter(model_field.annotation).validate_python(
            payload[name]
        )
    payload = model_type.model_construct(
        **normalized,
        candidate_id="candidate.pending",
        output_hash="sha256:" + "0" * 64,
        **(
            {
                "canonical_content_hash": "sha256:" + "0" * 64,
                "lineage_hash": "sha256:" + "0" * 64,
            }
            if model_type is DatasetArtifactCandidate
            else {}
        ),
    ).model_dump(mode="json", exclude_none=True)
    if model_type is DatasetArtifactCandidate:
        payload["canonical_content_hash"] = compute_data_artifact_canonical_content_hash(
            payload
        )
        payload["lineage_hash"] = compute_data_artifact_lineage_hash(payload)
    output_hash = compute_data_artifact_output_hash(payload)
    identity_hash = payload.get("canonical_content_hash", output_hash)
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"],
        identity_hash,
        schema_version=payload["schema_version"],
    )
    payload["output_hash"] = output_hash
    return model_type.model_validate(payload)


def _common_payload(projection: DataArtifactDomainProjection) -> dict[str, Any]:
    input_value = projection.input_value
    return {
        "manifest_pins": input_value.manifest_pins.model_dump(mode="json"),
        "source_snapshot_ids": projection.source_snapshot_ids,
        "evidence_ids": projection.evidence_ids,
        "mapping_rule_set_id": input_value.mapping_rule_set.rule_set_id,
        "mapping_rule_set_version": input_value.mapping_rule_set.version,
        "mapping_rule_set_content_hash": input_value.mapping_rule_set.content_hash,
        "conversion_catalog_id": input_value.conversion_catalog.catalog_id,
        "conversion_catalog_version": input_value.conversion_catalog.version,
        "conversion_catalog_content_hash": input_value.conversion_catalog.content_hash,
        "producer": projection.producer.model_dump(mode="json"),
        "input_hash": input_value.input_hash,
    }


def _assemble_data_artifact_candidates(
    projection: DataArtifactDomainProjection,
) -> DataArtifactBuildResult:
    """Serialize a domain projection without performing scientific derivation."""

    input_value = projection.input_value
    result = input_value.crossmatch_result
    common = _common_payload(projection)
    dataset = _candidate(
        DatasetArtifactCandidate,
        {
            "kind": "dataset",
            **common,
            "crossmatch_result_id": result.result_id,
            "crossmatch_input_hash": result.input_hash,
            "crossmatch_output_hash": result.output_hash,
            "crossmatch_content_hash": result.content_hash,
            "crossmatch_source_snapshot_ids": projection.crossmatch_source_snapshot_ids,
            "crossmatch_evidence": [
                evidence.model_dump(mode="json")
                for evidence in projection.crossmatch_evidence
            ],
            "crossmatch_evidence_ids": projection.crossmatch_evidence_ids,
            "requested_fields": tuple(field.field_id for field in projection.fields),
            "columns": [
                DatasetColumn(field=field).model_dump(mode="json")
                for field in projection.fields
            ],
            "rows": [row.model_dump(mode="json") for row in projection.rows],
            "source_values": [
                value.model_dump(mode="json") for value in projection.source_values
            ],
            "transformation_evidence": [
                evidence.model_dump(mode="json")
                for evidence in projection.transformation_evidence
            ],
            "selections": [
                selection.model_dump(mode="json")
                for selection in projection.selections
            ],
            "conflicts": [
                conflict.model_dump(mode="json") for conflict in projection.conflicts
            ],
            "row_count": len(projection.rows),
            "field_count": len(projection.fields),
            "quality_metric_input_declarations": projection.quality_metric_input_declarations,
            "quality_constraints_reference": input_value.quality_constraints_reference,
        },
    )
    field_dictionary = _candidate(
        FieldDictionaryArtifactCandidate,
        {
            "kind": "field_dictionary",
            **common,
            "crossmatch_source_snapshot_ids": projection.crossmatch_source_snapshot_ids,
            "requested_fields": tuple(field.field_id for field in projection.fields),
            "field_definitions": [
                field.model_dump(mode="json") for field in projection.fields
            ],
        },
    )
    source_collection = _candidate(
        SourceCollectionArtifactCandidate,
        {
            "kind": "source_collection",
            **common,
            "members": [
                member.model_dump(mode="json") for member in projection.source_members
            ],
            "source_value_ids": tuple(
                value.source_value_id for value in projection.source_values
            ),
            "crossmatch_result_id": result.result_id,
            "crossmatch_content_hash": result.content_hash,
            "crossmatch_source_snapshot_ids": projection.crossmatch_source_snapshot_ids,
            "alignment_record_keys": projection.alignment_record_keys,
            "conflict_record_keys": projection.conflict_record_keys,
            "review_required_record_keys": projection.review_required_record_keys,
            "inconclusive_record_keys": projection.inconclusive_record_keys,
        },
    )
    payload = {
        "schema_version": "2.0.0",
        "dataset": dataset,
        "field_dictionary": field_dictionary,
        "source_collection": source_collection,
        "input_hash": input_value.input_hash,
    }
    payload["output_hash"] = compute_data_artifact_output_hash(
        {
            **payload,
            "dataset": dataset.model_dump(mode="json"),
            "field_dictionary": field_dictionary.model_dump(mode="json"),
            "source_collection": source_collection.model_dump(mode="json"),
        }
    )
    return DataArtifactBuildResult.model_validate(payload)


def _bundle_commitment(result: DataArtifactBuildResult) -> str:
    return compute_canonical_payload_hash(
        [
            {
                "kind": candidate.kind,
                "candidate_id": candidate.candidate_id,
                "public_payload_hash": compute_data_artifact_public_payload_hash(candidate),
            }
            for candidate in (
                result.dataset,
                result.field_dictionary,
                result.source_collection,
            )
        ]
    )


def build_data_artifact_candidates(
    input: DataArtifactBuildInput,
) -> DataArtifactBuildResult:
    """Derive, serialize, independently admit, and finally seal one Data Artifact bundle."""

    try:
        validated_input = DataArtifactBuildInput.model_validate_json(input.model_dump_json())
    except (ValidationError, PydanticSerializationError) as exc:
        for check in (validate_runtime_input_integrity, validate_policy_bindings):
            try:
                check(input)
            except DataArtifactError as domain_error:
                raise domain_error from exc
        raise DataArtifactError(
            DataArtifactErrorCode.input_hash_mismatch,
            "Data Artifact input cannot be reparsed as a valid canonical build input",
            cause=exc,
        ) from exc

    projection = derive_data_artifact_domain_projection(validated_input)
    result = _assemble_data_artifact_candidates(projection)

    validate_data_artifact_candidates_against_input(result, validated_input)
    input_json = validated_input.model_dump_json()
    snapshot = DataArtifactAdmissionSnapshot(
        input_json=input_json,
        input_hash=validated_input.input_hash,
        context_hash=compute_data_artifact_context_hash(
            validated_input, input_json=input_json
        ),
        bundle_commitment_hash=_bundle_commitment(result),
    )
    for candidate in (
        result.dataset,
        result.field_dictionary,
        result.source_collection,
    ):
        seal_data_artifact_candidate(
            candidate,
            snapshot,
            public_payload_hash=compute_data_artifact_public_payload_hash(candidate),
        )
    return result


__all__ = ["build_data_artifact_candidates"]
