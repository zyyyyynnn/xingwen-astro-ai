"""ResearchContract quality gate; it consumes C-05 metrics only."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from app.schemas.core import ArtifactKind, UnitPolicy
from app.schemas.data_quality import (
    DataQualityRuleSet,
    DatasetQualityResult,
    QualityConstraintResult,
    QualityGateStatus,
    QualityMetricId,
    QualityMetricResult,
    QualityMetricStatus,
    ResearchContractQualityGate,
    compute_quality_content_hash,
)
from app.schemas.data_artifacts import DatasetArtifactCandidate, SourceCollectionArtifactCandidate
from app.schemas.manifest import ManifestBundle
from app.schemas.core import ResearchContract


def evaluate_contract_gate(
    contract: ResearchContract,
    *,
    dataset_candidate: DatasetArtifactCandidate,
    source_collection_candidate: SourceCollectionArtifactCandidate,
    dataset_result: DatasetQualityResult,
    manifests: ManifestBundle,
    rules: DataQualityRuleSet,
) -> ResearchContractQualityGate:
    checks: list[QualityConstraintResult] = []
    checks.append(
        _metric_check(
            rules,
            constraint_id="contract.source_completeness_min",
            source_field="quality_constraints.source_completeness_min",
            metric=dataset_result.source_scope_completeness,
            threshold=Decimal(str(contract.quality_constraints.source_completeness_min)),
        )
    )
    checks.append(
        _metric_check(
            rules,
            constraint_id="contract.unit_consistency_min",
            source_field="quality_constraints.unit_consistency_min",
            metric=dataset_result.unit_consistency,
            threshold=Decimal(str(contract.quality_constraints.unit_consistency_min)),
            not_applicable_is_pass=True,
        )
    )
    checks.append(
        _metric_check(
            rules,
            constraint_id="contract.evidence_minimum_coverage",
            source_field="evidence_requirements.minimum_coverage",
            metric=dataset_result.evidence_coverage,
            threshold=Decimal(str(contract.evidence_requirements.minimum_coverage)),
        )
    )
    checks.append(
        _boolean_check(
            rules,
            constraint_id="contract.unit_policy",
            source_field="data_requirements.unit_policy",
            observed=contract.data_requirements.unit_policy is UnitPolicy.canonical,
            input_locator="research_contract.data_requirements.unit_policy",
        )
    )
    checks.append(
        _boolean_check(
            rules,
            constraint_id="contract.requested_fields",
            source_field="requested_fields",
            observed=tuple(contract.requested_fields) == tuple(dataset_candidate.requested_fields),
            input_locator="research_contract.requested_fields",
        )
    )
    allowed_table_sources = set(manifests.resolve_source_scope(contract.source_scope.allowed_sources))
    actual_table_sources = {member.source_id for member in source_collection_candidate.members}
    checks.append(
        _boolean_check(
            rules,
            constraint_id="contract.source_scope",
            source_field="source_scope.allowed_sources",
            observed=actual_table_sources <= allowed_table_sources,
            input_locator="research_contract.source_scope.allowed_sources",
        )
    )
    locator_ok = not contract.evidence_requirements.require_locator or bool(dataset_candidate.evidence_ids)
    snapshot_ok = not contract.evidence_requirements.require_source_snapshot or bool(
        dataset_candidate.source_snapshot_ids
    )
    checks.append(
        _boolean_check(
            rules,
            constraint_id="contract.require_locator",
            source_field="evidence_requirements.require_locator",
            observed=locator_ok,
            input_locator="research_contract.evidence_requirements.require_locator",
        )
    )
    checks.append(
        _boolean_check(
            rules,
            constraint_id="contract.require_source_snapshot",
            source_field="evidence_requirements.require_source_snapshot",
            observed=snapshot_ok,
            input_locator="research_contract.evidence_requirements.require_source_snapshot",
        )
    )
    status = (
        QualityGateStatus.fail
        if any(item.result is QualityGateStatus.fail for item in checks)
        else QualityGateStatus.insufficient
        if any(item.result is QualityGateStatus.insufficient for item in checks)
        else QualityGateStatus.pass_
    )
    payload = {
        "overall_status": status,
        "checks": [item.model_dump(mode="json") for item in checks],
        "rule_binding_version": rules.version,
        "input_locator": "research_contract",
    }
    return ResearchContractQualityGate(
        **payload,
        content_hash=compute_quality_content_hash(payload),
    )


def _metric_check(
    rules: DataQualityRuleSet,
    *,
    constraint_id: str,
    source_field: str,
    metric: QualityMetricResult,
    threshold: Decimal,
    not_applicable_is_pass: bool = False,
) -> QualityConstraintResult:
    if metric.status is QualityMetricStatus.insufficient:
        result = QualityGateStatus.insufficient
    elif metric.status is QualityMetricStatus.not_applicable and not_applicable_is_pass:
        result = QualityGateStatus.pass_
    elif metric.status is QualityMetricStatus.not_applicable or metric.value is None:
        result = QualityGateStatus.insufficient
    else:
        result = QualityGateStatus.pass_ if metric.value >= threshold else QualityGateStatus.fail
    return QualityConstraintResult(
        constraint_id=constraint_id,
        source_field=source_field,
        metric_id=metric.metric_id,
        observed_status=metric.status,
        observed_value=metric.value,
        threshold=threshold,
        operator="gte",
        result=result,
        rule_binding_version=rules.version,
        input_locator=metric.input_locator,
    )


def _boolean_check(
    rules: DataQualityRuleSet,
    *,
    constraint_id: str,
    source_field: str,
    observed: bool,
    input_locator: str,
) -> QualityConstraintResult:
    return QualityConstraintResult(
        constraint_id=constraint_id,
        source_field=source_field,
        metric_id=None,
        observed_status="not_checked",
        observed_value=None,
        threshold=None,
        operator="equals",
        result=QualityGateStatus.pass_ if observed else QualityGateStatus.fail,
        rule_binding_version=rules.version,
        input_locator=input_locator,
    )


__all__ = ["evaluate_contract_gate"]
