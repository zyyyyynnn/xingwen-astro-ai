import type {
  AnalysisReportArtifactContent as AnalysisReportDto,
  ChartAxis as ChartAxisDto,
  ChartSeries as ChartSeriesDto,
  ChartVisualizationSpec as ChartSpecDto,
  FitsImageVisualizationSpec as FitsSpecDto,
  LightCurveArtifactContent as LightCurveDto,
  ModelArtifactContent as ModelArtifactDto,
  ModelBinaryReference as ModelBinaryDto,
  ModelDiagnosticVisualizationSpec as DiagnosticSpecDto,
  ModelEvaluationArtifactContent as ModelEvaluationDto,
  ScientificArtifactRead as ScientificArtifactReadDto,
  ScientificMetric as ScientificMetricDto,
  ScientificResultBlock as ScientificResultBlockDto,
  ScientificSkillExecution as ScientificSkillExecutionDto,
  SpectrumArtifactContent as SpectrumDto,
  VisualizationArtifactContent as VisualizationDto,
  WwtAnnotation as WwtAnnotationDto,
  WwtCoordinate as WwtCoordinateDto,
  WwtFitsLayer as WwtFitsLayerDto,
  WwtSceneVisualizationSpec as WwtSpecDto,
  WwtTableLayer as WwtTableLayerDto,
  WwtTrackedObjectView as WwtTrackedObjectViewDto,
  WwtCoordinateView as WwtCoordinateViewDto,
} from "@xingwen/contracts";
import type {
  AnalysisReportReviewContent,
  ChartAxisReview,
  ChartSeriesReview,
  ContentHash,
  DomainEntityId,
  ModelArtifactReviewContent,
  ModelBinaryReview,
  ModelEvaluationReviewContent,
  LightCurveArtifactReviewContent,
  ScientificArtifactReview,
  ScientificMetricReview,
  ScientificResultBlockReview,
  ScientificSkillExecutionReview,
  ScientificVisualizationSpecReview,
  SemanticVersion,
  SpectrumArtifactReviewContent,
  UtcIsoTimestamp,
  VisualizationReviewContent,
  WwtAnnotationReview,
  WwtCoordinateReview,
  WwtFitsLayerReview,
  WwtSceneVisualizationReview,
  WwtTableLayerReview,
  WwtViewReview,
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
    status: dto.status as ScientificSkillExecutionReview["status"],
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
    lineWidth: dto.line_width ?? 2,
    fill: dto.fill ?? false,
    fillColorToken: dto.fill_color_token ?? "brand",
  };
}

function mapFitsLayer(dto: WwtFitsLayerDto): WwtFitsLayerReview {
  return {
    layerId: id(dto.layer_id),
    sourceSnapshotId: id(dto.source_snapshot_id),
    contentRef: dto.content_ref,
    contentHash: dto.content_hash as ContentHash,
    opacity: dto.opacity ?? 1,
    stretch: dto.stretch ?? "sqrt",
    colorMap: dto.color_map ?? "gray",
    vmin: dto.vmin ?? null,
    vmax: dto.vmax ?? null,
  };
}

function mapWwtView(
  dto: WwtCoordinateViewDto | WwtTrackedObjectViewDto,
): WwtViewReview {
  if ("target" in dto) {
    return {
      kind: "tracked_object",
      target: dto.target,
      fieldOfViewDegrees: dto.field_of_view_degrees ?? 10,
      rollDegrees: dto.roll_degrees ?? 0,
      transitionSeconds: dto.transition_seconds ?? 0,
    };
  }
  return {
    kind: "coordinates",
    center: mapCoordinate(dto.center),
    fieldOfViewDegrees: dto.field_of_view_degrees,
    rollDegrees: dto.roll_degrees ?? 0,
    transitionSeconds: dto.transition_seconds ?? 0,
  };
}

