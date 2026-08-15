/** Strict generated-contract fixtures for spectrum and light-curve artifacts. */

import type {
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  EvidenceDetail as EvidenceDetailDto,
  LightCurveArtifactContent,
  ProducerExecutionDetail,
  ProducerReference,
  ScientificArtifactRead as ScientificArtifactReadDto,
  ScientificEvidence,
  ScientificSkillExecution,
  SpectrumArtifactContent,
  SourceSnapshotDetail,
} from "@xingwen/contracts";

import type { FixtureScientificArtifact } from "./bundle";

const PROJECT_ID = "proj_01JEXAMPLE";
const RUN_ID = "run_01JEXAMPLE";
const CREATED_AT = "2026-07-21T08:24:00Z";

function hash(seed: string): string {
  const nibble = (seed.charCodeAt(0) % 16).toString(16);
  return `sha256:${nibble.repeat(64)}`;
}

const producer: ProducerReference = {
  type: "algorithm",
  name: "scientific_skill_fixture",
  version: "1.0.0",
  model_provider: null,
  model_name: null,
  prompt_name: null,
  prompt_version: null,
  prompt_hash: null,
  parameters_hash: hash("p"),
};

function execution(
  id: string,
  skillId: ScientificSkillExecution["skill_id"],
): ScientificSkillExecution {
  return {
    execution_id: id,
    skill_id: skillId,
    skill_revision: "1.0.0",
    status: "completed",
    input_hash: hash("i"),
    output_hash: hash("o"),
    duration_ms: 28,
    warnings: [],
  };
}

function producerExecution(id: string): ProducerExecutionDetail {
  return {
    id,
    run_id: RUN_ID,
    step_key: "analyzing_data",
    step_attempt_id: `${id}_attempt`,
    producer,
    parameters: { fixture: true },
    parameters_hash: hash("p"),
    input_hash: hash("i"),
    output_hash: hash("o"),
    status: "completed",
    started_at: CREATED_AT,
    finished_at: CREATED_AT,
    token_usage: null,
    latency_ms: 28,
    error_code: null,
  };
}

function sourceSnapshot(id: string, sourceId: string): SourceSnapshotDetail {
  return {
    id,
    source_id: sourceId,
    source_type: "scientific_service",
    retrieved_at: CREATED_AT,
    query: { object: "HD 123", fixture: true },
    query_hash: hash("q"),
    content_hash: hash("s"),
    request_metadata: { adapter: "demo_replay" },
    source_version_or_etag: "fixture-2026-07-21",
    license_note: "Deterministic Demo Replay source projection.",
  };
}

function evidence(
  id: string,
  artifactVersionId: string,
  snapshotId: string,
  targetType: string,
  targetId: string,
): EvidenceDetailDto {
  return {
    id,
    artifact_version_id: artifactVersionId,
    target_type: targetType,
    target_id: targetId,
    evidence_type: "service_response",
    source_snapshot_id: snapshotId,
    extraction_method: "registered_scientific_skill",
    confidence: 0.98,
    locator: { kind: "scientific_sample", target: targetId },
    quote_or_value: targetId,
    paper_id: null,
    created_at: CREATED_AT,
  };
}

function scientificEvidence(
  evidenceId: string,
  snapshotId: string,
  targetType: "spectrum" | "light_curve",
  targetId: string,
): ScientificEvidence {
  return {
    evidence_id: evidenceId,
    evidence_type: "service_response",
    extraction_method: "registered_scientific_skill",
    source_snapshot_id: snapshotId,
    target_type: targetType,
    target_id: targetId,
    locator: { kind: "scientific_sample", target: targetId },
    quote_or_value: targetId,
    confidence: 0.98,
  };
}

const spectrumPoints: SpectrumArtifactContent["points"] = [
  {
    wavelength: 500,
    flux: 1.2,
    continuum: 1.1,
    normalized_flux: 1.09,
    uncertainty: 0.02,
  },
  {
    wavelength: 501,
    flux: 1.22,
    continuum: 1.1,
    normalized_flux: 1.11,
    uncertainty: 0.02,
  },
  {
    wavelength: 502,
    flux: 1.25,
    continuum: 1.11,
    normalized_flux: 1.13,
    uncertainty: 0.02,
  },
  {
    wavelength: 503,
    flux: 1.28,
    continuum: 1.12,
    normalized_flux: 1.14,
    uncertainty: 0.02,
  },
  {
    wavelength: 504,
    flux: 1.31,
    continuum: 1.12,
    normalized_flux: 1.17,
    uncertainty: 0.02,
  },
  {
    wavelength: 505,
    flux: 1.29,
    continuum: 1.13,
    normalized_flux: 1.14,
    uncertainty: 0.02,
  },
  {
    wavelength: 506,
    flux: 1.27,
    continuum: 1.13,
    normalized_flux: 1.12,
    uncertainty: 0.02,
  },
  {
    wavelength: 507,
    flux: 1.24,
    continuum: 1.14,
    normalized_flux: 1.09,
    uncertainty: 0.02,
  },
];

