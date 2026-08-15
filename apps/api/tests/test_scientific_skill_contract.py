from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.artifact_publication import canonical_artifact_content_model
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    ModelArtifactContent,
    ModelEvaluationArtifactContent,
    VisualizationArtifactContent,
    scientific_artifact_output_hash,
)
from app.services.resource_authority import _scientific_binary_references
from app.services.scientific_artifacts import _declared_content_media_type


HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64


def _execution(skill_id: str) -> dict[str, object]:
    return {
        "execution_id": f"skill.{skill_id}",
        "skill_id": skill_id,
        "skill_revision": "1.0.0",
        "status": "completed",
        "input_hash": HASH_A,
        "output_hash": HASH_B,
        "duration_ms": 12,
        "warnings": [],
    }


def _seal(payload: dict[str, object]) -> dict[str, object]:
    sealed = deepcopy(payload)
    sealed["output_hash"] = scientific_artifact_output_hash(sealed)
    model = {
        "analysis_report": AnalysisReportArtifactContent,
        "visualization": VisualizationArtifactContent,
        "model_evaluation": ModelEvaluationArtifactContent,
        "model_artifact": ModelArtifactContent,
    }[str(sealed["kind"])]
    return model.model_validate(sealed).model_dump(mode="json")


def _analysis_payload() -> dict[str, object]:
    return _seal(
        {
            "kind": "analysis_report",
            "schema_version": "1.0.0",
            "report_id": "analysis.primary",
            "title": "Host-star data profile",
            "summary": "The admitted sample has complete identifier coverage.",
            "skill_executions": [_execution("data_profile")],
            "result_blocks": [
                {
                    "block_id": "result.profile",
                    "label": "Data profile output",
                    "representation": "record",
                    "payload": {"row_count": 3},
                    "content_hash": compute_canonical_payload_hash({"row_count": 3}),
                    "evidence_ids": ["evidence.coverage"],
                }
            ],
            "metrics": [
                {
                    "metric_id": "metric.coverage",
                    "label": "Identifier coverage",
                    "value": 1.0,
                    "unit": "ratio",
                    "evidence_ids": ["evidence.coverage"],
                }
            ],
            "findings": [
                {
                    "finding_id": "finding.coverage",
                    "title": "Complete identifiers",
                    "statement": "Every admitted row has a stable host-star identifier.",
                    "status": "supported",
                    "evidence_ids": ["evidence.coverage"],
                    "metric_ids": ["metric.coverage"],
                }
            ],
            "limitations": [],
            "human_required": [],
            "related_artifact_version_ids": ["version.dataset"],
            "source_snapshot_ids": ["snapshot.dataset"],
            "evidence_ids": ["evidence.coverage"],
            "input_hash": HASH_A,
        }
    )


def _wwt_payload() -> dict[str, object]:
    return _seal(
        {
            "kind": "visualization",
            "schema_version": "1.0.0",
            "visualization_id": "visualization.wwt",
            "title": "Target field",
            "description": "A reproducible WWT view of the selected field.",
            "spec": {
                "mode": "wwt_scene",
                "view": {
                    "kind": "coordinates",
                    "center": {"ra_hours": 0.712, "dec_degrees": 41.269},
                    "field_of_view_degrees": 2.0,
                },
                "background": "digitized_sky_survey",
                "coordinate_grids": [{"system": "equatorial", "labels": True}],
                "fits_layers": [
                    {
                        "layer_id": "layer.primary",
                        "source_snapshot_id": "snapshot.fits",
                        "content_ref": "content.fits.primary",
                        "content_hash": HASH_C,
                        "opacity": 0.9,
                    }
                ],
                "table_layers": [
                    {
                        "layer_id": "layer.catalog",
                        "source_snapshot_id": "snapshot.catalog",
                        "content_ref": "content.catalog",
                        "content_hash": HASH_B,
                        "media_type": "text/csv",
                        "coordinates": {
                            "kind": "spherical",
                            "frame": "sky",
                            "longitude_field": "ra",
                            "latitude_field": "dec",
                            "longitude_unit": "hours",
                        },
                    }
                ],
                "annotations": [
                    {
                        "annotation_id": "annotation.target",
                        "kind": "circle",
                        "points": [{"ra_hours": 0.712, "dec_degrees": 41.269}],
                        "color_token": "brand",
                        "radius_degrees": 0.1,
                    }
                ],
                "text_alternative": (
                    "A two-degree WWT view of the target field with a FITS layer."
                ),
            },
            "skill_executions": [_execution("wwt_scene")],
            "source_snapshot_ids": ["snapshot.fits", "snapshot.catalog"],
            "evidence_ids": [],
            "input_hash": HASH_A,
        }
    )


