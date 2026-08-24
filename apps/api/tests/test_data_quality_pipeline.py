from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.core import ResearchContract, compute_research_contract_content_hash
from app.schemas.data_quality import (
    DataQualityEvaluationInput,
    DataQualityEvaluationRejected,
    DataQualityEvaluationResult,
    QualityErrorCode,
    QualityMetricStatus,
    compute_data_quality_input_hash,
    compute_quality_rule_set_content_hash,
)
from services.data_pipeline.data_artifacts import build_data_artifact_candidates
from services.data_pipeline.data_quality import evaluate_data_quality
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set

from data_artifact_test_support import build_input


def _contract(*requested_fields: str, source_min: float = 1.0) -> ResearchContract:
    payload = {
        "id": "rc_data_quality_test",
        "project_id": "proj_data_quality_test",
        "version": 1,
        "research_goal": "Evaluate evidence-bound exoplanet data quality",
        "target_objects": ["exoplanet_candidate", "host_star"],
        "data_requirements": {
            "unit_policy": "canonical",
            "document_source_policy": "disabled",
        },
        "requested_fields": list(requested_fields),
        "source_scope": {"allowed_sources": ["nasa_exoplanet_archive"]},
        "paper_search_scope": {"max_candidates": 20},
        "output_requirements": ["dataset"],
        "evidence_requirements": {
            "require_locator": True,
            "require_source_snapshot": True,
            "minimum_coverage": 1.0,
        },
        "quality_constraints": {
            "source_completeness_min": source_min,
            "unit_consistency_min": 1.0,
        },
        "created_from_draft_id": "rcd_data_quality_test",
        "created_at": datetime(2026, 8, 3, tzinfo=timezone.utc),
        "content_hash": "sha256:" + "1" * 64,
    }
    payload["content_hash"] = compute_research_contract_content_hash(payload)
    return ResearchContract.model_validate(payload)


def make_quality_input(
    *requested_fields: str,
    scenario_id: str = "exact_one_to_one",
    rules=None,
    contract: ResearchContract | None = None,
    data_input=None,
):
    data_input = data_input or build_input(*requested_fields, scenario_id=scenario_id)
    build_result = build_data_artifact_candidates(data_input)
    quality_rules = rules or load_frozen_quality_rule_set()
    contract_value = contract or _contract(*requested_fields)
    payload = {
        "data_artifact_input": data_input,
        "dataset_candidate": build_result.dataset,
        "field_dictionary_candidate": build_result.field_dictionary,
        "source_collection_candidate": build_result.source_collection,
        "research_contract": contract_value,
        "quality_rule_set": quality_rules,
        "input_hash": "sha256:" + "0" * 64,
    }
    constructed = DataQualityEvaluationInput.model_construct(**payload)
    payload["input_hash"] = compute_data_quality_input_hash(constructed)
    return DataQualityEvaluationInput.model_validate(payload), build_result


def test_normal_case_produces_stable_three_layer_result() -> None:
    quality_input, _ = make_quality_input("star.tic_id")

    first = evaluate_data_quality(quality_input)
    second = evaluate_data_quality(
        quality_input.model_validate_json(quality_input.model_dump_json())
    )

    assert isinstance(first, DataQualityEvaluationResult)
    assert first == second
    assert first.contract_gate.overall_status.value == "pass"
    assert first.dataset_result.applicable_cell_count == 2
    assert first.dataset_result.completeness.value == 1
    assert first.dataset_result.object_match_coverage.numerator == 2
    assert first.dataset_result.object_match_coverage.denominator == 4
    assert first.dataset_result.evidence_coverage.value == 1
    assert first.field_results[0].field_id == "star.tic_id"
    assert (
        DataQualityEvaluationResult.model_validate_json(first.model_dump_json())
        == first
    )


def test_projected_field_scope_excludes_inapplicable_planet_rows() -> None:
    quality_input, _ = make_quality_input("star.tic_id")

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert [row.applicable_field_count for row in result.row_results] == [1, 1, 0]
    assert (
        result.row_results[-1].completeness.status is QualityMetricStatus.not_applicable
    )


