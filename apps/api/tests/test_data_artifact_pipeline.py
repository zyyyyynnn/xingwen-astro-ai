from __future__ import annotations

import pytest

from app.schemas.crossmatch import AdjudicationDecision
from app.schemas.data_artifacts import (
    CrossmatchRowAuthority,
    CrossmatchDataArtifactAuthority,
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
from services.data_pipeline.data_artifacts.projection import (
    derive_field_conflicts as _conflicts,
)
from decimal import Decimal
from types import SimpleNamespace
from pydantic import (
    BaseModel,
    ValidationError,
)
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    RawSourceRecordReference,
    SourceCollectionArtifactCandidate,
    compute_data_artifact_content_hash,
    compute_data_artifact_candidate_id,
    compute_data_artifact_canonical_content_hash,
    compute_data_artifact_lineage_hash,
    compute_data_artifact_output_hash,
    compute_raw_record_reference_registry_hash,
)
from services.data_pipeline.data_artifacts.conversion import (
    decimal_from_source,
    serialize_decimal,
)
from services.data_pipeline.data_artifacts.policy import load_mapping_rule_set
from services.data_pipeline.data_artifacts.policy import load_unit_conversion_catalog
from services.data_pipeline.manifest import load_frozen_manifest_bundle


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
        authority=CrossmatchDataArtifactAuthority(
            left_acquisition=crossmatch_input.left,
            right_acquisition=crossmatch_input.right,
            crossmatch_result=crossmatch_result,
            document_observations=(),
        ),
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
    return _build_input_from_crossmatch(crossmatch_input, "planet.orbital_period")


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
        not row.fields
        for row in first.dataset.rows
        if row.entity_level == "planet_candidate"
    )
    assert {
        evidence.locator.source_snapshot_id
        for evidence in first.dataset.transformation_evidence
    } == set(first.dataset.source_snapshot_ids)


