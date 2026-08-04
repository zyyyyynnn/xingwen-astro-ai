from __future__ import annotations

import pytest

from app.schemas.data_quality import QualityMetricStatus
from services.data_pipeline.data_quality.formulas import execute_metric
from services.data_pipeline.data_quality.policy import (
    compile_quality_evaluation_plan,
    load_frozen_quality_rule_set,
)


@pytest.mark.parametrize(
    (
        "applicable",
        "incomplete_source",
        "numerator",
        "denominator",
        "expected_status",
    ),
    (
        (True, False, 0, 0, QualityMetricStatus.not_applicable),
        (True, True, 1, 1, QualityMetricStatus.insufficient),
        (True, True, 0, 0, QualityMetricStatus.insufficient),
        (False, True, 0, 0, QualityMetricStatus.not_applicable),
    ),
)
def test_metric_state_priority(
    applicable: bool,
    incomplete_source: bool,
    numerator: int,
    denominator: int,
    expected_status: QualityMetricStatus,
) -> None:
    plan = compile_quality_evaluation_plan(load_frozen_quality_rule_set())

    result = execute_metric(
        plan,
        metric_id="field_completeness",
        scope="field",
        target_id="star.tic_id",
        observations={
            "field.mapped_count": numerator,
            "field.applicable_count": denominator,
        },
        incomplete_source=incomplete_source,
        applicable=applicable,
        input_locator="dataset.field.star.tic_id.completeness",
    )

    assert result.status is expected_status
    assert result.value is None
    if expected_status is QualityMetricStatus.not_applicable:
        assert result.numerator == 0
        assert result.denominator == 0
    else:
        assert result.numerator == numerator
        assert result.denominator == denominator
