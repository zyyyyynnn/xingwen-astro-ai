from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DatasetArtifactCandidate,
    ManifestPins,
    RawSourceRecordReference,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_candidate_id,
    compute_data_artifact_content_hash,
    compute_data_artifact_input_hash,
    compute_data_artifact_output_hash,
    compute_raw_record_reference_registry_hash,
)
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
    validate_data_artifact_quality_prerequisites,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError

from data_artifact_test_support import build_input


def _admit(candidate):
    return admit_artifact_candidate(
        candidate,
        schema_version=candidate.schema_version,
        source_snapshot_ids=candidate.source_snapshot_ids,
        evidence_ids=candidate.evidence_ids,
        evidence_validator=validate_data_artifact_evidence,
        domain_validator=validate_data_artifact_domain,
        quality_validator=validate_data_artifact_quality_prerequisites,
    )


def _input_from_crossmatch(crossmatch_input, *requested_fields: str) -> DataArtifactBuildInput:
    crossmatch_result = align_cross_source_records(crossmatch_input)
    baseline = build_input(*requested_fields)
    pins = ManifestPins(
        case_manifest_id=crossmatch_result.case_manifest_id,
        case_manifest_version=crossmatch_result.case_manifest_version,
        case_manifest_content_hash=crossmatch_result.case_manifest_content_hash,
        field_manifest_id=crossmatch_result.field_manifest_id,
        field_manifest_version=crossmatch_result.field_manifest_version,
        field_manifest_content_hash=crossmatch_result.field_manifest_content_hash,
    )
    unhashed = DataArtifactBuildInput.model_construct(
        manifest_pins=pins,
        requested_fields=requested_fields,
        left_acquisition=crossmatch_input.left,
        right_acquisition=crossmatch_input.right,
        crossmatch_result=crossmatch_result,
        mapping_rule_set=baseline.mapping_rule_set,
        conversion_catalog=baseline.conversion_catalog,
        producer_version=baseline.producer_version,
        quality_constraints_reference=baseline.quality_constraints_reference,
        input_hash="sha256:" + "0" * 64,
    )
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _rehash_candidate_payload(payload: dict) -> dict:
    payload["output_hash"] = compute_data_artifact_output_hash(payload)
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"], payload["output_hash"]
    )
    return payload


def _rehash_dataset_payload(payload: dict) -> dict:
    for collection in (
        "source_values",
        "transformation_evidence",
        "selections",
        "conflicts",
        "rows",
    ):
        for item in payload[collection]:
            item["content_hash"] = compute_data_artifact_content_hash(item)
    return _rehash_candidate_payload(payload)


def _replace_public_fields(original, replacement) -> None:
    for field_name in type(original).model_fields:
        object.__setattr__(original, field_name, getattr(replacement, field_name))


def test_public_build_rejects_self_consistent_non_frozen_c08_result() -> None:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "exact_one_to_one"
    )
    baseline_input = _scenario_input(scenario)
    alternate_capacity = baseline_input.rule_set.capacity.model_copy(
        update={
            "max_candidate_pairs": baseline_input.rule_set.capacity.max_candidate_pairs
            - 1
        }
    )
    alternate_scenario = scenario.model_copy(
        update={"capacity_override": alternate_capacity}
    )
    input_value = _input_from_crossmatch(
        _scenario_input(alternate_scenario),
        "star.tic_id",
    )

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(input_value)

    assert exc_info.value.code == "CROSSMATCH_RESULT_MISMATCH"


def test_publisher_replay_rejects_synchronized_dataset_semantic_tamper() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    )
    original = result.dataset
    payload = original.model_dump(mode="json")
    source_value = next(
        item
        for item in payload["source_values"]
        if item["canonical_field_id"] == "planet.name"
    )
    source_value_id = source_value["source_value_id"]
    forged_value = "Forged Planet c"
    source_value["raw_value"] = forged_value
    source_value["canonical_value"] = forged_value

    evidence = next(
        item
        for item in payload["transformation_evidence"]
        if item["source_value_id"] == source_value_id
    )
    evidence["raw_value"] = forged_value
    evidence["canonical_value"] = forged_value

    outcome_found = False
    for row in payload["rows"]:
        for outcome in row["fields"]:
            if source_value_id in outcome["candidate_source_value_ids"]:
                assert outcome["status"] == "mapped"
                outcome["canonical_value"] = forged_value
                outcome_found = True
    assert outcome_found

    damaged = DatasetArtifactCandidate.model_validate(
        _rehash_dataset_payload(payload)
    )
    _replace_public_fields(original, damaged)

    with pytest.raises(PublicationAdmissionError):
        _admit(original)


def test_publisher_replay_rejects_missing_unused_acquisition_record() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    )
    original = result.source_collection
    payload = original.model_dump(mode="json")
    left_member = payload["members"][0]
    assert left_member["raw_record_references"]

    dataset_record_keys = {
        (
            value.source_id,
            value.raw_record_row_key,
            value.raw_record_content_hash,
        )
        for value in result.dataset.source_values
    }
    removed = left_member["raw_record_references"][0]
    assert (
        removed["source_id"],
        tuple(tuple(item) for item in removed["row_key"]),
        removed["raw_record_content_hash"],
    ) not in dataset_record_keys

    left_member["raw_record_references"] = left_member["raw_record_references"][1:]
    references = tuple(
        RawSourceRecordReference.model_validate(item)
        for item in left_member["raw_record_references"]
    )
    left_member["raw_record_count"] = len(references)
    left_member["raw_record_reference_registry_hash"] = (
        compute_raw_record_reference_registry_hash(references)
    )
    damaged = SourceCollectionArtifactCandidate.model_validate(
        _rehash_candidate_payload(payload)
    )
    _replace_public_fields(original, damaged)

    with pytest.raises(PublicationAdmissionError):
        _admit(original)


def test_original_candidates_retain_typed_replay_context() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    for candidate in (
        result.dataset,
        result.field_dictionary,
        result.source_collection,
    ):
        context = getattr(candidate, "_artifact_publication_context", None)
        assert isinstance(context, DataArtifactBuildInput)
        assert context.input_hash == candidate.input_hash
        assert _admit(candidate).content["kind"] == candidate.kind


def test_reparsed_candidate_still_cannot_recreate_replay_context() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    reparsed = DatasetArtifactCandidate.model_validate_json(candidate.model_dump_json())

    assert getattr(reparsed, "_artifact_publication_context", None) is None
    with pytest.raises(PublicationAdmissionError, match="cannot bypass"):
        _admit(reparsed)
