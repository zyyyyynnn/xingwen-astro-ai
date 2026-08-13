"""Canonical contracts for bounded scientific skills and their Artifacts."""

from __future__ import annotations

from enum import StrEnum
import json
from math import isfinite
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from ._hashing import compute_canonical_payload_hash
from .core import (
    ArtifactKind,
    ContentHash,
    Identifier,
    JsonValue,
    ScientificSkillId,
    SemanticVersion,
    UtcDateTime,
)


MODEL_CONFIG = ConfigDict(extra="forbid", frozen=True)
NonEmptyString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
ShortString = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)
]


class ScientificSkillStatus(StrEnum):
    completed = "completed"
    partial = "partial"
    unsupported = "unsupported"
    failed = "failed"


class ScientificSupportStatus(StrEnum):
    supported = "supported"
    partial = "partial"
    unresolved = "unresolved"
    conflicted = "conflicted"


class ScientificSkillExecution(BaseModel):
    model_config = MODEL_CONFIG

    execution_id: Identifier
    skill_id: ScientificSkillId
    skill_revision: SemanticVersion
    status: ScientificSkillStatus
    input_hash: ContentHash
    output_hash: ContentHash | None = None
    duration_ms: int = Field(ge=0)
    warnings: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def validate_terminal_output(self) -> Self:
        if self.status in {
            ScientificSkillStatus.completed,
            ScientificSkillStatus.partial,
        }:
            if self.output_hash is None:
                raise ValueError(
                    "completed or partial skill execution requires output_hash"
                )
        elif self.output_hash is not None:
            raise ValueError(
                "unsupported or failed skill execution cannot declare output_hash"
            )
        return self


class ScientificMetric(BaseModel):
    model_config = MODEL_CONFIG

    metric_id: Identifier
    label: ShortString
    value: float | int | NonEmptyString
    unit: ShortString | None = None
    evidence_ids: tuple[Identifier, ...] = ()

    @field_validator("value")
    @classmethod
    def require_finite_numeric_value(
        cls, value: float | int | str
    ) -> float | int | str:
        if isinstance(value, float) and not isfinite(value):
            raise ValueError("metric value must be finite")
        return value

    @model_validator(mode="after")
    def require_unique_evidence(self) -> Self:
        _require_unique(self.evidence_ids, "metric evidence id")
        return self


class ScientificFinding(BaseModel):
    model_config = MODEL_CONFIG

    finding_id: Identifier
    title: ShortString
    statement: NonEmptyString
    status: ScientificSupportStatus
    evidence_ids: tuple[Identifier, ...]
    metric_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_support(self) -> Self:
        _require_unique(self.evidence_ids, "finding evidence id")
        _require_unique(self.metric_ids, "finding metric id")
        if self.status is ScientificSupportStatus.supported and not self.evidence_ids:
            raise ValueError("supported finding requires Evidence")
        return self


