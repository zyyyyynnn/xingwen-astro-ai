"""Leakage guarantees for split strategies in tabular modeling."""

from __future__ import annotations

import pytest

from app.schemas.core import ScientificSkillId
from services.scientific_skills.types import ScientificSkillRequest


def _request(parameters: dict[str, object]) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id="request.leakage",
        project_id="project.leakage",
        run_id="run.leakage",
        skill_id=ScientificSkillId.tabular_machine_learning,
        parameters=parameters,
        source_references=(),
    )


def _grouped_rows(groups: int = 6, per_group: int = 8) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_index in range(groups):
        label = "alpha" if group_index % 2 == 0 else "beta"
        for member in range(per_group):
            rows.append(
                {
                    "row_id": f"r{group_index}-{member}",
                    "x": float(group_index * 10 + member),
                    "y": float(member * 2 + group_index),
                    "observer": f"site_{group_index}",
                    "target": label,
                }
            )
    return rows


def test_group_split_keeps_groups_out_of_validation():
    from services.scientific_skills.modeling import evaluate_tabular_model

    result = evaluate_tabular_model(
        _request(
            {
                "rows": _grouped_rows(),
                "feature_fields": ["x", "y"],
                "target_field": "target",
                "split_strategy": "group",
                "group_field": "observer",
                "test_fraction": 0.3,
            }
        )
    )
    split = result["split"]
    assert split["strategy"] == "group"
    assert split["field"] == "observer"
    assert split["train_count"] + split["test_count"] == 48
    assert any("never cross" in item for item in result["limitations"])


def test_entity_split_behaves_like_group_split():
    from services.scientific_skills.modeling import evaluate_tabular_model

    result = evaluate_tabular_model(
        _request(
            {
                "rows": _grouped_rows(),
                "feature_fields": ["x", "y"],
                "target_field": "target",
                "split_strategy": "entity",
                "entity_field": "observer",
                "test_fraction": 0.3,
            }
        )
    )
    assert result["split"]["strategy"] == "entity"
    assert result["split"]["field"] == "observer"


def test_group_split_rejects_missing_group_field():
    from services.scientific_skills.modeling import evaluate_tabular_model

    with pytest.raises(ValueError, match="group split requires group_field"):
        evaluate_tabular_model(
            _request(
                {
                    "rows": _grouped_rows(),
                    "feature_fields": ["x", "y"],
                    "target_field": "target",
                    "split_strategy": "group",
                }
            )
        )


def test_time_split_never_trains_on_the_future():
    from services.scientific_skills.modeling import evaluate_tabular_model

    rows = [
        {
            "row_id": f"t{index}",
            "x": float(index),
            "y": float(index % 3),
            "observed_at": f"2024-01-{index + 1:02d}T00:00:00Z",
            "target": float(index * 2),
        }
        for index in range(30)
    ]
    result = evaluate_tabular_model(
        _request(
            {
                "rows": rows,
                "feature_fields": ["x", "y"],
                "target_field": "target",
                "task_kind": "regression",
                "split_strategy": "time",
                "time_field": "observed_at",
                "test_fraction": 0.3,
            }
        )
    )
    split = result["split"]
    assert split["strategy"] == "time"
    assert split["train_cutoff"] is not None
    assert split["cross_validation_folds"] is None
    assert any("future" in item for item in result["limitations"])
    predictions = result["predictions"]
    assert predictions
    validated_rows = {row["row_id"]: row["observed_at"] for row in rows}
    latest_train_time = max(
        validated_rows[f"t{index}"]
        for index in range(int(len(rows) * (1 - 0.3)))
    )
    assert all(
        validated_rows[item["row_id"]] > latest_train_time for item in predictions
    )


def test_stratified_split_is_rejected_for_regression():
    from services.scientific_skills.modeling import evaluate_tabular_model

    rows = [
        {"row_id": f"r{i}", "x": float(i), "target": float(i)}
        for i in range(20)
    ]
    with pytest.raises(ValueError, match="stratified split requires"):
        evaluate_tabular_model(
            _request(
                {
                    "rows": rows,
                    "feature_fields": ["x"],
                    "target_field": "target",
                    "task_kind": "regression",
                    "split_strategy": "stratified",
                }
            )
        )


def test_classification_reports_confusion_matrix_and_calibration():
    from services.scientific_skills.modeling import evaluate_tabular_model

    rows = []
    for index in range(40):
        label = "alpha" if index % 2 == 0 else "beta"
        rows.append(
            {
                "row_id": f"r{index}",
                "x": float(index % 2) + (index % 5) * 0.01,
                "y": float(index % 7),
                "target": label,
            }
        )
    result = evaluate_tabular_model(
        _request(
            {
                "rows": rows,
                "feature_fields": ["x", "y"],
                "target_field": "target",
            }
        )
    )
    confusion = result["confusion_matrix"]
    assert confusion["labels"] == ["alpha", "beta"]
    total = sum(sum(row) for row in confusion["rows"])
    assert total == result["split"]["test_count"]
    assert "brier_score" in result["metrics"]
    assert result["split"]["strategy"] == "stratified"


def test_group_cross_validation_respects_groups():
    from services.scientific_skills.modeling import _cross_validation_metrics
    from sklearn.ensemble import RandomForestClassifier

    matrix = [[float(i % 4)] for i in range(24)]
    labels = ["a" if i % 2 else "b" for i in range(24)]
    groups = [f"g{i // 4}" for i in range(24)]
    metrics = _cross_validation_metrics(
        RandomForestClassifier(n_estimators=10, random_state=0),
        matrix,
        labels,
        task="classification",
        folds=3,
        seed=42,
        groups=groups,
    )
    assert "cv_accuracy_mean" in metrics
    assert "cv_macro_f1_stddev" in metrics


