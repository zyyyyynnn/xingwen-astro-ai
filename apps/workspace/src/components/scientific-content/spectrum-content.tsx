import type { SpectrumArtifactReviewContent } from "@xingwen/domain";

import {
  formatNumber,
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

function SpectrumPointTable({
  points,
  surface,
  wavelengthUnit,
  fluxUnit,
}: {
  readonly points: readonly SpectrumArtifactReviewContent["points"][number][];
  readonly surface: ScientificContentSurface;
  readonly wavelengthUnit: string;
  readonly fluxUnit: string;
}) {
  const visible = points.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">光谱采样点</caption>
        <thead>
          <tr>
            <th scope="col">波长 ({wavelengthUnit})</th>
            <th scope="col">通量 ({fluxUnit})</th>
            <th scope="col">连续谱</th>
            <th scope="col">归一化通量</th>
            <th scope="col">不确定度</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((point, index) => (
            <tr key={`${point.wavelength}-${index}`}>
              <th scope="row">{formatNumber(point.wavelength)}</th>
              <td>{formatNumber(point.flux)}</td>
              <td>{formatNumber(point.continuum)}</td>
              <td>{formatNumber(point.normalizedFlux)}</td>
              <td>{formatNumber(point.uncertainty)}</td>
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

function SpectrumLineTable({
  lines,
  surface,
  wavelengthUnit,
}: {
  readonly lines: readonly SpectrumArtifactReviewContent["detectedLines"][number][];
  readonly surface: ScientificContentSurface;
  readonly wavelengthUnit: string;
}) {
  const visible = lines.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">检测到的谱线</caption>
        <thead>
          <tr>
            <th scope="col">谱线</th>
            <th scope="col">类型</th>
            <th scope="col">观测波长 ({wavelengthUnit})</th>
            <th scope="col">归一化通量</th>
            <th scope="col">显著性 / 等效宽度</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((line, index) => (
            <tr key={line.lineId}>
              <th scope="row">{`谱线 ${index + 1}`}</th>
              <td>{line.kind === "emission" ? "发射" : "吸收"}</td>
              <td>{formatNumber(line.observedWavelength)}</td>
              <td>{formatNumber(line.normalizedFlux)}</td>
              <td>
                <span>{formatNumber(line.significanceSigma)} σ</span>
                <small>等效宽度 {formatNumber(line.equivalentWidth)}</small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {limitNote(lines.length, visible.length, "条谱线") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(lines.length, visible.length, "条谱线")}
        </p>
      ) : null}
    </div>
  );
}

export function SpectrumContent({
  content,
  title,
  sourceMode,
  surface,
}: {
  readonly content: SpectrumArtifactReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--spectrum"
      data-surface={surface}
    >
      <ScientificContentHeader
        title={content.title || title}
        subtitle={`光谱 · ${content.objectName}`}
      />
      <div className="scientific-artifact__summary" aria-label="光谱摘要">
        <span>采样 {content.sampleCount} 点</span>
        <span>S/N {formatNumber(content.signalToNoise, 2)}</span>
        <span>谱线 {content.detectedLines.length} 条</span>
        <span>
          波长 {content.wavelengthUnit} · 通量 {content.fluxUnit}
        </span>
        <span>静止波长 {formatNumber(content.restWavelength)}</span>
        <span>径向速度 {formatNumber(content.radialVelocityKmS)} km/s</span>
        <span>{sourceModeLabel(sourceMode)}</span>
      </div>
      <section className="scientific-artifact__section">
        <h4>采样点</h4>
        {content.points.length > 0 ? (
          <SpectrumPointTable
            points={content.points}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
            fluxUnit={content.fluxUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">未提供光谱采样点。</p>
        )}
      </section>
      <section className="scientific-artifact__section">
        <h4>检测到的谱线</h4>
        {content.detectedLines.length > 0 ? (
          <SpectrumLineTable
            lines={content.detectedLines}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
          />
        ) : (
          <p className="scientific-artifact__empty">当前版本未检测到谱线。</p>
        )}
      </section>
    </article>
  );
}