class ScientificResultBlock(BaseModel):
    """Bounded structured output retained for inspection and downstream reuse."""

    model_config = MODEL_CONFIG

    block_id: Identifier
    label: ShortString
    representation: Literal[
        "record", "table", "catalog", "statistics", "timeseries", "matrix"
    ]
    payload: JsonValue
    content_hash: ContentHash
    evidence_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def validate_payload(self) -> Self:
        encoded = json.dumps(
            self.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > 4 * 1024 * 1024:
            raise ValueError("scientific result block exceeds 4 MiB")
        expected = compute_canonical_payload_hash(self.payload)
        if self.content_hash != expected:
            raise ValueError(
                f"scientific result block content_hash mismatch: {expected}"
            )
        _require_unique(self.evidence_ids, "result block evidence id")
        return self


class ScientificEvidence(BaseModel):
    """Evidence materialized with a newly published scientific ArtifactVersion."""

    model_config = MODEL_CONFIG

    evidence_id: Identifier
    target_type: Literal["result_block", "metric", "visualization", "evaluation"]
    target_id: Identifier
    source_snapshot_id: Identifier
    evidence_type: Literal["service_response", "input_snapshot", "computation"]
    locator: dict[str, JsonValue]
    quote_or_value: JsonValue | None = None
    extraction_method: Literal["registered_scientific_skill"] = (
        "registered_scientific_skill"
    )
    confidence: float = Field(default=1.0, ge=0, le=1)


class AnalysisReportArtifactContent(BaseModel):
    """Evidence-backed result of one or more bounded analysis skills."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.analysis_report] = ArtifactKind.analysis_report
    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: Identifier
    title: ShortString
    summary: NonEmptyString
    skill_executions: tuple[ScientificSkillExecution, ...] = Field(min_length=1)
    result_blocks: tuple[ScientificResultBlock, ...] = Field(min_length=1)
    metrics: tuple[ScientificMetric, ...] = ()
    findings: tuple[ScientificFinding, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()
    human_required: tuple[NonEmptyString, ...] = ()
    related_artifact_version_ids: tuple[Identifier, ...] = ()
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_report(self, info: ValidationInfo) -> Self:
        _require_unique(
            tuple(item.execution_id for item in self.skill_executions),
            "skill execution id",
        )
        _require_unique(
            tuple(item.block_id for item in self.result_blocks), "result block id"
        )
        metric_ids = tuple(item.metric_id for item in self.metrics)
        _require_unique(metric_ids, "metric id")
        _require_unique(tuple(item.finding_id for item in self.findings), "finding id")
        metric_registry = set(metric_ids)
        if any(
            metric_id not in metric_registry
            for finding in self.findings
            for metric_id in finding.metric_ids
        ):
            raise ValueError("finding metric_ids must reference report metrics")
        _validate_artifact_evidence(
            self.evidence_ids,
            tuple(
                evidence_id
                for item in (*self.result_blocks, *self.metrics, *self.findings)
                for evidence_id in item.evidence_ids
            ),
        )
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={
                **{item.block_id: "result_block" for item in self.result_blocks},
                **{item.metric_id: "metric" for item in self.metrics},
            },
            source_snapshot_ids=self.source_snapshot_ids,
        )
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_unique(self.related_artifact_version_ids, "related ArtifactVersion id")
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is AnalysisReportArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


class VisualizationMode(StrEnum):
    chart = "chart"
    fits_image = "fits_image"
    wwt_scene = "wwt_scene"
    model_diagnostic = "model_diagnostic"


class ChartAxis(BaseModel):
    model_config = MODEL_CONFIG

    field: Identifier
    label: ShortString
    unit: ShortString | None = None
    scale: Literal["linear", "log", "time", "category"] = "linear"


class ChartPoint(BaseModel):
    """One bounded, publication-owned datum for a declarative chart."""

    model_config = MODEL_CONFIG

    x: float | int | NonEmptyString
    y: float | int | NonEmptyString


class ChartSeries(BaseModel):
    model_config = MODEL_CONFIG

    series_id: Identifier
    label: ShortString
    x_field: Identifier
    y_field: Identifier
    mark: Literal["line", "point", "bar", "area"]
    color_token: Literal[
        "brand", "information", "success", "warning", "error", "neutral"
    ] = "brand"
    points: tuple[ChartPoint, ...] = Field(min_length=1, max_length=2000)


class ChartVisualizationSpec(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal[VisualizationMode.chart] = VisualizationMode.chart
    dataset_artifact_version_id: Identifier
    x_axis: ChartAxis
    y_axis: ChartAxis
    series: tuple[ChartSeries, ...] = Field(min_length=1)


class FitsImageVisualizationSpec(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal[VisualizationMode.fits_image] = VisualizationMode.fits_image
    source_snapshot_id: Identifier
    content_ref: Identifier
    content_hash: ContentHash
    stretch: Literal["linear", "sqrt", "log", "power", "histogram_equalization"] = (
        "sqrt"
    )
    color_map: Literal["gray", "viridis", "magma", "inferno"] = "gray"


class WwtCoordinate(BaseModel):
    model_config = MODEL_CONFIG

    ra_hours: float = Field(ge=0, lt=24)
    dec_degrees: float = Field(ge=-90, le=90)


class WwtAnnotation(BaseModel):
    model_config = MODEL_CONFIG

    annotation_id: Identifier
    kind: Literal["circle", "line", "label"]
    points: tuple[WwtCoordinate, ...] = Field(min_length=1, max_length=1000)
    label: ShortString | None = None
    color_token: Literal[
        "brand", "information", "success", "warning", "error", "neutral"
    ] = "brand"
    radius_degrees: float | None = Field(default=None, gt=0, le=180)

    @model_validator(mode="after")
    def validate_annotation_shape(self) -> Self:
        if self.kind == "circle" and (
            len(self.points) != 1 or self.radius_degrees is None
        ):
            raise ValueError("circle annotation requires one point and radius_degrees")
        if self.kind == "line" and len(self.points) < 2:
            raise ValueError("line annotation requires at least two points")
        if self.kind == "label" and (len(self.points) != 1 or self.label is None):
            raise ValueError("label annotation requires one point and label")
        return self


class WwtFitsLayer(BaseModel):
    model_config = MODEL_CONFIG

    layer_id: Identifier
    source_snapshot_id: Identifier
    content_ref: Identifier
    content_hash: ContentHash
    opacity: float = Field(default=1.0, ge=0, le=1)


class WwtSceneVisualizationSpec(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal[VisualizationMode.wwt_scene] = VisualizationMode.wwt_scene
    center: WwtCoordinate
    field_of_view_degrees: float = Field(gt=0, le=180)
    observed_at: UtcDateTime | None = None
    background: Literal["digitized_sky_survey", "gaia", "wise", "solar_system"] = (
        "digitized_sky_survey"
    )
    coordinate_grid: Literal["none", "equatorial", "galactic", "ecliptic", "altaz"] = (
        "equatorial"
    )
    fits_layers: tuple[WwtFitsLayer, ...] = ()
    annotations: tuple[WwtAnnotation, ...] = ()

    @model_validator(mode="after")
    def require_unique_scene_ids(self) -> Self:
        _require_unique(
            tuple(item.layer_id for item in self.fits_layers), "WWT layer id"
        )
        _require_unique(
            tuple(item.annotation_id for item in self.annotations),
            "WWT annotation id",
        )
        return self


class ModelDiagnosticVisualizationSpec(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal[VisualizationMode.model_diagnostic] = (
        VisualizationMode.model_diagnostic
    )
    model_evaluation_artifact_version_id: Identifier
    diagnostic: Literal[
        "confusion_matrix",
        "roc_curve",
        "precision_recall",
        "residuals",
        "forecast",
        "feature_importance",
    ]


VisualizationSpec = Annotated[
    ChartVisualizationSpec
    | FitsImageVisualizationSpec
    | WwtSceneVisualizationSpec
    | ModelDiagnosticVisualizationSpec,
    Field(discriminator="mode"),
]


class VisualizationArtifactContent(BaseModel):
    """Declarative visualization; never executable code or an arbitrary URL."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.visualization] = ArtifactKind.visualization
    schema_version: Literal["1.0.0"] = "1.0.0"
    visualization_id: Identifier
    title: ShortString
    description: NonEmptyString
    spec: VisualizationSpec
    skill_executions: tuple[ScientificSkillExecution, ...] = Field(min_length=1)
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_visualization(self, info: ValidationInfo) -> Self:
        _require_unique(
            tuple(item.execution_id for item in self.skill_executions),
            "skill execution id",
        )
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_unique(self.evidence_ids, "evidence id")
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={self.visualization_id: "visualization"},
            source_snapshot_ids=self.source_snapshot_ids,
        )
        declared_snapshots = set(self.source_snapshot_ids)
        spec_snapshots: set[str] = set()
        if isinstance(self.spec, FitsImageVisualizationSpec):
            spec_snapshots.add(self.spec.source_snapshot_id)
        elif isinstance(self.spec, WwtSceneVisualizationSpec):
            spec_snapshots.update(
                item.source_snapshot_id for item in self.spec.fits_layers
            )
        if not spec_snapshots.issubset(declared_snapshots):
            raise ValueError(
                "visualization spec snapshots must be declared by the Artifact"
            )
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is VisualizationArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


