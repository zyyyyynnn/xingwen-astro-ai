from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.data_artifacts import LimitStatus, MappedCanonicalValue, UncertaintyStatus
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_artifacts.errors import DataArtifactError
from services.data_pipeline.data_artifacts.pipeline import (
    _limit,
    _numeric_values_agree,
    _uncertainty,
)
from services.data_pipeline.data_artifacts.policy import load_mapping_rule_set
from services.data_pipeline.manifest import load_frozen_manifest_bundle

from data_artifact_test_support import build_input


def test_mapping_uses_c08_normalized_identity_and_preserves_all_sources() -> None:
    result = build_data_artifact_candidates(build_input("star.tic_id"))
    paired = next(row for row in result.dataset.rows if row.crossmatch_record_type == "paired")
    outcome = paired.fields[0]

    assert isinstance(outcome, MappedCanonicalValue)
    assert outcome.canonical_value == "TIC 101"
    assert len(outcome.candidate_source_value_ids) == 2
    assert not outcome.conflict_ids
    retained = {
        value.source_value_id: value
        for value in result.dataset.source_values
        if value.source_value_id in outcome.candidate_source_value_ids
    }
    assert {value.raw_field for value in retained.values()} == {"tid", "tic_id"}
    assert {value.source_id for value in retained.values()} == {
        "nasa_exoplanet_archive.toi",
        "nasa_exoplanet_archive.ps",
    }
    assert all(value.source_id != "nasa_exoplanet_archive.pscomppars" for value in retained.values())
    selected = retained[outcome.selected_source_value_id]
    assert selected.source_priority == 1
    assert selected.source_id == "nasa_exoplanet_archive.toi"


def test_requested_field_order_is_canonical_and_hash_invariant() -> None:
    first_input = build_input("star.tic_id", "star.name")
    second_input = build_input("star.name", "star.tic_id")

    first = build_data_artifact_candidates(first_input)
    second = build_data_artifact_candidates(second_input)

    assert first_input.input_hash == second_input.input_hash
    assert first == second
    assert first.dataset.requested_fields == ("star.tic_id", "star.name")
    assert any(field.status == "declared_null" for row in first.dataset.rows for field in row.fields)


def _radius_context():
    input_value = build_input("star.tic_id")
    bundle = load_frozen_manifest_bundle()
    field = next(item for item in bundle.field_manifest.fields if item.field_id == "planet.radius")
    alias = next(
        item
        for item in field.source_aliases
        if item.source_id == "nasa_exoplanet_archive.ps" and item.raw_field == "pl_radj"
    )
    candidate = next(
        item
        for item in input_value.crossmatch_result.candidates
        if item.side.value == "right"
    )
    return input_value, bundle, field, alias, candidate


def test_asymmetric_uncertainty_preserves_signs_null_locator_and_conversion() -> None:
    input_value, bundle, field, alias, candidate = _radius_context()
    record = SimpleNamespace(
        payload={"pl_radjerr1": "0.1", "pl_radjerr2": None}
    )

    uncertainty = _uncertainty(record, candidate, field, alias, input_value, bundle)

    assert uncertainty.status is UncertaintyStatus.partial
    assert str(uncertainty.source_positive) == "0.1"
    assert uncertainty.source_negative is None
    assert str(uncertainty.canonical_positive) == "1.120898073093868079835687744"
    assert uncertainty.positive_locator is not None
    assert uncertainty.negative_locator is not None


def test_invalid_uncertainty_fails_with_stable_local_code() -> None:
    input_value, bundle, field, alias, candidate = _radius_context()
    record = SimpleNamespace(payload={"pl_radjerr1": "invalid", "pl_radjerr2": "-0.1"})

    with pytest.raises(DataArtifactError) as exc_info:
        _uncertainty(record, candidate, field, alias, input_value, bundle)

    assert exc_info.value.code == "INVALID_UNCERTAINTY"
    assert exc_info.value.cause is not None