function mapTableLayer(dto: WwtTableLayerDto): WwtTableLayerReview {
  const coordinates =
    "x_field" in dto.coordinates
      ? {
          kind: "cartesian" as const,
          frame: dto.coordinates.frame,
          xField: dto.coordinates.x_field,
          yField: dto.coordinates.y_field,
          zField: dto.coordinates.z_field,
          xyzUnit: dto.coordinates.xyz_unit,
        }
      : {
          kind: "spherical" as const,
          frame: dto.coordinates.frame ?? "sky",
          longitudeField: dto.coordinates.longitude_field,
          latitudeField: dto.coordinates.latitude_field,
          longitudeUnit: dto.coordinates.longitude_unit ?? "degrees",
          altitudeField: dto.coordinates.altitude_field ?? null,
        };
  return {
    layerId: id(dto.layer_id),
    sourceSnapshotId: id(dto.source_snapshot_id),
    contentRef: dto.content_ref,
    contentHash: dto.content_hash as ContentHash,
    mediaType: dto.media_type,
    coordinates,
    timeSeries:
      dto.time_series === null || dto.time_series === undefined
        ? null
        : {
            timeField: dto.time_series.time_field,
            decayDays: dto.time_series.decay_days,
          },
    sizeField: dto.size_field ?? null,
    sizeScale: dto.size_scale ?? 1,
    colorToken: dto.color_token ?? "brand",
    colorField: dto.color_field ?? null,
    markerScale: dto.marker_scale ?? "screen",
    opacity: dto.opacity ?? 1,
  };
}