def test_pipeline_dataset_identity_distinguishes_entities_with_same_measurement() -> (
    None
):
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

    rows = [
        row
        for row in dataset.rows
        if isinstance(row.row_authority, CrossmatchRowAuthority)
        and row.row_authority.alignment_status.value == alignment_status
    ]
    assert rows
    assert all(row.canonical_row_identity.member_entities for row in rows)
    assert all(
        row.canonical_row_identity.alignment_status
        == row.row_authority.alignment_status
        and row.canonical_row_identity.entity_level == row.entity_level
        and row.canonical_row_identity.record_type == row.row_authority.record_type
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

    rejected = next(
        row
        for row in dataset.rows
        if isinstance(row.row_authority, CrossmatchRowAuthority)
        and row.row_authority.alignment_status.value == "rejected"
    )
    assert rejected.fields == ()
    assert rejected.canonical_row_identity.alignment_status == "rejected"
    assert rejected.canonical_row_identity.member_entities


def test_projection_requires_non_nullable_fields_only_for_applicable_sources() -> None:
    dataset = build_data_artifact_candidates(build_input("planet.toi_id")).dataset

    toi_row = next(
        row for row in dataset.rows if row.entity_level == "planet_candidate"
    )
    ps_row = next(row for row in dataset.rows if row.entity_level == "planet_assertion")

    assert toi_row.projected_field_ids == ("planet.toi_id",)
    assert ps_row.projected_field_ids == ()


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

    assert any(
        isinstance(row.row_authority, CrossmatchRowAuthority)
        and row.row_authority.alignment_status.value == "inconclusive"
        for row in result.dataset.rows
    )
    assert result.source_collection.authority.inconclusive_record_keys


def test_acquisition_payload_tamper_is_rejected_even_with_recomputed_input_hash() -> (
    None
):
    from app.schemas.data_artifacts import compute_data_artifact_input_hash

    input_value = build_input("star.tic_id")
    assert isinstance(input_value.authority, CrossmatchDataArtifactAuthority)
    record = input_value.authority.left_acquisition.records[0]
    tampered_record = record.model_copy(
        update={"payload": {**record.payload, "tid": 999}}
    )
    tampered_left = input_value.authority.left_acquisition.model_copy(
        update={"records": (tampered_record,)}
    )
    tampered_authority = input_value.authority.model_copy(
        update={"left_acquisition": tampered_left}
    )
    tampered = input_value.model_copy(update={"authority": tampered_authority})
    tampered = tampered.model_copy(
        update={"input_hash": compute_data_artifact_input_hash(tampered)}
    )

    with pytest.raises(DataArtifactError) as exc_info:
        build_data_artifact_candidates(tampered)

    assert exc_info.value.code == "SOURCE_RECORD_HASH_MISMATCH"


# --- durable data-artifact semantics moved from the removed review-history suite ---
def _rehash_candidate_payload(payload: dict) -> dict:
    if payload["kind"] == "dataset":
        payload["canonical_content_hash"] = (
            compute_data_artifact_canonical_content_hash(payload)
        )
        payload["lineage_hash"] = compute_data_artifact_lineage_hash(payload)
    payload["output_hash"] = compute_data_artifact_output_hash(payload)
    identity_hash = payload.get("canonical_content_hash", payload["output_hash"])
    payload["candidate_id"] = compute_data_artifact_candidate_id(
        payload["kind"],
        identity_hash,
        schema_version=payload["schema_version"],
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


def _numeric_values(*values: str):
    return tuple(
        SimpleNamespace(
            source_value_id=f"source.{index}",
            source_id=f"source-{index}",
            canonical_value=value,
        )
        for index, value in enumerate(values)
    )


def test_output_hash_ignores_nested_nulls_for_dict_and_model_inputs() -> None:
    class Payload(BaseModel):
        kind: str
        metadata: dict[str, object | None]

    payload = Payload(
        kind="source_collection",
        metadata={"catalog": "NASA", "missing_value": None},
    )

    assert compute_data_artifact_output_hash(payload) == (
        compute_data_artifact_output_hash(payload.model_dump(mode="json"))
    )


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


def test_source_collection_members_bind_each_source_and_all_raw_records() -> None:
    input_value = build_input("star.tic_id")
    result = build_data_artifact_candidates(input_value)

    assert tuple(
        member.side.value for member in result.source_collection.crossmatch_sources
    ) == (
        "left",
        "right",
    )
    assert isinstance(input_value.authority, CrossmatchDataArtifactAuthority)
    acquisitions = (
        input_value.authority.left_acquisition,
        input_value.authority.right_acquisition,
    )
    for member, acquisition in zip(
        result.source_collection.crossmatch_sources, acquisitions
    ):
        assert member.source_id == acquisition.snapshot.source_id
        assert member.source_snapshot_id == acquisition.snapshot.snapshot_id
        assert member.completion == acquisition.completion
        assert len(member.raw_record_references) == len(acquisition.records)
        assert {
            (reference.row_key, reference.raw_record_content_hash)
            for reference in member.raw_record_references
        } == {(record.row_key, record.content_hash) for record in acquisition.records}


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
    assert all(row.projected_field_ids == ("planet.radius",) for row in assertion_rows)
    assert all(
        isinstance(row.row_authority, CrossmatchRowAuthority)
        and len(row.row_authority.source_member_ids) == 1
        for row in assertion_rows
    )


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


def test_source_collection_keeps_one_record_reference_for_multi_field_use() -> None:
    input_value = build_input("star.tic_id", "star.name")
    result = build_data_artifact_candidates(input_value)

    for member, acquisition in zip(
        result.source_collection.crossmatch_sources,
        (
            input_value.authority.left_acquisition,
            input_value.authority.right_acquisition,
        ),
    ):
        assert len(member.raw_record_references) == len(acquisition.records)


def test_dataset_rejects_synchronized_extra_snapshot() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    payload = result.dataset.model_dump(mode="json")
    extra = "snapshot.forged"
    payload["source_snapshot_ids"].append(extra)
    payload["authority"]["source_snapshot_ids"].append(extra)
    with pytest.raises(ValidationError, match="exactly two snapshots"):
        DatasetArtifactCandidate.model_validate(_rehash_dataset_tree(payload))


def test_source_collection_members_survive_reversed_snapshot_sort_order() -> None:
    candidate = build_data_artifact_candidates(
        build_input("star.tic_id")
    ).source_collection
    payload = candidate.model_dump(mode="json")
    replacements = ("snapshot.z-left", "snapshot.a-right")
    for member, replacement in zip(payload["crossmatch_sources"], replacements):
        member["source_snapshot_id"] = replacement
        member["source_snapshot"]["snapshot_id"] = replacement
        for reference in member["raw_record_references"]:
            reference["source_snapshot_id"] = replacement
        _refresh_raw_record_registry(member)
    payload["source_snapshot_ids"] = sorted(replacements)
    payload["authority"]["source_snapshot_ids"] = sorted(replacements)
    _rehash_candidate_payload(payload)

    reparsed = SourceCollectionArtifactCandidate.model_validate(payload)

    assert tuple(member.side.value for member in reparsed.crossmatch_sources) == (
        "left",
        "right",
    )
    assert (
        tuple(member.source_snapshot_id for member in reparsed.crossmatch_sources)
        == replacements
    )
    assert reparsed.source_snapshot_ids == tuple(sorted(replacements))


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
        assert (
            conflicts[0].absolute_difference
            == reversed_conflicts[0].absolute_difference
        )
        assert (
            conflicts[0].relative_difference
            == reversed_conflicts[0].relative_difference
        )


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
