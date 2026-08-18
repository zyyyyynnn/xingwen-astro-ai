import type {
  ChartSeriesReview,
  VisualizationReviewContent,
} from "@xingwen/domain";

import {
  ScientificContentHeader,
  SURFACE_LIMITS,
  formatNumber,
  humanizeToken,
  limitNote,
  sourceModeLabel,
  taxonomyLabel,
  type ScientificContentSurface,
} from "./shared";

const MARK_LABELS: Record<string, string> = {
  line: "折线",
  point: "散点",
  bar: "柱状",
  area: "面积",
};

function ChartSeriesTable({
  series,
  surface,
  xLabel,
  yLabel,
}: {
  readonly series: ChartSeriesReview;
  readonly surface: ScientificContentSurface;
  readonly xLabel: string;
  readonly yLabel: string;
}) {
  const visible = series.points.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">{series.label}采样点</caption>
        <thead>
          <tr>
            <th scope="col">{xLabel}</th>
            <th scope="col">{yLabel}</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((point, index) => (
            <tr key={`${String(point.x)}-${index}`}>
              <th scope="row">{String(point.x)}</th>
              <td>{String(point.y)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(series.points.length, visible.length, "个数据点") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(series.points.length, visible.length, "个数据点")}
        </p>
      ) : null}
    </div>
  );
}

function ChartSummary({
  content,
  surface,
}: {
  readonly content: VisualizationReviewContent;
  readonly surface: ScientificContentSurface;
}) {
  if (content.spec.mode !== "chart") return null;
  const { spec } = content;
  const xLabel = spec.xAxis.unit
    ? `${spec.xAxis.label} (${spec.xAxis.unit})`
    : spec.xAxis.label;
  const yLabel = spec.yAxis.unit
    ? `${spec.yAxis.label} (${spec.yAxis.unit})`
    : spec.yAxis.label;
  return (
    <>
      <div className="scientific-artifact__summary" aria-label="图表摘要">
        <span>
          横轴 {xLabel} · {humanizeToken(spec.xAxis.scale)}
        </span>
        <span>
          纵轴 {yLabel} · {humanizeToken(spec.yAxis.scale)}
        </span>
        <span>序列 {spec.series.length} 条</span>
      </div>
      {spec.series.map((series) => (
        <section key={series.seriesId} className="scientific-artifact__section">
          <h4>
            {series.label} · {MARK_LABELS[series.mark] ?? series.mark}
          </h4>
          {series.points.length > 0 ? (
            <ChartSeriesTable
              series={series}
              surface={surface}
              xLabel={xLabel}
              yLabel={yLabel}
            />
          ) : (
            <p className="scientific-artifact__empty">未提供数据点。</p>
          )}
        </section>
      ))}
    </>
  );
}

function FitsImageSummary({
  content,
}: {
  readonly content: VisualizationReviewContent;
}) {
  if (content.spec.mode !== "fits_image") return null;
  const { spec } = content;
  return (
    <div className="scientific-artifact__summary" aria-label="FITS 图像摘要">
      <span>拉伸 {humanizeToken(spec.stretch)}</span>
      <span>色表 {spec.colorMap}</span>
      <span>FITS 图像二进制内容随证据与下载能力提供</span>
    </div>
  );
}

function WwtSceneSummary({
  content,
}: {
  readonly content: VisualizationReviewContent;
}) {
  if (content.spec.mode !== "wwt_scene") return null;
  const { spec } = content;
  const view = spec.view;
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
        <span>坐标网格 {spec.coordinateGrids.length} 个</span>
        <span>FITS 图层 {spec.fitsLayers.length} 个</span>
        <span>表格图层 {spec.tableLayers.length} 个</span>
        <span>注释 {spec.annotations.length} 个</span>
      </div>
      <section className="scientific-artifact__section">
        <h4>场景说明</h4>
        <p>{spec.textAlternative}</p>
      </section>
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
      <span>诊断类型 {humanizeToken(content.spec.diagnostic)}</span>
      <span>关联模型评估结果可在工作台结果索引中打开</span>
    </div>
  );
}

export function VisualizationContent({
  content,
  title,
  sourceMode,
  surface,
}: {
  readonly content: VisualizationReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--visualization"
      data-surface={surface}
    >
      <ScientificContentHeader
        title={content.title || title}
        subtitle={`可视化 · ${sourceModeLabel(sourceMode)}`}
      />
      {content.description ? (
        <p className="artifact-view__lead">{content.description}</p>
      ) : null}
      <ChartSummary content={content} surface={surface} />
      <FitsImageSummary content={content} />
      <WwtSceneSummary content={content} />
      <ModelDiagnosticSummary content={content} />
    </article>
  );
}
