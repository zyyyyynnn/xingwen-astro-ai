from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas.core import ResearchContract
from app.schemas.data_quality import (
    DataQualityEvaluationRejected,
    DataQualityEvaluationResult,
    DataQualityRuleSet,
    QualityErrorCode,
    QualityMetricResult,
    QualityMetricStatus,
    compute_quality_content_hash,
    compute_quality_output_hash,
    compute_quality_rule_set_content_hash,
    compute_research_contract_content_hash,
)
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set

from data_artifact_test_support import build_input
from test_data_quality_pipeline import _contract, make_quality_input


def _valid_contract(*requested_fields: str) -> ResearchContract:
    contract = _contract(*requested_fields)
    payload = contract.model_dump(mode="json")
    payload["content_hash"] = compute_research_contract_content_hash(payload)
    return ResearchContract.model_validate(payload)


def _rebuild_result(payload: dict) -> DataQualityEvaluationResult:
    dataset = payload["dataset_result"]
    dataset["content_hash"] = compute_quality_content_hash(dataset)
    payload["output_hash"] = compute_quality_output_hash(payload)
    payload["content_hash"] = compute_quality_content_hash(payload)
    return DataQualityEvaluationResult.model_validate(payload)


def test_row_flags_use_independent_formula_scope_and_metric_ids() -> None:
    quality_input, _ = make_quality_input("star.tic_id", scenario_id="identifier_conflict")

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    row = result.row_results[0]
    assert row.low_confidence.metric_id.value == "row_low_confidence_flag"
    assert row.review_required.metric_id.value == "row_review_required_flag"
    assert row.inconclusive.metric_id.value == "row_inconclusive_flag"
    assert row.low_confidence.formula_id == "row_low_confidence_flag.v1"
    assert row.review_required.formula_id == "row_review_required_flag.v1"
    assert row.inconclusive.formula_id == "row_inconclusive_flag.v1"
    assert result.field_results[0].same_source_conflict_rate.metric_id.value == (
        "field_same_source_conflict_rate"
    )
    assert result.field_results[0].cross_source_conflict_rate.metric_id.value == (
        "field_cross_source_conflict_rate"
    )


def test_formula_scope_mismatch_is_rejected_by_the_metric_schema() -> None:
    with pytest.raises(ValueError, match="formula scope"):
        QualityMetricResult(
            metric_id="row_completeness",
            scope="row",
            target_id="row.1",
            status="determinate",
            numerator=1,
            denominator=1,
            value=Decimal("1"),
            formula_id="row_completeness.v1",
            formula_version="1.0.0",
            formula_scope="dataset",
            precision_digits=28,
            input_locator="dataset.row.row.1.completeness",
        )


def test_incomplete_source_propagates_to_all_applicable_metric_layers() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        scenario_id="truncated_inconclusive",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert result.field_results[0].completeness.status is QualityMetricStatus.insufficient
    assert result.field_results[0].evidence_coverage.status is QualityMetricStatus.insufficient
    assert result.row_results[0].completeness.status is QualityMetricStatus.insufficient
    assert result.row_results[0].inconclusive.status is QualityMetricStatus.insufficient
    assert result.dataset_result.completeness.status is QualityMetricStatus.insufficient
    assert result.dataset_result.object_match_coverage.status is QualityMetricStatus.insufficient
    assert result.dataset_result.low_confidence_edge_rate.status is not QualityMetricStatus.determinate
    assert result.dataset_result.review_required_record_rate.status is not QualityMetricStatus.determinate
    assert result.dataset_result.inconclusive_record_rate.status is QualityMetricStatus.insufficient


def test_contract_hash_drift_is_rejected_even_when_input_hash_is_recomputed() -> None:
    valid = _valid_contract("star.tic_id")
    payload = valid.model_dump(mode="json")
    payload["quality_constraints"]["unit_consistency_min"] = 0.5
    drifted = ResearchContract.model_validate(payload)
    quality_input, _ = make_quality_input("star.tic_id", contract=drifted)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationRejected)
    assert result.error_code is QualityErrorCode.QUALITY_RESEARCH_CONTRACT_MISMATCH


