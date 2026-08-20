import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import type {
  AnalysisReportReviewContent,
  LightCurveArtifactReviewContent,
  ModelArtifactReviewContent,
  ModelEvaluationReviewContent,
  ScientificArtifactReview,
  ScientificArtifactReviewContent,
  SpectrumArtifactReviewContent,
  VisualizationReviewContent,
} from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScientificArtifactRenderer } from "./scientific-artifact-renderer";

const downloadBytes = vi.fn();
vi.mock("../presentation/browser-download", () => ({
  downloadBytes: (...args: unknown[]) => downloadBytes(...args),
}));

afterEach(() => {
  cleanup();
  downloadBytes.mockClear();
});

function makeReview(
  content: ScientificArtifactReviewContent,
): ScientificArtifactReview {
  return {
    artifactVersionId: asEntityId("artifact-version-1"),
    artifactId: asEntityId("artifact-1"),
    projectId: asEntityId("project-1"),
    versionNumber: 1,
    supersedesVersionId: null,
    sourceMode: "live",
    contentHash: "sha256:content",
    inputHash: "sha256:input",
    createdAt: "2026-08-18T00:00:00Z",
    content,
    producerExecution: {
      id: asEntityId("producer-execution-1"),
      producerName: "scientific-skills",
      producerVersion: "1.0.0",
      status: "completed",
      startedAt: "2026-08-18T00:00:00Z",
      finishedAt: "2026-08-18T00:01:00Z",
      inputHash: "sha256:input",
      outputHash: "sha256:output",
      parametersHash: "sha256:parameters",
      latencyMs: 1000,
      errorCode: null,
    },
    sourceSnapshots: [],
    evidence: [],
  };
}

const spectrumContent: SpectrumArtifactReviewContent = {
  kind: "spectrum",
  schemaVersion: "1.0.0",
  spectrumId: asEntityId("spectrum-1"),
  title: "Vega 光谱分析",
  objectName: "Vega",
  wavelengthUnit: "nm",
  fluxUnit: "erg/s/cm^2/A",
  sampleCount: 2,
  points: [
    {
      wavelength: 500.5,
      flux: 1.2,
      continuum: 1.1,
      normalizedFlux: 1.09,
      uncertainty: 0.02,
    },
    {
      wavelength: 656.3,
      flux: 0.8,
      continuum: 1.0,
      normalizedFlux: 0.8,
      uncertainty: null,
    },
  ],
  signalToNoise: 42.5,
  detectedLines: [
    {
      lineId: asEntityId("line-1"),
      kind: "absorption",
      observedWavelength: 656.3,
      normalizedFlux: 0.8,
      significanceSigma: 6.2,
      equivalentWidth: 0.45,
    },
  ],
  restWavelength: 656.28,
  radialVelocityKmS: 12.4,
  skillExecutions: [],
  sourceSnapshotIds: [],
  evidenceIds: [asEntityId("evidence-1"), asEntityId("evidence-2")],
  inputHash: "sha256:input",
  outputHash: "sha256:output",
};

