from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.contracts.manifest_policy import confirm_research_contract
from app.db.models import ResearchContractModel
from app.schemas.core import (
    ResearchContract,
    ResearchContractInput,
    compute_research_contract_content_hash,
)
from app.schemas.crossmatch import AdjudicationDecision
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
)
from app.schemas.manifest import load_manifest_bundle
from app.services.research import _contract as read_persisted_contract
from app.workflow.publisher import PublicationAdmissionError, admit_artifact_candidate
from services.data_pipeline.crossmatch.benchmark import (
    _scenario_input,
    load_crossmatch_benchmark,
)
from services.data_pipeline.data_artifacts.admission import (
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from services.data_pipeline.data_quality.errors import DataQualityError
from services.data_pipeline.data_quality.policy import load_frozen_quality_rule_set

from data_artifact_test_support import build_input
from test_data_artifact_pipeline import _build_input_from_crossmatch
from test_data_quality_pipeline import _contract, make_quality_input


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_ROOT = REPO_ROOT / "services/data_pipeline/manifests/exoplanet_host_star"


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
    with pytest.raises(ValidationError, match="formula scope"):
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


def test_production_confirmed_contract_enters_c05_without_hash_translation() -> None:
    draft = _contract("star.tic_id")
    contract_input = ResearchContractInput.model_validate(
        draft.model_dump(mode="json", include=set(ResearchContractInput.model_fields))
    )
    manifests = load_manifest_bundle(
        MANIFEST_ROOT / "case-manifest.v1.json",
        MANIFEST_ROOT / "field-manifest.v1.json",
    )
    confirmed = confirm_research_contract(
        contract_input,
        id="11111111-1111-4111-8111-111111111111",
        project_id="22222222-2222-4222-8222-222222222222",
        version=3,
        created_from_draft_id="33333333-3333-4333-8333-333333333333",
        created_at=draft.created_at,
        content_hash=compute_research_contract_content_hash(contract_input),
        case_key="exoplanet_host_star",
        manifests=manifests,
    )
    persisted = ResearchContractModel(
        id=UUID(confirmed.id),
        project_id=UUID(confirmed.project_id),
        version=confirmed.version,
        content_hash=confirmed.content_hash,
        content=contract_input.model_dump(mode="json"),
        created_from_draft_id=UUID(confirmed.created_from_draft_id),
        created_at=confirmed.created_at,
    )
    read_contract = read_persisted_contract(persisted)
    quality_input, _ = make_quality_input("star.tic_id", contract=read_contract)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert read_contract == confirmed
    assert result.input_references.research_contract_content_hash == confirmed.content_hash


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


def test_low_confidence_edge_component_marks_only_its_dataset_row() -> None:
    low_input, _ = make_quality_input(
        "system.right_ascension",
        scenario_id="coordinate_threshold_boundary",
    )
    ordinary_input, _ = make_quality_input("star.tic_id", scenario_id="exact_one_to_one")
    low_result = evaluate_data_quality(low_input)
    ordinary_result = evaluate_data_quality(ordinary_input)

    assert isinstance(low_result, DataQualityEvaluationResult)
    assert isinstance(ordinary_result, DataQualityEvaluationResult)
    assert low_result.dataset_result.low_confidence_edge_rate.numerator == 1
    flagged = [
        row
        for row in low_result.row_results
        if row.low_confidence.status is QualityMetricStatus.determinate
    ]
    ordinary = [row for row in low_result.row_results if row not in flagged]
    assert len(flagged) == 1
    assert flagged[0].low_confidence.value == Decimal("1")
    assert all(
        row.low_confidence.status is QualityMetricStatus.not_applicable for row in ordinary
    )
    ordinary_row = next(
        row for row in ordinary_result.row_results if row.alignment_status.value == "accepted"
    )
    assert ordinary_row.low_confidence.value == Decimal("0")


@pytest.mark.parametrize(
    ("adjudication", "expected_alignment", "expected_review"),
    (
        (None, "conflict", Decimal("1")),
        (AdjudicationDecision.keep_unresolved, "conflict", Decimal("1")),
        (AdjudicationDecision.accepted, "accepted", Decimal("0")),
        (AdjudicationDecision.rejected, "rejected", Decimal("0")),
    ),
)
def test_conflict_review_required_follows_final_c04_alignment(
    adjudication,
    expected_alignment: str,
    expected_review: Decimal,
) -> None:
    benchmark = load_crossmatch_benchmark()
    scenario = next(
        item for item in benchmark.scenarios if item.scenario_id == "identifier_conflict"
    )
    if adjudication is not None:
        scenario = scenario.model_copy(
            update={"manual_adjudication": adjudication, "manual_binding": "valid"}
        )
    data_input = _build_input_from_crossmatch(
        _scenario_input(scenario),
        "star.tic_id",
    )
    quality_input, _ = make_quality_input("star.tic_id", data_input=data_input)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    conflict_row = next(
        row
        for row in result.row_results
        if row.canonical_row_identity.record_type == "conflict_group"
    )
    assert conflict_row.alignment_status.value == expected_alignment
    assert conflict_row.review_required.value == expected_review


def test_self_consistent_fake_result_is_rejected_by_canonical_admission() -> None:
    quality_input, build_result = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_metric = fake_payload["dataset_result"]["object_match_coverage"]
    fake_metric["numerator"] = 3
    fake_metric["value"] = "0.75"
    fake_result = _rebuild_result(fake_payload)

    with pytest.raises(DataQualityError) as exc_info:
        admit_data_artifact_quality(
            build_result=build_result,
            evaluation_input=quality_input,
            evaluation_result=fake_result,
        )
    assert exc_info.value.code is QualityErrorCode.QUALITY_RESULT_HASH_MISMATCH


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
    from services.data_pipeline.data_quality.formulas import execute_metric
    from services.data_pipeline.data_quality.policy import compile_quality_evaluation_plan

    frozen = load_frozen_quality_rule_set()
    payload = frozen.model_dump(mode="json")
    payload["formula_registry"][0]["formula_id"] = "field_completeness.rebound.v1"
    metric_plan = payload["formula_registry"][0]
    metric_plan["numerator_observation"] = "field.declared_null_count"
    metric_plan["denominator_observation"] = "field.applicable_count"
    payload["content_hash"] = compute_quality_rule_set_content_hash(payload)
    rebound = DataQualityRuleSet.model_validate(payload)
    plan = compile_quality_evaluation_plan(rebound)

    metric = execute_metric(
        plan,
        metric_id="field_completeness",
        scope="field",
        target_id="star.tic_id",
        observations={
            "field.mapped_count": 1,
            "field.declared_null_count": 0,
            "field.applicable_count": 1,
        },
        incomplete_source=False,
        input_locator="dataset.field.star.tic_id.completeness",
    )

    assert metric.formula_id == "field_completeness.rebound.v1"
    assert metric.numerator == 0


def test_plan_interpreter_drives_empty_denominator_and_incomplete_policies() -> None:
    from services.data_pipeline.data_quality.formulas import execute_metric
    from services.data_pipeline.data_quality.policy import compile_quality_evaluation_plan

    frozen = load_frozen_quality_rule_set()
    payload = frozen.model_dump(mode="json")
    formula = payload["formula_registry"][0]
    formula["empty_denominator_policy"] = "insufficient"
    formula["incomplete_source_policy"] = "not_applicable"
    payload["content_hash"] = compute_quality_rule_set_content_hash(payload)
    plan = compile_quality_evaluation_plan(DataQualityRuleSet.model_validate(payload))

    empty = execute_metric(
        plan,
        metric_id="field_completeness",
        scope="field",
        target_id="star.tic_id",
        observations={"field.mapped_count": 0, "field.applicable_count": 0},
        incomplete_source=False,
        input_locator="dataset.field.star.tic_id.completeness",
    )
    incomplete = execute_metric(
        plan,
        metric_id="field_completeness",
        scope="field",
        target_id="star.tic_id",
        observations={"field.mapped_count": 1, "field.applicable_count": 1},
        incomplete_source=True,
        input_locator="dataset.field.star.tic_id.completeness",
    )

    assert empty.status is QualityMetricStatus.insufficient
    assert incomplete.status is QualityMetricStatus.not_applicable


def test_plan_interpreter_missing_observation_has_stable_error_code() -> None:
    from services.data_pipeline.data_quality.formulas import execute_metric
    from services.data_pipeline.data_quality.policy import compile_quality_evaluation_plan

    plan = compile_quality_evaluation_plan(load_frozen_quality_rule_set())
    with pytest.raises(DataQualityError) as exc_info:
        execute_metric(
            plan,
            metric_id="field_completeness",
            scope="field",
            target_id="star.tic_id",
            observations={},
            incomplete_source=False,
            input_locator="dataset.field.star.tic_id.completeness",
        )
    assert exc_info.value.code is QualityErrorCode.QUALITY_METRIC_FORMULA_INVALID


def test_result_domain_closure_rejects_missing_dataset_row_reference() -> None:
    quality_input, _ = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_payload["dataset_result"]["row_result_ids"] = []

    with pytest.raises(ValidationError, match="row_result_ids|domain closure"):
        _rebuild_result(fake_payload)


def test_result_id_is_bound_to_input_and_rule_set() -> None:
    quality_input, _ = make_quality_input("star.tic_id")
    evaluated = evaluate_data_quality(quality_input)
    assert isinstance(evaluated, DataQualityEvaluationResult)
    fake_payload = evaluated.model_dump(mode="json")
    fake_payload["result_id"] = "quality.forged"

    with pytest.raises(ValidationError, match="result_id"):
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
