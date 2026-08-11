from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.contracts.manifest_policy import validate_research_contract_admission
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
    validate_data_artifact_candidates_against_input,
    validate_data_artifact_domain,
    validate_data_artifact_evidence,
)
from services.data_pipeline.data_quality import (
    admit_data_artifact_quality,
    build_data_quality_publication_validator,
    evaluate_data_quality,
)
from data_artifact_test_support import build_data_publication_bindings
from services.data_pipeline.data_quality.errors import DataQualityError
from services.data_pipeline.data_quality.observations import observe_quality
from services.data_pipeline.data_quality.policy import (
    compile_quality_evaluation_plan,
    load_frozen_quality_rule_set,
)
from services.data_pipeline.manifest import load_frozen_manifest_bundle

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
    assert row.low_confidence.formula_id == "row_low_confidence_flag"
    assert row.review_required.formula_id == "row_review_required_flag"
    assert row.inconclusive.formula_id == "row_inconclusive_flag"
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
            formula_id="row_completeness",
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


def test_production_confirmed_contract_enters_data_quality_without_hash_translation() -> None:
    draft = _contract("star.tic_id")
    contract_input = ResearchContractInput.model_validate(
        draft.model_dump(mode="json", include=set(ResearchContractInput.model_fields))
    )
    manifests = load_manifest_bundle(
        MANIFEST_ROOT / "case-manifest.json",
        MANIFEST_ROOT / "field-manifest.json",
    )
    content_hash = compute_research_contract_content_hash(contract_input)
    validate_research_contract_admission(
        contract_input,
        content_hash=content_hash,
        case_key="exoplanet_host_star",
        manifests=manifests,
    )
    persisted = ResearchContractModel(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        project_id=UUID("22222222-2222-4222-8222-222222222222"),
        version=3,
        content_hash=content_hash,
        content=contract_input.model_dump(mode="json"),
        created_from_draft_id=UUID("33333333-3333-4333-8333-333333333333"),
        created_at=draft.created_at,
    )
    read_contract = read_persisted_contract(persisted)
    quality_input, _ = make_quality_input("star.tic_id", contract=read_contract)

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    assert read_contract.content_hash == content_hash
    assert read_contract.model_dump(
        mode="json", include=set(ResearchContractInput.model_fields)
    ) == contract_input.model_dump(mode="json")
    assert result.input_references.research_contract_content_hash == content_hash


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
    assert ordinary_row.low_confidence.denominator == 1


