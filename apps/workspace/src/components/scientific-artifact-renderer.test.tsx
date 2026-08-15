import {
  asEntityId,
  type ContentHash,
  type ScientificArtifactReview,
} from "@xingwen/domain";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ScientificArtifactRenderer } from "./scientific-artifact-renderer";

afterEach(cleanup);

const hash = (value: string) => value as ContentHash;

function scientificReview(
  content: ScientificArtifactReview["content"],
): ScientificArtifactReview {
  return {
    artifactVersionId: asEntityId("artv_scientific_formal_01"),
    artifactId: asEntityId("artifact_scientific_formal_01"),
    projectId: asEntityId("project_scientific_formal_01"),
    versionNumber: 1,
    supersedesVersionId: null,
    sourceMode: "fixture",
    contentHash: hash("hash-content"),
    inputHash: hash("hash-input"),
    createdAt: "2026-08-14T00:00:00Z",
    content,
    producerExecution: {
      id: asEntityId("exec_scientific_formal_01"),
      producerName: "fixture-scientific-skill",
      producerVersion: "1.0.0",
      status: "completed",
      startedAt: "2026-08-14T00:00:00Z",
      finishedAt: "2026-08-14T00:00:01Z",
      inputHash: hash("hash-input"),
      outputHash: hash("hash-output"),
      parametersHash: hash("hash-parameters"),
      latencyMs: 1000,
      errorCode: null,
    },
    sourceSnapshots: [],
    evidence: [],
  };
}

const skillExecution = {
  executionId: asEntityId("exec_scientific_skill_01"),
  skillRevision: "1.0.0" as const,
  status: "completed" as const,
  inputHash: hash("hash-skill-input"),
  outputHash: hash("hash-skill-output"),
  durationMs: 50,
  warnings: [],
};

