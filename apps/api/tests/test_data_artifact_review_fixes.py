from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.data_artifacts import (
    DataArtifactBuildInput,
    DataArtifactBuildResult,
    DatasetArtifactCandidate,
    FieldDictionaryArtifactCandidate,
    RawSourceRecordReference,
    SourceCollectionArtifactCandidate,
    MappingRuleSet,
    UnitConversionCatalog,
    compute_data_artifact_content_hash,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_input_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
    compute_raw_record_reference_registry_hash,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.conversion import (
    decimal_from_source,
    serialize_decimal,
)
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_artifacts.errors import DataArtifactError
from services.data_pipeline.data_artifacts.projection import (
    derive_field_conflicts as _conflicts,
)
from services.data_pipeline.data_artifacts.policy import load_mapping_rule_set
from services.data_pipeline.data_artifacts.policy import load_unit_conversion_catalog
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from data_artifact_test_support import build_input


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


def test_host_star_row_does_not_project_planet_fields() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="same_tic_host_only")
    )

    host = next(row for row in result.dataset.rows if row.entity_level == "host_star")
    assertion = next(
        row for row in result.dataset.rows if row.entity_level == "planet_assertion"
    )

    assert host.fields == ()
    assert assertion.fields[0].canonical_field_id == "planet.name"
    assert assertion.fields[0].status == "mapped"


def test_multiple_planet_assertions_stay_out_of_the_host_row() -> None:
    result = build_data_artifact_candidates(
        build_input("planet.name", scenario_id="multiple_planet_assertions")
    )

    host = next(row for row in result.dataset.rows if row.entity_level == "host_star")
    assertions = [
        row for row in result.dataset.rows if row.entity_level == "planet_assertion"
    ]

    assert host.fields == ()
    assert len(assertions) == 2
    assert all(len(row.fields) == 1 for row in assertions)
    assert all(not row.conflict_ids for row in assertions)
    assert {
        row.canonical_row_identity.member_entities[0].logical_assertion_key
        for row in assertions
    } == {
        "pl_name=Assertion Planet b|pl_refname=Reference A",
        "pl_name=Assertion Planet b|pl_refname=Reference B",
    }
    assert len({row.canonical_row_identity for row in assertions}) == 2


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("numeric_comparison", "absolute_tolerance"), "0.1"),
        (("numeric_comparison", "relative_tolerance"), "0.01"),
        (("capacity", "max_rows"), 9999),
        (("producer_version",), "1.0.1"),
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
        if item["rule_id"] == "unit.jupiter_radius_to_earth_radius.v1"
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


def _refresh_raw_record_registry(member: dict) -> None:
    references = tuple(
        RawSourceRecordReference.model_validate(item)
        for item in member["raw_record_references"]
    )
    member["raw_record_count"] = len(references)
    member["raw_record_reference_registry_hash"] = (
        compute_raw_record_reference_registry_hash(references)
    )


def test_source_collection_members_bind_each_source_and_all_raw_records() -> None:
    input_value = build_input("star.tic_id")
    result = build_data_artifact_candidates(input_value)

    assert tuple(member.side.value for member in result.source_collection.members) == (
        "left",
        "right",
    )
    acquisitions = (input_value.left_acquisition, input_value.right_acquisition)
    for member, acquisition in zip(result.source_collection.members, acquisitions):
        assert member.source_id == acquisition.snapshot.source_id
        assert member.source_snapshot_id == acquisition.snapshot.snapshot_id
        assert member.completion == acquisition.completion
        assert len(member.raw_record_references) == len(acquisition.records)
        assert {
            (reference.row_key, reference.raw_record_content_hash)
            for reference in member.raw_record_references
        } == {(record.row_key, record.content_hash) for record in acquisition.records}


def test_dataset_rejects_orphan_source_value_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    orphan = deepcopy(payload["source_values"][0])
    orphan["source_value_id"] = "source_value.orphan"
    orphan["content_hash"] = compute_data_artifact_content_hash(orphan)
    payload["source_values"].append(orphan)
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="source value registry|orphan"):
        DatasetArtifactCandidate.model_validate(payload)


