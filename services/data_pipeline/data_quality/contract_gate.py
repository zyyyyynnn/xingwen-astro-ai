"""Compile Contract gate observations from the immutable Data Quality Evaluation plan."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.schemas.core import ResearchContract, UnitPolicy
from app.schemas.data_artifacts import (
    DatasetArtifactCandidate,
    SourceCollectionArtifactCandidate,
)
from app.schemas.data_quality import (
    DatasetQualityResult,
    QualityConstraintResult,
    QualityEvaluationPlan,
    QualityGateStatus,
    QualityMetricResult,
    QualityMetricStatus,
    ResearchContractQualityGate,
    compute_quality_content_hash,
)
from app.schemas.manifest import ManifestBundle


def evaluate_contract_gate(
    contract: ResearchContract,
    *,
    dataset_candidate: DatasetArtifactCandidate,
    source_collection_candidate: SourceCollectionArtifactCandidate,
    dataset_result: DatasetQualityResult,
    manifests: ManifestBundle,
    plan: QualityEvaluationPlan,
) -> ResearchContractQualityGate:
    """Evaluate exactly the gate bindings compiled from the frozen RuleSet.

    The binding list is the only source of gate order, metric target, operator,
    Contract threshold locator, and result locator.  The observation catalogue
    below contains domain facts; it does not decide which facts are gates.
    """

    observations = _collect_observations(
        contract,
        dataset_candidate=dataset_candidate,
        source_collection_candidate=source_collection_candidate,
        dataset_result=dataset_result,
        manifests=manifests,
    )
    checks = tuple(
        _evaluate_binding(contract, binding, observations, dataset_result)
        for binding in plan.gate_bindings
    )
    overall_status = aggregate_gate_status(checks)
    payload = {
        "overall_status": overall_status,
        "checks": [item.model_dump(mode="json") for item in checks],
        "rule_binding_version": plan.rule_set_version,
        "input_locator": "research_contract",
    }
    return ResearchContractQualityGate(
        **payload,
        content_hash=compute_quality_content_hash(payload),
    )


def _collect_observations(
    contract: ResearchContract,
    *,
    dataset_candidate: DatasetArtifactCandidate,
    source_collection_candidate: SourceCollectionArtifactCandidate,
    dataset_result: DatasetQualityResult,
    manifests: ManifestBundle,
) -> dict[str, QualityMetricResult | bool]:
    allowed_sources = set(
        manifests.resolve_source_scope(contract.source_scope.allowed_sources)
    )
    actual_sources = {
        member.source_id for member in source_collection_candidate.members
    }
    observations: dict[str, QualityMetricResult | bool] = {
        f"dataset.{field_name}": getattr(dataset_result, field_name)
        for field_name in DatasetQualityResult.model_fields
        if isinstance(getattr(dataset_result, field_name), QualityMetricResult)
    }
    observations.update(
        {
            "contract.unit_policy_canonical": contract.data_requirements.unit_policy
            is UnitPolicy.canonical,
            "candidate.requested_fields_exact": set(contract.requested_fields)
            == set(dataset_candidate.requested_fields),
            "candidate.source_scope_allowed": actual_sources <= allowed_sources,
            "candidate.evidence_locator_present": (
                not contract.evidence_requirements.require_locator
                or bool(dataset_candidate.evidence_ids)
            ),
            "candidate.source_snapshot_present": (
                not contract.evidence_requirements.require_source_snapshot
                or bool(dataset_candidate.source_snapshot_ids)
            ),
        }
    )
    return observations


def _evaluate_binding(
    contract: ResearchContract,
    binding,
    observations: dict[str, QualityMetricResult | bool],
    dataset_result: DatasetQualityResult,
) -> QualityConstraintResult:
    if binding.metric_id is None:
        try:
            observed = observations[binding.observation_key]
        except KeyError as error:
            raise ValueError(
                f"quality gate binding references unknown observation: {binding.observation_key}"
            ) from error
        if not isinstance(observed, bool):
            raise ValueError("non-metric quality gate observation must be boolean")
        return QualityConstraintResult(
            constraint_id=binding.constraint_id,
            source_field=binding.contract_path,
            metric_id=None,
            observation_key=binding.observation_key,
            observed_status="not_checked",
            observed_value=None,
            threshold=None,
            operator=binding.operator,
            result=QualityGateStatus.pass_ if observed else QualityGateStatus.fail,
            rule_binding_version=binding.rule_binding_version,
            input_locator=binding.input_locator,
        )
    try:
        observed = getattr(dataset_result, binding.result_field or "")
    except AttributeError as error:
        raise ValueError(
            f"metric quality gate binding references unknown result field: {binding.result_field}"
        ) from error
    if (
        not isinstance(observed, QualityMetricResult)
        or observed.metric_id != binding.metric_id
    ):
        raise ValueError(
            "metric quality gate binding does not resolve to its declared metric"
        )
    try:
        if observations[binding.observation_key] is not observed:
            raise ValueError(
                "metric quality gate observation key is not bound to result field"
            )
    except KeyError as error:
        raise ValueError(
            f"quality gate binding references unknown observation: {binding.observation_key}"
        ) from error
    return evaluate_metric_constraint(
        contract,
        constraint_id=binding.constraint_id,
        contract_path=binding.contract_path,
        observation_key=binding.observation_key,
        metric=observed,
        operator=binding.operator,
        rule_binding_version=binding.rule_binding_version,
        input_locator=binding.input_locator,
        not_applicable_result=binding.not_applicable_result,
    )


def evaluate_metric_constraint(
    contract: ResearchContract,
    *,
    constraint_id: str,
    contract_path: str,
    observation_key: str,
    metric: QualityMetricResult,
    operator: str,
    rule_binding_version: str,
    input_locator: str,
    not_applicable_result: str,
) -> QualityConstraintResult:
    """Apply one compiled metric gate to an immutable Contract threshold."""

    threshold = _contract_decimal(contract, contract_path)
    return QualityConstraintResult(
        constraint_id=constraint_id,
        source_field=contract_path,
        metric_id=metric.metric_id,
        observation_key=observation_key,
        observed_status=metric.status,
        observed_value=metric.value,
        threshold=threshold,
        operator=operator,
        result=_metric_gate_status(
            metric,
            threshold,
            operator,
            not_applicable_result,
        ),
        rule_binding_version=rule_binding_version,
        input_locator=input_locator,
    )


def _contract_decimal(contract: ResearchContract, path: str) -> Decimal:
    current: Any = contract
    for segment in path.split("."):
        try:
            current = getattr(current, segment)
        except AttributeError as error:
            raise ValueError(
                f"Contract threshold locator is invalid: {path}"
            ) from error
    if isinstance(current, bool) or not isinstance(current, (int, float, Decimal)):
        raise ValueError(f"Contract gate locator is not numeric: {path}")
    return Decimal(str(current))


def _metric_gate_status(
    metric: QualityMetricResult,
    threshold: Decimal,
    operator: str,
    not_applicable_result: str,
) -> QualityGateStatus:
    if metric.status is QualityMetricStatus.insufficient:
        return QualityGateStatus.insufficient
    if metric.status is QualityMetricStatus.not_applicable:
        return (
            QualityGateStatus.pass_
            if not_applicable_result == "pass"
            else QualityGateStatus.insufficient
        )
    if metric.value is None:
        return QualityGateStatus.insufficient
    if operator == "gte" and metric.value >= threshold:
        return QualityGateStatus.pass_
    if operator == "equals" and metric.value == threshold:
        return QualityGateStatus.pass_
    return QualityGateStatus.fail


def aggregate_gate_status(
    checks: tuple[QualityConstraintResult, ...],
) -> QualityGateStatus:
    if any(item.result is QualityGateStatus.fail for item in checks):
        return QualityGateStatus.fail
    if any(item.result is QualityGateStatus.insufficient for item in checks):
        return QualityGateStatus.insufficient
    return QualityGateStatus.pass_


__all__ = [
    "aggregate_gate_status",
    "evaluate_contract_gate",
    "evaluate_metric_constraint",
]
