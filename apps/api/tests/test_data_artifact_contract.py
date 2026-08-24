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
from copy import deepcopy
from decimal import Decimal
from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    SourceCollectionArtifactCandidate,
    MappingRuleSet,
    UnitConversionCatalog,
    compute_data_artifact_content_hash,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_input_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError


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


# --- durable data-artifact semantics moved from the removed review-history suite ---
def _rehash_policy_input(
    input_value: DataArtifactBuildInput,
    *,
    mapping_rule_set: dict | None = None,
    conversion_catalog: dict | None = None,
) -> DataArtifactBuildInput:
    updates: dict[str, object] = {}
    if mapping_rule_set is not None:
        mapping_rule_set["content_hash"] = compute_data_artifact_content_hash(
            mapping_rule_set
        )
        updates["mapping_rule_set"] = MappingRuleSet.model_validate(mapping_rule_set)
    if conversion_catalog is not None:
        conversion_catalog["content_hash"] = compute_data_artifact_content_hash(
            conversion_catalog
        )
        updates["conversion_catalog"] = UnitConversionCatalog.model_validate(
            conversion_catalog
        )
    unhashed = input_value.model_copy(update=updates)
    payload = unhashed.model_dump(mode="json")
    payload["input_hash"] = compute_data_artifact_input_hash(unhashed)
    return DataArtifactBuildInput.model_validate(payload)


def _rehash_candidate_payload(payload: dict) -> dict:
    if payload["kind"] == "dataset":
        payload["canonical_content_hash"] = (
            compute_data_artifact_canonical_content_hash(payload)
        )
        payload["lineage_hash"] = compute_data_artifact_lineage_hash(payload)
    payload["output_hash"] = compute_data_artifact_output_hash(payload)
    identity_hash = payload.get("canonical_content_hash", payload["output_hash"])
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"], identity_hash
    )
    return payload


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("numeric_comparison", "absolute_tolerance"), "0.1"),
        (("numeric_comparison", "relative_tolerance"), "0.01"),
        (("capacity", "max_rows"), 9999),
        (("producer_version",), "9.9.9"),
    ),
)
def test_public_build_rejects_self_consistent_non_frozen_mapping_policy(
    path: tuple[str, ...], replacement: object
) -> None:
    input_value = build_input("star.tic_id")
    rule_payload = deepcopy(input_value.mapping_rule_set.model_dump(mode="json"))
    target = rule_payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = replacement
    tampered = _rehash_policy_input(input_value, mapping_rule_set=rule_payload)

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "MAPPING_RULE_MISMATCH"


def test_public_build_rejects_self_consistent_non_frozen_conversion_catalog() -> None:
    input_value = build_input("planet.radius")
    catalog_payload = deepcopy(input_value.conversion_catalog.model_dump(mode="json"))
    rule = next(
        item
        for item in catalog_payload["rules"]
        if item["rule_id"] == "unit.jupiter_radius_to_earth_radius"
    )
    rule["factor_numerator"] = "71492001"
    rule["factor"] = str(
        int(rule["factor_numerator"]) / int(rule["factor_denominator"])
    )
    # Preserve exact Decimal self-consistency rather than relying on binary float text.
    from decimal import Decimal, localcontext

    with localcontext() as context:
        context.prec = catalog_payload["precision_digits"]
        rule["factor"] = str(
            Decimal(rule["factor_numerator"]) / Decimal(rule["factor_denominator"])
        )
    tampered = _rehash_policy_input(input_value, conversion_catalog=catalog_payload)

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "CONVERSION_CATALOG_MISMATCH"


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("rule_set_id",), "replacement.mapping.rules"),
        (("version",), "9.9.9"),
        (("numeric_comparison", "threshold_inclusive"), False),
        (("numeric_comparison", "relative_denominator_floor"), "1E-20"),
        (("entity_projection_policy", "version"), "9.9.9"),
        (
            (
                "entity_projection_policy",
                "rules",
                0,
                "allowed_object_types",
            ),
            ["planet", "star", "system"],
        ),
        (("capacity", "max_transformation_evidence"), 499999),
    ),
)
def test_public_build_rejects_additional_self_consistent_mapping_policy_tamper(
    path: tuple[str | int, ...], replacement: object
) -> None:
    input_value = build_input("star.tic_id")
    payload = deepcopy(input_value.mapping_rule_set.model_dump(mode="json"))
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = replacement
    tampered = _rehash_policy_input(input_value, mapping_rule_set=payload)

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "MAPPING_RULE_MISMATCH"


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("catalog_id",), "replacement.unit.conversions"),
        (("version",), "9.9.9"),
        (("decimal_capacity", "max_adjusted_exponent"), 999),
        (("rules", 1, "quantity_kind"), "mass"),
        (("rules", 1, "source_unit"), "earth_radius"),
    ),
)
def test_public_build_rejects_catalog_identity_and_capacity_tamper(
    path: tuple[str | int, ...], replacement: object
) -> None:
    input_value = build_input("planet.mass")
    payload = deepcopy(input_value.conversion_catalog.model_dump(mode="json"))
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = replacement
    tampered = _rehash_policy_input(input_value, conversion_catalog=payload)

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "CONVERSION_CATALOG_MISMATCH"


def test_public_build_rejects_self_consistent_jupiter_mass_factor_tamper() -> None:
    input_value = build_input("planet.mass")
    payload = deepcopy(input_value.conversion_catalog.model_dump(mode="json"))
    rule = next(
        item
        for item in payload["rules"]
        if item["rule_id"] == "unit.jupiter_mass_to_earth_mass"
    )
    rule["factor_numerator"] = str(int(rule["factor_numerator"]) + 1)
    from decimal import localcontext

    with localcontext() as context:
        context.prec = payload["precision_digits"]
        rule["factor"] = str(
            Decimal(rule["factor_numerator"]) / Decimal(rule["factor_denominator"])
        )
    tampered = _rehash_policy_input(input_value, conversion_catalog=payload)

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "CONVERSION_CATALOG_MISMATCH"


@pytest.mark.parametrize("tamper", ("row_key", "record_hash"))
def test_source_collection_rejects_raw_record_reference_tamper(tamper: str) -> None:
    candidate = build_data_artifact_candidates(
        build_input("star.tic_id")
    ).source_collection
    payload = candidate.model_dump(mode="json")
    reference = payload["crossmatch_sources"][0]["raw_record_references"][0]
    if tamper == "row_key":
        reference["row_key"][0][1] = f"{reference['row_key'][0][1]}-tampered"
    else:
        reference["raw_record_content_hash"] = f"sha256:{'0' * 64}"
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="raw record registry"):
        SourceCollectionArtifactCandidate.model_validate(payload)