def test_dataset_rejects_evidence_value_drift_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["transformation_evidence"][0]["raw_value"] = "forged"
    payload["transformation_evidence"][0]["content_hash"] = (
        compute_data_artifact_content_hash(payload["transformation_evidence"][0])
    )
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="Evidence.*source value|raw value"):
        DatasetArtifactCandidate.model_validate(payload)


def test_build_result_rejects_cross_candidate_producer_drift() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    dictionary_payload = result.field_dictionary.model_dump(mode="json")
    dictionary_payload["producer"]["producer_version"] = "1.0.1"
    _rehash_candidate_payload(dictionary_payload)
    dictionary = FieldDictionaryArtifactCandidate.model_validate(dictionary_payload)
    payload = result.model_dump(mode="json")
    payload["field_dictionary"] = dictionary.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="producer|candidate.*common"):
        DataArtifactBuildResult.model_validate(payload)


def test_numeric_conflict_uses_collection_span_not_selected_representative() -> None:
    field = next(
        item
        for item in load_frozen_manifest_bundle().field_manifest.fields
        if item.field_id == "planet.radius"
    )
    rule_set = load_mapping_rule_set()
    comparison = rule_set.numeric_comparison.model_copy(
        update={"absolute_tolerance": Decimal("0.1")}
    )
    rule_set = rule_set.model_copy(update={"numeric_comparison": comparison})
    values = tuple(
        SimpleNamespace(
            source_value_id=f"source.{index}",
            source_id=f"source-{index}",
            canonical_value=value,
        )
        for index, value in enumerate(("0.09", "0", "0.18"))
    )

    assert _conflicts(field, values, rule_set)


@pytest.mark.parametrize("value", ("0", "-0", "0.0", "-0.0", "0E-20", "-0E+20"))
def test_decimal_zero_has_one_canonical_serialization(value: str) -> None:
    assert serialize_decimal(Decimal(value)) == "0"


@pytest.mark.parametrize("value", ("1e100000", "1e-100000"))
def test_decimal_serialization_rejects_extreme_exponents_before_rendering(
    value: str,
) -> None:
    with pytest.raises(DataArtifactError) as exc_info:
        serialize_decimal(Decimal(value))

    assert exc_info.value.code == "CAPACITY_EXCEEDED"


@pytest.mark.parametrize(
    "scenario_id",
    ("exact_one_to_many", "exact_many_to_many"),
)
def test_planet_radius_assertions_are_not_merged_into_host_rows(
    scenario_id: str,
) -> None:
    result = build_data_artifact_candidates(
        build_input("planet.radius", scenario_id=scenario_id)
    )
    host_rows = [row for row in result.dataset.rows if row.entity_level == "host_star"]
    assertion_rows = [
        row for row in result.dataset.rows if row.entity_level == "planet_assertion"
    ]

    assert host_rows and all(not row.fields for row in host_rows)
    assert assertion_rows
    assert all(
        row.projected_field_ids == ("planet.radius",) for row in assertion_rows
    )
    assert all(len(row.source_member_ids) == 1 for row in assertion_rows)


def test_host_row_projection_contains_only_star_and_system_fields() -> None:
    result = build_data_artifact_candidates(
        build_input(
            "planet.name",
            "star.tic_id",
            scenario_id="same_tic_host_only",
        )
    )
    host = next(row for row in result.dataset.rows if row.entity_level == "host_star")

    assert host.projected_field_ids == ("star.tic_id",)


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("rule_set_id",), "replacement.mapping.rules"),
        (("version",), "1.0.1"),
        (("numeric_comparison", "threshold_inclusive"), False),
        (("numeric_comparison", "relative_denominator_floor"), "1E-20"),
        (("entity_projection_policy", "version"), "1.0.1"),
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
        (("version",), "1.0.1"),
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
        if item["rule_id"] == "unit.jupiter_mass_to_earth_mass.v1"
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


def test_source_collection_json_reparse_preserves_member_bindings() -> None:
    candidate = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id="truncated_inconclusive")
    ).source_collection

    reparsed = SourceCollectionArtifactCandidate.model_validate_json(
        candidate.model_dump_json()
    )

    assert reparsed.members == candidate.members
    assert reparsed.members[0].completion != reparsed.members[1].completion


