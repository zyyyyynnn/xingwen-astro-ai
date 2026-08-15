from __future__ import annotations

from base64 import b64decode

import onnx
import pytest

from app.schemas.core import ScientificSkillId
from app.services.content_storage import sha256_content_hash
from services.scientific_skills.registry import build_scientific_skill_registry
from services.scientific_skills.types import ScientificSkillRequest


def _rows() -> list[dict[str, object]]:
    fields = tuple(f"sample_{index:02d}" for index in range(8))
    rows: list[dict[str, object]] = []
    for index in range(48):
        variable = index % 2 == 1
        row: dict[str, object] = {
            "row_id": f"series.{index:02d}",
            "target": "variable" if variable else "stable",
        }
        for offset, field in enumerate(fields):
            baseline = 1.0 if variable and offset % 2 else 0.0
            row[field] = baseline + index / 1000
        rows.append(row)
    return rows


def _request(**overrides: object) -> ScientificSkillRequest:
    parameters: dict[str, object] = {
        "rows": _rows(),
        "series_fields": [f"sample_{index:02d}" for index in range(8)],
        "target_field": "target",
        "algorithm": "random_forest",
        "test_fraction": 0.25,
        "random_seed": 17,
        "cv_folds": 4,
    }
    parameters.update(overrides)
    return ScientificSkillRequest(
        request_id="request.time-series-classification",
        project_id="project.time-series-classification",
        run_id="run.time-series-classification",
        skill_id=ScientificSkillId.time_series_classification,
        parameters=parameters,
        source_references=(),
    )


def test_time_series_classifier_is_bounded_reproducible_and_onnx_backed() -> None:
    registry = build_scientific_skill_registry()

    first = registry.execute(_request()).output
    second = registry.execute(_request()).output

    assert first == second
    assert first["task_kind"] == "time_series_classification"
    assert first["series_layout"] == "ordered_fields"
    assert first["sequence_length"] == 8
    assert first["split"]["strategy"] == "stratified_holdout"
    assert first["split"]["cross_validation_folds"] == 4
    assert 0 <= first["metrics"]["accuracy"] <= 1
    assert 0 <= first["metrics"]["cv_macro_f1_mean"] <= 1
    assert "accuracy" in first["baseline_metrics"]
    model_binary = first["model_binary"]
    content = b64decode(model_binary["content_base64"], validate=True)
    assert sha256_content_hash(content) == model_binary["content_hash"]
    onnx.checker.check_model(onnx.load_model_from_string(content))


def test_time_series_classifier_rejects_reference_side_model_controls() -> None:
    registry = build_scientific_skill_registry()

    with pytest.raises(ValueError, match="unsupported scientific skill parameters"):
        registry.execute(_request(model_type="LSTM"))
    with pytest.raises(ValueError, match="at least four samples"):
        registry.execute(_request(series_fields=["sample_00", "sample_01"]))
