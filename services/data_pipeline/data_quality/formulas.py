"""Closed, deterministic C-05 ratio formula helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.schemas.data_quality import (
    QualityEvaluationPlan,
    QualityMetricId,
    QualityMetricResult,
    QualityMetricScope,
    QualityMetricStatus,
)


def make_metric(
    plan: QualityEvaluationPlan,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    numerator: int = 0,
    denominator: int = 0,
    status: QualityMetricStatus | None = None,
    incomplete_source: bool = False,
    applicable: bool = True,
    input_locator: str,
) -> QualityMetricResult:
    """Create one metric from the compiled plan; no dynamic expressions run."""

    metric_id = QualityMetricId(metric_id)
    scope = QualityMetricScope(scope)
    metric_plan = next((item for item in plan.metrics if item.metric_id is metric_id), None)
    if metric_plan is None:
        raise ValueError(f"unregistered quality metric: {metric_id.value}")
    if metric_plan.scope is not scope:
        raise ValueError("quality metric scope does not match compiled plan")
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ValueError("quality ratio counts are invalid")
    if not applicable:
        status = QualityMetricStatus.not_applicable
    elif incomplete_source and metric_plan.incomplete_source_policy == "insufficient":
        status = QualityMetricStatus.insufficient
    elif status is None and denominator <= 0:
        status = (
            QualityMetricStatus.not_applicable
            if metric_plan.empty_denominator_policy == "not_applicable"
            else QualityMetricStatus.insufficient
        )
    elif status is None:
        status = (
            QualityMetricStatus.determinate
            if denominator > 0
            else QualityMetricStatus.insufficient
        )
    value: Decimal | None = None
    if status is QualityMetricStatus.determinate:
        with localcontext() as context:
            context.prec = plan.precision_digits
            context.rounding = ROUND_HALF_EVEN
            value = Decimal(numerator) / Decimal(denominator)
    elif status is QualityMetricStatus.not_applicable:
        numerator = 0
        denominator = 0
    return QualityMetricResult(
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        status=status,
        numerator=numerator,
        denominator=denominator,
        value=value,
        formula_id=metric_plan.formula_id,
        formula_version=metric_plan.formula_version,
        formula_scope=metric_plan.scope,
        precision_digits=plan.precision_digits,
        input_locator=input_locator,
    )


def insufficient_metric(
    plan: QualityEvaluationPlan,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    numerator: int,
    denominator: int,
    input_locator: str,
) -> QualityMetricResult:
    return make_metric(
        plan,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        numerator=numerator,
        denominator=denominator,
        status=QualityMetricStatus.insufficient,
        input_locator=input_locator,
    )


def not_applicable_metric(
    plan: QualityEvaluationPlan,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    input_locator: str,
) -> QualityMetricResult:
    return make_metric(
        plan,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        status=QualityMetricStatus.not_applicable,
        input_locator=input_locator,
    )


__all__ = ["insufficient_metric", "make_metric", "not_applicable_metric"]
