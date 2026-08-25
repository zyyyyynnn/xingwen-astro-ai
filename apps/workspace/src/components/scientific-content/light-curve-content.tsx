import type { LightCurveArtifactReviewContent } from "@xingwen/domain";

import {
  formatNumber,
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

const VALUE_KIND_LABELS: Record<string, string> = {
  relative_flux: "相对流量",
  flux: "流量",
  magnitude: "星等",
};

const NORMALIZATION_LABELS: Record<string, string> = {
  median_division: "中值相除",
  median_subtraction: "中值相减",
};

function valueKindLabel(
  value: LightCurveArtifactReviewContent["valueKind"],
): string {
  return VALUE_KIND_LABELS[value] ?? value;
}

function normalizationLabel(
  value: LightCurveArtifactReviewContent["normalization"],
): string {
  return NORMALIZATION_LABELS[value] ?? value;
}

function PeriodogramTable({
  peaks,
  surface,
  timeUnit,
}: {
  readonly peaks: readonly LightCurveArtifactReviewContent["periodPeaks"][number][];
  readonly surface: ScientificContentSurface;
  readonly timeUnit: string;
}) {
  const visible = peaks.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光变周期峰值</caption>
        <thead>
          <tr>
            <th scope="col">周期 ({timeUnit})</th>
            <th scope="col">功率</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((peak, index) => (
            <tr key={`${peak.period}-${index}`}>
              <th scope="row">{formatNumber(peak.period)}</th>
              <td>{formatNumber(peak.power)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(peaks.length, visible.length, "个周期峰值") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(peaks.length, visible.length, "个周期峰值")}
        </p>
      ) : null}
    </div>
  );
}

function LightCurvePointTable({
  points,
  surface,
  timeUnit,
  valueUnit,
}: {
  readonly points: readonly LightCurveArtifactReviewContent["points"][number][];
  readonly surface: ScientificContentSurface;
  readonly timeUnit: string;
  readonly valueUnit: string;
}) {
  const visible = points.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光变曲线采样点</caption>
        <thead>
          <tr>
            <th scope="col">时间 ({timeUnit})</th>
            <th scope="col">值 ({valueUnit})</th>
            <th scope="col">归一化值</th>
            <th scope="col">不确定度</th>
            <th scope="col">质量 / 相位</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((point, index) => (
            <tr key={`${point.time}-${index}`}>
              <th scope="row">{formatNumber(point.time)}</th>
              <td>{formatNumber(point.value)}</td>
              <td>{formatNumber(point.normalizedValue)}</td>
              <td>{formatNumber(point.uncertainty)}</td>
              <td>
                <span>{point.quality === "good" ? "有效" : "剔除"}</span>
                <small>相位 {formatNumber(point.phase, 3)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(points.length, visible.length, "个采样点") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(points.length, visible.length, "个采样点")}
        </p>
      ) : null}
    </div>
  );
}

export function LightCurveContent({
  content,
  title,
  sourceMode,
  surface,
  enhancementOnly = false,
}: {
  readonly content: LightCurveArtifactReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly enhancementOnly?: boolean;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--light-curve"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <ScientificContentHeader
          title={content.title || title}
          subtitle={`光变曲线 · ${content.objectName}`}
        />
      ) : null}
      {!enhancementOnly ? (
        <div className="scientific-artifact__summary" aria-label="光变曲线摘要">
          <span>采样 {content.sampleCount} 点</span>
          <span>有效 {content.acceptedSampleCount}</span>
          <span>剔除 {content.rejectedSampleCount}</span>
          <span>
            周期 {formatNumber(content.bestPeriod)} {content.timeUnit}
          </span>
          <span>FAP {formatNumber(content.falseAlarmProbability, 4)}</span>
          <span>
            {content.timeScale.toUpperCase()} · {content.timeUnit}
          </span>
          <span>
            {valueKindLabel(content.valueKind)} · {content.valueUnit} ·{" "}
            {normalizationLabel(content.normalization)}
          </span>
          <span>{sourceModeLabel(sourceMode)}</span>
        </div>
      ) : null}
      <section className="scientific-artifact__section">
        <h4>周期分析</h4>
        {!enhancementOnly ? (
          <div className="scientific-artifact__summary">
            <span>最佳功率 {formatNumber(content.bestPower, 4)}</span>
            <span>
              持续时间 {formatNumber(content.duration)} {content.timeUnit}
            </span>
            <span>
              中位采样间隔 {formatNumber(content.medianCadence)}{" "}
              {content.timeUnit}
            </span>
          </div>
        ) : null}
        {content.periodPeaks.length > 0 ? (
          <PeriodogramTable
            peaks={content.periodPeaks}
            surface={surface}
            timeUnit={content.timeUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供周期峰值。</p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>采样点</h4>
        {content.points.length > 0 ? (
          <LightCurvePointTable
            points={content.points}
            surface={surface}
            timeUnit={content.timeUnit}
            valueUnit={content.valueUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供光变曲线采样点。</p>
        )}
      </section>
    </article>
  );
}