function mapWwtScene(scene: WwtSpecDto): WwtSceneVisualizationReview {
  return {
    mode: "wwt_scene",
    view: mapWwtView(scene.view),
    time: {
      mode: scene.time?.mode ?? "system_clock",
      observedAt: (scene.time?.observed_at ?? null) as UtcIsoTimestamp | null,
      rate: scene.time?.rate ?? null,
    },
    observer:
      scene.observer === null || scene.observer === undefined
        ? null
        : {
            latitudeDegrees: scene.observer.latitude_degrees,
            longitudeDegrees: scene.observer.longitude_degrees,
            elevationMeters: scene.observer.elevation_meters ?? 0,
            localHorizonMode: scene.observer.local_horizon_mode ?? false,
          },
    background: scene.background ?? "digitized_sky_survey",
    foreground:
      scene.foreground === null || scene.foreground === undefined
        ? null
        : {
            imageSet: scene.foreground.image_set,
            opacity: scene.foreground.opacity ?? 1,
          },
    solarSystem:
      scene.solar_system === null || scene.solar_system === undefined
        ? null
        : {
            cosmos: scene.solar_system.cosmos ?? false,
            lighting: scene.solar_system.lighting ?? true,
            milkyWay: scene.solar_system.milky_way ?? true,
            minorPlanets: scene.solar_system.minor_planets ?? false,
            minorOrbits: scene.solar_system.minor_orbits ?? false,
            orbits: scene.solar_system.orbits ?? true,
            planets: scene.solar_system.planets ?? true,
            scale: scene.solar_system.scale ?? 1,
            stars: scene.solar_system.stars ?? true,
          },
    coordinateGrids: (
      scene.coordinate_grids ?? [{ system: "equatorial", labels: true }]
    ).map((grid) => ({
      system: grid.system,
      labels: grid.labels ?? true,
    })),
    constellations: {
      boundaries: scene.constellations?.boundaries ?? false,
      figures: scene.constellations?.figures ?? false,
      pictures: scene.constellations?.pictures ?? false,
      labels: scene.constellations?.labels ?? false,
    },
    precessionChart: scene.precession_chart ?? false,
    fitsLayers: (scene.fits_layers ?? []).map(mapFitsLayer),
    tableLayers: (scene.table_layers ?? []).map(mapTableLayer),
    annotations: (scene.annotations ?? []).map(mapAnnotation),
    tourSteps: (scene.tour_steps ?? []).map((step) => ({
      stepId: id(step.step_id),
      view: mapWwtView(step.view),
      observedAt: (step.observed_at ?? null) as UtcIsoTimestamp | null,
      holdSeconds: step.hold_seconds ?? 0,
    })),
    tourAutoplay: scene.tour_autoplay ?? false,
    tourLoop: scene.tour_loop ?? false,
    readbacks: [
      ...(scene.readbacks ?? [
        "center_coordinates",
        "field_of_view",
        "current_time",
      ]),
    ],
    textAlternative: scene.text_alternative,
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
    return mapWwtScene(dto as WwtSpecDto);
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
    trainingInput: {
      kind: dto.training_input.kind,
      refId: id(dto.training_input.ref_id),
    },
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
    modelBinary: dto.model_binary ? mapModelBinary(dto.model_binary) : null,
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

function mapModelBinary(dto: ModelBinaryDto): ModelBinaryReview {
  return {
    contentRef: dto.content_ref,
    contentHash: dto.content_hash as ContentHash,
    mediaType: dto.media_type,
  };
}

function mapModelArtifact(dto: ModelArtifactDto): ModelArtifactReviewContent {
  if (
    dto.kind !== "model_artifact" ||
    dto.schema_version !== "1.0.0" ||
    dto.model_binary.media_type !== "application/onnx"
  ) {
    throw invalidScientificContent();
  }
  return {
    kind: "model_artifact",
    schemaVersion: dto.schema_version,
    modelId: id(dto.model_id),
    title: dto.title,
    status: dto.status ?? "active",
    taskKind: dto.task_kind,
    algorithm: dto.algorithm,
    algorithmVersion: dto.algorithm_version,
    trainingInput: {
      kind: dto.training_input.kind,
      refId: id(dto.training_input.ref_id),
    },
    evaluationId: id(dto.evaluation_id),
    featureFields: dto.feature_fields.map(id),
    targetField: id(dto.target_field),
    modelBinary: {
      ...mapModelBinary(dto.model_binary),
      mediaType: "application/onnx",
    },
    inputName: id(dto.input_name),
    outputNames: dto.output_names.map(id),
    inputShape: [...dto.input_shape],
    opsetImports: { ...dto.opset_imports },
    dependencyRevisions: [...dto.dependency_revisions],
    skillExecution: mapExecution(dto.skill_execution),
    limitations: [...(dto.limitations ?? [])],
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
    inputHash: dto.input_hash as ContentHash,
    outputHash: dto.output_hash as ContentHash,
  };
}

function mapSpectrum(dto: SpectrumDto): SpectrumArtifactReviewContent {
  if (dto.kind !== "spectrum" || dto.schema_version !== "1.0.0") {
    throw invalidScientificContent();
  }
  return {
    kind: "spectrum",
    schemaVersion: dto.schema_version,
    spectrumId: id(dto.spectrum_id),
    title: dto.title,
    objectName: dto.object_name,
    wavelengthUnit: dto.wavelength_unit,
    fluxUnit: dto.flux_unit,
    sampleCount: dto.sample_count,
    points: dto.points.map((point) => ({
      wavelength: point.wavelength,
      flux: point.flux,
      continuum: point.continuum,
      normalizedFlux: point.normalized_flux,
      uncertainty: point.uncertainty ?? null,
    })),
    signalToNoise: dto.signal_to_noise,
    detectedLines: dto.detected_lines.map((line) => ({
      lineId: id(line.line_id),
      kind: line.kind,
      observedWavelength: line.observed_wavelength,
      normalizedFlux: line.normalized_flux,
      significanceSigma: line.significance_sigma,
      equivalentWidth: line.equivalent_width,
    })),
    restWavelength: dto.rest_wavelength ?? null,
    radialVelocityKmS: dto.radial_velocity_km_s ?? null,
    skillExecutions: dto.skill_executions.map(mapExecution),
    sourceSnapshotIds: dto.source_snapshot_ids.map(id),
    evidenceIds: dto.evidence_ids.map(id),
    inputHash: dto.input_hash as ContentHash,
    outputHash: dto.output_hash as ContentHash,
  };
}

function mapLightCurve(dto: LightCurveDto): LightCurveArtifactReviewContent {
  if (dto.kind !== "light_curve" || dto.schema_version !== "1.0.0") {
    throw invalidScientificContent();
  }
  return {
    kind: "light_curve",
    schemaVersion: dto.schema_version,
    lightCurveId: id(dto.light_curve_id),
    title: dto.title,
    objectName: dto.object_name,
    timeScale: dto.time_scale,
    timeUnit: dto.time_unit,
    valueUnit: dto.value_unit,
    valueKind: dto.value_kind,
    normalization: dto.normalization,
    sampleCount: dto.sample_count,
    acceptedSampleCount: dto.accepted_sample_count,
    rejectedSampleCount: dto.rejected_sample_count,
    duration: dto.duration,
    medianCadence: dto.median_cadence,
    bestPeriod: dto.best_period,
    bestPower: dto.best_power,
    falseAlarmProbability: dto.false_alarm_probability ?? null,
    periodPeaks: dto.period_peaks.map((peak) => ({
      period: peak.period,
      power: peak.power,
    })),
    points: dto.points.map((point) => ({
      time: point.time,
      value: point.value,
      normalizedValue: point.normalized_value,
      uncertainty: point.uncertainty ?? null,
      quality: point.quality,
      phase: point.phase,
    })),
    skillExecutions: dto.skill_executions.map(mapExecution),
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
          : dto.content.kind === "model_artifact"
            ? mapModelArtifact(dto.content)
            : dto.content.kind === "spectrum"
              ? mapSpectrum(dto.content)
              : dto.content.kind === "light_curve"
                ? mapLightCurve(dto.content)
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