class ModelTaskKind(StrEnum):
    classification = "classification"
    regression = "regression"
    forecast = "forecast"
    image_classification = "image_classification"


class ModelSplitReference(BaseModel):
    model_config = MODEL_CONFIG

    strategy: Literal["holdout", "stratified_holdout", "time_ordered"]
    random_seed: int | None = Field(default=None, ge=0, le=2**32 - 1)
    train_fraction: float = Field(gt=0, lt=1)
    validation_fraction: float = Field(ge=0, lt=1)
    test_fraction: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def validate_fractions(self) -> Self:
        if (
            abs(self.train_fraction + self.validation_fraction + self.test_fraction - 1)
            > 1e-9
        ):
            raise ValueError("model split fractions must total 1")
        if self.strategy == "time_ordered" and self.random_seed is not None:
            raise ValueError("time_ordered split cannot use random_seed")
        return self


class ModelBinaryReference(BaseModel):
    model_config = MODEL_CONFIG

    content_ref: Identifier
    content_hash: ContentHash
    media_type: Literal[
        "application/onnx", "application/vnd.sklearn", "application/octet-stream"
    ]


class ModelEvaluationArtifactContent(BaseModel):
    """Reproducible evaluation metadata for a bounded scientific model task."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.model_evaluation] = ArtifactKind.model_evaluation
    schema_version: Literal["1.0.0"] = "1.0.0"
    evaluation_id: Identifier
    title: ShortString
    task_kind: ModelTaskKind
    algorithm: Identifier
    algorithm_version: ShortString
    dataset_artifact_version_id: Identifier
    feature_fields: tuple[Identifier, ...] = Field(min_length=1)
    target_field: Identifier
    split: ModelSplitReference
    metrics: tuple[ScientificMetric, ...] = Field(min_length=1)
    baseline_metrics: tuple[ScientificMetric, ...] = ()
    skill_execution: ScientificSkillExecution
    model_binary: ModelBinaryReference | None = None
    diagnostic_visualization_ids: tuple[Identifier, ...] = ()
    limitations: tuple[NonEmptyString, ...] = ()
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_evaluation(self, info: ValidationInfo) -> Self:
        if self.skill_execution.skill_id not in {
            ScientificSkillId.tabular_machine_learning,
            ScientificSkillId.time_series_forecast,
            ScientificSkillId.image_classification,
        }:
            raise ValueError("model evaluation requires a model-training skill")
        _require_unique(self.feature_fields, "model feature field")
        if self.target_field in self.feature_fields:
            raise ValueError("target_field cannot also be a feature field")
        all_metrics = (*self.metrics, *self.baseline_metrics)
        _require_unique(
            tuple(item.metric_id for item in all_metrics), "model metric id"
        )
        _validate_artifact_evidence(
            self.evidence_ids,
            tuple(
                evidence_id
                for metric in all_metrics
                for evidence_id in metric.evidence_ids
            ),
        )
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={
                self.evaluation_id: "evaluation",
                **{item.metric_id: "metric" for item in all_metrics},
            },
            source_snapshot_ids=self.source_snapshot_ids,
        )
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_unique(
            self.diagnostic_visualization_ids, "diagnostic visualization id"
        )
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is ModelEvaluationArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


ScientificArtifactContent = (
    AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | ModelEvaluationArtifactContent
)


def scientific_artifact_output_hash(
    value: ScientificArtifactContent | dict[str, Any],
) -> str:
    if isinstance(value, BaseModel):
        payload = value.model_dump(mode="json")
    else:
        unsealed = dict(value)
        kind = unsealed.get("kind")
        model = {
            ArtifactKind.analysis_report: AnalysisReportArtifactContent,
            ArtifactKind.visualization: VisualizationArtifactContent,
            ArtifactKind.model_evaluation: ModelEvaluationArtifactContent,
        }.get(kind)
        if model is None:
            raise ValueError(f"unsupported scientific Artifact kind: {kind}")
        unsealed["output_hash"] = "sha256:" + "0" * 64
        normalized = model.model_validate(
            unsealed,
            context={"skip_scientific_output_hash_validation": True},
        )
        payload = normalized.model_dump(mode="json")
    payload.pop("output_hash", None)
    return compute_canonical_payload_hash(payload)


def _require_output_hash(
    value: ScientificArtifactContent,
    info: ValidationInfo,
) -> None:
    if info.context and info.context.get("skip_scientific_output_hash_validation"):
        return
    expected = scientific_artifact_output_hash(value)
    if value.output_hash != expected:
        raise ValueError(f"output_hash does not match scientific Artifact: {expected}")


def _validate_artifact_evidence(
    declared: tuple[str, ...], used: tuple[str, ...]
) -> None:
    _require_unique(declared, "artifact evidence id")
    if tuple(sorted(set(used))) != declared:
        raise ValueError(
            "evidence_ids must equal the sorted metric/finding Evidence union"
        )


def _validate_scientific_evidence(
    evidence: tuple[ScientificEvidence, ...],
    *,
    evidence_ids: tuple[str, ...],
    targets: dict[str, str],
    source_snapshot_ids: tuple[str, ...],
) -> None:
    _require_unique(
        tuple(item.evidence_id for item in evidence), "scientific evidence id"
    )
    if any(item.evidence_id not in evidence_ids for item in evidence):
        raise ValueError("scientific Evidence must be declared by the Artifact")
    sources = set(source_snapshot_ids)
    for item in evidence:
        if targets.get(item.target_id) != item.target_type:
            raise ValueError(
                "scientific Evidence target is not declared by the Artifact"
            )
        if item.source_snapshot_id not in sources:
            raise ValueError(
                "scientific Evidence source is not declared by the Artifact"
            )


def _require_unique(values: tuple[str, ...], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label}s must be unique")


__all__ = [
    "AnalysisReportArtifactContent",
    "ChartVisualizationSpec",
    "FitsImageVisualizationSpec",
    "ModelEvaluationArtifactContent",
    "ScientificArtifactContent",
    "ScientificFinding",
    "ScientificEvidence",
    "ScientificMetric",
    "ScientificResultBlock",
    "ScientificSkillExecution",
    "ScientificSkillStatus",
    "ScientificSupportStatus",
    "VisualizationArtifactContent",
    "VisualizationMode",
    "WwtSceneVisualizationSpec",
    "scientific_artifact_output_hash",
]
