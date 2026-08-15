import { describe, expect, it } from "vitest";

import { mapScientificArtifactRead } from "../src/scientific-artifact-repository";

const hash = (value: string) => value;

function mapRead(content: unknown) {
  return mapScientificArtifactRead({
    artifact_version_id: "artv_scientific_formal_01",
    artifact_id: "artifact_scientific_formal_01",
    project_id: "project_scientific_formal_01",
    version_number: 1,
    supersedes_version_id: null,
    source_mode: "fixture",
    content_hash: hash("hash-content"),
    input_hash: hash("hash-input"),
    created_at: "2026-08-14T00:00:00Z",
    content,
    producer_execution: {
      id: "exec_scientific_formal_01",
      producer: { name: "fixture-scientific-skill", version: "1.0.0" },
      status: "completed",
      started_at: "2026-08-14T00:00:00Z",
      finished_at: "2026-08-14T00:00:01Z",
      input_hash: hash("hash-input"),
      output_hash: hash("hash-output"),
      parameters_hash: hash("hash-parameters"),
      latency_ms: 1000,
      error_code: null,
    },
    source_snapshots: [],
    evidence: [],
  } as Parameters<typeof mapScientificArtifactRead>[0]);
}

const execution = {
  execution_id: "exec_scientific_skill_01",
  skill_id: "spectrum_analysis",
  skill_revision: "1.0.0",
  status: "completed",
  input_hash: hash("hash-skill-input"),
  output_hash: hash("hash-skill-output"),
  duration_ms: 50,
  warnings: [],
};

describe("scientific artifact repository", () => {
  it("maps the stable Spectrum payload into the domain review", () => {
    const review = mapRead({
      kind: "spectrum",
      schema_version: "1.0.0",
      spectrum_id: "spectrum_01",
      title: "Synthetic spectrum",
      object_name: "HD 123",
      wavelength_unit: "nm",
      flux_unit: "erg/s/cm²",
      sample_count: 8,
      points: [
        {
          wavelength: 500,
          flux: 1.2,
          continuum: 1.1,
          normalized_flux: 1.09,
          uncertainty: 0.02,
        },
      ],
      signal_to_noise: 25,
      detected_lines: [],
      rest_wavelength: 500,
      radial_velocity_km_s: 60,
      skill_executions: [execution],
      source_snapshot_ids: [],
      evidence_ids: [],
      input_hash: hash("hash-spectrum-input"),
      output_hash: hash("hash-spectrum-output"),
    });

    expect(review.content).toMatchObject({
      kind: "spectrum",
      spectrumId: "spectrum_01",
      signalToNoise: 25,
      points: [{ normalizedFlux: 1.09 }],
    });
  });

  it("maps the stable LightCurve payload without exposing transport names", () => {
    const review = mapRead({
      kind: "light_curve",
      schema_version: "1.0.0",
      light_curve_id: "light_curve_01",
      title: "Synthetic light curve",
      object_name: "HD 123",
      time_scale: "utc",
      time_unit: "d",
      value_unit: "relative",
      value_kind: "relative_flux",
      normalization: "median_division",
      sample_count: 8,
      accepted_sample_count: 7,
      rejected_sample_count: 1,
      duration: 12,
      median_cadence: 1.5,
      best_period: 3,
      best_power: 0.82,
      false_alarm_probability: 0.01,
      period_peaks: [{ period: 3, power: 0.82 }],
      points: [
        {
          time: 1,
          value: 1.01,
          normalized_value: 1,
          uncertainty: 0.01,
          quality: "rejected",
          phase: 0.25,
        },
      ],
      skill_executions: [{ ...execution, skill_id: "light_curve_analysis" }],
      source_snapshot_ids: [],
      evidence_ids: [],
      input_hash: hash("hash-light-input"),
      output_hash: hash("hash-light-output"),
    });

    expect(review.content).toMatchObject({
      kind: "light_curve",
      lightCurveId: "light_curve_01",
      acceptedSampleCount: 7,
      periodPeaks: [{ period: 3, power: 0.82 }],
    });
  });
});
