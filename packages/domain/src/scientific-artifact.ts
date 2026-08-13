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
  readonly datasetArtifactVersionId: DomainEntityId;
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
  readonly kind: "circle" | "line" | "label";
  readonly points: readonly WwtCoordinateReview[];
  readonly label: string | null;
  readonly colorToken: ChartSeriesReview["colorToken"];
  readonly radiusDegrees: number | null;
}

export interface WwtFitsLayerReview {
  readonly layerId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly contentRef: string;
  readonly contentHash: ContentHash;
  readonly opacity: number;
}

export interface WwtSceneVisualizationReview {
  readonly mode: "wwt_scene";
  readonly center: WwtCoordinateReview;
  readonly fieldOfViewDegrees: number;
  readonly observedAt: UtcIsoTimestamp | null;
  readonly background:
    "digitized_sky_survey" | "gaia" | "wise" | "solar_system";
  readonly coordinateGrid:
    "none" | "equatorial" | "galactic" | "ecliptic" | "altaz";
  readonly fitsLayers: readonly WwtFitsLayerReview[];
  readonly annotations: readonly WwtAnnotationReview[];
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
  readonly strategy: "holdout" | "stratified_holdout" | "time_ordered";
  readonly randomSeed: number | null;
  readonly trainFraction: number;
  readonly validationFraction: number;
  readonly testFraction: number;
}

export interface ModelEvaluationReviewContent {
  readonly kind: "model_evaluation";
  readonly schemaVersion: SemanticVersion;
  readonly evaluationId: DomainEntityId;
  readonly title: string;
  readonly taskKind:
    "classification" | "regression" | "forecast" | "image_classification";
  readonly algorithm: string;
  readonly algorithmVersion: string;
  readonly datasetArtifactVersionId: DomainEntityId;
  readonly featureFields: readonly DomainEntityId[];
  readonly targetField: DomainEntityId;
  readonly split: ModelSplitReview;
  readonly metrics: readonly ScientificMetricReview[];
  readonly baselineMetrics: readonly ScientificMetricReview[];
  readonly skillExecution: ScientificSkillExecutionReview;
  readonly diagnosticVisualizationIds: readonly DomainEntityId[];
  readonly limitations: readonly string[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash;
}

export type ScientificArtifactReviewContent =
  | AnalysisReportReviewContent
  | VisualizationReviewContent
  | ModelEvaluationReviewContent;

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
