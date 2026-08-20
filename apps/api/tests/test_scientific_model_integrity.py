"""Leakage-safe model evaluation through the public scientific skill API.

These tests never touch private split helpers: they execute the registered
``tabular_machine_learning`` skill and derive every leakage assertion from the
public output (prediction row ids, split report, metrics).
"""

from __future__ import annotations

from uuid import uuid4

from app.schemas.core import ScientificSkillId
from services.scientific_skills import (
    ScientificSkillBudget,
    ScientificSkillRequest,
    build_scientific_skill_registry,
)

PROJECT_ID = str(uuid4())
RUN_ID = str(uuid4())


def _request(parameters: dict[str, object]) -> ScientificSkillRequest:
    return ScientificSkillRequest(
        request_id="request.model_integrity",
        project_id=PROJECT_ID,
        run_id=RUN_ID,
        skill_id=ScientificSkillId.tabular_machine_learning,
        parameters=parameters,
        source_references=(),
        budget=ScientificSkillBudget(timeout_seconds=60),
    )


def _grouped_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group_index in range(6):
        group = f"telescope.{group_index}"
        label = "variable" if group_index % 2 == 0 else "quiet"
        for member in range(8):
            index = group_index * 8 + member
            rows.append(
                {
                    "row_id": f"row.{index}",
                    "telescope": group,
                    "amplitude": float(group_index * 3 + member % 3),
                    "period": float(1.0 + 0.1 * member),
                    "label": label,
                }
            )
    return rows


def _time_series_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(60):
        rows.append(
            {
                "row_id": f"obs.{index}",
                "day": float(index),
                "value": float(2 * index + (index % 5)),
            }
        )
    return rows


def _entity_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for entity_index in range(6):
        object_id = f"star.{entity_index}"
        label = "variable" if entity_index % 2 == 0 else "quiet"
        for observation in range(8):
            index = entity_index * 8 + observation
            rows.append(
                {
                    "row_id": f"obs.{index}",
                    "object_id": object_id,
                    "amplitude": float(entity_index * 3 + observation % 3),
                    "period": float(1.0 + 0.1 * observation),
                    "label": label,
                }
            )
    return rows


def test_group_split_keeps_test_groups_out_of_training() -> None:
    rows = _grouped_rows()
    result = build_scientific_skill_registry().execute(
        _request(
            {
                "rows": rows,
                "feature_fields": ["amplitude", "period"],
                "target_field": "label",
                "task_kind": "classification",
                "algorithm": "random_forest",
                "split_strategy": "group",
                "group_field": "telescope",
            }
        )
    )

    predictions = result.output["predictions"]
    assert predictions, "group split must evaluate a test partition"

    # Derive the test groups from the prediction row ids alone, then compare
    # against the groups carried by every row that stayed in training.
    group_by_row = {str(row["row_id"]): str(row["telescope"]) for row in rows}
    test_row_ids = {str(item["row_id"]) for item in predictions}
    test_groups = {group_by_row[row_id] for row_id in test_row_ids}
    training_groups = {
        group_by_row[row_id]
        for row_id in group_by_row
        if row_id not in test_row_ids
    }
    assert test_groups, "test partition must cover at least one group"
    assert training_groups, "training partition must cover at least one group"
    assert test_groups & training_groups == set(), (
        "a group leaked across the train/test boundary"
    )


def test_entity_split_keeps_test_entities_out_of_training() -> None:
    rows = _entity_rows()
    result = build_scientific_skill_registry().execute(
        _request(
            {
                "rows": rows,
                "feature_fields": ["amplitude", "period"],
                "target_field": "label",
                "task_kind": "classification",
                "algorithm": "random_forest",
                "split_strategy": "entity",
                "entity_field": "object_id",
            }
        )
    )

    predictions = result.output["predictions"]
    assert predictions, "entity split must evaluate a test partition"

    entity_by_row = {str(row["row_id"]): str(row["object_id"]) for row in rows}
    test_row_ids = {str(item["row_id"]) for item in predictions}
    test_entities = {entity_by_row[row_id] for row_id in test_row_ids}
    training_entities = {
        entity_by_row[str(row["row_id"])]
        for row in rows
        if str(row["row_id"]) not in test_row_ids
    }
    assert training_entities, "training partition must cover at least one entity"
    assert test_entities & training_entities == set(), (
        "an entity leaked across the train/test boundary"
    )


def test_time_split_evaluates_only_rows_after_the_training_cutoff() -> None:
    rows = _time_series_rows()
    result = build_scientific_skill_registry().execute(
        _request(
            {
                "rows": rows,
                "feature_fields": ["day"],
                "target_field": "value",
                "task_kind": "regression",
                "algorithm": "linear_regression",
                "split_strategy": "time",
                "time_field": "day",
            }
        )
    )

    split = result.output["split"]
    assert split["strategy"] == "time"
    train_cutoff = float(split["train_cutoff"])
    time_by_row = {str(row["row_id"]): float(row["day"]) for row in rows}
    predictions = result.output["predictions"]
    assert predictions
    for item in predictions:
        assert time_by_row[str(item["row_id"])] > train_cutoff, (
            "a test prediction predates the training cutoff"
        )
    # Time splits must skip cross-validation rather than leak the future.
    assert split["cross_validation_folds"] is None


def test_group_split_reports_grouped_cross_validation_metrics() -> None:
    result = build_scientific_skill_registry().execute(
        _request(
            {
                "rows": _grouped_rows(),
                "feature_fields": ["amplitude", "period"],
                "target_field": "label",
                "task_kind": "classification",
                "algorithm": "random_forest",
                "split_strategy": "group",
                "group_field": "telescope",
                "cv_folds": 3,
            }
        )
    )

    metrics = result.output["metrics"]
    split = result.output["split"]
    assert split["strategy"] == "group"
    assert split["cross_validation_folds"] == 3
    assert "cv_accuracy_mean" in metrics
    assert "cv_macro_f1_mean" in metrics
