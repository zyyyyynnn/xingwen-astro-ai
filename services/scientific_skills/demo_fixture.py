"""Generate the deterministic scientific-artifact Demo Replay fixture.

The fixture is authored through the current Pydantic publication and read
contracts, not transcribed into TypeScript. It exercises the four scientific
review surfaces that do not require a binary payload: analysis, chart, model
evaluation, and a WorldWide Telescope scene.

Regenerate the committed JSON with:

    uv run --project apps/api python -m services.scientific_skills.demo_fixture
    pnpm prettier --write packages/data-access/src/fixture/scientific-artifacts.fixture.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas._hashing import compute_canonical_payload_hash
from app.schemas.core import (
    ArtifactVersionDetail,
    ProducerExecutionDetail,
    ProducerReference,
    SourceMode,
)
from app.schemas.scientific_artifact_api import ScientificArtifactRead
from app.schemas.scientific_skills import (
    AnalysisReportArtifactContent,
    ChartAxis,
    ChartPoint,
    ChartSeries,
    ChartVisualizationSpec,
    ModelEvaluationArtifactContent,
    ModelSplitReference,
    ScientificFinding,
    ScientificMetric,
    ScientificResultBlock,
    ScientificSkillExecution,
    VisualizationArtifactContent,
    WwtAnnotation,
    WwtCoordinate,
    WwtCoordinateGrid,
    WwtCoordinateView,
    WwtSceneVisualizationSpec,
    scientific_artifact_output_hash,
)


_PROJECT_ID = "proj_01JEXAMPLE"
_RUN_ID = "run_01JEXAMPLE"
_CREATED_AT = datetime(2026, 7, 21, 8, 23, tzinfo=timezone.utc)
_INPUT_HASH = "sha256:" + "c" * 64
_SKILL_OUTPUT_HASH = "sha256:" + "d" * 64
_PARAMETERS_HASH = compute_canonical_payload_hash({})


def _execution(skill_id: str, suffix: str) -> ScientificSkillExecution:
    return ScientificSkillExecution.model_validate(
        {
            "execution_id": f"skill.{suffix}",
            "skill_id": skill_id,
            "skill_revision": "1.0.0",
            "status": "completed",
            "input_hash": _INPUT_HASH,
            "output_hash": _SKILL_OUTPUT_HASH,
            "duration_ms": 18,
            "warnings": [],
        }
    )


def _seal(model: type[Any], payload: dict[str, Any]) -> Any:
    payload["output_hash"] = "sha256:" + "0" * 64
    draft = model.model_validate(
        payload,
        context={"skip_scientific_output_hash_validation": True},
    )
    payload["output_hash"] = scientific_artifact_output_hash(draft)
    return model.model_validate(payload)


def _analysis() -> AnalysisReportArtifactContent:
    rows = {
        "rows": [
            {"toi_id": "TOI-1234.01", "effective_temperature_k": 5800},
            {"toi_id": "TOI-5678.01", "effective_temperature_k": 5120},
            {"toi_id": "TOI-9012.01", "effective_temperature_k": 6240},
        ]
    }
    return _seal(
        AnalysisReportArtifactContent,
        {
            "kind": "analysis_report",
            "schema_version": "1.0.0",
            "report_id": "analysis.host_star_profile",
            "title": "宿主星样本数据剖析",
            "summary": "冻结样本包含 3 个候选目标，标识符与有效温度字段均完整。",
            "skill_executions": [_execution("data_profile", "profile")],
            "result_blocks": [
                ScientificResultBlock(
                    block_id="result.host_star_rows",
                    label="宿主星参数预览",
                    representation="table",
                    payload=rows,
                    content_hash=compute_canonical_payload_hash(rows),
                    evidence_ids=(),
                )
            ],
            "metrics": [
                ScientificMetric(
                    metric_id="metric.row_count",
                    label="样本量",
                    value=3,
                    unit="rows",
                    evidence_ids=(),
                ),
                ScientificMetric(
                    metric_id="metric.temperature_mean",
                    label="平均有效温度",
                    value=5720,
                    unit="K",
                    evidence_ids=(),
                ),
            ],
            "findings": [
                ScientificFinding(
                    finding_id="finding.coverage",
                    title="字段覆盖完整",
                    statement="三个 Demo Replay 目标均具有 TOI 标识符与有效温度。",
                    status="unresolved",
                    evidence_ids=(),
                    metric_ids=("metric.row_count",),
                )
            ],
            "limitations": ["Demo Replay 仅用于展示，不代表实时目录查询结果。"],
            "human_required": ["正式分析前需确认目标筛选阈值。"],
            "related_artifact_version_ids": ["artv_dataset_01"],
            "source_snapshot_ids": [],
            "evidence_ids": [],
            "input_hash": _INPUT_HASH,
        },
    )


def _chart() -> VisualizationArtifactContent:
    return _seal(
        VisualizationArtifactContent,
        {
            "kind": "visualization",
            "schema_version": "1.0.0",
            "visualization_id": "visualization.temperature_radius",
            "title": "宿主星温度—半径关系",
            "description": "冻结 Demo Replay 样本的声明式散点与趋势线。",
            "spec": ChartVisualizationSpec(
                dataset_artifact_version_id="artv_dataset_01",
                x_axis=ChartAxis(
                    field="star.effective_temperature",
                    label="有效温度",
                    unit="K",
                ),
                y_axis=ChartAxis(
                    field="star.radius",
                    label="恒星半径",
                    unit="R_sun",
                ),
                series=(
                    ChartSeries(
                        series_id="series.host_stars",
                        label="宿主星",
                        x_field="star.effective_temperature",
                        y_field="star.radius",
                        mark="point",
                        color_token="brand",
                        points=(
                            ChartPoint(x=5120, y=0.82),
                            ChartPoint(x=5800, y=1.03),
                            ChartPoint(x=6240, y=1.26),
                        ),
                    ),
                    ChartSeries(
                        series_id="series.trend",
                        label="趋势",
                        x_field="star.effective_temperature",
                        y_field="star.radius",
                        mark="line",
                        color_token="information",
                        points=(
                            ChartPoint(x=5120, y=0.84),
                            ChartPoint(x=5800, y=1.02),
                            ChartPoint(x=6240, y=1.24),
                        ),
                    ),
                ),
            ),
            "skill_executions": [_execution("chart_visualization", "chart")],
            "source_snapshot_ids": [],
            "evidence_ids": [],
            "input_hash": _INPUT_HASH,
        },
    )


def _model() -> ModelEvaluationArtifactContent:
    return _seal(
        ModelEvaluationArtifactContent,
        {
            "kind": "model_evaluation",
            "schema_version": "1.0.0",
            "evaluation_id": "evaluation.host_star_classifier",
            "title": "宿主星候选分类评估",
            "task_kind": "classification",
            "algorithm": "random_forest",
            "algorithm_version": "scikit-learn:1.9",
            "training_input": {
                "kind": "dataset_artifact_version",
                "ref_id": "artv_dataset_01",
            },
            "feature_fields": [
                "star.effective_temperature",
                "star.radius",
                "star.mass",
            ],
            "target_field": "planet.disposition",
            "split": ModelSplitReference(
                strategy="stratified_holdout",
                random_seed=42,
                train_fraction=0.7,
                validation_fraction=0.1,
                test_fraction=0.2,
            ),
            "metrics": [
                ScientificMetric(
                    metric_id="metric.macro_f1",
                    label="Macro F1",
                    value=0.84,
                    evidence_ids=(),
                ),
                ScientificMetric(
                    metric_id="metric.roc_auc",
                    label="ROC AUC",
                    value=0.9,
                    evidence_ids=(),
                ),
            ],
            "baseline_metrics": [
                ScientificMetric(
                    metric_id="metric.baseline_macro_f1",
                    label="Macro F1",
                    value=0.62,
                    evidence_ids=(),
                )
            ],
            "skill_execution": _execution(
                "tabular_machine_learning", "host_star_classifier"
            ),
            "diagnostic_visualization_ids": [],
            "limitations": ["样本为确定性 Demo Replay 数据，指标不得外推。"],
            "source_snapshot_ids": [],
            "evidence_ids": [],
            "input_hash": _INPUT_HASH,
        },
    )


def _wwt() -> VisualizationArtifactContent:
    return _seal(
        VisualizationArtifactContent,
        {
            "kind": "visualization",
            "schema_version": "1.0.0",
            "visualization_id": "visualization.target_field",
            "title": "TOI 候选目标天区",
            "description": "WWT 数字巡天背景上的目标位置与比较路径。",
            "spec": WwtSceneVisualizationSpec(
                view=WwtCoordinateView(
                    center=WwtCoordinate(ra_hours=10.25, dec_degrees=-12.4),
                    field_of_view_degrees=4,
                ),
                background="digitized_sky_survey",
                coordinate_grids=(WwtCoordinateGrid(system="equatorial"),),
                fits_layers=(),
                annotations=(
                    WwtAnnotation(
                        annotation_id="annotation.target",
                        kind="circle",
                        points=(WwtCoordinate(ra_hours=10.25, dec_degrees=-12.4),),
                        label="TOI-1234.01",
                        color_token="brand",
                        radius_degrees=0.08,
                    ),
                    WwtAnnotation(
                        annotation_id="annotation.comparison_path",
                        kind="line",
                        points=(
                            WwtCoordinate(ra_hours=10.18, dec_degrees=-12.6),
                            WwtCoordinate(ra_hours=10.25, dec_degrees=-12.4),
                            WwtCoordinate(ra_hours=10.34, dec_degrees=-12.15),
                        ),
                        label="比较星路径",
                        color_token="information",
                    ),
                ),
                text_alternative=(
                    "以 TOI-1234.01 为中心的四度数字巡天天区，包含目标圆圈和比较星路径。"
                ),
            ),
            "skill_executions": [_execution("wwt_scene", "wwt")],
            "source_snapshot_ids": [],
            "evidence_ids": [],
            "input_hash": _INPUT_HASH,
        },
    )


def _entry(
    suffix: str,
    content: AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | ModelEvaluationArtifactContent,
) -> dict[str, Any]:
    artifact_id = f"art_scientific_{suffix}"
    version_id = f"artv_scientific_{suffix}"
    content_dump = content.model_dump(mode="json")
    content_hash = compute_canonical_payload_hash(content_dump)
    producer = ProducerReference(
        type="algorithm",
        name="scientific_artifact_assembler",
        version="1.0.0",
        parameters_hash=_PARAMETERS_HASH,
    )
    execution = ProducerExecutionDetail(
        id=f"pexec_scientific_{suffix}",
        run_id=_RUN_ID,
        step_key=(
            "training_models"
            if content.kind == "model_evaluation"
            else (
                "building_visualizations"
                if content.kind == "visualization"
                else "analyzing_data"
            )
        ),
        step_attempt_id=f"attempt_scientific_{suffix}",
        producer=producer,
        parameters={},
        parameters_hash=_PARAMETERS_HASH,
        input_hash=_INPUT_HASH,
        output_hash=content_hash,
        status="completed",
        started_at=_CREATED_AT,
        finished_at=_CREATED_AT,
        token_usage=None,
        latency_ms=18,
        error_code=None,
    )
    read = ScientificArtifactRead(
        artifact_version_id=version_id,
        artifact_id=artifact_id,
        project_id=_PROJECT_ID,
        version_number=1,
        supersedes_version_id=None,
        source_mode=SourceMode.fixture,
        content_hash=content_hash,
        input_hash=_INPUT_HASH,
        created_at=_CREATED_AT,
        content=content,
        producer_execution=execution,
        source_snapshots=(),
        evidence=(),
    )
    version = ArtifactVersionDetail(
        id=version_id,
        artifact_id=artifact_id,
        project_id=_PROJECT_ID,
        created_by_run_id=_RUN_ID,
        version_number=1,
        schema_version=content.schema_version,
        content=content_dump,
        content_hash=content_hash,
        input_hash=_INPUT_HASH,
        source_mode=SourceMode.fixture,
        producer=producer,
        source_snapshot_ids=(),
        evidence_ids=(),
        supersedes_version_id=None,
        created_at=_CREATED_AT,
        producer_execution=execution,
        source_snapshots=(),
        evidence=(),
    )
    return {
        "version": version.model_dump(mode="json", exclude_none=False),
        "read": read.model_dump(mode="json", exclude_none=False),
        "content_blobs": [],
    }


def build_scientific_fixture_document() -> dict[str, Any]:
    entries = [
        _entry("analysis", _analysis()),
        _entry("chart", _chart()),
        _entry("model", _model()),
        _entry("wwt", _wwt()),
    ]
    return {
        "$generated": {
            "tool": "services.scientific_skills.demo_fixture",
            "command": (
                "uv run --project apps/api python -m "
                "services.scientific_skills.demo_fixture"
            ),
            "scenario_id": "exoplanet_host_star.scientific_artifacts",
            "provenance_note": (
                "Deterministic Demo Replay generated through current scientific "
                "publication and read contracts; never live data."
            ),
        },
        "entries": entries,
    }


FIXTURE_OUTPUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "data-access"
    / "src"
    / "fixture"
    / "scientific-artifacts.fixture.json"
)


def main() -> None:
    FIXTURE_OUTPUT_PATH.write_text(
        json.dumps(build_scientific_fixture_document(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {FIXTURE_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
