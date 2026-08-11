"""Load and authenticate the frozen data quality RuleSet."""

from __future__ import annotations

from pathlib import Path

from app.schemas.data_quality import (
    DataQualityRuleSet,
    QualityEvaluationPlan,
    QualityMetricPlan,
    compute_quality_evaluation_plan_content_hash,
)


_RULE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "manifests"
    / "exoplanet_host_star"
    / "quality-rules"
)
DEFAULT_QUALITY_RULE_SET_PATH = _RULE_ROOT / "quality-rules.json"


def load_quality_rule_set(
    path: Path = DEFAULT_QUALITY_RULE_SET_PATH,
) -> DataQualityRuleSet:
    """Parse one versioned RuleSet; model validation includes its self-hash."""

    return DataQualityRuleSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_frozen_quality_rule_set() -> DataQualityRuleSet:
    """Load only the repository-authored Data Quality Evaluation RuleSet."""

    return load_quality_rule_set(DEFAULT_QUALITY_RULE_SET_PATH)


def require_frozen_quality_rule_set(candidate: DataQualityRuleSet) -> DataQualityRuleSet:
    """Reject caller rules even when a caller recomputed a modified self-hash."""

    frozen = load_frozen_quality_rule_set()
    if candidate != frozen:
        raise ValueError("caller quality RuleSet is not the frozen repository RuleSet")
    return frozen


def compile_quality_evaluation_plan(rules: DataQualityRuleSet) -> QualityEvaluationPlan:
    """Compile one immutable execution/validation plan from RuleSet metadata."""

    metrics = tuple(
        QualityMetricPlan(
            metric_id=formula.metric_id,
            scope=formula.scope,
            formula_id=formula.formula_id,
            formula_version=formula.version,
            result_field=formula.result_field,
            manifest_input=formula.manifest_input,
            formula_kind=formula.formula_kind,
            numerator_observation=formula.numerator_observation,
            denominator_observation=formula.denominator_observation,
            applicability=formula.applicability,
            incomplete_source_policy=formula.incomplete_source_policy,
            empty_denominator_policy=formula.empty_denominator_policy,
        )
        for formula in rules.formula_registry
    )
    payload = {
        "rule_set_id": rules.rule_set_id,
        "rule_set_version": rules.version,
        "rule_set_content_hash": rules.content_hash,
        "precision_digits": rules.precision_digits,
        "rounding_mode": rules.rounding_mode,
        "ratio_serialization": rules.ratio_serialization,
        "metrics": [item.model_dump(mode="json") for item in metrics],
        "gate_bindings": [item.model_dump(mode="json") for item in rules.gate_bindings],
    }
    return QualityEvaluationPlan(
        **payload,
        content_hash=compute_quality_evaluation_plan_content_hash(payload),
    )


def load_frozen_quality_evaluation_plan() -> QualityEvaluationPlan:
    return compile_quality_evaluation_plan(load_frozen_quality_rule_set())


def require_frozen_quality_evaluation_plan(candidate: QualityEvaluationPlan) -> QualityEvaluationPlan:
    frozen = load_frozen_quality_evaluation_plan()
    if candidate != frozen:
        raise ValueError("caller quality evaluation plan is not the frozen repository plan")
    return frozen


__all__ = [
    "DEFAULT_QUALITY_RULE_SET_PATH",
    "compile_quality_evaluation_plan",
    "load_frozen_quality_evaluation_plan",
    "load_frozen_quality_rule_set",
    "load_quality_rule_set",
    "require_frozen_quality_evaluation_plan",
    "require_frozen_quality_rule_set",
]