@pytest.mark.parametrize(
    ("adjudication", "expected_alignment", "expected_review"),
    (
        (None, "conflict", Decimal("1")),
        (AdjudicationDecision.keep_unresolved, "conflict", Decimal("1")),
        (AdjudicationDecision.accepted, "accepted", Decimal("0")),
        (AdjudicationDecision.rejected, "rejected", Decimal("0")),
    ),
)
def test_conflict_review_required_follows_final_data_artifact_alignment(
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
    assert conflict_row.low_confidence.status is QualityMetricStatus.not_applicable
    assert conflict_row.low_confidence.denominator == 0
    assert conflict_row.review_required.value == expected_review


def test_unpaired_row_confidence_is_not_applicable() -> None:
    quality_input, _ = make_quality_input(
        "star.tic_id",
        scenario_id="truncated_inconclusive",
    )

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    unpaired = next(
        row
        for row in result.row_results
        if row.canonical_row_identity.record_type == "unpaired"
    )
    assert unpaired.low_confidence.status is QualityMetricStatus.not_applicable
    assert unpaired.low_confidence.denominator == 0


def test_metric_capacity_counts_exact_public_plan_records_at_boundary() -> None:
    from services.data_pipeline.data_quality.evaluator import (
        _count_public_metric_records,
        _validate_capacity,
    )

    quality_input, _ = make_quality_input("star.tic_id")
    rules = load_frozen_quality_rule_set()
    plan = compile_quality_evaluation_plan(rules)
    exact_count = _count_public_metric_records(quality_input, plan)
    old_estimate = (
        len(quality_input.dataset_candidate.rows)
        * len(quality_input.dataset_candidate.columns)
        * 30
    )
    at_limit = rules.model_copy(
        update={
            "capacity": rules.capacity.model_copy(
                update={"max_metric_records": exact_count}
            )
        }
    )

    _validate_capacity(quality_input, at_limit, plan)

    assert exact_count == (
        len(quality_input.dataset_candidate.columns)
        * sum(metric.scope.value == "field" for metric in plan.metrics)
        + len(quality_input.dataset_candidate.rows)
        * sum(metric.scope.value == "row" for metric in plan.metrics)
        + sum(metric.scope.value == "dataset" for metric in plan.metrics)
        + len(plan.gate_bindings)
    )
    assert exact_count < old_estimate


def test_metric_capacity_rejects_one_record_over_limit_with_stable_code() -> None:
    from services.data_pipeline.data_quality.evaluator import (
        _count_public_metric_records,
        _validate_capacity,
    )

    quality_input, _ = make_quality_input("star.tic_id")
    rules = load_frozen_quality_rule_set()
    plan = compile_quality_evaluation_plan(rules)
    exact_count = _count_public_metric_records(quality_input, plan)
    below_limit = rules.model_copy(
        update={
            "capacity": rules.capacity.model_copy(
                update={"max_metric_records": exact_count - 1}
            )
        }
    )

    with pytest.raises(DataQualityError) as exc_info:
        _validate_capacity(quality_input, below_limit, plan)

    assert exc_info.value.code is QualityErrorCode.QUALITY_CAPACITY_EXCEEDED


class _CountingTuple(tuple):
    def __new__(cls, values, visits: list[int]):
        instance = super().__new__(cls, values)
        instance.visits = visits
        return instance

    def __iter__(self):
        self.visits[0] += 1
        return super().__iter__()


def test_observations_visit_each_row_outcome_sequence_once() -> None:
    quality_input, _ = make_quality_input("star.tic_id")
    visits = [0]
    rows = tuple(
        row.model_copy(update={"fields": _CountingTuple(row.fields, visits)})
        for row in quality_input.dataset_candidate.rows
    )
    candidate = quality_input.dataset_candidate.model_copy(update={"rows": rows})

    observations = observe_quality(
        candidate,
        quality_input.data_artifact_input.crossmatch_result,
        load_frozen_manifest_bundle(),
    )

    assert len(observations.rows) == len(rows)
    assert visits[0] == len(rows)


def test_missing_data_artifact_evidence_is_rejected_at_data_artifact_boundary() -> None:
    quality_input, build_result = make_quality_input("star.tic_id")
    malformed = build_result.dataset.model_copy(update={"transformation_evidence": ()})

    with pytest.raises(ValueError, match="Evidence set differs"):
        validate_data_artifact_candidates_against_input(
            malformed,
            quality_input.data_artifact_input,
        )

    assert "QUALITY_EVIDENCE_GAP" not in QualityErrorCode.__members__


def test_unit_consistency_counts_retained_source_value_assertions() -> None:
    quality_input, _ = make_quality_input(
        "system.right_ascension",
        scenario_id="manual_decision_valid",
    )
    rules = load_frozen_quality_rule_set()

    result = evaluate_data_quality(quality_input)

    assert isinstance(result, DataQualityEvaluationResult)
    field = result.field_results[0]
    assert field.mapped_count == 2
    assert field.unit_consistency.denominator == 3
    assert result.dataset_result.unit_consistency.denominator == 3
    unit_formulas = [
        formula
        for formula in rules.formula_registry
        if "unit_consistency" in formula.metric_id.value
    ]
    assert all(
        "retained non-null SourceValue assertions" in formula.denominator_definition
        for formula in unit_formulas
    )
    assert all(
        formula.denominator_observation.value.endswith("unit_applicable_assertion_count")
        for formula in unit_formulas
    )


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
    payload["formula_registry"][0]["formula_id"] = "field_completeness.rebound"
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

    assert metric.formula_id == "field_completeness.rebound"
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
        raise AssertionError("Publisher must not re-run data-quality evaluation")

    monkeypatch.setattr(
        "services.data_pipeline.data_quality.admission.evaluate_data_quality",
        fail_if_recomputed,
    )

    try:
        candidate = build_result.dataset
        snapshots, evidence = build_data_publication_bindings(candidate)
        admit_artifact_candidate(
            candidate,
            schema_version=candidate.schema_version,
            source_snapshot_ids=candidate.source_snapshot_ids,
            evidence_ids=candidate.evidence_ids,
            evidence_validator=validate_data_artifact_evidence,
            domain_validator=validate_data_artifact_domain,
            quality_validator=validator,
            source_snapshot_bindings=snapshots,
            evidence_bindings=evidence,
        )
    except AssertionError as error:
        pytest.fail(str(error))
