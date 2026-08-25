import type { ContentHash, VisualizationReviewContent } from "@xingwen/domain";

import { ScientificChart } from "../scientific-chart";
import { WwtSceneControls } from "../wwt-scene-controls";
import { WwtViewport } from "../wwt-viewport";
import {
  ScientificContentHeader,
  formatNumber,
  sourceModeLabel,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";

const STRETCH_LABELS: Readonly<
  Record<
    Extract<
      VisualizationReviewContent["spec"],
      { mode: "fits_image" }
    >["stretch"],
    string
  >
> = {
  linear: "线性",
  sqrt: "平方根",
  log: "对数",
  power: "幂律",
  histogram_equalization: "直方图均衡",
};

const DIAGNOSTIC_LABELS: Readonly<
  Record<
    Extract<
      VisualizationReviewContent["spec"],
      { mode: "model_diagnostic" }
    >["diagnostic"],
    string
  >
> = {
  confusion_matrix: "混淆矩阵",
  roc_curve: "ROC 曲线",
  precision_recall: "精确率—召回率",
  residuals: "残差",
  forecast: "预测",
  feature_importance: "特征重要性",
};

function ChartSummary({
  content,
}: {
  readonly content: VisualizationReviewContent;
}) {
  if (content.spec.mode !== "chart") return null;
  const { spec } = content;
  return (
    <>
      <div className="scientific-artifact__summary" aria-label="图表摘要">
        <span>序列 {spec.series.length} 条</span>
        <span>
          数据点{" "}
          {spec.series.reduce(
            (count, series) => count + series.points.length,
            0,
          )}{" "}
          个
        </span>
      </div>
      <ScientificChart chart={spec} title={content.title} />
    </>
  );
}

function FitsImageSummary({
  content,
  loadContent,
}: {
  readonly content: VisualizationReviewContent;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  if (content.spec.mode !== "fits_image") return null;
  const { spec } = content;
  if (!loadContent) {
    return (
      <>
        <div
          className="scientific-artifact__summary"
          aria-label="FITS 图像摘要"
        >
          <span>拉伸 {STRETCH_LABELS[spec.stretch]}</span>
          <span>色表 {spec.colorMap}</span>
        </div>
        <p className="scientific-artifact__empty">
          当前界面未接入 FITS 二进制读取通道。
        </p>
      </>
    );
  }
  return <WwtViewport spec={spec} loadContent={loadContent} />;
}

function WwtSceneSummary({
  content,
  versionNumber,
  loadContent,
}: {
  readonly content: VisualizationReviewContent;
  readonly versionNumber: number;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  if (content.spec.mode !== "wwt_scene") return null;
  const { spec } = content;
  const view = spec.view;
  if (!loadContent) {
    return (
      <>
        <div className="scientific-artifact__summary" aria-label="天球场景摘要">
          {view.kind === "coordinates" ? (
            <span>
              中心 RA {formatNumber(view.center.raHours, 3)} h · Dec{" "}
              {formatNumber(view.center.decDegrees, 3)}°
            </span>
          ) : (
            <span>跟踪目标 {taxonomyLabel(view.target)}</span>
          )}
          <span>视场 {formatNumber(view.fieldOfViewDegrees, 3)}°</span>
        </div>
        <p className="scientific-artifact__empty">
          当前界面未接入天球场景二进制读取通道。
        </p>
        <section className="scientific-artifact__section">
          <h4>场景说明</h4>
          <p>{spec.textAlternative}</p>
        </section>
      </>
    );
  }
  return (
    <>
      <div className="scientific-artifact__summary" aria-label="天球场景摘要">
        <span>坐标网格 {spec.coordinateGrids.length} 个</span>
        <span>FITS 图层 {spec.fitsLayers.length} 个</span>
        <span>表格图层 {spec.tableLayers.length} 个</span>
        <span>注释 {spec.annotations.length} 个</span>
      </div>
      <WwtSceneControls
        key={`${content.visualizationId}:${versionNumber}`}
        spec={spec}
        loadContent={loadContent}
      />
    </>
  );
}

function ModelDiagnosticSummary({
  content,
}: {
  readonly content: VisualizationReviewContent;
}) {
  if (content.spec.mode !== "model_diagnostic") return null;
  return (
    <div className="scientific-artifact__summary" aria-label="模型诊断摘要">
      <span>诊断类型 {DIAGNOSTIC_LABELS[content.spec.diagnostic]}</span>
      <span>关联模型评估结果可在工作台结果索引中打开</span>
    </div>
  );
}

export function VisualizationContent({
  content,
  title,
  sourceMode,
  surface,
  versionNumber,
  loadContent,
  enhancementOnly = false,
}: {
  readonly content: VisualizationReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly versionNumber: number;
  readonly loadContent?: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly enhancementOnly?: boolean;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--visualization"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <ScientificContentHeader
          title={content.title || title}
          subtitle={`可视化 · ${sourceModeLabel(sourceMode)}`}
        />
      ) : null}
      {!enhancementOnly && content.description ? (
        <p className="artifact-view__lead">{content.description}</p>
      ) : null}
      <ChartSummary content={content} />
      <FitsImageSummary content={content} loadContent={loadContent} />
      <WwtSceneSummary
        content={content}
        versionNumber={versionNumber}
        loadContent={loadContent}
      />
      <ModelDiagnosticSummary content={content} />
    </article>
  );
}