def test_source_collection_rejects_license_source_mismatch() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    payload = candidate.model_dump(mode="json")
    payload["members"][0]["license_note"] = "forged license binding"
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="SourceSnapshot"):
        SourceCollectionArtifactCandidate.model_validate(payload)


def test_source_collection_keeps_one_record_reference_for_multi_field_use() -> None:
    input_value = build_input("star.tic_id", "star.name")
    result = build_data_artifact_candidates(input_value)

    for member, acquisition in zip(
        result.source_collection.members,
        (input_value.left_acquisition, input_value.right_acquisition),
    ):
        assert len(member.raw_record_references) == len(acquisition.records)


def _rehash_dataset_tree(payload: dict) -> dict:
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


def test_dataset_rejects_orphan_evidence_after_synchronized_rehash() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    orphan = deepcopy(payload["transformation_evidence"][0])
    orphan["evidence_id"] = "evidence.transformation.orphan"
    payload["transformation_evidence"].append(orphan)
    _rehash_dataset_tree(payload)

    with pytest.raises(ValidationError, match="Evidence references|Evidence registry"):
        DatasetArtifactCandidate.model_validate(payload)


def test_dataset_rejects_conflict_field_and_candidate_set_drift() -> None:
    candidate = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    ).dataset
    for mutation in ("field", "candidate_set"):
        payload = candidate.model_dump(mode="json")
        conflict = payload["conflicts"][0]
        if mutation == "field":
            conflict["canonical_field_id"] = "star.tic_id"
        else:
            conflict["source_value_ids"] = conflict["source_value_ids"][:-1]
        _rehash_dataset_tree(payload)

        with pytest.raises(ValidationError, match="conflict"):
            DatasetArtifactCandidate.model_validate(payload)


def test_build_result_rejects_dataset_dictionary_projection_drift() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    payload["columns"][0]["field"]["label_en"] = "Forged label"
    dataset = DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))
    build_payload = result.model_dump(mode="json")
    build_payload["dataset"] = dataset.model_dump(mode="json")
    build_payload["output_hash"] = compute_data_artifact_output_hash(build_payload)

    with pytest.raises(ValidationError, match="FieldDictionary definitions"):
        DataArtifactBuildResult.model_validate(build_payload)


def test_dataset_rejects_synchronized_extra_snapshot() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    extra = "snapshot.forged"
    payload["source_snapshot_ids"].append(extra)
    payload["crossmatch_source_snapshot_ids"].append(extra)
    with pytest.raises(ValidationError, match="two crossmatch SourceSnapshots"):
        DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))


def test_dataset_rejects_synchronized_missing_snapshot() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    payload["source_snapshot_ids"] = payload["source_snapshot_ids"][:1]
    payload["crossmatch_source_snapshot_ids"] = payload[
        "crossmatch_source_snapshot_ids"
    ][:1]

    with pytest.raises(ValidationError, match="two crossmatch SourceSnapshots"):
        DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))


def test_source_collection_members_survive_reversed_snapshot_sort_order() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    payload = candidate.model_dump(mode="json")
    replacements = ("snapshot.z-left", "snapshot.a-right")
    for member, replacement in zip(payload["members"], replacements):
        member["source_snapshot_id"] = replacement
        member["source_snapshot"]["snapshot_id"] = replacement
        for reference in member["raw_record_references"]:
            reference["source_snapshot_id"] = replacement
        _refresh_raw_record_registry(member)
    payload["source_snapshot_ids"] = sorted(replacements)
    _rehash_candidate_payload(payload)

    reparsed = SourceCollectionArtifactCandidate.model_validate(payload)

    assert tuple(member.side.value for member in reparsed.members) == ("left", "right")
    assert tuple(member.source_snapshot_id for member in reparsed.members) == replacements
    assert reparsed.source_snapshot_ids == tuple(sorted(replacements))


