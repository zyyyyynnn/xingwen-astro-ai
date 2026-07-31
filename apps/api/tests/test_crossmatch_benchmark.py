from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.schemas.crossmatch import (
    CrossmatchBenchmarkManifest,
    compute_crossmatch_content_hash,
)
from services.data_pipeline.crossmatch.benchmark import (
    DEFAULT_CROSSMATCH_BENCHMARK_PATH,
    evaluate_crossmatch_benchmark,
    load_crossmatch_benchmark,
)


REQUIRED_SCENARIOS = {
    "exact_one_to_one",
    "exact_one_to_many",
    "exact_many_to_one",
    "exact_many_to_many",
    "identifier_coordinate_conflict",
    "same_tic_host_only",
    "multiple_planet_assertions",
    "gaia_not_inferred",
    "coordinate_only",
    "coordinate_ra_wrap",
    "coordinate_pole",
    "coordinate_zero_distance",
    "coordinate_threshold_boundary",
    "coordinate_outside_threshold",
    "coordinate_multiple_candidates",
    "curated_alias",
    "compound_alias",
    "alias_conflict",
    "identifier_conflict",
    "complete_unmatched",
    "truncated_inconclusive",
    "invalid_coordinate",
    "supplemental_complete_unmatched",
    "duplicate_record_reference",
    "record_source_mismatch",
    "manual_decision_valid",
    "manual_decision_stale_binding",
    "eligible_capacity_exceeded",
}


def test_frozen_crossmatch_benchmark_has_all_28_required_scenarios() -> None:
    benchmark = load_crossmatch_benchmark()
    raw_payload = json.loads(
        DEFAULT_CROSSMATCH_BENCHMARK_PATH.read_text(encoding="utf-8")
    )

    assert len(benchmark.scenarios) == 28
    assert {scenario.scenario_id for scenario in benchmark.scenarios} == (
        REQUIRED_SCENARIOS
    )
    assert benchmark.data_level == "synthetic_fixture"
    assert "not scientific ground truth" in benchmark.provenance_note
    assert compute_crossmatch_content_hash(raw_payload) == benchmark.content_hash


def test_frozen_crossmatch_benchmark_is_machine_executable_and_green() -> None:
    report = evaluate_crossmatch_benchmark(load_crossmatch_benchmark())

    assert report.scenario_count == 28
    assert report.passed_count == 28
    assert report.failed_count == 0
    assert all(result.status == "passed" for result in report.results)
    assert report.content_hash.startswith("sha256:")


def test_crossmatch_benchmark_rejects_content_tampering() -> None:
    payload = json.loads(
        DEFAULT_CROSSMATCH_BENCHMARK_PATH.read_text(encoding="utf-8")
    )
    payload["scenarios"][0]["description"] = "tampered"

    with pytest.raises(ValidationError, match="content_hash"):
        CrossmatchBenchmarkManifest.model_validate(payload)


def test_engine_never_emits_reserved_rejected_decision() -> None:
    # `MatchDecision.rejected` is a reserved Contract value; the automatic
    # engine must not emit it on any frozen benchmark scenario.
    from services.data_pipeline.crossmatch import align_cross_source_records
    from services.data_pipeline.crossmatch.benchmark import _scenario_input
    from services.data_pipeline.crossmatch.errors import CrossmatchError
    from app.schemas.crossmatch import MatchDecision

    benchmark = load_crossmatch_benchmark()
    for scenario in benchmark.scenarios:
        try:
            result = align_cross_source_records(_scenario_input(scenario))
        except (CrossmatchError, ValidationError):
            # Negative scenarios raise by design and produce no records.
            continue
        assert all(
            record.decision is not MatchDecision.rejected
            for record in result.records
        ), scenario.scenario_id