describe("Scientific artifact renderer", () => {
  it("renders the governed PaperCollection candidate table", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.paperAcquisition.getReview(
      asEntityId("artv_papcol_01"),
    );

    render(
      <ScientificArtifactRenderer
        review={{
          ...runtime.researchAdapter.toPaperAcquisitionViewModel(review),
          kind: "paper_collection",
        }}
        title="Retrieved papers"
        versionNumber={1}
        surface="docked"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Retrieved papers" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "论文候选与筛选结果" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/DOI \/ arXiv/).length).toBeGreaterThan(0);
  });

  it("renders LiteratureClaim text from the formal read contract", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.literatureArtifacts.getClaims(
      asEntityId("artv_claims_01"),
    );

    render(
      <ScientificArtifactRenderer
        review={runtime.researchAdapter.toLiteratureArtifactViewModel(review)}
        title="Literature claims"
        versionNumber={1}
        surface="fullscreen"
      />,
    );

    expect(screen.getByText("claim_01")).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "The host star TIC-5678 has an effective temperature of 5800 K.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders relation and trace surfaces as structured tables and steps", async () => {
    const runtime = createTestRuntime();
    const relation =
      await runtime.repositories.literatureArtifacts.getRelations(
        asEntityId("artv_rels_01"),
      );
    const trace =
      await runtime.repositories.literatureArtifacts.getReasoningTraces(
        asEntityId("artv_traces_01"),
      );

    render(
      <ScientificArtifactRenderer
        review={runtime.researchAdapter.toLiteratureArtifactViewModel(relation)}
        title="Literature relations"
        versionNumber={1}
        surface="thread"
      />,
    );
    expect(
      screen.getByRole("table", { name: "文献声明关系与推导证据" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "The host star TIC-5678 has an effective temperature of 5800 K.",
      ).length,
    ).toBeGreaterThan(0);

    cleanup();
    render(
      <ScientificArtifactRenderer
        review={runtime.researchAdapter.toLiteratureArtifactViewModel(trace)}
        title="Reasoning traces"
        versionNumber={1}
        surface="thread"
      />,
    );
    expect(screen.getByText("trace_01")).toBeInTheDocument();
    expect(
      screen.getByText("Compare the host-star identity in each claim."),
    ).toBeInTheDocument();
  });

  it("renders graph nodes and edges without falling back to raw JSON", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.graphArtifacts.getReview(
      asEntityId("artv_graph_01"),
    );

    render(
      <ScientificArtifactRenderer
        review={runtime.researchAdapter.toGraphArtifactViewModel(review)}
        title="Evidence graph"
        versionNumber={1}
        surface="fullscreen"
      />,
    );

    expect(screen.getByText("node_01")).toBeInTheDocument();
    expect(screen.getByText("edge_01")).toBeInTheDocument();
    expect(screen.getByText("Exoplanet candidate dataset")).toBeInTheDocument();
    expect(
      screen.getByText("Host-star temperature finding"),
    ).toBeInTheDocument();
  });

  it.each(["thread", "docked", "fullscreen"] as const)(
    "renders Spectrum through the shared host surface: %s",
    (surface) => {
      const review = scientificReview({
        kind: "spectrum",
        schemaVersion: "1.0.0",
        spectrumId: asEntityId("spectrum_01"),
        title: "Synthetic spectrum",
        objectName: "HD 123",
        wavelengthUnit: "nm",
        fluxUnit: "erg/s/cm²",
        sampleCount: 8,
        points: [
          {
            wavelength: 500,
            flux: 1.2,
            continuum: 1.1,
            normalizedFlux: 1.09,
            uncertainty: 0.02,
          },
        ],
        signalToNoise: 25,
        detectedLines: [
          {
            lineId: asEntityId("line_01"),
            kind: "emission",
            observedWavelength: 500.1,
            normalizedFlux: 1.3,
            significanceSigma: 6,
            equivalentWidth: 0.4,
          },
        ],
        restWavelength: 500,
        radialVelocityKmS: 60,
        skillExecutions: [
          { ...skillExecution, skillId: "spectrum_analysis" as const },
        ],
        sourceSnapshotIds: [],
        evidenceIds: [],
        inputHash: hash("hash-spectrum-input"),
        outputHash: hash("hash-spectrum-output"),
      });

      const { container } = render(
        <ScientificArtifactRenderer
          review={review}
          title="Spectrum"
          versionNumber={1}
          surface={surface}
        />,
      );

      expect(
        container.querySelector(
          `.scientific-artifact[data-surface="${surface}"]`,
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("table", { name: "光谱采样点" }),
      ).toBeInTheDocument();
      expect(screen.getByText("line_01")).toBeInTheDocument();
    },
  );

  it("renders LightCurve summary, period peaks, and quality rows", () => {
    const review = scientificReview({
      kind: "light_curve",
      schemaVersion: "1.0.0",
      lightCurveId: asEntityId("light_curve_01"),
      title: "Synthetic light curve",
      objectName: "HD 123",
      timeScale: "utc",
      timeUnit: "d",
      valueUnit: "relative",
      valueKind: "relative_flux",
      normalization: "median_division",
      sampleCount: 8,
      acceptedSampleCount: 7,
      rejectedSampleCount: 1,
      duration: 12,
      medianCadence: 1.5,
      bestPeriod: 3,
      bestPower: 0.82,
      falseAlarmProbability: 0.01,
      periodPeaks: [{ period: 3, power: 0.82 }],
      points: [
        {
          time: 1,
          value: 1.01,
          normalizedValue: 1,
          uncertainty: 0.01,
          quality: "rejected",
          phase: 0.25,
        },
      ],
      skillExecutions: [
        { ...skillExecution, skillId: "light_curve_analysis" as const },
      ],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: hash("hash-light-input"),
      outputHash: hash("hash-light-output"),
    });

    render(
      <ScientificArtifactRenderer
        review={review}
        title="Light curve"
        versionNumber={1}
        surface="fullscreen"
      />,
    );

    expect(
      screen.getByRole("table", { name: "光变周期峰值" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "光变曲线采样点" }),
    ).toBeInTheDocument();
    expect(screen.getByText("剔除 1")).toBeInTheDocument();
    expect(screen.getByText("剔除")).toBeInTheDocument();
    expect(screen.queryByText(/output_hash/)).not.toBeInTheDocument();
  });

  it.each(["thread", "docked", "fullscreen"] as const)(
    "renders the formal Spectrum fixture through the registry surface: %s",
    async (surface) => {
      const runtime = createTestRuntime();
      const review = await runtime.repositories.scientificArtifacts.getReview(
        asEntityId("artv_scientific_spectrum"),
      );
      const { container } = render(
        <ScientificArtifactRenderer
          review={review}
          title="HD 123 optical spectrum"
          versionNumber={1}
          surface={surface}
        />,
      );
      expect(
        container.querySelector(
          `.scientific-artifact[data-surface="${surface}"]`,
        ),
      ).toBeInTheDocument();
      expect(screen.getByText("line_h_alpha")).toBeInTheDocument();
    },
  );

  it("renders the formal LightCurve fixture in fullscreen", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.scientificArtifacts.getReview(
      asEntityId("artv_scientific_light_curve"),
    );
    render(
      <ScientificArtifactRenderer
        review={review}
        title="HD 123 transit light curve"
        versionNumber={1}
        surface="fullscreen"
      />,
    );
    expect(screen.getByText(/3\.0000 d/)).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "光变曲线采样点" }),
    ).toBeInTheDocument();
  });

  it("opens formal spectrum evidence from the scientific surface", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.scientificArtifacts.getReview(
      asEntityId("artv_scientific_spectrum"),
    );
    const onSelectEvidence = vi.fn();
    render(
      <ScientificArtifactRenderer
        review={review}
        title="HD 123 optical spectrum"
        versionNumber={1}
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "证据 1" }));
    expect(onSelectEvidence).toHaveBeenCalledWith(
      asEntityId("evd_spectrum_01"),
    );
  });
});
