from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas.data_quality import (
    DataQualityEvaluationRejected,
    DataQualityEvaluationResult,
    QualityErrorCode,
    QualityMetricResult,
    QualityMetricStatus,
    compute_quality_content_hash,
    compute_quality_output_hash,
)
from services.data_pipeline.data_quality import evaluate_data_quality


def test_quality_metric_uses_closed_decimal_ratio_states() -> None:
    metric = QualityMetricResult(
        metric_id="field_completeness",
        scope="field",
        target_id="planet.toi_id",
        status=QualityMetricStatus.determinate,
        numerator=2,
        denominator=3,
        value=Decimal("0.6666666666666666666666666667"),
        formula_id="field_completeness.v1",
        formula_version="1.0.0",
        threshold=None,
        threshold_source=None,
        input_locator="dataset.field.planet.toi_id",
    )

    assert metric.value == Decimal("0.6666666666666666666666666667")
    assert metric.model_dump(mode="json")["value"] == "0.6666666666666666666666666667"


def test_quality_metric_rejects_empty_determinate_ratio() -> None:
    with pytest.raises(ValueError, match="denominator"):
        QualityMetricResult(
            metric_id="field_completeness",
            scope="field",
            target_id="planet.toi_id",
            status=QualityMetricStatus.determinate,
            numerator=0,
            denominator=0,
            value=None,
            formula_id="field_completeness.v1",
            formula_version="1.0.0",
            threshold=None,
            threshold_source=None,
            input_locator="dataset.field.planet.toi_id",
        )


def test_rejected_quality_outcome_carries_no_fake_metrics() -> None:
    payload = {
        "kind": "data_quality_rejected",
        "schema_version": "1.0.0",
        "failure_stage": "input_validation",
        "error_code": QualityErrorCode.QUALITY_INPUT_INVALID,
        "message": "quality input is invalid",
        "input_hash": None,
        "rule_set_reference": None,
        "field_results": [],
        "row_results": [],
        "dataset_result": None,
    }
    payload["output_hash"] = compute_quality_output_hash(payload)
    payload["content_hash"] = compute_quality_content_hash(payload)
    rejected = DataQualityEvaluationRejected(**payload)

    assert rejected.field_results == ()
    assert rejected.row_results == ()
    assert rejected.dataset_result is None
    assert rejected.model_dump(mode="json")["error_code"] == "QUALITY_INPUT_INVALID"


def test_quality_result_does_not_extend_core_artifact_kinds() -> None:
    assert DataQualityEvaluationResult.model_fields["kind"].default == "data_quality"


def test_public_entry_rejects_untyped_input_without_fake_quality_rows() -> None:
    result = evaluate_data_quality({"unexpected": True})

    assert isinstance(result, DataQualityEvaluationRejected)
    assert result.error_code is QualityErrorCode.QUALITY_INPUT_INVALID
    assert result.field_results == ()
    assert result.dataset_result is None
