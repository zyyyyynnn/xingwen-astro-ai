"""Closed, deterministic interpreter for compiled Data Quality Evaluation metric plans."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from typing import Mapping

from app.schemas.data_quality import (
    QualityEvaluationPlan,
    QualityErrorCode,
    QualityFailureStage,
    QualityFormulaKind,
    QualityMetricId,
    QualityMetricResult,
    QualityMetricScope,
    QualityMetricStatus,
)

from .errors import DataQualityError


def execute_metric(
    plan: QualityEvaluationPlan,
    *,
    metric_id: QualityMetricId | str,
    scope: QualityMetricScope | str,
    target_id: str,
    observations: Mapping[str, int | bool],
    incomplete_source: bool,
    input_locator: str,
    applicable: bool = True,
) -> QualityMetricResult:
    """Execute exactly one metric using only its immutable plan binding."""

    try:
        resolved_metric_id = QualityMetricId(metric_id)
        resolved_scope = QualityMetricScope(scope)
    except ValueError as error:
        raise _formula_error("quality metric identity is outside the closed plan", error) from error

    metric_plan = next(
        (item for item in plan.metrics if item.metric_id is resolved_metric_id),
        None,
    )
    if metric_plan is None:
        raise _formula_error("quality metric is not registered in the compiled plan")
    if metric_plan.scope is not resolved_scope:
        raise _formula_error("quality metric scope does not match the compiled plan")

    numerator_key = metric_plan.numerator_observation.value
    denominator_key = metric_plan.denominator_observation.value
    try:
        numerator_observation = observations[numerator_key]
        denominator_observation = observations[denominator_key]
    except KeyError as error:
        raise _formula_error("quality formula observation is missing", error) from error

    if isinstance(denominator_observation, bool) or not isinstance(
        denominator_observation, int
    ):
        raise _formula_error("quality formula denominator observation must be an integer count")
    denominator = denominator_observation
    if metric_plan.formula_kind is QualityFormulaKind.flag:
        if not isinstance(numerator_observation, bool):
            raise _formula_error("quality flag numerator observation must be boolean")
        numerator = int(numerator_observation)
    else:
        if isinstance(numerator_observation, bool) or not isinstance(
            numerator_observation, int
        ):
            raise _formula_error("quality ratio numerator observation must be an integer count")
        numerator = numerator_observation

    if numerator < 0 or denominator < 0 or numerator > denominator:
        raise _formula_error("quality formula counts are invalid")

    structurally_not_applicable = not applicable or (
        metric_plan.formula_kind is QualityFormulaKind.flag and denominator == 0
    )
    if structurally_not_applicable:
        status = QualityMetricStatus.not_applicable
    elif incomplete_source:
        status = QualityMetricStatus(metric_plan.incomplete_source_policy)
    elif denominator == 0:
        status = QualityMetricStatus(metric_plan.empty_denominator_policy)
    else:
        status = QualityMetricStatus.determinate

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
        metric_id=resolved_metric_id,
        scope=resolved_scope,
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


def _formula_error(message: str, cause: Exception | None = None) -> DataQualityError:
    return DataQualityError(
        QualityErrorCode.QUALITY_METRIC_FORMULA_INVALID,
        message,
        stage=QualityFailureStage.metric_validation,
        cause=cause,
    )


__all__ = ["execute_metric"]
