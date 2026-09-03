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
  NonEmptyString,
  PublicArtifactPresentation,
  ScientificArtifactReview,
  ScientificArtifactReviewContent,
  SpectrumArtifactReviewContent,
  VisualizationReviewContent,
} from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildScientificArtifactDiffSnapshot,
  compareScientificSnapshots,
} from "../presentation/scientific-diff";

import {
  ScientificArtifactRenderer as ScientificArtifactRendererImpl,
  type ScientificArtifactRendererProps,
} from "./scientific-artifact-renderer";

function text(value: string): NonEmptyString {
  return value as NonEmptyString;
}

function emptyPresentation(
  kind: PublicArtifactPresentation["kind"],
): PublicArtifactPresentation {
  return {
    kind,
    summary: null,
    facts: [],
    sections: [],
    entries: [],
    tables: [],
    graphNodes: [],
    graphEdges: [],
  };
}

function presentationFor(
  content: ScientificArtifactReviewContent,
): PublicArtifactPresentation {
  const presentation = emptyPresentation(content.kind);
  if (content.kind === "analysis_report") {
    return {
      ...presentation,
      summary: text(content.summary),
      facts: content.metrics.map((metric) => ({
        label: text(metric.label),
        values: [
          text(`${metric.value}${metric.unit ? ` ${metric.unit}` : ""}`),
        ],
      })),
      entries: content.findings.map((finding) => ({
        key: finding.findingId,
        title: text(finding.title),
        externalUrl: null,
        status: text(finding.status),
        assessment: null,
        paragraphs: [text(finding.statement)],
        facts: [],
        evidenceIds: finding.evidenceIds,
        reasoningTrace: null,
        canAdjudicate: null,
        relation: null,
      })),
      sections: [
        ...(content.limitations.length
          ? [
              {
                title: text("限制"),
                paragraphs: content.limitations.map((value) => ({
                  text: text(value),
                  status: null,
                  evidenceIds: [],
                })),
              },
            ]
          : []),
        ...(content.humanRequired.length
          ? [
              {
                title: text("待人工确认"),
                paragraphs: content.humanRequired.map((value) => ({
                  text: text(value),
                  status: null,
                  evidenceIds: [],
                })),
              },
            ]
          : []),
      ],
    };
  }
  if (content.kind === "visualization") {
    return {
      ...presentation,
      summary: text(content.description || "可视化结果已冻结。"),
    };
  }
  if (content.kind === "spectrum") {
    return {
      ...presentation,
      facts: [
        {
          label: text("信噪比"),
          values: [text(String(content.signalToNoise))],
        },
      ],
    };
  }
  if (content.kind === "light_curve") {
    return {
      ...presentation,
      facts: [
        {
          label: text("时间尺度"),
          values: [text(content.timeScale.toUpperCase())],
        },
      ],
    };
  }
  if (content.kind === "model_evaluation") {
    const split = content.split;
    return {
      ...presentation,
      facts: [
        {
          label: text("算法"),
          values: [text(content.algorithm)],
        },
        {
          label: text("训练数据"),
          values: [text("研究数据集")],
        },
        {
          label: text("划分方式"),
          values: [text("实体隔离划分")],
        },
        {
          label: text("划分字段"),
          values: [text(String(split.field))],
        },
        {
          label: text("交叉验证"),
          values: [text(`${split.crossValidationFolds} 折`)],
        },
      ],
      sections: content.limitations.length
        ? [
            {
              title: text("限制"),
              paragraphs: content.limitations.map((value) => ({
                text: text(value),
                status: null,
                evidenceIds: [],
              })),
            },
          ]
        : [],
    };
  }
  if (content.kind === "model_artifact") {
    return {
      ...presentation,
      facts: [
        {
          label: text("算法"),
          values: [text(content.algorithm)],
        },
      ],
    };
  }
  return presentation;
}

