from __future__ import annotations

from app.schemas.core import ScientificSkillId
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import (
    ScientificSkillBudget,
    ScientificSkillRequest,
)


def _execute(task_kind: str, rows: list[dict[str, object]]) -> dict[str, object]:
    request = ScientificSkillRequest(
        request_id=f"request.model.{task_kind}",
        project_id="project.model",
        run_id="run.model",
        skill_id=ScientificSkillId.tabular_machine_learning,
        parameters={
            "rows": rows,
            "feature_fields": ["x", "y"],
            "target_field": "target",
            "task_kind": task_kind,
            "algorithm": "random_forest",
            "test_fraction": 0.25,
            "random_seed": 17,
            "cv_folds": 4,
        },
        source_references=(),
        budget=ScientificSkillBudget(max_input_rows=1000),
    )
    return build_scientific_skill_registry().execute(request).output


def test_classifier_reports_cross_validation_calibration_and_importance() -> None:
    rows = [
        {
            "row_id": f"row.{index}",
            "x": float(index),
            "y": float((index * 7) % 13),
            "target": "variable" if index % 2 else "stable",
        }
        for index in range(1, 49)
    ]

    output = _execute("classification", rows)
    metrics = output["metrics"]

    assert output["split"]["cross_validation_folds"] == 4
    assert 0 <= metrics["log_loss"]
    assert 0 <= metrics["brier_score"] <= 1
    assert 0 <= metrics["cv_accuracy_mean"] <= 1
    assert metrics["cv_accuracy_stddev"] >= 0
    assert (
        abs(metrics["feature_importance_x"] + metrics["feature_importance_y"] - 1)
        < 1e-9
    )


def test_regressor_reports_cross_validation_and_normalized_importance() -> None:
    rows = [
        {
            "row_id": f"row.{index}",
            "x": float(index),
            "y": float(index % 5),
            "target": float(index * 2 + (index % 3)),
        }
        for index in range(1, 49)
    ]

    metrics = _execute("regression", rows)["metrics"]

    assert metrics["cv_mean_absolute_error_mean"] >= 0
    assert metrics["cv_root_mean_squared_error_mean"] >= 0
    assert (
        abs(metrics["feature_importance_x"] + metrics["feature_importance_y"] - 1)
        < 1e-9
    )
