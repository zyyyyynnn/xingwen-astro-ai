import type { Evidence } from "./evidence";
import type { ScientificSkillId, SourceMode } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type {
  ProducerExecutionSummary,
  SourceSnapshotSummary,
} from "./paper-acquisition";
import type {
  ContentHash,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";

export type ScientificSkillStatus =
  "completed" | "partial" | "unsupported" | "failed";
export type ScientificSupportStatus =
  "supported" | "partial" | "unresolved" | "conflicted";

export interface ScientificSkillExecutionReview {
  readonly executionId: DomainEntityId;
  readonly skillId: ScientificSkillId;
  readonly skillRevision: SemanticVersion;
  readonly status: ScientificSkillStatus;
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash | null;
  readonly durationMs: number;
  readonly warnings: readonly string[];
}

export interface ScientificMetricReview {
  readonly metricId: DomainEntityId;
  readonly label: string;
  readonly value: number | string;
  readonly unit: string | null;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface ScientificResultBlockReview {
  readonly blockId: DomainEntityId;
  readonly label: string;
  readonly representation:
    "record" | "table" | "catalog" | "statistics" | "timeseries" | "matrix";
  readonly payload: unknown;
  readonly contentHash: ContentHash;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface ScientificFindingReview {
  readonly findingId: DomainEntityId;
  readonly title: string;
  readonly statement: string;
  readonly status: ScientificSupportStatus;
  readonly evidenceIds: readonly DomainEntityId[];
  readonly metricIds: readonly DomainEntityId[];
}

export interface AnalysisReportReviewContent {
  readonly kind: "analysis_report";
  readonly schemaVersion: SemanticVersion;
  readonly reportId: DomainEntityId;
  readonly title: string;
  readonly summary: string;
  readonly skillExecutions: readonly ScientificSkillExecutionReview[];
  readonly resultBlocks: readonly ScientificResultBlockReview[];
  readonly metrics: readonly ScientificMetricReview[];
  readonly findings: readonly ScientificFindingReview[];
  readonly limitations: readonly string[];
  readonly humanRequired: readonly string[];
  readonly relatedArtifactVersionIds: readonly DomainEntityId[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export interface ChartAxisReview {
  readonly field: DomainEntityId;
  readonly label: string;
  readonly unit: string | null;
  readonly scale: "linear" | "log" | "time" | "category";
}

export interface ChartSeriesReview {
  readonly seriesId: DomainEntityId;
  readonly label: string;
  readonly xField: DomainEntityId;
  readonly yField: DomainEntityId;
  readonly mark: "line" | "point" | "bar" | "area";
  readonly colorToken:
    "brand" | "information" | "success" | "warning" | "error" | "neutral";
  readonly points: readonly ChartPointReview[];
}

export interface ChartPointReview {
  readonly x: number | string;
  readonly y: number | string;
}

export interface ChartVisualizationReview {
  readonly mode: "chart";
  readonly datasetArtifactVersionId: DomainEntityId | null;
  readonly sourceSnapshotId: DomainEntityId | null;
  readonly xAxis: ChartAxisReview;
  readonly yAxis: ChartAxisReview;
  readonly series: readonly ChartSeriesReview[];
}

export interface FitsImageVisualizationReview {
  readonly mode: "fits_image";
  readonly sourceSnapshotId: DomainEntityId;
  readonly contentRef: string;
  readonly contentHash: ContentHash;
  readonly stretch:
    "linear" | "sqrt" | "log" | "power" | "histogram_equalization";
  readonly colorMap: "gray" | "viridis" | "magma" | "inferno";
}

export interface WwtCoordinateReview {
  readonly raHours: number;
  readonly decDegrees: number;
}

export interface WwtAnnotationReview {
  readonly annotationId: DomainEntityId;
  readonly kind: "circle" | "line" | "point" | "label";
  readonly points: readonly WwtCoordinateReview[];
  readonly label: string | null;
  readonly colorToken: ChartSeriesReview["colorToken"];
  readonly radiusDegrees: number | null;
  readonly lineWidth: number;
  readonly fill: boolean;
  readonly fillColorToken: ChartSeriesReview["colorToken"];
}

export interface WwtFitsLayerReview {
  readonly layerId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly contentRef: string;
  readonly contentHash: ContentHash;
  readonly opacity: number;
  readonly stretch: FitsImageVisualizationReview["stretch"];
  readonly colorMap: FitsImageVisualizationReview["colorMap"];
  readonly vmin: number | null;
  readonly vmax: number | null;
}

export interface WwtCoordinateViewReview {
  readonly kind: "coordinates";
  readonly center: WwtCoordinateReview;
  readonly fieldOfViewDegrees: number;
  readonly rollDegrees: number;
  readonly transitionSeconds: number;
}

export interface WwtTrackedObjectViewReview {
  readonly kind: "tracked_object";
  readonly target:
    | "sun"
    | "mercury"
    | "venus"
    | "earth"
    | "moon"
    | "mars"
    | "jupiter"
    | "saturn"
    | "uranus"
    | "neptune"
    | "pluto";
  readonly fieldOfViewDegrees: number;
  readonly rollDegrees: number;
  readonly transitionSeconds: number;
}

export type WwtViewReview =
  WwtCoordinateViewReview | WwtTrackedObjectViewReview;

export interface WwtTimeControlReview {
  readonly mode: "system_clock" | "paused" | "playback";
  readonly observedAt: UtcIsoTimestamp | null;
  readonly rate: number | null;
}

export interface WwtObserverReview {
  readonly latitudeDegrees: number;
  readonly longitudeDegrees: number;
  readonly elevationMeters: number;
  readonly localHorizonMode: boolean;
}

export interface WwtCoordinateGridReview {
  readonly system: "equatorial" | "galactic" | "ecliptic" | "altaz";
  readonly labels: boolean;
}

export interface WwtForegroundReview {
  readonly imageSet: "digitized_sky_survey" | "gaia" | "wise";
  readonly opacity: number;
}

export interface WwtSolarSystemOptionsReview {
  readonly cosmos: boolean;
  readonly lighting: boolean;
  readonly milkyWay: boolean;
  readonly minorPlanets: boolean;
  readonly minorOrbits: boolean;
  readonly orbits: boolean;
  readonly planets: boolean;
  readonly scale: number;
  readonly stars: boolean;
}

export interface WwtConstellationOverlaysReview {
  readonly boundaries: boolean;
  readonly figures: boolean;
  readonly pictures: boolean;
  readonly labels: boolean;
}

export interface WwtSphericalTableCoordinatesReview {
  readonly kind: "spherical";
  readonly frame:
    "sky" | "ecliptic" | "galactic" | WwtTrackedObjectViewReview["target"];
  readonly longitudeField: string;
  readonly latitudeField: string;
  readonly longitudeUnit: "degrees" | "hours";
  readonly altitudeField: string | null;
}

export interface WwtCartesianTableCoordinatesReview {
  readonly kind: "cartesian";
  readonly frame: WwtTrackedObjectViewReview["target"];
  readonly xField: string;
  readonly yField: string;
  readonly zField: string;
  readonly xyzUnit: "m" | "km" | "au" | "pc" | "kpc" | "mpc";
}

export type WwtTableCoordinatesReview =
  WwtSphericalTableCoordinatesReview | WwtCartesianTableCoordinatesReview;

export interface WwtTableTimeSeriesReview {
  readonly timeField: string;
  readonly decayDays: number;
}

export interface WwtTableLayerReview {
  readonly layerId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly contentRef: string;
  readonly contentHash: ContentHash;
  readonly mediaType:
    | "text/csv"
    | "text/tab-separated-values"
    | "application/vnd.ivoa.votable+xml";
  readonly coordinates: WwtTableCoordinatesReview;
  readonly timeSeries: WwtTableTimeSeriesReview | null;
  readonly sizeField: string | null;
  readonly sizeScale: number;
  readonly colorToken: ChartSeriesReview["colorToken"];
  readonly colorField: string | null;
  readonly markerScale: "screen" | "world";
  readonly opacity: number;
}

export interface WwtSceneStepReview {
  readonly stepId: DomainEntityId;
  readonly view: WwtViewReview;
  readonly observedAt: UtcIsoTimestamp | null;
  readonly holdSeconds: number;
}

export type WwtReadbackRequest =
  "center_coordinates" | "field_of_view" | "camera_roll" | "current_time";

export interface WwtSceneVisualizationReview {
  readonly mode: "wwt_scene";
  readonly view: WwtViewReview;
  readonly time: WwtTimeControlReview;
  readonly observer: WwtObserverReview | null;
  readonly background:
    "digitized_sky_survey" | "gaia" | "wise" | "solar_system";
  readonly foreground: WwtForegroundReview | null;
  readonly solarSystem: WwtSolarSystemOptionsReview | null;
  readonly coordinateGrids: readonly WwtCoordinateGridReview[];
  readonly constellations: WwtConstellationOverlaysReview;
  readonly precessionChart: boolean;
  readonly fitsLayers: readonly WwtFitsLayerReview[];
  readonly tableLayers: readonly WwtTableLayerReview[];
  readonly annotations: readonly WwtAnnotationReview[];
  readonly tourSteps: readonly WwtSceneStepReview[];
  readonly tourAutoplay: boolean;
  readonly tourLoop: boolean;
  readonly readbacks: readonly WwtReadbackRequest[];
  readonly textAlternative: string;
}

export interface ModelDiagnosticVisualizationReview {
  readonly mode: "model_diagnostic";
  readonly modelEvaluationArtifactVersionId: DomainEntityId;
  readonly diagnostic:
    | "confusion_matrix"
    | "roc_curve"
    | "precision_recall"
    | "residuals"
    | "forecast"
    | "feature_importance";
}

export type ScientificVisualizationSpecReview =
  | ChartVisualizationReview
  | FitsImageVisualizationReview
  | WwtSceneVisualizationReview
  | ModelDiagnosticVisualizationReview;

export interface VisualizationReviewContent {
  readonly kind: "visualization";
  readonly schemaVersion: SemanticVersion;
  readonly visualizationId: DomainEntityId;
  readonly title: string;
  readonly description: string;
  readonly spec: ScientificVisualizationSpecReview;
  readonly skillExecutions: readonly ScientificSkillExecutionReview[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export interface ModelSplitReview {
  readonly strategy: "random" | "stratified" | "group" | "entity" | "time";
  readonly field: DomainEntityId | null;
  readonly randomSeed: number | null;
  readonly trainFraction: number;
  readonly validationFraction: number;
  readonly testFraction: number;
  readonly crossValidationFolds: number | null;
  readonly trainCutoff: string | number | null;
}

export interface ModelTrainingInputReview {
  readonly kind: "dataset_artifact_version" | "source_snapshot";
  readonly refId: DomainEntityId;
}

export interface ModelBinaryReview {
  readonly contentRef: string;
  readonly contentHash: ContentHash;
  readonly mediaType:
    "application/onnx" | "application/vnd.sklearn" | "application/octet-stream";
}

export interface ModelEvaluationMetricReview extends ScientificMetricReview {
  readonly metricKey: string;
  readonly optimization: "maximize" | "minimize" | "none";
  readonly category: "holdout" | "cross_validation" | "feature_importance";
}

export interface ModelEvaluationReviewContent {
  readonly kind: "model_evaluation";
  readonly schemaVersion: SemanticVersion;
  readonly evaluationId: DomainEntityId;
  readonly title: string;
  readonly taskKind:
    | "classification"
    | "regression"
    | "forecast"
    | "image_classification"
    | "time_series_classification";
  readonly algorithm: string;
  readonly algorithmVersion: string;
  readonly trainingInput: ModelTrainingInputReview;
  readonly featureFields: readonly DomainEntityId[];
  readonly targetField: DomainEntityId;
  readonly split: ModelSplitReview;
  readonly metrics: readonly ModelEvaluationMetricReview[];
  readonly baselineMetrics: readonly ModelEvaluationMetricReview[];
  readonly diagnostics: {
    readonly evaluatedSampleCount: number;
    readonly confusionMatrix: {
      readonly labels: readonly (string | number | boolean)[];
      readonly rows: readonly (readonly number[])[];
    } | null;
    readonly regressionPredictions: readonly {
      readonly rowId: DomainEntityId;
      readonly actual: number;
      readonly predicted: number;
    }[];
    readonly forecast: readonly {
      readonly step: number;
      readonly predictedValue: number;
    }[];
  } | null;
  readonly skillExecution: ScientificSkillExecutionReview;
  readonly modelBinary: ModelBinaryReview | null;
  readonly diagnosticVisualizationIds: readonly DomainEntityId[];
  readonly limitations: readonly string[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export interface ModelArtifactReviewContent {
  readonly kind: "model_artifact";
  readonly schemaVersion: SemanticVersion;
  readonly modelId: DomainEntityId;
  readonly title: string;
  readonly status: "active" | "deprecated" | "revoked";
  readonly taskKind:
    | "classification"
    | "regression"
    | "forecast"
    | "image_classification"
    | "time_series_classification";
  readonly algorithm: string;
  readonly algorithmVersion: string;
  readonly trainingInput: ModelTrainingInputReview;
  readonly evaluationId: DomainEntityId;
  readonly featureFields: readonly DomainEntityId[];
  readonly targetField: DomainEntityId;
  readonly modelBinary: ModelBinaryReview & {
    readonly mediaType: "application/onnx";
  };
  readonly inputName: DomainEntityId;
  readonly inputDtype: string | null;
  readonly outputNames: readonly DomainEntityId[];
  readonly outputMetadata: Readonly<
    Record<
      string,
      {
        readonly valueKind:
          "tensor" | "sequence" | "map" | "optional" | "sparse_tensor";
        readonly dtype: string | null;
        readonly shape: readonly (number | string | null)[] | null;
      } | null
    >
  >;
  readonly inputShape: readonly (number | null)[];
  readonly opsetImports: Readonly<Record<string, number>>;
  readonly dependencyRevisions: readonly string[];
  readonly skillExecution: ScientificSkillExecutionReview;
  readonly limitations: readonly string[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export interface SpectrumPointReview {
  readonly wavelength: number;
  readonly flux: number;
  readonly continuum: number;
  readonly normalizedFlux: number;
  readonly uncertainty: number | null;
}

export interface SpectrumLineReview {
  readonly lineId: DomainEntityId;
  readonly kind: "emission" | "absorption";
  readonly observedWavelength: number;
  readonly normalizedFlux: number;
  readonly significanceSigma: number;
  readonly equivalentWidth: number;
}

export interface SpectrumArtifactReviewContent {
  readonly kind: "spectrum";
  readonly schemaVersion: SemanticVersion;
  readonly spectrumId: DomainEntityId;
  readonly title: string;
  readonly objectName: string;
  readonly wavelengthUnit: string;
  readonly fluxUnit: string;
  readonly sampleCount: number;
  readonly points: readonly SpectrumPointReview[];
  readonly signalToNoise: number | null;
  readonly detectedLines: readonly SpectrumLineReview[];
  readonly restWavelength: number | null;
  readonly radialVelocityKmS: number | null;
  readonly skillExecutions: readonly ScientificSkillExecutionReview[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export interface LightCurvePointReview {
  readonly time: number;
  readonly value: number;
  readonly normalizedValue: number;
  readonly uncertainty: number | null;
  readonly quality: "good" | "rejected";
  readonly phase: number;
}

export interface PeriodogramPeakReview {
  readonly period: number;
  readonly power: number;
}

export interface LightCurveArtifactReviewContent {
  readonly kind: "light_curve";
  readonly schemaVersion: SemanticVersion;
  readonly lightCurveId: DomainEntityId;
  readonly title: string;
  readonly objectName: string;
  readonly timeScale: "utc" | "tai" | "tt" | "tdb";
  readonly timeUnit: string;
  readonly valueUnit: string;
  readonly valueKind: "relative_flux" | "flux" | "magnitude";
  readonly normalization: "median_division" | "median_subtraction";
  readonly sampleCount: number;
  readonly acceptedSampleCount: number;
  readonly rejectedSampleCount: number;
  readonly duration: number;
  readonly medianCadence: number;
  readonly bestPeriod: number;
  readonly bestPower: number;
  readonly falseAlarmProbability: number | null;
  readonly periodPeaks: readonly PeriodogramPeakReview[];
  readonly points: readonly LightCurvePointReview[];
  readonly skillExecutions: readonly ScientificSkillExecutionReview[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export type ScientificArtifactReviewContent =
  | AnalysisReportReviewContent
  | VisualizationReviewContent
  | ModelEvaluationReviewContent
  | ModelArtifactReviewContent
  | SpectrumArtifactReviewContent
  | LightCurveArtifactReviewContent;

export interface ScientificArtifactReview {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly versionNumber: number;
  readonly supersedesVersionId: DomainEntityId | null;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly content: ScientificArtifactReviewContent;
  readonly producerExecution: ProducerExecutionSummary;
  readonly sourceSnapshots: readonly SourceSnapshotSummary[];
  readonly evidence: readonly Evidence[];
}