def test_source_collection_rejects_missing_or_duplicate_member() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    for members in (
        candidate.members[:1],
        (candidate.members[0], candidate.members[0]),
    ):
        payload = candidate.model_dump(mode="json")
        payload["members"] = [item.model_dump(mode="json") for item in members]
        payload["source_snapshot_ids"] = sorted(
            {item.source_snapshot_id for item in members}
        )
        _rehash_candidate_payload(payload)
        with pytest.raises(ValidationError, match="left/right|independent"):
            SourceCollectionArtifactCandidate.model_validate(payload)


def test_build_result_rejects_candidate_from_another_build() -> None:
    first = build_data_artifact_candidates(build_input("star.tic_id"))
    second = build_data_artifact_candidates(build_input("planet.name"))
    payload = first.model_dump(mode="json")
    payload["field_dictionary"] = second.field_dictionary.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="common bindings|requested fields"):
        DataArtifactBuildResult.model_validate(payload)


def test_build_result_json_reparse_cannot_recreate_bundle_seals() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))

    reparsed = DataArtifactBuildResult.model_validate(result.model_dump(mode="json"))
    assert reparsed.dataset.__artifact_publication_is_admitted__() is False
    assert reparsed.field_dictionary.__artifact_publication_is_admitted__() is False
    assert reparsed.source_collection.__artifact_publication_is_admitted__() is False


def test_build_result_rejects_source_collection_missing_used_raw_record() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    collection_payload = result.source_collection.model_dump(mode="json")
    collection_payload["members"][0]["raw_record_references"] = []
    _refresh_raw_record_registry(collection_payload["members"][0])
    collection = SourceCollectionArtifactCandidate.model_validate(
        _rehash_candidate_payload(collection_payload)
    )
    payload = result.model_dump(mode="json")
    payload["source_collection"] = collection.model_dump(mode="json")
    payload["output_hash"] = compute_data_artifact_output_hash(payload)

    with pytest.raises(ValidationError, match="raw records"):
        DataArtifactBuildResult.model_validate(payload)


@pytest.mark.parametrize("tamper", ("row_key", "record_hash"))
def test_source_collection_rejects_raw_record_reference_tamper(tamper: str) -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).source_collection
    payload = candidate.model_dump(mode="json")
    reference = payload["members"][0]["raw_record_references"][0]
    if tamper == "row_key":
        reference["row_key"][0][1] = f"{reference['row_key'][0][1]}-tampered"
    else:
        reference["raw_record_content_hash"] = f"sha256:{'0' * 64}"
    _rehash_candidate_payload(payload)

    with pytest.raises(ValidationError, match="raw record registry"):
        SourceCollectionArtifactCandidate.model_validate(payload)


def test_dataset_rejects_orphan_and_missing_conflict_references() -> None:
    candidate = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    ).dataset

    orphan_payload = candidate.model_dump(mode="json")
    orphan = deepcopy(orphan_payload["conflicts"][0])
    orphan["conflict_id"] = "conflict.field.orphan"
    orphan_payload["conflicts"].append(orphan)
    _rehash_dataset_tree(orphan_payload)
    with pytest.raises(ValidationError, match="conflict registry.*orphan"):
        DatasetArtifactCandidate.model_validate(orphan_payload)

    missing_payload = candidate.model_dump(mode="json")
    row = next(item for item in missing_payload["rows"] if item["conflict_ids"])
    row["conflict_ids"] = []
    conflicted_outcome = next(item for item in row["fields"] if item.get("conflict_ids"))
    conflicted_outcome["conflict_ids"] = []
    _rehash_dataset_tree(missing_payload)
    with pytest.raises(ValidationError, match="selection status|conflict registry"):
        DatasetArtifactCandidate.model_validate(missing_payload)


