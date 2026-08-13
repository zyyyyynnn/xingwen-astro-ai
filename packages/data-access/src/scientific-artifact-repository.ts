import type {
  AnalysisReportArtifactContent as AnalysisReportDto,
  ChartAxis as ChartAxisDto,
  ChartSeries as ChartSeriesDto,
  ChartVisualizationSpec as ChartSpecDto,
  FitsImageVisualizationSpec as FitsSpecDto,
  ModelDiagnosticVisualizationSpec as DiagnosticSpecDto,
  ModelEvaluationArtifactContent as ModelEvaluationDto,
  ScientificArtifactRead as ScientificArtifactReadDto,
  ScientificMetric as ScientificMetricDto,
  ScientificResultBlock as ScientificResultBlockDto,
  ScientificSkillExecution as ScientificSkillExecutionDto,
  VisualizationArtifactContent as VisualizationDto,
  WwtAnnotation as WwtAnnotationDto,
  WwtCoordinate as WwtCoordinateDto,
  WwtFitsLayer as WwtFitsLayerDto,
  WwtSceneVisualizationSpec as WwtSpecDto,
} from "@xingwen/contracts";
import type {
  AnalysisReportReviewContent,
  ChartAxisReview,
  ChartSeriesReview,
  ContentHash,
  DomainEntityId,
  ModelEvaluationReviewContent,
  ScientificArtifactReview,
  ScientificMetricReview,
  ScientificResultBlockReview,
  ScientificSkillExecutionReview,
  ScientificVisualizationSpecReview,
  SemanticVersion,
  UtcIsoTimestamp,
  VisualizationReviewContent,
  WwtAnnotationReview,
  WwtCoordinateReview,
  WwtFitsLayerReview,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { ValidationError } from "./errors";
import { HttpClient, seg } from "./http-client";
import { mapEvidenceDetail } from "./mapping";
import {
  mapProducerExecutionSummary,
  mapSnapshotSummary,
  parseContract,
} from "./paper-acquisition-repository";
import type { ScientificArtifactRepository } from "./ports";

function id(value: string): DomainEntityId {
  return asEntityId(value);
}

function mapExecution(
  dto: ScientificSkillExecutionDto,
): ScientificSkillExecutionReview {
  return {
    executionId: id(dto.execution_id),
    skillId: dto.skill_id,
    skillRevision: dto.skill_revision as SemanticVersion,
    status: dto.status,
    inputHash: dto.input_hash as ContentHash,
    outputHash: (dto.output_hash ?? null) as ContentHash | null,
    durationMs: dto.duration_ms,
    warnings: [...(dto.warnings ?? [])],
  };
}

function mapMetric(dto: ScientificMetricDto): ScientificMetricReview {
  return {
    metricId: id(dto.metric_id),
    label: dto.label,
    value: dto.value,
    unit: dto.unit ?? null,
    evidenceIds: (dto.evidence_ids ?? []).map(id),
  };
}

function mapResultBlock(
  dto: ScientificResultBlockDto,
): ScientificResultBlockReview {
  return {
    blockId: id(dto.block_id),
    label: dto.label,
    representation: dto.representation,
    payload: dto.payload,
    contentHash: dto.content_hash as ContentHash,
    evidenceIds: (dto.evidence_ids ?? []).map(id),
  };
}

function mapAnalysis(dto: AnalysisReportDto): AnalysisReportReviewContent {
  if (dto.kind !== "analysis_report" || dto.schema_version !== "1.0.0") {
    throw invalidScientificContent();
  }
  return {
    kind: "analysis_report",
    schemaVersion: dto.schema_version,
    reportId: id(dto.report_id),
    title: dto.title,
    summary: dto.summary,
    skillExecutions: dto.skill_executions.map(mapExecution),
    resultBlocks: dto.result_blocks.map(mapResultBlock),
    metrics: (dto.metrics ?? []).map(mapMetric),
    findings: (dto.findings ?? []).map((finding) => ({
      findingId: id(finding.finding_id),
      title: finding.title,
      statement: finding.statement,
      status: finding.status,
      evidenceIds: finding.evidence_ids.map(id),
      metricIds: (finding.metric_ids ?? []).map(id),
    })),
    limitations: [...(dto.limitations ?? [])],
    humanRequired: [...(dto.human_required ?? [])],
    relatedArtifactVersionIds: (dto.related_artifact_version_ids ?? []).map(id),
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
    inputHash: dto.input_hash as ContentHash,
    outputHash: dto.output_hash as ContentHash,
  };
}

function mapAxis(dto: ChartAxisDto): ChartAxisReview {
  return {
    field: id(dto.field),
    label: dto.label,
    unit: dto.unit ?? null,
    scale: dto.scale ?? "linear",
  };
}

function mapSeries(dto: ChartSeriesDto): ChartSeriesReview {
  return {
    seriesId: id(dto.series_id),
    label: dto.label,
    xField: id(dto.x_field),
    yField: id(dto.y_field),
    mark: dto.mark,
    colorToken: dto.color_token ?? "brand",
    points: dto.points.map((point) => ({ x: point.x, y: point.y })),
  };
}

function mapCoordinate(dto: WwtCoordinateDto): WwtCoordinateReview {
  return { raHours: dto.ra_hours, decDegrees: dto.dec_degrees };
}

function mapAnnotation(dto: WwtAnnotationDto): WwtAnnotationReview {
  return {
    annotationId: id(dto.annotation_id),
    kind: dto.kind,
    points: dto.points.map(mapCoordinate),
    label: dto.label ?? null,
    colorToken: dto.color_token ?? "brand",
    radiusDegrees: dto.radius_degrees ?? null,
  };
}

function mapFitsLayer(dto: WwtFitsLayerDto): WwtFitsLayerReview {
  return {
    layerId: id(dto.layer_id),
    sourceSnapshotId: id(dto.source_snapshot_id),
    contentRef: dto.content_ref,
    contentHash: dto.content_hash as ContentHash,
    opacity: dto.opacity ?? 1,
  };
}

function mapSpec(
  dto: VisualizationDto["spec"],
): ScientificVisualizationSpecReview {
  if (dto.mode === "chart") {
    const chart = dto as ChartSpecDto;
    return {
      mode: "chart",
      datasetArtifactVersionId: id(chart.dataset_artifact_version_id),
      xAxis: mapAxis(chart.x_axis),
      yAxis: mapAxis(chart.y_axis),
      series: chart.series.map(mapSeries),
    };
  }
  if (dto.mode === "fits_image") {
    const fits = dto as FitsSpecDto;
    return {
      mode: "fits_image",
      sourceSnapshotId: id(fits.source_snapshot_id),
      contentRef: fits.content_ref,
      contentHash: fits.content_hash as ContentHash,
      stretch: fits.stretch ?? "sqrt",
      colorMap: fits.color_map ?? "gray",
    };
  }
  if (dto.mode === "wwt_scene") {
    const scene = dto as WwtSpecDto;
    return {
      mode: "wwt_scene",
      center: mapCoordinate(scene.center),
      fieldOfViewDegrees: scene.field_of_view_degrees,
      observedAt: (scene.observed_at ?? null) as UtcIsoTimestamp | null,
      background: scene.background ?? "digitized_sky_survey",
      coordinateGrid: scene.coordinate_grid ?? "equatorial",
      fitsLayers: (scene.fits_layers ?? []).map(mapFitsLayer),
      annotations: (scene.annotations ?? []).map(mapAnnotation),
    };
  }
  if (dto.mode === "model_diagnostic") {
    const diagnostic = dto as DiagnosticSpecDto;
    return {
      mode: "model_diagnostic",
      modelEvaluationArtifactVersionId: id(
        diagnostic.model_evaluation_artifact_version_id,
      ),
      diagnostic: diagnostic.diagnostic,
    };
  }
  throw invalidScientificContent();
}

function mapVisualization(dto: VisualizationDto): VisualizationReviewContent {
  if (dto.kind !== "visualization" || dto.schema_version !== "1.0.0") {
    throw invalidScientificContent();
  }
  return {
    kind: "visualization",
    schemaVersion: dto.schema_version,
    visualizationId: id(dto.visualization_id),
    title: dto.title,
    description: dto.description,
    spec: mapSpec(dto.spec),
    skillExecutions: dto.skill_executions.map(mapExecution),
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
    inputHash: dto.input_hash as ContentHash,
    outputHash: dto.output_hash as ContentHash,
  };
}

function mapModel(dto: ModelEvaluationDto): ModelEvaluationReviewContent {
  if (dto.kind !== "model_evaluation" || dto.schema_version !== "1.0.0") {
    throw invalidScientificContent();
  }
  return {
    kind: "model_evaluation",
    schemaVersion: dto.schema_version,
    evaluationId: id(dto.evaluation_id),
    title: dto.title,
    taskKind: dto.task_kind,
    algorithm: dto.algorithm,
    algorithmVersion: dto.algorithm_version,
    datasetArtifactVersionId: id(dto.dataset_artifact_version_id),
    featureFields: dto.feature_fields.map(id),
    targetField: id(dto.target_field),
    split: {
      strategy: dto.split.strategy,
      randomSeed: dto.split.random_seed ?? null,
      trainFraction: dto.split.train_fraction,
      validationFraction: dto.split.validation_fraction,
      testFraction: dto.split.test_fraction,
    },
    metrics: dto.metrics.map(mapMetric),
    baselineMetrics: (dto.baseline_metrics ?? []).map(mapMetric),
    skillExecution: mapExecution(dto.skill_execution),
    diagnosticVisualizationIds: (dto.diagnostic_visualization_ids ?? []).map(
      id,
    ),
    limitations: [...(dto.limitations ?? [])],
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
    inputHash: dto.input_hash as ContentHash,
    outputHash: dto.output_hash as ContentHash,
  };
}

export function mapScientificArtifactRead(
  dto: ScientificArtifactReadDto,
): ScientificArtifactReview {
  const content =
    dto.content.kind === "analysis_report"
      ? mapAnalysis(dto.content)
      : dto.content.kind === "visualization"
        ? mapVisualization(dto.content)
        : dto.content.kind === "model_evaluation"
          ? mapModel(dto.content)
          : null;
  if (content === null) throw invalidScientificContent();
  return {
    artifactVersionId: id(dto.artifact_version_id),
    artifactId: id(dto.artifact_id),
    projectId: id(dto.project_id),
    versionNumber: dto.version_number,
    supersedesVersionId: dto.supersedes_version_id
      ? id(dto.supersedes_version_id)
      : null,
    sourceMode: dto.source_mode,
    contentHash: dto.content_hash as ContentHash,
    inputHash: dto.input_hash as ContentHash,
    createdAt: dto.created_at as UtcIsoTimestamp,
    content,
    producerExecution: mapProducerExecutionSummary(dto.producer_execution),
    sourceSnapshots: dto.source_snapshots.map(mapSnapshotSummary),
    evidence: dto.evidence.map(mapEvidenceDetail),
  };
}

function invalidScientificContent(): ValidationError {
  return new ValidationError(
    "Scientific Artifact content is missing its current discriminator",
    "SCIENTIFIC_ARTIFACT_INVALID",
    [],
  );
}

export function createScientificArtifactRepository(
  http: HttpClient,
): ScientificArtifactRepository {
  return {
    async getReview(artifactVersionId) {
      const payload = await http.getRequired<unknown>(
        `/api/artifact-versions/${seg(artifactVersionId)}/scientific`,
      );
      return mapScientificArtifactRead(
        parseContract<ScientificArtifactReadDto>(
          "ScientificArtifactRead",
          payload,
        ),
      );
    },
    getContent(artifactVersionId, contentHash) {
      return http.getArrayBuffer(
        `/api/artifact-versions/${seg(artifactVersionId)}/scientific/content/${seg(contentHash)}`,
      );
    },
  };
}