def _model_payload() -> dict[str, object]:
    return _seal(
        {
            "kind": "model_evaluation",
            "schema_version": "1.0.0",
            "evaluation_id": "evaluation.classifier",
            "title": "Host-star classifier",
            "task_kind": "classification",
            "algorithm": "random_forest",
            "algorithm_version": "scikit-learn:current",
            "training_input": {
                "kind": "dataset_artifact_version",
                "ref_id": "version.dataset",
            },
            "feature_fields": ["star.mass", "star.radius"],
            "target_field": "star.class",
            "split": {
                "strategy": "stratified_holdout",
                "random_seed": 42,
                "train_fraction": 0.7,
                "validation_fraction": 0.1,
                "test_fraction": 0.2,
            },
            "metrics": [
                {
                    "metric_id": "metric.f1",
                    "label": "Macro F1",
                    "value": 0.81,
                    "evidence_ids": ["evidence.dataset"],
                }
            ],
            "baseline_metrics": [],
            "skill_execution": _execution("tabular_machine_learning"),
            "diagnostic_visualization_ids": [],
            "limitations": ["The evaluation is limited to the frozen sample."],
            "source_snapshot_ids": ["snapshot.dataset"],
            "evidence_ids": ["evidence.dataset"],
            "input_hash": HASH_A,
        }
    )


def _model_artifact_payload() -> dict[str, object]:
    return _seal(
        {
            "kind": "model_artifact",
            "schema_version": "1.0.0",
            "model_id": "model.classifier",
            "title": "Host-star classifier model",
            "status": "active",
            "task_kind": "classification",
            "algorithm": "random_forest",
            "algorithm_version": "scikit-learn:current",
            "training_input": {
                "kind": "dataset_artifact_version",
                "ref_id": "version.dataset",
            },
            "evaluation_id": "evaluation.classifier",
            "feature_fields": ["star.mass", "star.radius"],
            "target_field": "star.class",
            "model_binary": {
                "content_ref": "models/classifier.onnx",
                "content_hash": HASH_C,
                "media_type": "application/onnx",
            },
            "input_name": "X",
            "output_names": ["label", "probabilities"],
            "input_shape": [None, 2],
            "opset_imports": {"ai.onnx": 21, "ai.onnx.ml": 3},
            "dependency_revisions": [
                "onnx==1.22.0",
                "onnxruntime==1.28.0",
                "scikit-learn==1.9.1",
                "skl2onnx==1.20.0",
            ],
            "skill_execution": _execution("tabular_machine_learning"),
            "limitations": [],
            "source_snapshot_ids": [],
            "evidence_ids": [],
            "input_hash": HASH_A,
        }
    )


@pytest.mark.parametrize(
    ("kind", "model", "payload_factory"),
    [
        ("analysis_report", AnalysisReportArtifactContent, _analysis_payload),
        ("visualization", VisualizationArtifactContent, _wwt_payload),
        ("model_evaluation", ModelEvaluationArtifactContent, _model_payload),
        ("model_artifact", ModelArtifactContent, _model_artifact_payload),
    ],
)
def test_scientific_artifacts_are_canonical_current_publication_models(
    kind: str,
    model: type[BaseModel],
    payload_factory: Callable[[], dict[str, object]],
) -> None:
    payload = payload_factory()
    candidate = model.model_validate(payload)

    assert canonical_artifact_content_model(kind) is model
    assert candidate.__artifact_publication_is_admitted__() is True  # type: ignore[attr-defined]
    assert candidate.model_dump(mode="json") == payload


def test_analysis_report_rejects_evidence_registry_drift() -> None:
    payload = _analysis_payload()
    payload["evidence_ids"] = []

    with pytest.raises(ValidationError, match="Evidence union"):
        AnalysisReportArtifactContent.model_validate(payload)


def test_wwt_scene_rejects_undeclared_fits_snapshot() -> None:
    payload = _wwt_payload()
    payload["source_snapshot_ids"] = []

    with pytest.raises(ValidationError, match="snapshots must be declared"):
        VisualizationArtifactContent.model_validate(payload)


def test_wwt_scene_declares_fits_and_table_content_resources() -> None:
    payload = _wwt_payload()
    content = VisualizationArtifactContent.model_validate(payload)

    assert _scientific_binary_references("visualization", payload) == (
        (HASH_C, "content.fits.primary"),
        (HASH_B, "content.catalog"),
    )
    assert _declared_content_media_type(content, HASH_C) == "application/fits"
    assert _declared_content_media_type(content, HASH_B) == "text/csv"


def test_model_evaluation_rejects_non_training_skill() -> None:
    payload = _model_payload()
    payload["skill_execution"] = _execution("data_profile")

    with pytest.raises(ValidationError, match="model-training skill"):
        ModelEvaluationArtifactContent.model_validate(payload)


def test_model_artifact_rejects_executable_python_serialization() -> None:
    payload = _model_artifact_payload()
    payload["model_binary"] = {
        "content_ref": "models/classifier.pkl",
        "content_hash": HASH_C,
        "media_type": "application/vnd.sklearn",
    }

    with pytest.raises(ValidationError, match="accepts only ONNX"):
        ModelArtifactContent.model_validate(payload)


def test_scientific_artifact_rejects_output_hash_drift() -> None:
    payload = _analysis_payload()
    payload["summary"] = "Mutated after sealing."

    with pytest.raises(ValidationError, match="output_hash does not match"):
        AnalysisReportArtifactContent.model_validate(payload)
