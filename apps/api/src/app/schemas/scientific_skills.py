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
    target_type: Literal[
        "result_block",
        "metric",
        "visualization",
        "spectrum",
        "light_curve",
        "evaluation",
        "model",
    ]
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


class WwtCoordinateView(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["coordinates"] = "coordinates"
    center: WwtCoordinate
    field_of_view_degrees: float = Field(gt=0, le=180)
    roll_degrees: float = Field(default=0, ge=-180, le=180)
    transition_seconds: float = Field(default=0, ge=0, le=120)


class WwtTrackedObjectView(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["tracked_object"] = "tracked_object"
    target: Literal[
        "sun",
        "mercury",
        "venus",
        "earth",
        "moon",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
    ]
    field_of_view_degrees: float = Field(default=10, gt=0, le=180)
    roll_degrees: float = Field(default=0, ge=-180, le=180)
    transition_seconds: float = Field(default=0, ge=0, le=120)


WwtView = Annotated[
    WwtCoordinateView | WwtTrackedObjectView,
    Field(discriminator="kind"),
]


class WwtTimeControl(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal["system_clock", "paused", "playback"] = "system_clock"
    observed_at: UtcDateTime | None = None
    rate: float | None = Field(default=None, ge=-1_000_000, le=1_000_000)

    @model_validator(mode="after")
    def validate_clock_intent(self) -> Self:
        if self.mode == "system_clock":
            if self.observed_at is not None or self.rate is not None:
                raise ValueError("system_clock time cannot declare observed_at or rate")
            return self
        if self.observed_at is None:
            raise ValueError(f"{self.mode} time requires observed_at")
        if self.mode == "paused":
            if self.rate is not None:
                raise ValueError("paused time cannot declare rate")
            return self
        if self.rate is None or self.rate == 0:
            raise ValueError("playback rate must be non-zero")
        return self


class WwtObserver(BaseModel):
    model_config = MODEL_CONFIG

    latitude_degrees: float = Field(ge=-90, le=90)
    longitude_degrees: float = Field(ge=-180, le=180)
    elevation_meters: float = Field(default=0, ge=-500, le=100_000)
    local_horizon_mode: bool = False


class WwtCoordinateGrid(BaseModel):
    model_config = MODEL_CONFIG

    system: Literal["equatorial", "galactic", "ecliptic", "altaz"]
    labels: bool = True


class WwtForeground(BaseModel):
    model_config = MODEL_CONFIG

    image_set: Literal["digitized_sky_survey", "gaia", "wise"]
    opacity: float = Field(default=1, ge=0, le=1)


class WwtSolarSystemOptions(BaseModel):
    model_config = MODEL_CONFIG

    cosmos: bool = False
    lighting: bool = True
    milky_way: bool = True
    minor_planets: bool = False
    minor_orbits: bool = False
    orbits: bool = True
    planets: bool = True
    scale: float = Field(default=1, ge=1, le=100)
    stars: bool = True


class WwtConstellationOverlays(BaseModel):
    model_config = MODEL_CONFIG

    boundaries: bool = False
    figures: bool = False
    pictures: bool = False
    labels: bool = False


class WwtAnnotation(BaseModel):
    model_config = MODEL_CONFIG

    annotation_id: Identifier
    kind: Literal["circle", "line", "point", "label"]
    points: tuple[WwtCoordinate, ...] = Field(min_length=1, max_length=1000)
    label: ShortString | None = None
    color_token: Literal[
        "brand", "information", "success", "warning", "error", "neutral"
    ] = "brand"
    radius_degrees: float | None = Field(default=None, gt=0, le=180)
    line_width: float = Field(default=2, gt=0, le=20)
    fill: bool = False
    fill_color_token: Literal[
        "brand", "information", "success", "warning", "error", "neutral"
    ] = "brand"

    @model_validator(mode="after")
    def validate_annotation_shape(self) -> Self:
        if self.kind == "circle" and (
            len(self.points) != 1 or self.radius_degrees is None
        ):
            raise ValueError("circle annotation requires one point and radius_degrees")
        if self.kind == "line" and len(self.points) < 2:
            raise ValueError("line annotation requires at least two points")
        if self.kind == "point" and (
            len(self.points) != 1 or self.radius_degrees is not None
        ):
            raise ValueError("point annotation requires one point and no radius")
        if self.kind == "label" and (len(self.points) != 1 or self.label is None):
            raise ValueError("label annotation requires one point and label")
        if self.kind != "circle" and self.fill:
            raise ValueError("only circle annotations can be filled")
        return self


class WwtFitsLayer(BaseModel):
    model_config = MODEL_CONFIG

    layer_id: Identifier
    source_snapshot_id: Identifier
    content_ref: Identifier
    content_hash: ContentHash
    opacity: float = Field(default=1.0, ge=0, le=1)
    stretch: Literal["linear", "sqrt", "log", "power", "histogram_equalization"] = (
        "sqrt"
    )
    color_map: Literal["gray", "viridis", "magma", "inferno"] = "gray"
    vmin: float | None = Field(default=None, allow_inf_nan=False)
    vmax: float | None = Field(default=None, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_display_range(self) -> Self:
        if (self.vmin is None) != (self.vmax is None):
            raise ValueError("WWT FITS vmin and vmax must be declared together")
        if self.vmin is not None and self.vmax is not None and self.vmin >= self.vmax:
            raise ValueError("WWT FITS vmin must be lower than vmax")
        return self


class WwtSphericalTableCoordinates(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["spherical"] = "spherical"
    frame: Literal[
        "sky",
        "ecliptic",
        "galactic",
        "sun",
        "mercury",
        "venus",
        "earth",
        "moon",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
    ] = "sky"
    longitude_field: ShortString
    latitude_field: ShortString
    longitude_unit: Literal["degrees", "hours"] = "degrees"
    altitude_field: ShortString | None = None


class WwtCartesianTableCoordinates(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["cartesian"] = "cartesian"
    frame: Literal[
        "sun",
        "mercury",
        "venus",
        "earth",
        "moon",
        "mars",
        "jupiter",
        "saturn",
        "uranus",
        "neptune",
        "pluto",
    ]
    x_field: ShortString
    y_field: ShortString
    z_field: ShortString
    xyz_unit: Literal["m", "km", "au", "pc", "kpc", "mpc"]


WwtTableCoordinates = Annotated[
    WwtSphericalTableCoordinates | WwtCartesianTableCoordinates,
    Field(discriminator="kind"),
]


class WwtTableTimeSeries(BaseModel):
    model_config = MODEL_CONFIG

    time_field: ShortString
    decay_days: float = Field(gt=0, le=365_250)


class WwtTableLayer(BaseModel):
    model_config = MODEL_CONFIG

    layer_id: Identifier
    source_snapshot_id: Identifier
    content_ref: Identifier
    content_hash: ContentHash
    media_type: Literal[
        "text/csv",
        "text/tab-separated-values",
        "application/vnd.ivoa.votable+xml",
    ]
    coordinates: WwtTableCoordinates
    time_series: WwtTableTimeSeries | None = None
    size_field: ShortString | None = None
    size_scale: float = Field(default=1, gt=0, le=1000)
    color_token: Literal[
        "brand", "information", "success", "warning", "error", "neutral"
    ] = "brand"
    color_field: ShortString | None = None
    marker_scale: Literal["screen", "world"] = "screen"
    opacity: float = Field(default=1, ge=0, le=1)


class WwtSceneStep(BaseModel):
    model_config = MODEL_CONFIG

    step_id: Identifier
    view: WwtView
    observed_at: UtcDateTime | None = None
    hold_seconds: float = Field(default=0, ge=0, le=3600)


class WwtSceneVisualizationSpec(BaseModel):
    model_config = MODEL_CONFIG

    mode: Literal[VisualizationMode.wwt_scene] = VisualizationMode.wwt_scene
    view: WwtView
    time: WwtTimeControl = Field(default_factory=WwtTimeControl)
    observer: WwtObserver | None = None
    background: Literal["digitized_sky_survey", "gaia", "wise", "solar_system"] = (
        "digitized_sky_survey"
    )
    foreground: WwtForeground | None = None
    solar_system: WwtSolarSystemOptions | None = None
    coordinate_grids: tuple[WwtCoordinateGrid, ...] = Field(
        default=(WwtCoordinateGrid(system="equatorial"),),
        max_length=4,
    )
    constellations: WwtConstellationOverlays = Field(
        default_factory=WwtConstellationOverlays
    )
    precession_chart: bool = False
    fits_layers: tuple[WwtFitsLayer, ...] = Field(default=(), max_length=64)
    table_layers: tuple[WwtTableLayer, ...] = Field(default=(), max_length=64)
    annotations: tuple[WwtAnnotation, ...] = Field(default=(), max_length=1000)
    tour_steps: tuple[WwtSceneStep, ...] = Field(default=(), max_length=512)
    tour_autoplay: bool = False
    tour_loop: bool = False
    readbacks: tuple[
        Literal["center_coordinates", "field_of_view", "camera_roll", "current_time"],
        ...,
    ] = Field(
        default=("center_coordinates", "field_of_view", "current_time"),
        max_length=4,
    )
    text_alternative: NonEmptyString

    @model_validator(mode="after")
    def require_unique_scene_ids(self) -> Self:
        _require_unique(
            tuple(item.layer_id for item in (*self.fits_layers, *self.table_layers)),
            "WWT layer id",
        )
        _require_unique(
            tuple(item.annotation_id for item in self.annotations),
            "WWT annotation id",
        )
        _require_unique(
            tuple(item.step_id for item in self.tour_steps),
            "WWT tour step id",
        )
        _require_unique(
            tuple(item.system for item in self.coordinate_grids),
            "WWT coordinate grid",
        )
        _require_unique(self.readbacks, "WWT readback")
        if any(item.system == "altaz" for item in self.coordinate_grids) and (
            self.observer is None
        ):
            raise ValueError("altaz grid requires an observer")
        tracked_views = self.view.kind == "tracked_object" or any(
            step.view.kind == "tracked_object" for step in self.tour_steps
        )
        if tracked_views and self.background != "solar_system":
            raise ValueError("tracked-object views require the solar_system background")
        if self.solar_system is not None and self.background != "solar_system":
            raise ValueError("solar-system options require the solar_system background")
        has_sky_only_overlays = (
            self.foreground is not None
            or self.precession_chart
            or any(
                (
                    self.constellations.boundaries,
                    self.constellations.figures,
                    self.constellations.pictures,
                    self.constellations.labels,
                )
            )
        )
        if self.background == "solar_system" and has_sky_only_overlays:
            raise ValueError(
                "foreground, constellation, and precession overlays require a sky background"
            )
        if (self.tour_autoplay or self.tour_loop) and not self.tour_steps:
            raise ValueError("tour playback options require tour_steps")
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
            spec_snapshots.update(
                item.source_snapshot_id for item in self.spec.table_layers
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


class SpectrumPoint(BaseModel):
    model_config = MODEL_CONFIG

    wavelength: float = Field(gt=0)
    flux: float
    continuum: float
    normalized_flux: float
    uncertainty: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def require_finite_values(self) -> Self:
        values = (self.wavelength, self.flux, self.continuum, self.normalized_flux)
        if any(not isfinite(value) for value in values) or (
            self.uncertainty is not None and not isfinite(self.uncertainty)
        ):
            raise ValueError("spectrum point values must be finite")
        return self


class SpectrumLine(BaseModel):
    model_config = MODEL_CONFIG

    line_id: Identifier
    kind: Literal["emission", "absorption"]
    observed_wavelength: float = Field(gt=0)
    normalized_flux: float
    significance_sigma: float = Field(ge=0)
    equivalent_width: float

    @model_validator(mode="after")
    def require_finite_values(self) -> Self:
        values = (
            self.observed_wavelength,
            self.normalized_flux,
            self.significance_sigma,
            self.equivalent_width,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("spectrum line values must be finite")
        return self


class SpectrumArtifactContent(BaseModel):
    """Continuum-normalized spectrum with bounded samples and detected lines."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.spectrum] = ArtifactKind.spectrum
    schema_version: Literal["1.0.0"] = "1.0.0"
    spectrum_id: Identifier
    title: ShortString
    object_name: ShortString
    wavelength_unit: ShortString
    flux_unit: ShortString
    sample_count: int = Field(ge=8)
    points: tuple[SpectrumPoint, ...] = Field(min_length=8, max_length=10_000)
    signal_to_noise: float = Field(ge=0)
    detected_lines: tuple[SpectrumLine, ...] = Field(max_length=32)
    rest_wavelength: float | None = Field(default=None, gt=0)
    radial_velocity_km_s: float | None = None
    skill_executions: tuple[ScientificSkillExecution, ...] = Field(min_length=1)
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_spectrum(self, info: ValidationInfo) -> Self:
        if any(
            execution.skill_id is not ScientificSkillId.spectrum_analysis
            for execution in self.skill_executions
        ):
            raise ValueError("spectrum Artifact requires spectrum_analysis execution")
        _require_unique(
            tuple(item.execution_id for item in self.skill_executions),
            "skill execution id",
        )
        _require_unique(
            tuple(item.line_id for item in self.detected_lines), "spectrum line id"
        )
        wavelengths = tuple(item.wavelength for item in self.points)
        if any(right <= left for left, right in zip(wavelengths, wavelengths[1:])):
            raise ValueError("spectrum display wavelengths must be strictly increasing")
        if not isfinite(self.signal_to_noise) or (
            self.radial_velocity_km_s is not None
            and not isfinite(self.radial_velocity_km_s)
        ):
            raise ValueError("spectrum summary values must be finite")
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_unique(self.evidence_ids, "artifact evidence id")
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={self.spectrum_id: "spectrum"},
            source_snapshot_ids=self.source_snapshot_ids,
        )
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is SpectrumArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


class LightCurvePoint(BaseModel):
    model_config = MODEL_CONFIG

    time: float
    value: float
    normalized_value: float
    uncertainty: float | None = Field(default=None, gt=0)
    quality: Literal["good", "rejected"]
    phase: float = Field(ge=0, lt=1)

    @model_validator(mode="after")
    def require_finite_values(self) -> Self:
        values = (self.time, self.value, self.normalized_value, self.phase)
        if any(not isfinite(value) for value in values) or (
            self.uncertainty is not None and not isfinite(self.uncertainty)
        ):
            raise ValueError("light-curve point values must be finite")
        return self


class PeriodogramPeak(BaseModel):
    model_config = MODEL_CONFIG

    period: float = Field(gt=0)
    power: float = Field(ge=0)

    @model_validator(mode="after")
    def require_finite_values(self) -> Self:
        if not isfinite(self.period) or not isfinite(self.power):
            raise ValueError("periodogram peak values must be finite")
        return self


class LightCurveArtifactContent(BaseModel):
    """Quality-filtered light curve with a bounded Lomb-Scargle period result."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.light_curve] = ArtifactKind.light_curve
    schema_version: Literal["1.0.0"] = "1.0.0"
    light_curve_id: Identifier
    title: ShortString
    object_name: ShortString
    time_scale: Literal["utc", "tai", "tt", "tdb"]
    time_unit: ShortString
    value_unit: ShortString
    value_kind: Literal["relative_flux", "flux", "magnitude"]
    normalization: Literal["median_division", "median_subtraction"]
    sample_count: int = Field(ge=8)
    accepted_sample_count: int = Field(ge=5)
    rejected_sample_count: int = Field(ge=0)
    duration: float = Field(gt=0)
    median_cadence: float = Field(gt=0)
    best_period: float = Field(gt=0)
    best_power: float = Field(ge=0)
    false_alarm_probability: float | None = Field(default=None, ge=0, le=1)
    period_peaks: tuple[PeriodogramPeak, ...] = Field(min_length=1, max_length=10)
    points: tuple[LightCurvePoint, ...] = Field(min_length=8, max_length=10_000)
    skill_executions: tuple[ScientificSkillExecution, ...] = Field(min_length=1)
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_light_curve(self, info: ValidationInfo) -> Self:
        if self.accepted_sample_count + self.rejected_sample_count != self.sample_count:
            raise ValueError("light-curve quality counts must equal sample_count")
        if any(
            execution.skill_id is not ScientificSkillId.light_curve_analysis
            for execution in self.skill_executions
        ):
            raise ValueError(
                "light-curve Artifact requires light_curve_analysis execution"
            )
        _require_unique(
            tuple(item.execution_id for item in self.skill_executions),
            "skill execution id",
        )
        times = tuple(item.time for item in self.points)
        if any(right <= left for left, right in zip(times, times[1:])):
            raise ValueError("light-curve display times must be strictly increasing")
        summary = (
            self.duration,
            self.median_cadence,
            self.best_period,
            self.best_power,
        )
        if any(not isfinite(value) for value in summary):
            raise ValueError("light-curve summary values must be finite")
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_unique(self.evidence_ids, "artifact evidence id")
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={self.light_curve_id: "light_curve"},
            source_snapshot_ids=self.source_snapshot_ids,
        )
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is LightCurveArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


class ModelTaskKind(StrEnum):
    classification = "classification"
    regression = "regression"
    time_series_classification = "time_series_classification"
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


class ModelTrainingInputReference(BaseModel):
    model_config = MODEL_CONFIG

    kind: Literal["dataset_artifact_version", "source_snapshot"]
    ref_id: Identifier


class ImagePreprocessingSpecification(BaseModel):
    """Fixed server-owned preprocessing applied to every training image."""

    model_config = MODEL_CONFIG

    schema_version: Literal["1.0.0"] = "1.0.0"
    color_mode: Literal["RGB"] = "RGB"
    exif_transpose: Literal[True] = True
    resize_height: Literal[32] = 32
    resize_width: Literal[32] = 32
    resize_mode: Literal["contain_pad"] = "contain_pad"
    resampling: Literal["bilinear"] = "bilinear"
    normalization: Literal["uint8_to_unit_interval"] = "uint8_to_unit_interval"


class ImageLabelDefinition(BaseModel):
    model_config = MODEL_CONFIG

    class_index: int = Field(ge=0)
    label: ShortString
    sample_count: int = Field(ge=2)


class ImageTrainingSpecification(BaseModel):
    """Reproducible label and tensor contract for an image training run."""

    model_config = MODEL_CONFIG

    manifest_schema_version: Literal["1.0.0"] = "1.0.0"
    preprocessing: ImagePreprocessingSpecification
    image_shape: tuple[Literal[32], Literal[32], Literal[3]]
    image_count: int = Field(ge=10)
    source_total_pixels: int = Field(gt=0)
    label_schema: tuple[ImageLabelDefinition, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_labels(self) -> Self:
        if tuple(item.class_index for item in self.label_schema) != tuple(
            range(len(self.label_schema))
        ):
            raise ValueError("image label class indexes must be contiguous")
        labels = tuple(item.label for item in self.label_schema)
        if labels != tuple(sorted(labels, key=lambda value: (value.casefold(), value))):
            raise ValueError("image label schema must use canonical order")
        if len({label.casefold() for label in labels}) != len(labels):
            raise ValueError("image labels must be case-insensitively unique")
        if sum(item.sample_count for item in self.label_schema) != self.image_count:
            raise ValueError("image label sample counts must equal image_count")
        return self


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
    training_input: ModelTrainingInputReference
    image_training: ImageTrainingSpecification | None = None
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
            ScientificSkillId.time_series_classification,
            ScientificSkillId.time_series_forecast,
            ScientificSkillId.image_classification,
        }:
            raise ValueError("model evaluation requires a model-training skill")
        if (
            self.training_input.kind == "source_snapshot"
            and self.training_input.ref_id not in self.source_snapshot_ids
        ):
            raise ValueError("model training SourceSnapshot must be declared")
        if (self.task_kind is ModelTaskKind.image_classification) != (
            self.image_training is not None
        ):
            raise ValueError(
                "only image classification requires an image training specification"
            )
        _require_unique(self.feature_fields, "model feature field")
        if self.image_training is not None and len(self.feature_fields) != (
            self.image_training.image_shape[0]
            * self.image_training.image_shape[1]
            * self.image_training.image_shape[2]
        ):
            raise ValueError("image model features must match the image training shape")
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


class ModelArtifactStatus(StrEnum):
    active = "active"
    deprecated = "deprecated"
    revoked = "revoked"


class ModelArtifactContent(BaseModel):
    """Safe, immutable ONNX model and its inference contract."""

    model_config = MODEL_CONFIG
    __artifact_publication_requires_admission__: ClassVar[bool] = True

    kind: Literal[ArtifactKind.model_artifact] = ArtifactKind.model_artifact
    schema_version: Literal["1.0.0"] = "1.0.0"
    model_id: Identifier
    title: ShortString
    status: ModelArtifactStatus = ModelArtifactStatus.active
    task_kind: ModelTaskKind
    algorithm: Identifier
    algorithm_version: ShortString
    training_input: ModelTrainingInputReference
    image_training: ImageTrainingSpecification | None = None
    evaluation_id: Identifier
    feature_fields: tuple[Identifier, ...] = Field(min_length=1)
    target_field: Identifier
    model_binary: ModelBinaryReference
    input_name: Identifier
    output_names: tuple[Identifier, ...] = Field(min_length=1)
    input_shape: tuple[int | None, ...] = Field(min_length=2)
    opset_imports: dict[Identifier, int] = Field(min_length=1)
    dependency_revisions: tuple[NonEmptyString, ...] = Field(min_length=1)
    skill_execution: ScientificSkillExecution
    limitations: tuple[NonEmptyString, ...] = ()
    scientific_evidence: tuple[ScientificEvidence, ...] = ()
    source_snapshot_ids: tuple[Identifier, ...]
    evidence_ids: tuple[Identifier, ...]
    input_hash: ContentHash
    output_hash: ContentHash

    @model_validator(mode="after")
    def validate_model_artifact(self, info: ValidationInfo) -> Self:
        if self.skill_execution.skill_id not in {
            ScientificSkillId.tabular_machine_learning,
            ScientificSkillId.time_series_classification,
            ScientificSkillId.time_series_forecast,
            ScientificSkillId.image_classification,
        }:
            raise ValueError("model Artifact requires a model-training skill")
        if (
            self.training_input.kind == "source_snapshot"
            and self.training_input.ref_id not in self.source_snapshot_ids
        ):
            raise ValueError("model training SourceSnapshot must be declared")
        if (self.task_kind is ModelTaskKind.image_classification) != (
            self.image_training is not None
        ):
            raise ValueError(
                "only image classification requires an image training specification"
            )
        if self.model_binary.media_type != "application/onnx":
            raise ValueError("model Artifact accepts only ONNX binaries")
        _require_unique(self.feature_fields, "model feature field")
        _require_unique(self.output_names, "model output name")
        _require_unique(self.dependency_revisions, "model dependency revision")
        if self.target_field in self.feature_fields:
            raise ValueError("target_field cannot also be a feature field")
        if self.input_shape[0] is not None or any(
            value is None or value <= 0 for value in self.input_shape[1:]
        ):
            raise ValueError(
                "model input shape must use a dynamic batch and positive feature axes"
            )
        if self.input_shape[-1] != len(self.feature_fields):
            raise ValueError("model input shape must match the feature registry")
        if self.image_training is not None and len(self.feature_fields) != (
            self.image_training.image_shape[0]
            * self.image_training.image_shape[1]
            * self.image_training.image_shape[2]
        ):
            raise ValueError("image model features must match the image training shape")
        if any(version < 1 for version in self.opset_imports.values()):
            raise ValueError("ONNX opset versions must be positive")
        _require_unique(self.evidence_ids, "artifact evidence id")
        if tuple(sorted(self.evidence_ids)) != self.evidence_ids:
            raise ValueError("model Artifact evidence_ids must use canonical order")
        _validate_scientific_evidence(
            self.scientific_evidence,
            evidence_ids=self.evidence_ids,
            targets={self.model_id: "model"},
            source_snapshot_ids=self.source_snapshot_ids,
        )
        _require_unique(self.source_snapshot_ids, "source snapshot id")
        _require_output_hash(self, info)
        return self

    def __artifact_publication_is_admitted__(self) -> bool:
        return (
            type(self) is ModelArtifactContent
            and self.output_hash == scientific_artifact_output_hash(self)
        )


ScientificArtifactContent = (
    AnalysisReportArtifactContent
    | VisualizationArtifactContent
    | SpectrumArtifactContent
    | LightCurveArtifactContent
    | ModelEvaluationArtifactContent
    | ModelArtifactContent
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
            ArtifactKind.spectrum: SpectrumArtifactContent,
            ArtifactKind.light_curve: LightCurveArtifactContent,
            ArtifactKind.model_evaluation: ModelEvaluationArtifactContent,
            ArtifactKind.model_artifact: ModelArtifactContent,
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
    "LightCurveArtifactContent",
    "LightCurvePoint",
    "ImageLabelDefinition",
    "ImagePreprocessingSpecification",
    "ImageTrainingSpecification",
    "ModelArtifactContent",
    "ModelArtifactStatus",
    "ModelTrainingInputReference",
    "ModelEvaluationArtifactContent",
    "ScientificArtifactContent",
    "ScientificFinding",
    "ScientificEvidence",
    "ScientificMetric",
    "ScientificResultBlock",
    "ScientificSkillExecution",
    "ScientificSkillStatus",
    "ScientificSupportStatus",
    "SpectrumArtifactContent",
    "SpectrumLine",
    "SpectrumPoint",
    "VisualizationArtifactContent",
    "VisualizationMode",
    "WwtAnnotation",
    "WwtCartesianTableCoordinates",
    "WwtConstellationOverlays",
    "WwtCoordinate",
    "WwtCoordinateGrid",
    "WwtCoordinateView",
    "WwtFitsLayer",
    "WwtForeground",
    "WwtObserver",
    "WwtSceneVisualizationSpec",
    "WwtSceneStep",
    "WwtSolarSystemOptions",
    "WwtSphericalTableCoordinates",
    "WwtTableLayer",
    "WwtTableCoordinates",
    "WwtTableTimeSeries",
    "WwtTimeControl",
    "WwtTrackedObjectView",
    "WwtView",
    "scientific_artifact_output_hash",
]
