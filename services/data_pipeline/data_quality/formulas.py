"""Closed, deterministic C-05 ratio formula helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.schemas.data_quality import (
    DataQualityRuleSet,
    QualityMetricId,
    QualityMetricResult,
    QualityMetricScope,
    QualityMetricStatus,
)


def make_metric(
    rules: DataQualityRuleSet,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    numerator: int = 0,
    denominator: int = 0,
    status: QualityMetricStatus | None = None,
    threshold: Decimal | None = None,
    threshold_source: str | None = None,
    input_locator: str,
) -> QualityMetricResult:
    """Create one metric from a RuleSet formula; no dynamic expressions run."""

    formula = next((item for item in rules.formula_registry if item.metric_id is metric_id), None)
    if formula is None:
        raise ValueError(f"unregistered quality metric: {metric_id.value}")
    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise ValueError("quality ratio counts are invalid")
    if status is None:
        status = (
            QualityMetricStatus.determinate
            if denominator > 0
            else QualityMetricStatus.not_applicable
        )
    value: Decimal | None = None
    if status is QualityMetricStatus.determinate:
        with localcontext() as context:
            context.prec = rules.precision_digits
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
        formula_id=formula.formula_id,
        formula_version=formula.version,
        threshold=threshold,
        threshold_source=threshold_source,
        input_locator=input_locator,
    )


def insufficient_metric(
    rules: DataQualityRuleSet,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    numerator: int,
    denominator: int,
    input_locator: str,
) -> QualityMetricResult:
    return make_metric(
        rules,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        numerator=numerator,
        denominator=denominator,
        status=QualityMetricStatus.insufficient,
        input_locator=input_locator,
    )


def not_applicable_metric(
    rules: DataQualityRuleSet,
    *,
    metric_id: QualityMetricId,
    scope: QualityMetricScope,
    target_id: str,
    input_locator: str,
) -> QualityMetricResult:
    return make_metric(
        rules,
        metric_id=metric_id,
        scope=scope,
        target_id=target_id,
        status=QualityMetricStatus.not_applicable,
        input_locator=input_locator,
    )


__all__ = ["insufficient_metric", "make_metric", "not_applicable_metric"]