describe("ScientificArtifactRenderer scientific content", () => {
  it("renders spectrum measurements and wired evidence selection", () => {
    const onSelectEvidence = vi.fn();
    render(
      <ScientificArtifactRenderer
        review={makeReview(spectrumContent)}
        title="光谱结果"
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
      />,
    );

    expect(screen.getByText("Vega 光谱分析")).toBeInTheDocument();
    expect(screen.getByText(/S\/N 42.50/)).toBeInTheDocument();
    expect(screen.getByText("500.5000")).toBeInTheDocument();
    expect(screen.getByText("吸收")).toBeInTheDocument();

    const links = screen.getAllByRole("button", { name: "证据 1" });
    expect(links.length).toBeGreaterThan(0);
    const firstLink = links[0];
    if (!firstLink) throw new Error("Evidence link is not rendered.");
    fireEvent.click(firstLink);
    expect(onSelectEvidence).toHaveBeenCalledWith(asEntityId("evidence-1"));
  });

  it("hides evidence controls when no selection wiring exists", () => {
    render(
      <ScientificArtifactRenderer
        review={makeReview(spectrumContent)}
        title="光谱结果"
        surface="fullscreen"
      />,
    );
    expect(screen.queryByRole("button", { name: "证据 1" })).toBeNull();
  });

  it("renders analysis report findings, metrics and human review warnings", () => {
    const content: AnalysisReportReviewContent = {
      kind: "analysis_report",
      schemaVersion: "1.0.0",
      reportId: asEntityId("report-1"),
      title: "系外行星宿主恒星分析",
      summary: "对候选恒星样本完成统计画像。",
      skillExecutions: [],
      resultBlocks: [],
      metrics: [
        {
          metricId: asEntityId("metric-1"),
          label: "样本数",
          value: 128,
          unit: "颗",
          evidenceIds: [],
        },
      ],
      findings: [
        {
          findingId: asEntityId("finding-1"),
          title: "金属丰度偏高",
          statement: "样本平均金属丰度高于场星均值。",
          status: "partial",
          evidenceIds: [asEntityId("evidence-3")],
          metricIds: [asEntityId("metric-1")],
        },
      ],
      limitations: ["样本量有限"],
      humanRequired: ["请人工核对光谱分类"],
      relatedArtifactVersionIds: [],
      sourceSnapshotIds: [],
      evidenceIds: [asEntityId("evidence-3")],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };
    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="分析报告"
        surface="fullscreen"
      />,
    );

    expect(
      screen.getByText("对候选恒星样本完成统计画像。"),
    ).toBeInTheDocument();
    expect(screen.getByText("样本数")).toBeInTheDocument();
    expect(screen.getByText("金属丰度偏高")).toBeInTheDocument();
    expect(screen.getByText("样本量有限")).toBeInTheDocument();
    expect(screen.getByText("需要人工确认")).toBeInTheDocument();
    expect(screen.getByText("请人工核对光谱分类")).toBeInTheDocument();
  });

  it("renders astronomy source rows as a bounded sortable table with units and evidence", () => {
    const sourceEvidenceId = asEntityId("evidence-gaia-source");
    const parallaxEvidenceId = asEntityId("evidence-gaia-parallax");
    const onSelectEvidence = vi.fn();
    const content: AnalysisReportReviewContent = {
      kind: "analysis_report",
      schemaVersion: "1.0.0",
      reportId: asEntityId("report-gaia"),
      title: "Gaia 锥形检索",
      summary: "返回两个 Gaia DR3 源。",
      skillExecutions: [],
      resultBlocks: [
        {
          blockId: asEntityId("result-gaia"),
          label: "Gaia DR3 查询结果",
          representation: "catalog",
          payload: {
            service: "gaia_archive",
            data_release: "gaiadr3",
            coordinate_frame: "ICRS",
            column_metadata: [
              { field: "column_1", label: "Gaia 源标识", unit: null },
              { field: "column_2", label: "视差", unit: "mas" },
            ],
            rows: [
              {
                column_1: "Gaia DR3 2",
                column_2: "2.4",
                cell_evidence_ids: {
                  column_1: sourceEvidenceId,
                  column_2: parallaxEvidenceId,
                },
              },
            ],
          },
          contentHash: "sha256:gaia",
          evidenceIds: [sourceEvidenceId, parallaxEvidenceId],
        },
      ],
      metrics: [],
      findings: [],
      limitations: [],
      humanRequired: [],
      relatedArtifactVersionIds: [],
      sourceSnapshotIds: [asEntityId("snapshot-gaia")],
      evidenceIds: [sourceEvidenceId, parallaxEvidenceId],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };

    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="Gaia 查询"
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
      />,
    );

    expect(screen.getByText("数据服务：")).toBeInTheDocument();
    expect(screen.getByText("ICRS")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "视差 (mas)" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Gaia DR3 2/ }));
    expect(onSelectEvidence).toHaveBeenLastCalledWith(sourceEvidenceId);
    fireEvent.click(screen.getByRole("button", { name: /2\.4.*mas/ }));
    expect(onSelectEvidence).toHaveBeenLastCalledWith(parallaxEvidenceId);
    expect(screen.queryByText(/column_metadata/)).toBeNull();
  });

  it("renders every typed analysis result block without exposing transport tokens", () => {
    const content: AnalysisReportReviewContent = {
      kind: "analysis_report",
      schemaVersion: "1.0.0",
      reportId: asEntityId("report-statistics"),
      title: "统计分析",
      summary: "已完成描述统计与假设检验。",
      skillExecutions: [],
      resultBlocks: [
        {
          blockId: asEntityId("result-fields"),
          label: "字段概览",
          representation: "table",
          payload: {
            rows: [{ field: "mass", missing_count: 0 }],
          },
          contentHash: "sha256:fields",
          evidenceIds: [],
        },
        {
          blockId: asEntityId("result-statistics"),
          label: "描述统计",
          representation: "statistics",
          payload: {
            rows: [{ field: "mass", mean: 1.1 }],
          },
          contentHash: "sha256:statistics",
          evidenceIds: [],
        },
        {
          blockId: asEntityId("result-hypothesis"),
          label: "假设检验",
          representation: "statistics",
          payload: {
            rows: [{ test: "welch_t", p_value: 0.03 }],
          },
          contentHash: "sha256:hypothesis",
          evidenceIds: [],
        },
        {
          blockId: asEntityId("result-correlations"),
          label: "相关系数",
          representation: "matrix",
          payload: {
            rows: [{ left: "mass", right: "radius", value: 0.8 }],
          },
          contentHash: "sha256:correlations",
          evidenceIds: [],
        },
      ],
      metrics: [],
      findings: [],
      limitations: [],
      humanRequired: [],
      relatedArtifactVersionIds: [],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };

    const { container } = render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="分析报告"
        surface="fullscreen"
      />,
    );

    expect(screen.getByText("字段概览")).toBeInTheDocument();
    expect(screen.getByText("描述统计")).toBeInTheDocument();
    expect(screen.getByText("假设检验")).toBeInTheDocument();
    expect(screen.getByText("相关系数")).toBeInTheDocument();
    expect(screen.getByText("welch_t")).toBeInTheDocument();
    expect(screen.getByText("0.8")).toBeInTheDocument();
    expect(container.querySelector("pre")).toBeNull();
    expect(screen.queryByText("statistics")).toBeNull();
    expect(screen.queryByText("matrix")).toBeNull();
  });

  it("keeps light-curve time-scale identity visible", () => {
    const content: LightCurveArtifactReviewContent = {
      kind: "light_curve",
      schemaVersion: "1.0.0",
      lightCurveId: asEntityId("lc-1"),
      title: "WASP-12b 光变",
      objectName: "WASP-12",
      timeScale: "tdb",
      timeUnit: "d",
      valueUnit: "relative flux",
      valueKind: "relative_flux",
      normalization: "median_division",
      sampleCount: 1,
      acceptedSampleCount: 1,
      rejectedSampleCount: 0,
      duration: 3.2,
      medianCadence: 0.02,
      bestPeriod: 1.09,
      bestPower: 88.4,
      falseAlarmProbability: 0.001,
      periodPeaks: [{ period: 1.09, power: 88.4 }],
      points: [
        {
          time: 2459000.5,
          value: 1.0,
          normalizedValue: 1.0,
          uncertainty: 0.01,
          quality: "good",
          phase: 0.45,
        },
      ],
      skillExecutions: [],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };
    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="光变结果"
        surface="fullscreen"
      />,
    );
    expect(screen.getByText(/TDB · d/)).toBeInTheDocument();
    expect(screen.getByText(/1.0900 d/)).toBeInTheDocument();
  });

  it("renders visualization chart content as an accessible table", () => {
    const content: VisualizationReviewContent = {
      kind: "visualization",
      schemaVersion: "1.0.0",
      visualizationId: asEntityId("viz-1"),
      title: "相关图",
      description: "有效温度与金属丰度关系。",
      spec: {
        mode: "chart",
        datasetArtifactVersionId: asEntityId("dataset-version-1"),
        sourceSnapshotId: null,
        xAxis: {
          field: asEntityId("teff"),
          label: "有效温度",
          unit: "K",
          scale: "linear",
        },
        yAxis: {
          field: asEntityId("feh"),
          label: "金属丰度",
          unit: "dex",
          scale: "linear",
        },
        series: [
          {
            seriesId: asEntityId("series-1"),
            label: "候选样本",
            xField: asEntityId("teff"),
            yField: asEntityId("feh"),
            mark: "point",
            colorToken: "brand",
            points: [
              { x: 5800, y: 0.12 },
              { x: 6100, y: 0.21 },
            ],
          },
        ],
      },
      skillExecutions: [],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };
    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="可视化"
        surface="fullscreen"
      />,
    );
    expect(screen.getByText("有效温度与金属丰度关系。")).toBeInTheDocument();
    expect(screen.getByText("候选样本 · 散点")).toBeInTheDocument();
    expect(screen.getByText("5800")).toBeInTheDocument();
  });

  it("downloads the ONNX model binary through the immutable content channel", async () => {
    const content: ModelArtifactReviewContent = {
      kind: "model_artifact",
      schemaVersion: "1.0.0",
      modelId: asEntityId("model-1"),
      title: "宿主分类模型",
      status: "active",
      taskKind: "classification",
      algorithm: "random_forest",
      algorithmVersion: "1.6.1",
      trainingInput: {
        kind: "dataset_artifact_version",
        refId: asEntityId("dataset-1"),
      },
      evaluationId: asEntityId("evaluation-1"),
      featureFields: [asEntityId("teff"), asEntityId("feh")],
      targetField: asEntityId("host_label"),
      modelBinary: {
        contentRef: "model.onnx",
        contentHash: "sha256:model",
        mediaType: "application/onnx",
      },
      inputName: asEntityId("features"),
      outputNames: [asEntityId("prediction")],
      inputShape: [null, 2],
      opsetImports: { ai_onnx_ml: 1 },
      dependencyRevisions: ["scikit-learn 1.6.1"],
      skillExecution: {
        executionId: asEntityId("execution-1"),
        skillId: "tabular_machine_learning",
        skillRevision: "1.0.0",
        status: "completed",
        inputHash: "sha256:input",
        outputHash: "sha256:output",
        durationMs: 1200,
        warnings: [],
      },
      limitations: [],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };
    const loadContent = vi.fn(async () => new ArrayBuffer(8));
    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="模型产物"
        surface="fullscreen"
        loadContent={loadContent}
      />,
    );

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "下载 ONNX 模型" }));
    });
    expect(loadContent).toHaveBeenCalledWith("sha256:model");
    expect(downloadBytes).toHaveBeenCalledWith(
      expect.objectContaining({
        fileName: "random_forest.onnx",
        mediaType: "application/onnx",
      }),
    );
  });

  it("renders exact entity split provenance and runtime limitations", () => {
    const content: ModelEvaluationReviewContent = {
      kind: "model_evaluation",
      schemaVersion: "1.0.0",
      evaluationId: asEntityId("evaluation-1"),
      title: "宿主星分类评估",
      taskKind: "classification",
      algorithm: "random_forest",
      algorithmVersion: "1.6.1",
      trainingInput: {
        kind: "dataset_artifact_version",
        refId: asEntityId("dataset-1"),
      },
      featureFields: [asEntityId("teff"), asEntityId("feh")],
      targetField: asEntityId("host_label"),
      split: {
        strategy: "entity",
        field: asEntityId("object_id"),
        randomSeed: 42,
        trainFraction: 0.8,
        validationFraction: 0,
        testFraction: 0.2,
        crossValidationFolds: 5,
        trainCutoff: null,
      },
      metrics: [],
      baselineMetrics: [],
      skillExecution: {
        executionId: asEntityId("execution-1"),
        skillId: "tabular_machine_learning",
        skillRevision: "1.0.0",
        status: "completed",
        inputHash: "sha256:input",
        outputHash: "sha256:output",
        durationMs: 1200,
        warnings: [],
      },
      modelBinary: null,
      diagnosticVisualizationIds: [],
      limitations: ["同一实体不会跨越训练与测试边界"],
      sourceSnapshotIds: [],
      evidenceIds: [],
      inputHash: "sha256:input",
      outputHash: "sha256:output",
    };

    render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="模型评估"
        surface="fullscreen"
      />,
    );

    expect(screen.getByText(/实体隔离划分/)).toHaveTextContent(
      "实体隔离划分 · 划分字段 object_id · 随机种子 42 · 5 折交叉验证",
    );
    expect(
      screen.getByText("同一实体不会跨越训练与测试边界"),
    ).toBeInTheDocument();
  });
});