@pytest.mark.parametrize(
    ("flag", "expected"),
    ((0, LimitStatus.measured), (1, LimitStatus.lower_limit), (-1, LimitStatus.upper_limit)),
)
def test_manifest_limit_flags_are_closed_and_preserved(flag: int, expected: LimitStatus) -> None:
    _, _, _, alias, candidate = _radius_context()
    record = SimpleNamespace(payload={"pl_radjlim": flag})

    limit = _limit(record, candidate, alias, "1")

    assert limit.status is expected
    assert limit.raw_flag == flag
    assert limit.locator is not None


def test_unknown_limit_and_limit_without_value_fail_closed() -> None:
    _, _, _, alias, candidate = _radius_context()

    with pytest.raises(DataArtifactError) as unknown:
        _limit(SimpleNamespace(payload={"pl_radjlim": 9}), candidate, alias, "1")
    with pytest.raises(DataArtifactError) as missing:
        _limit(SimpleNamespace(payload={"pl_radjlim": 1}), candidate, alias, None)

    assert unknown.value.code == "UNKNOWN_LIMIT_FLAG"
    assert missing.value.code == "LIMIT_WITHOUT_VALUE"


def test_numeric_conflict_threshold_is_stable_below_at_and_above_boundary() -> None:
    rule_set = load_mapping_rule_set()
    comparison = rule_set.numeric_comparison.model_copy(
        update={"absolute_tolerance": Decimal("0.1")}
    )
    rule_set = rule_set.model_copy(update={"numeric_comparison": comparison})

    assert _numeric_values_agree(Decimal("1"), Decimal("1.09"), rule_set)
    assert _numeric_values_agree(Decimal("1"), Decimal("1.1"), rule_set)
    assert not _numeric_values_agree(Decimal("1"), Decimal("1.1001"), rule_set)


@pytest.mark.parametrize(
    ("scenario_id", "member_count"),
    (
        ("exact_one_to_many", 3),
        ("exact_many_to_one", 3),
        ("exact_many_to_many", 4),
    ),
)
def test_accepted_non_one_to_one_topology_retains_every_member(
    scenario_id: str,
    member_count: int,
) -> None:
    result = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id=scenario_id)
    )
    accepted = next(row for row in result.dataset.rows if row.alignment_status == "accepted")

    assert len(accepted.source_member_ids) == member_count


def test_identity_conflict_remains_unresolved_without_field_selection() -> None:
    result = build_data_artifact_candidates(
        build_input("star.tic_id", scenario_id="identifier_conflict")
    )
    conflict = next(row for row in result.dataset.rows if row.alignment_status == "conflict")

    assert conflict.fields[0].status == "unresolved"
    conflict_evidence = [
        item
        for item in result.dataset.transformation_evidence
        if item.dataset_row_id == conflict.row_id
    ]
    assert conflict_evidence
    assert all(item.selection_status == "conflict" for item in conflict_evidence)
    assert len(result.dataset.selections) == sum(
        field.status == "mapped" for row in result.dataset.rows for field in row.fields
    )


def test_valid_manual_adjudication_accepts_coordinate_pair_without_rerunning_crossmatch() -> None:
    result = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    )
    paired = next(row for row in result.dataset.rows if row.crossmatch_record_type == "paired")

    assert paired.alignment_status == "accepted"
    assert paired.fields[0].status == "mapped"
    assert len(paired.source_member_ids) == 2
    assert result.dataset.conflicts


def test_numeric_cross_source_conflict_selects_display_but_retains_both_values() -> None:
    result = build_data_artifact_candidates(
        build_input("system.right_ascension", scenario_id="manual_decision_valid")
    )
    paired = next(row for row in result.dataset.rows if row.crossmatch_record_type == "paired")
    outcome = paired.fields[0]

    assert outcome.status == "mapped"
    assert outcome.conflict_ids
    assert len(outcome.candidate_source_value_ids) == 2
    retained = {
        value.source_value_id: value
        for value in result.dataset.source_values
        if value.source_value_id in outcome.candidate_source_value_ids
    }
    assert retained[outcome.selected_source_value_id].source_id == "nasa_exoplanet_archive.toi"
    assert {value.canonical_value for value in retained.values()} == {"10", "10.00025"}
