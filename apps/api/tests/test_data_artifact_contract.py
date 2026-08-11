from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.schemas.data_artifacts import (
    CanonicalValueOutcome,
    DataArtifactCapacity,
    DataArtifactErrorCode,
    DeclaredNullValue,
    MappedCanonicalValue,
    UnresolvedCanonicalValue,
    DatasetArtifactCandidate,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.policy import load_mapping_rule_set

from data_artifact_test_support import build_input


def test_data_artifact_contracts_are_strict_frozen_and_closed() -> None:
    capacity = DataArtifactCapacity(
        max_rows=10,
        max_requested_fields=4,
        max_source_values_per_field=5,
        max_transformation_evidence=100,
        max_conflict_candidates=10,
        max_total_cell_outcomes=40,
    )

    with pytest.raises(ValidationError):
        capacity.max_rows = 11  # type: ignore[misc]
    with pytest.raises(ValidationError, match="Extra inputs"):
        DataArtifactCapacity.model_validate(
            {**capacity.model_dump(mode="json"), "unexpected": True}
        )
    with pytest.raises(ValueError):
        DataArtifactErrorCode("unknown")


def test_canonical_value_outcome_is_a_discriminated_union() -> None:
    schema = TypeAdapter(CanonicalValueOutcome).json_schema()

    assert schema["discriminator"]["propertyName"] == "status"
    assert set(schema["discriminator"]["mapping"]) == {
        "mapped",
        "declared_null",
        "unresolved",
    }
    assert MappedCanonicalValue.model_fields["status"].default == "mapped"
    assert DeclaredNullValue.model_fields["status"].default == "declared_null"
    assert UnresolvedCanonicalValue.model_fields["status"].default == "unresolved"


def test_candidate_identity_and_output_hash_fail_closed() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["candidate_id"] = "candidate.dataset.tampered"

    with pytest.raises(ValidationError, match="candidate_id"):
        DatasetArtifactCandidate.model_validate(payload)

    payload = candidate.model_dump(mode="json")
    payload["row_count"] += 1
    with pytest.raises(ValidationError, match="row/field count"):
        DatasetArtifactCandidate.model_validate(payload)


def test_mapping_rule_set_tamper_fails_content_hash_validation() -> None:
    rule_set = load_mapping_rule_set()
    payload = rule_set.model_dump(mode="json")
    payload["capacity"]["max_rows"] -= 1

    with pytest.raises(ValidationError, match="content_hash"):
        type(rule_set).model_validate(payload)