function ScientificArtifactRenderer(
  props: Omit<ScientificArtifactRendererProps, "presentation">,
) {
  return (
    <ScientificArtifactRendererImpl
      {...props}
      presentation={
        "content" in props.review
          ? presentationFor(props.review.content)
          : emptyPresentation(props.review.kind)
      }
    />
  );
}

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
  it("names the spectrum and toggles authoritative line details with Enter and Space", () => {
    render(
      <ScientificArtifactRenderer
        review={makeReview(spectrumContent)}
        title="光谱结果"
        surface="fullscreen"
      />,
    );
    expect(
      screen.getByRole("img", {
        name: /光谱通量与特征谱线.*包含 2 个采样点与 1 条检测谱线/,
      }),
    ).toBeInTheDocument();
    const line = screen.getByRole("button", {
      name: "选择吸收谱线 656.30 nm，显著性 6.20 sigma",
    });
    expect(line).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(line, { key: "Enter" });
    expect(line).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("选中谱线详情")).toHaveTextContent(
      "等效宽度0.4500 nm",
    );
    expect(fireEvent.keyDown(line, { key: " ", cancelable: true })).toBe(false);
    expect(line).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByLabelText("选中谱线详情")).toBeNull();
  });
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

    expect(screen.getByText("信噪比 (S/N)")).toBeInTheDocument();
    expect(screen.getByText("42.5")).toBeInTheDocument();
    expect(screen.getByText("500.5000")).toBeInTheDocument();
    expect(screen.getByText("吸收")).toBeInTheDocument();

    const links = screen.getAllByRole("button", { name: "查看证据 1" });
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
    expect(screen.queryByRole("button", { name: "查看证据 1" })).toBeNull();
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
      <ScientificArtifactRendererImpl
        review={makeReview(content)}
        title="分析报告"
        surface="fullscreen"
        presentation={{
          ...emptyPresentation("analysis_report"),
          summary: text("通用摘要不应覆盖领域报告。"),
          facts: [
            {
              label: text("通用指标"),
              values: [text("不应显示")],
            },
          ],
        }}
      />,
    );

    expect(screen.getByText("系外行星宿主恒星分析")).toBeInTheDocument();
    expect(screen.getByText("分析报告 · 实时数据")).toBeInTheDocument();
    expect(
      screen.getByText("对候选恒星样本完成统计画像。"),
    ).toBeInTheDocument();
    expect(screen.getByText("样本数")).toBeInTheDocument();
    expect(screen.getByText("金属丰度偏高")).toBeInTheDocument();
    expect(screen.getByText("样本量有限")).toBeInTheDocument();
    expect(screen.getByText("需要人工确认")).toBeInTheDocument();
    expect(screen.getByText("请人工核对光谱分类")).toBeInTheDocument();
    expect(screen.getAllByText("对候选恒星样本完成统计画像。")).toHaveLength(1);
    expect(screen.queryByText("通用摘要不应覆盖领域报告。")).toBeNull();
    expect(screen.queryByText("通用指标")).toBeNull();
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
            rows: [
              {
                field: "mass",
                present_count: 2,
                absent_count: 1,
                non_null_count: 1,
                null_count: 1,
              },
            ],
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
    expect(
      screen.getByRole("columnheader", { name: "包含字段的记录" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "未包含字段的记录" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "空值记录" }),
    ).toBeInTheDocument();
    expect(screen.getByText("描述统计")).toBeInTheDocument();
    expect(screen.getByText("假设检验")).toBeInTheDocument();
    expect(screen.getByText("相关系数")).toBeInTheDocument();
    expect(screen.getByText("welch_t")).toBeInTheDocument();
    expect(screen.getByText("0.8")).toBeInTheDocument();
    expect(container.querySelector("pre")).toBeNull();
    expect(screen.queryByText("statistics")).toBeNull();
    expect(screen.queryByText("matrix")).toBeNull();
  });

  it("keeps light-curve units consistent and supports numeric axes and keyboard inspection", () => {
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
      sampleCount: 2,
      acceptedSampleCount: 2,
      rejectedSampleCount: 0,
      duration: 3.2,
      medianCadence: 120 / 86_400,
      bestPeriod: 1.09,
      bestPower: 88.4,
      falseAlarmProbability: 1e-12,
      periodPeaks: [{ period: 1.09, power: 88.4 }],
      points: [
        {
          time: 2459000.5,
          value: 100,
          normalizedValue: 1.0,
          uncertainty: 0.01,
          quality: "good",
          phase: 0.45,
        },
        {
          time: 2459000.6,
          value: 110,
          normalizedValue: 1.1,
          uncertainty: 1,
          quality: "good",
          phase: 0.49,
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
    expect(screen.getByText("TDB")).toBeInTheDocument();
    expect(screen.getByText("1.00e-12")).toBeInTheDocument();
    expect(screen.getByText("2.00 min")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /光变时间序列.*包含 2 个测量点/ }),
    ).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("tab", { name: /相位折叠曲线/ }), {
      button: 0,
    });
    const phase = screen.getByRole("img", {
      name: /光变相位折叠图.*2 个带相位的测量点/,
    });
    expect(phase).toBeInTheDocument();
    fireEvent.focus(phase);
    expect(screen.getByRole("status")).toHaveTextContent("1.0000");
    fireEvent.keyDown(phase, { key: "End" });
    expect(screen.getByRole("status")).toHaveTextContent("1.1000");
    expect(phase.querySelectorAll(".scientific-plot__ticks text")).toHaveLength(
      10,
    );
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: /周期图谱 \(Periodogram\)/ }),
      { button: 0 },
    );
    expect(
      screen.getByRole("img", { name: /光变周期峰值.*1 个峰值记录/ }),
    ).toBeInTheDocument();
    // The peak table is collapsed by default (spec §48) — expand first.
    fireEvent.click(screen.getByRole("button", { name: /周期图谱峰值候选/ }));
    expect(
      screen.getByRole("columnheader", { name: "周期 (d)" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: /FAP/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("1.0900")).toBeInTheDocument();
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

  it("downloads the immutable ONNX binary and recovers from a failed download", async () => {
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
      inputDtype: "DOUBLE",
      outputNames: [asEntityId("prediction")],
      outputMetadata: {
        prediction: { valueKind: "tensor", dtype: "INT64", shape: ["batch"] },
      },
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
    expect(screen.getByText("DOUBLE")).toBeVisible();
    expect(screen.getByText("INT64")).toBeVisible();
    expect(screen.getByText("[batch]")).toBeVisible();
    expect(screen.getByText("ai_onnx_ml · 1")).toBeVisible();
    expect(screen.queryByText(/Opset 17|Softmax|Float32/)).toBeNull();
    const ioChanges = compareScientificSnapshots(
      buildScientificArtifactDiffSnapshot(
        makeReview({ ...content, inputDtype: null }),
      ),
      buildScientificArtifactDiffSnapshot(makeReview(content)),
    ).find((result) => result.category === "conclusions");
    expect(ioChanges?.changes).toEqual([
      expect.objectContaining({ key: "model-input", kind: "changed" }),
    ]);
    expect(
      screen.getByText("ONNX 模型交付产物包 · 随机森林 · 1.6.1"),
    ).toBeVisible();
    expect(screen.queryByText("active")).not.toBeInTheDocument();
    expect(screen.queryByText("scikit-learn 1.6.1")).not.toBeInTheDocument();
    expect(downloadBytes).toHaveBeenCalledWith(
      expect.objectContaining({
        fileName: "random_forest.onnx",
        mediaType: "application/onnx",
      }),
    );
    loadContent.mockRejectedValueOnce(new Error("private storage details"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "下载 ONNX 模型" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "模型下载失败，请检查连接后重试。",
    );
    expect(
      screen.queryByText("private storage details"),
    ).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: "重新下载 ONNX 模型" }),
      );
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(downloadBytes).toHaveBeenCalledTimes(2);
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
      metrics: [
        {
          metricId: asEntityId("metric-accuracy"),
          metricKey: "accuracy",
          optimization: "maximize",
          category: "holdout",
          label: "准确率",
          value: 0.75,
          unit: null,
          evidenceIds: [],
        },
        {
          metricId: asEntityId("metric-cv-accuracy"),
          metricKey: "cv_accuracy_mean",
          optimization: "none",
          category: "cross_validation",
          label: "准确率 · 均值",
          value: 0.72,
          unit: null,
          evidenceIds: [],
        },
        {
          metricId: asEntityId("metric-importance"),
          metricKey: "feature_importance_teff",
          optimization: "none",
          category: "feature_importance",
          label: "teff",
          value: 0.64,
          unit: null,
          evidenceIds: [],
        },
      ],
      baselineMetrics: [
        {
          metricId: asEntityId("baseline-accuracy"),
          metricKey: "accuracy",
          optimization: "maximize",
          category: "holdout",
          label: "基线准确率",
          value: 0.5,
          unit: null,
          evidenceIds: [],
        },
      ],
      diagnostics: {
        evaluatedSampleCount: 4,
        confusionMatrix: {
          labels: ["star", "galaxy"],
          rows: [
            [2, 0],
            [1, 1],
          ],
        },
        regressionPredictions: [],
        forecast: [],
      },
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

    const view = render(
      <ScientificArtifactRenderer
        review={makeReview(content)}
        title="模型评估"
        surface="fullscreen"
      />,
    );

    expect(
      screen.getByText("实体隔离划分 (Target Entity Split)"),
    ).toBeInTheDocument();
    expect(screen.getByText("object_id")).toBeInTheDocument();
    expect(screen.getByText("随机森林")).toBeInTheDocument();
    expect(screen.getByText("研究数据集")).toBeInTheDocument();
    expect(screen.queryByText("算法版本")).not.toBeInTheDocument();
    expect(screen.queryByText("随机种子")).not.toBeInTheDocument();
    expect(screen.queryByText("42")).not.toBeInTheDocument();
    expect(screen.getByText("5 折 CV")).toBeInTheDocument();
    expect(
      screen.getByText("同一实体不会跨越训练与测试边界"),
    ).toBeInTheDocument();
    expect(screen.getByText("+0.250 对比基线 · 改善")).toBeInTheDocument();
    const scientificChanges = compareScientificSnapshots(
      buildScientificArtifactDiffSnapshot(makeReview(content)),
      buildScientificArtifactDiffSnapshot(
        makeReview({
          ...content,
          metrics: content.metrics.map((metric) => ({
            ...metric,
            metricId: asEntityId(`new-${metric.metricId}`),
          })),
          baselineMetrics: content.baselineMetrics.map((metric) => ({
            ...metric,
            value: 0.6,
          })),
          diagnostics: {
            evaluatedSampleCount: 4,
            confusionMatrix: {
              labels: ["star", "galaxy"],
              rows: [
                [1, 1],
                [1, 1],
              ],
            },
            regressionPredictions: [],
            forecast: [],
          },
        }),
      ),
    ).find((result) => result.category === "conclusions");
    expect(scientificChanges?.changes).toHaveLength(3);
    expect(scientificChanges?.changes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: "baseline:accuracy", kind: "changed" }),
        expect.objectContaining({
          key: 'confusion:["star","star"]',
          kind: "changed",
        }),
        expect.objectContaining({
          key: 'confusion:["star","galaxy"]',
          kind: "changed",
        }),
      ]),
    );
    expect(screen.queryByText("准确率 · 均值")).not.toBeInTheDocument();
    expect(screen.queryAllByText("测试集独立评估")).toHaveLength(0);
    fireEvent.click(
      screen.getByRole("button", { name: "交叉验证与特征重要性 · 2 项" }),
    );
    expect(
      screen.getByRole("region", { name: "全样本交叉验证" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("rowheader", { name: "准确率 · 均值" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", {
        name: "特征重要性（模型贡献，不代表因果关系）",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "分类混淆矩阵" }),
    ).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "测试集诊断 · 4 个样本" }),
    );
    expect(
      screen.getByRole("region", { name: "分类混淆矩阵" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "galaxy" }),
    ).toBeInTheDocument();

    view.rerender(
      <ScientificArtifactRenderer
        title="模型评估"
        surface="fullscreen"
        review={makeReview({
          ...content,
          evaluationId: asEntityId("forecast-evaluation"),
          taskKind: "forecast",
          metrics: [
            {
              metricId: asEntityId("metric-mae"),
              unit: null,
              evidenceIds: [],
              metricKey: "mae",
              optimization: "minimize",
              category: "holdout",
              label: "平均绝对误差",
              value: 0.1,
            },
          ],
          baselineMetrics: [
            {
              metricId: asEntityId("baseline-mae"),
              unit: null,
              evidenceIds: [],
              metricKey: "mae",
              optimization: "minimize",
              category: "holdout",
              label: "基线平均绝对误差",
              value: 0.2,
            },
          ],
          diagnostics: {
            evaluatedSampleCount: 4,
            confusionMatrix: null,
            regressionPredictions: [
              { rowId: asEntityId("row-40"), actual: 1.01, predicted: 1.02 },
            ],
            forecast: Array.from({ length: 51 }, (_, index) => ({
              step: index + 1,
              predictedValue: index / 10,
            })),
          },
        })}
      />,
    );
    expect(screen.getByText("-0.100 对比基线 · 改善")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "测试集诊断 · 4 个样本" }),
    );
    expect(
      screen.getByText("均匀抽取 1 / 4 个测试样本", { exact: false }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(screen.getByRole("status")).toHaveTextContent("第 51 步，共 51 步");
    expect(screen.getByRole("rowheader", { name: "51" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  });
});
