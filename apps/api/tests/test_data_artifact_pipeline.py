from __future__ import annotations

import pytest

from app.schemas.crossmatch import AdjudicationDecision
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    ManifestPins,
    MappedCanonicalValue,
    compute_data_artifact_input_hash,
)
from app.schemas.source_acquisition import (
    RawDataSourceRecord,
    compute_raw_data_record_hash,
)
from services.data_pipeline.crossmatch import align_cross_source_records
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.errors import DataArtifactError

from data_artifact_test_support import build_input


def _build_input_from_crossmatch(
    crossmatch_input, *requested_fields: str
) -> DataArtifactBuildInput:
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


def _same_measurement_for_scenario(scenario_id: str) -> DataArtifactBuildInput:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == scenario_id
    )
    crossmatch_input = _scenario_input(scenario)

    def add_measurement(acquisition):
        records = []
        for record in acquisition.records:
            payload = {
                **record.payload,
                "pl_orbper": 1.0,
                "pl_orbperlim": 0,
            }
            records.append(
                RawDataSourceRecord(
                    source_id=record.source_id,
                    row_key=record.row_key,
                    payload=payload,
                    content_hash=compute_raw_data_record_hash(
                        source_id=record.source_id,
                        row_key=record.row_key,
                        payload=payload,
                    ),
                )
            )
        return acquisition.model_copy(update={"records": tuple(records)})

    crossmatch_input = crossmatch_input.model_copy(
        update={
            "left": add_measurement(crossmatch_input.left),
            "right": add_measurement(crossmatch_input.right),
        }
    )
    return _build_input_from_crossmatch(
        crossmatch_input, "planet.orbital_period"
    )


def test_pipeline_builds_three_deterministic_evidence_first_candidates() -> None:
    input_value = build_input("star.tic_id")

    first = build_data_artifact_candidates(input_value)
    second = build_data_artifact_candidates(input_value)

    assert isinstance(first, DataArtifactBuildResult)
    assert first == second
    assert first.output_hash == second.output_hash
    assert first.dataset.kind == "dataset"
    assert first.field_dictionary.kind == "field_dictionary"
    assert first.source_collection.kind == "source_collection"
    assert first.dataset.row_count == len(first.dataset.rows) == 3
    assert first.dataset.field_count == 1
    assert len(first.dataset.source_snapshot_ids) == 2
    assert first.dataset.evidence_ids
    assert first.dataset.quality_evaluation_status == "not_evaluated"
    projected = [field for row in first.dataset.rows for field in row.fields]
    assert projected
    assert all(isinstance(field, MappedCanonicalValue) for field in projected)
    assert all(
        not row.fields for row in first.dataset.rows if row.entity_level == "planet_candidate"
    )
    assert {
        evidence.locator.source_snapshot_id
        for evidence in first.dataset.transformation_evidence
    } == set(first.dataset.source_snapshot_ids)


def test_pipeline_dataset_identity_distinguishes_entities_with_same_measurement() -> None:
    first = build_data_artifact_candidates(
        _same_measurement_for_scenario("exact_one_to_one")
    ).dataset
    second = build_data_artifact_candidates(
        _same_measurement_for_scenario("same_tic_host_only")
    ).dataset

    assert [
        field.canonical_value
        for row in first.rows
        for field in row.fields
        if isinstance(field, MappedCanonicalValue)
    ] == ["1", "1"]
    assert [
        field.canonical_value
        for row in second.rows
        for field in row.fields
        if isinstance(field, MappedCanonicalValue)
    ] == ["1", "1"]
    assert first.canonical_content_hash != second.canonical_content_hash
    assert first.candidate_id != second.candidate_id
    assert first.lineage_hash != second.lineage_hash
    assert first.output_hash != second.output_hash


@pytest.mark.parametrize(
    ("scenario_id", "alignment_status"),
    (
        ("exact_one_to_one", "accepted"),
        ("exact_one_to_one", "unmatched"),
        ("coordinate_only", "review_required"),
        ("truncated_inconclusive", "inconclusive"),
        ("alias_conflict", "conflict"),
    ),
)
def test_pipeline_canonical_row_identity_covers_alignment_semantics(
    scenario_id: str,
    alignment_status: str,
) -> None:
    dataset = build_data_artifact_candidates(
        build_input("planet.name", scenario_id=scenario_id)
    ).dataset

    rows = [row for row in dataset.rows if row.alignment_status == alignment_status]
    assert rows
    assert all(row.canonical_row_identity.member_entities for row in rows)
    assert all(
        row.canonical_row_identity.alignment_status == row.alignment_status
        and row.canonical_row_identity.entity_level == row.entity_level
        and row.canonical_row_identity.record_type == row.crossmatch_record_type
        for row in rows
    )


def test_pipeline_canonical_row_identity_covers_rejected_empty_row() -> None:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "coordinate_only"
    ).model_copy(update={"manual_adjudication": AdjudicationDecision.rejected})
    dataset = build_data_artifact_candidates(
        _build_input_from_crossmatch(_scenario_input(scenario), "planet.name")
    ).dataset

    rejected = next(row for row in dataset.rows if row.alignment_status == "rejected")
    assert rejected.fields == ()
    assert rejected.canonical_row_identity.alignment_status == "rejected"
    assert rejected.canonical_row_identity.member_entities


def test_pipeline_rejects_raw_source_column_as_requested_field() -> None:
    input_value = build_input("star.tic_id")
    from app.schemas.data_artifacts import compute_data_artifact_input_hash

    input_value = input_value.model_copy(update={"requested_fields": ("pl_rade",)})
    input_value = input_value.model_copy(
        update={"input_hash": compute_data_artifact_input_hash(input_value)}
    )

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(input_value)

    assert exc_info.value.code == "UNSUPPORTED_REQUESTED_FIELD"


def test_incomplete_crossmatch_scope_stays_inconclusive() -> None:
    result = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id="truncated_inconclusive")
    )

    assert any(row.alignment_status == "inconclusive" for row in result.dataset.rows)
    assert result.source_collection.inconclusive_record_keys


def test_acquisition_payload_tamper_is_rejected_even_with_recomputed_input_hash() -> None:
    from app.schemas.data_artifacts import compute_data_artifact_input_hash

    input_value = build_input("star.tic_id")
    record = input_value.left_acquisition.records[0]
    tampered_record = record.model_copy(
        update={"payload": {**record.payload, "tid": 999}}
    )
    tampered_left = input_value.left_acquisition.model_copy(
        update={"records": (tampered_record,)}
    )
    tampered = input_value.model_copy(update={"left_acquisition": tampered_left})
    tampered = tampered.model_copy(
        update={"input_hash": compute_data_artifact_input_hash(tampered)}
    )

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "SOURCE_RECORD_HASH_MISMATCH"