def test_manifest_declared_unit_metric_uses_data_artifact_canonical_unit_admission() -> (
    None
):
    quality_input, _ = make_quality_input(
        "system.right_ascension",
        scenario_id="coordinate_only",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert (
        result.dataset_result.unit_consistency.status is QualityMetricStatus.determinate
    )
    assert result.dataset_result.unit_consistency.numerator == 1
    assert result.dataset_result.unit_consistency.denominator == 1


def test_truncated_source_is_insufficient_not_zero_or_failure() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        scenario_id="truncated_inconclusive",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert (
        result.dataset_result.source_scope_completeness.status
        is QualityMetricStatus.insufficient
    )
    assert result.dataset_result.source_scope_completeness.value is None
    assert result.contract_gate.overall_status.value == "insufficient"


def test_conflict_and_review_are_retained_as_raw_dataset_metrics() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        scenario_id="identifier_conflict",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert result.dataset_result.cross_source_conflict_rate.numerator == 1
    assert result.dataset_result.review_required_record_rate.numerator == 1
    assert (
        result.dataset_result.evidence_coverage.status
        is QualityMetricStatus.determinate
    )


def test_inconclusive_unpaired_scope_does_not_become_evidence_gap() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        scenario_id="truncated_inconclusive",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert result.dataset_result.inconclusive_record_rate.numerator > 0
    assert (
        result.dataset_result.inconclusive_record_rate.status
        is QualityMetricStatus.insufficient
    )
    assert (
        result.dataset_result.evidence_coverage.status
        is QualityMetricStatus.insufficient
    )


def test_recomputed_tampered_rule_set_is_rejected_as_non_frozen() -> None:
    frozen = load_frozen_quality_rule_set()
    tampered_payload = frozen.model_dump(mode="json")
    tampered_payload["precision_digits"] = 27
    tampered_payload["content_hash"] = compute_quality_rule_set_content_hash(
        tampered_payload
    )
    tampered = type(frozen).model_validate(tampered_payload)
    quality_input, _ = make_quality_input("star.tic_id", rules=tampered)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationRejected)
    assert result.error_code is QualityErrorCode.QUALITY_RULE_SET_MISMATCH


def test_rule_policy_formula_and_capacity_tampering_stays_non_frozen() -> None:
    frozen = load_frozen_quality_rule_set()
    payload = frozen.model_dump(mode="json")
    payload["formula_registry"][0]["formula_id"] = "field_completeness.tampered"
    payload["empty_denominator_policy"] = "insufficient"
    payload["capacity"]["max_rows"] = 99_999
    payload["content_hash"] = compute_quality_rule_set_content_hash(payload)
    tampered = type(frozen).model_validate(payload)
    quality_input, _ = make_quality_input("star.tic_id", rules=tampered)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationRejected)
    assert result.error_code is QualityErrorCode.QUALITY_RULE_SET_MISMATCH


def test_valid_candidate_from_another_data_artifact_build_cannot_be_reused() -> None:
    data_input = build_input("star.tic_id")
    original = build_data_artifact_candidates(data_input)
    foreign = build_data_artifact_candidates(build_input("planet.name"))
    rules = load_frozen_quality_rule_set()
    payload = {
        "data_artifact_input": data_input,
        "dataset_candidate": foreign.dataset,
        "field_dictionary_candidate": original.field_dictionary,
        "source_collection_candidate": original.source_collection,
        "research_contract": _contract("star.tic_id"),
        "quality_rule_set": rules,
        "input_hash": "sha256:" + "0" * 64,
    }
    constructed = DataQualityEvaluationInput.model_construct(**payload)
    payload["input_hash"] = compute_data_quality_input_hash(constructed)
    quality_input = DataQualityEvaluationInput.model_validate(payload)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationRejected)
    assert (
        result.error_code is QualityErrorCode.QUALITY_DATA_ARTIFACT_CANDIDATE_MISMATCH
    )
