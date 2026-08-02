from __future__ import annotations

import pytest

from app.schemas.data_artifacts import (
    DataArtifactBuildResult,
    MappedCanonicalValue,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.errors import DataArtifactError

from data_artifact_test_support import build_input


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
