"""Diagnostics are measured data, validated before Artifact publication."""

import pytest
from pydantic import ValidationError

from app.schemas.scientific_skills import (
    ModelEvaluationDiagnostics,
    ModelOutputMetadata,
)


@pytest.mark.parametrize(
    "changes",
    [
        {"confusion_matrix": {"labels": ["star", "galaxy"], "rows": [[1, 0], [0, 1]]}},
        {"confusion_matrix": {"labels": ["star", "galaxy"], "rows": [[2, -1], [0, 3]]}},
        {"confusion_matrix": {"labels": ["star", "galaxy"], "rows": [[2], [2]]}},
        {
            "regression_predictions": [
                {"row_id": "sample", "actual": 1, "predicted": float("nan")}
            ]
        },
        {
            "regression_predictions": [
                {"row_id": "sample", "actual": 1, "predicted": 1}
            ]
            * 2
        },
        {"forecast": [{"step": 2, "predicted_value": 3}]},
    ],
)
def test_invalid_measurements_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ModelEvaluationDiagnostics.model_validate(
            {"evaluated_sample_count": 4, **changes}
        )


def test_non_tensor_outputs_do_not_claim_tensor_metadata() -> None:
    with pytest.raises(ValidationError):
        ModelOutputMetadata(value_kind="sequence", dtype="FLOAT", shape=[None, 2])
    metadata = ModelOutputMetadata(
        value_kind="tensor", dtype="INT64", shape=["batch", 2]
    )
    assert metadata.shape == ("batch", 2)