def test_requested_field_order_is_a_set_semantic_for_contract_gate() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        "star.name",
        contract=_valid_contract("star.name", "star.tic_id"),
    )
    assert quality_input.dataset_candidate.requested_fields == ("star.tic_id", "star.name")

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert result.contract_gate.overall_status.value == "pass"


def test_self_consistent_fake_result_is_rejected_by_canonical_admission() -> None:
    quality_input, build_result = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_metric = fake_payload["dataset_result"]["object_match_coverage"]
    fake_metric["numerator"] = 3
    fake_metric["value"] = "0.75"
    fake_result = _rebuild_result(fake_payload)

    with pytest.raises(Exception, match="quality admission"):
        admit_data_artifact_quality(
            build_result=build_result,
            evaluation_input=quality_input,
            evaluation_result=fake_result,
        )


def test_rule_set_binding_compiles_into_the_gate_plan() -> None:
    from services.data_pipeline.data_quality.policy import compile_quality_evaluation_plan

    rules = load_frozen_quality_rule_set()
    plan = compile_quality_evaluation_plan(rules)

    assert tuple(item.constraint_id for item in plan.gate_bindings) == tuple(
        item.constraint_id for item in rules.gate_bindings
    )
    assert tuple(item.metric_id for item in plan.metrics) == tuple(
        item.metric_id for item in rules.formula_registry
    )


def test_compiled_rule_set_formula_binding_drives_metric_creation() -> None:
    from services.data_pipeline.data_quality.formulas import make_metric
    from services.data_pipeline.data_quality.policy import compile_quality_evaluation_plan

    frozen = load_frozen_quality_rule_set()
    payload = frozen.model_dump(mode="json")
    payload["formula_registry"][0]["formula_id"] = "field_completeness.rebound.v1"
    payload["content_hash"] = compute_quality_rule_set_content_hash(payload)
    rebound = DataQualityRuleSet.model_validate(payload)
    plan = compile_quality_evaluation_plan(rebound)

    metric = make_metric(
        plan,
        metric_id="field_completeness",
        scope="field",
        target_id="star.tic_id",
        numerator=1,
        denominator=1,
        input_locator="dataset.field.star.tic_id.completeness",
    )

    assert metric.formula_id == "field_completeness.rebound.v1"


def test_result_domain_closure_rejects_missing_dataset_row_reference() -> None:
    quality_input, _ = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_payload["dataset_result"]["row_result_ids"] = []

    with pytest.raises(ValueError, match="row_result_ids|domain closure"):
        _rebuild_result(fake_payload)


def test_result_id_is_bound_to_input_and_rule_set() -> None:
    quality_input, _ = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_payload["result_id"] = "quality.forged"

    with pytest.raises(ValueError, match="result_id"):
        _rebuild_result(fake_payload)


def test_metric_schema_does_not_carry_gate_threshold_placeholders() -> None:
    from app.schemas.data_quality import QualityMetricResult

    assert "threshold" not in QualityMetricResult.model_fields
    assert "threshold_source" not in QualityMetricResult.model_fields


def test_publisher_validators_use_admission_commitment_without_re_evaluation(monkeypatch) -> None:
    quality_input, build_result = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    import services.data_pipeline.data_quality.admission as admission_module

    admission_calls = []
    canonical_evaluate = admission_module.evaluate_data_quality

    def count_admission_evaluation(value):
        admission_calls.append(value)
        return canonical_evaluate(value)

    monkeypatch.setattr(admission_module, "evaluate_data_quality", count_admission_evaluation)
    admitted = admit_data_artifact_quality(
        build_result=build_result,
        evaluation_input=quality_input,
        evaluation_result=evaluated,
    )
    assert len(admission_calls) == 1
    validator = build_data_quality_publication_validator(admitted, candidate_kind="dataset")

    def fail_if_recomputed(_value):
        raise AssertionError("Publisher must not re-run the C-05 evaluator")

    monkeypatch.setattr(
        "services.data_pipeline.data_quality.admission.evaluate_data_quality",
        fail_if_recomputed,
    )

    try:
        candidate = build_result.dataset
        admit_artifact_candidate(
            candidate,
            schema_version=candidate.schema_version,
            source_snapshot_ids=candidate.source_snapshot_ids,
            evidence_ids=candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validator,
        )
    except AssertionError as error:
        pytest.fail(str(error))