const lightCurvePoints: LightCurveArtifactContent["points"] = [
  {
    time: 1,
    value: 1.01,
    normalized_value: 1,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.1,
  },
  {
    time: 2,
    value: 1.03,
    normalized_value: 1.02,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.2,
  },
  {
    time: 3,
    value: 0.99,
    normalized_value: 0.98,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.3,
  },
  {
    time: 4,
    value: 0.97,
    normalized_value: 0.96,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.4,
  },
  {
    time: 5,
    value: 1.02,
    normalized_value: 1.01,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.5,
  },
  {
    time: 6,
    value: 1.04,
    normalized_value: 1.03,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.6,
  },
  {
    time: 7,
    value: 1,
    normalized_value: 0.99,
    uncertainty: 0.01,
    quality: "rejected",
    phase: 0.7,
  },
  {
    time: 8,
    value: 0.98,
    normalized_value: 0.97,
    uncertainty: 0.01,
    quality: "good",
    phase: 0.8,
  },
];

const spectrumContent: SpectrumArtifactContent = {
  kind: "spectrum",
  schema_version: "1.0.0",
  spectrum_id: "spectrum_hd123",
  title: "HD 123 optical spectrum",
  object_name: "HD 123",
  wavelength_unit: "nm",
  flux_unit: "erg/s/cm²",
  sample_count: spectrumPoints.length,
  points: spectrumPoints,
  signal_to_noise: 25,
  detected_lines: [
    {
      line_id: "line_h_alpha",
      kind: "emission",
      observed_wavelength: 500.1,
      normalized_flux: 1.3,
      significance_sigma: 6,
      equivalent_width: 0.4,
    },
  ],
  rest_wavelength: 500,
  radial_velocity_km_s: 60,
  skill_executions: [execution("skill.spectrum", "spectrum_analysis")],
  scientific_evidence: [
    scientificEvidence(
      "evd_spectrum_01",
      "snap_spectrum_01",
      "spectrum",
      "spectrum_hd123",
    ),
  ],
  source_snapshot_ids: ["snap_spectrum_01"],
  evidence_ids: ["evd_spectrum_01"],
  input_hash: hash("i"),
  output_hash: hash("o"),
};

const lightCurveContent: LightCurveArtifactContent = {
  kind: "light_curve",
  schema_version: "1.0.0",
  light_curve_id: "light_curve_hd123",
  title: "HD 123 transit light curve",
  object_name: "HD 123",
  time_scale: "utc",
  time_unit: "d",
  value_unit: "relative",
  value_kind: "relative_flux",
  normalization: "median_division",
  sample_count: lightCurvePoints.length,
  accepted_sample_count: 7,
  rejected_sample_count: 1,
  duration: 12,
  median_cadence: 1.5,
  best_period: 3,
  best_power: 0.82,
  false_alarm_probability: 0.01,
  period_peaks: [
    { period: 3, power: 0.82 },
    { period: 6, power: 0.31 },
  ],
  points: lightCurvePoints,
  skill_executions: [execution("skill.light_curve", "light_curve_analysis")],
  scientific_evidence: [
    scientificEvidence(
      "evd_light_curve_01",
      "snap_light_curve_01",
      "light_curve",
      "light_curve_hd123",
    ),
  ],
  source_snapshot_ids: ["snap_light_curve_01"],
  evidence_ids: ["evd_light_curve_01"],
  input_hash: hash("i"),
  output_hash: hash("o"),
};

function makeFixture(
  artifactId: string,
  artifactVersionId: string,
  content: SpectrumArtifactContent | LightCurveArtifactContent,
  snapshot: SourceSnapshotDetail,
  evidenceRecord: EvidenceDetailDto,
  executionId: string,
): FixtureScientificArtifact {
  const executionRecord = producerExecution(executionId);
  const version: ArtifactVersionDetailDto = {
    id: artifactVersionId,
    artifact_id: artifactId,
    project_id: PROJECT_ID,
    created_by_run_id: RUN_ID,
    version_number: 1,
    schema_version: "1.0.0",
    content: { ...content },
    content_hash: hash(
      artifactVersionId === "artv_scientific_spectrum" ? "a" : "b",
    ),
    input_hash: content.input_hash,
    source_mode: "fixture",
    producer,
    producer_execution: executionRecord,
    source_snapshot_ids: [snapshot.id],
    source_snapshots: [snapshot],
    evidence_ids: [evidenceRecord.id],
    evidence: [evidenceRecord],
    supersedes_version_id: null,
    created_at: CREATED_AT,
  };
  const read: ScientificArtifactReadDto = {
    artifact_version_id: artifactVersionId,
    artifact_id: artifactId,
    project_id: PROJECT_ID,
    version_number: 1,
    supersedes_version_id: null,
    source_mode: "fixture",
    content_hash: version.content_hash,
    input_hash: content.input_hash,
    created_at: CREATED_AT,
    content,
    producer_execution: executionRecord,
    source_snapshots: [snapshot],
    evidence: [evidenceRecord],
  };
  return { version, read, contentBlobs: [] };
}

export const formalScientificArtifactFixtures: readonly FixtureScientificArtifact[] =
  [
    makeFixture(
      "art_scientific_spectrum",
      "artv_scientific_spectrum",
      spectrumContent,
      sourceSnapshot("snap_spectrum_01", "spectral_service_fixture"),
      evidence(
        "evd_spectrum_01",
        "artv_scientific_spectrum",
        "snap_spectrum_01",
        "visualization",
        "spectrum_hd123",
      ),
      "pexec_scientific_spectrum",
    ),
    makeFixture(
      "art_scientific_light_curve",
      "artv_scientific_light_curve",
      lightCurveContent,
      sourceSnapshot("snap_light_curve_01", "time_series_service_fixture"),
      evidence(
        "evd_light_curve_01",
        "artv_scientific_light_curve",
        "snap_light_curve_01",
        "visualization",
        "light_curve_hd123",
      ),
      "pexec_scientific_light_curve",
    ),
  ];