def test_publisher_validators_independently_revalidate_damaged_candidate() -> None:
    candidate = build_data_artifact_candidates(build_input("star.tic_id")).dataset
    payload = candidate.model_dump(mode="json")
    payload["transformation_evidence"][0]["raw_value"] = "forged"
    payload["transformation_evidence"][0]["content_hash"] = (
        compute_data_artifact_content_hash(payload["transformation_evidence"][0])
    )
    _rehash_candidate_payload(payload)
    damaged_evidence = candidate.transformation_evidence[0].model_copy(
        update={
            "raw_value": "forged",
            "content_hash": payload["transformation_evidence"][0]["content_hash"],
        }
    )
    damaged = candidate.model_copy(
        update={
            "transformation_evidence": (
                damaged_evidence,
                *candidate.transformation_evidence[1:],
            ),
            "output_hash": payload["output_hash"],
            "candidate_id": payload["candidate_id"],
        }
    )
    context = SimpleNamespace(
        candidate=damaged,
        source_snapshot_ids=tuple(payload["source_snapshot_ids"]),
        evidence_ids=tuple(payload["evidence_ids"]),
    )

    with pytest.raises(
        ValueError, match="Dataset Evidence set.*complete domain projection"
    ):
        validate_data_artifact_evidence(context)
    with pytest.raises(
        ValueError, match="Dataset Evidence set.*complete domain projection"
    ):
        validate_data_artifact_domain(context)


def _numeric_values(*values: str):
    return tuple(
        SimpleNamespace(
            source_value_id=f"source.{index}",
            source_id=f"source-{index}",
            canonical_value=value,
        )
        for index, value in enumerate(values)
    )


@pytest.mark.parametrize(
    ("values", "absolute", "relative", "inclusive", "has_conflict"),
    (
        (("-1", "-1.09", "-1.18"), "0.1", "0", True, True),
        (("-0.05", "0", "0.05"), "0.1", "0", True, False),
        (("100", "109"), "0", "0.1", True, False),
        (("100", "112"), "0", "0.1", True, True),
        (("0", "0.1"), "0.1", "0", True, False),
        (("0", "0.1"), "0.1", "0", False, True),
        (("1000000000", "1000000001"), "0", "0.000000002", True, False),
        (("0", "1E-30"), "0", "0.1", True, False),
        (("1", "1"), "0", "0", True, False),
        (("1", "1"), "0", "0", False, False),
    ),
)
def test_numeric_collection_tolerance_semantics(
    values: tuple[str, ...],
    absolute: str,
    relative: str,
    inclusive: bool,
    has_conflict: bool,
) -> None:
    field = next(
        item
        for item in load_frozen_manifest_bundle().field_manifest.fields
        if item.field_id == "planet.radius"
    )
    rule_set = load_mapping_rule_set()
    comparison = rule_set.numeric_comparison.model_copy(
        update={
            "absolute_tolerance": Decimal(absolute),
            "relative_tolerance": Decimal(relative),
            "threshold_inclusive": inclusive,
        }
    )
    rule_set = rule_set.model_copy(update={"numeric_comparison": comparison})

    conflicts = _conflicts(field, _numeric_values(*values), rule_set)
    reversed_conflicts = _conflicts(
        field, tuple(reversed(_numeric_values(*values))), rule_set
    )

    assert bool(conflicts) is has_conflict
    assert bool(reversed_conflicts) is has_conflict
    if conflicts:
        assert conflicts[0].absolute_difference == reversed_conflicts[0].absolute_difference
        assert conflicts[0].relative_difference == reversed_conflicts[0].relative_difference


@pytest.mark.parametrize(
    "value",
    (
        "12345678901234567890123456789012345678901234567890123456789012345",
        "0." + "0" * 1001 + "1",
    ),
)
def test_decimal_capacity_rejects_excess_precision_or_scale(value: str) -> None:
    with pytest.raises(DataArtifactError) as exc_info:
        serialize_decimal(Decimal(value))

    assert exc_info.value.code == "CAPACITY_EXCEEDED"


def test_decimal_scientific_and_trailing_zero_forms_are_stable() -> None:
    assert (
        load_unit_conversion_catalog().zero_serialization_policy
        == "canonical_unsigned_zero"
    )
    assert serialize_decimal(Decimal("1.2300E+2")) == "123"
    assert serialize_decimal(Decimal("1.2300E-2")) == "0.0123"


@pytest.mark.parametrize("value", ("-0", "-0.0", "-0E+20"))
def test_decimal_parsing_normalizes_negative_zero_before_hashing(value: str) -> None:
    parsed = decimal_from_source(value)

    assert parsed == Decimal(0)
    assert parsed.as_tuple().sign == 0
