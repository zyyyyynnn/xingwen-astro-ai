import { useId, useMemo, useState, useRef, type MouseEvent } from "react";
import type { SpectrumArtifactReviewContent } from "@xingwen/domain";

import {
  formatNumber,
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

interface SpectrumPoint {
  readonly wavelength: number;
  readonly flux: number;
  readonly continuum?: number | null;
  readonly normalizedFlux?: number | null;
  readonly uncertainty?: number | null;
}

interface DetectedLine {
  readonly lineId: string;
  readonly kind: "emission" | "absorption";
  readonly observedWavelength: number;
  readonly normalizedFlux: number;
  readonly significanceSigma: number;
  readonly equivalentWidth: number;
}

function SpectrumPlot({
  points,
  lines,
  wavelengthUnit,
  fluxUnit,
}: {
  readonly points: readonly SpectrumPoint[];
  readonly lines: readonly DetectedLine[];
  readonly wavelengthUnit: string;
  readonly fluxUnit: string;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const plotId = useId();
  const selectedLine = lines.find((line) => line.lineId === selectedLineId);

  const { minW, maxW, minF, maxF, pathD, continuumD, pointsWithCoords } =
    useMemo(() => {
      const first = points[0];
      if (!first) {
        return {
          minW: 3800,
          maxW: 6800,
          minF: 0,
          maxF: 1.2,
          pathD: "",
          continuumD: "",
          pointsWithCoords: [],
        };
      }

      let minW = first.wavelength;
      let maxW = first.wavelength;
      let minF = first.flux;
      let maxF = first.flux;

      for (const p of points) {
        if (p.wavelength < minW) minW = p.wavelength;
        if (p.wavelength > maxW) maxW = p.wavelength;
        if (p.flux < minF) minF = p.flux;
        if (p.flux > maxF) maxF = p.flux;
      }

      // Add 5% padding to flux range
      const fRange = Math.max(maxF - minF, 0.1);
      const paddedMinF = Math.max(0, minF - fRange * 0.05);
      const paddedMaxF = maxF + fRange * 0.08;

      const width = 800;
      const height = 320;
      const margin = { top: 24, right: 30, bottom: 40, left: 60 };
      const innerW = width - margin.left - margin.right;
      const innerH = height - margin.top - margin.bottom;

      const getX = (w: number) =>
        margin.left + ((w - minW) / (maxW - minW || 1)) * innerW;
      const getY = (f: number) =>
        margin.top +
        (1 - (f - paddedMinF) / (paddedMaxF - paddedMinF || 1)) * innerH;

      const coords = points.map((p) => ({
        ...p,
        x: getX(p.wavelength),
        y: getY(p.flux),
        continuumY: p.continuum != null ? getY(p.continuum) : null,
      }));

      const d = coords.reduce(
        (acc, pt, idx) =>
          idx === 0
            ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`
            : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
        "",
      );

      const contD = coords
        .map((pt, index) => {
          if (pt.continuumY === null) return "";
          const command =
            index === 0 || coords[index - 1]?.continuumY == null ? "M" : "L";
          return `${command} ${pt.x.toFixed(1)} ${pt.continuumY.toFixed(1)}`;
        })
        .join(" ");

      return {
        minW,
        maxW,
        minF: paddedMinF,
        maxF: paddedMaxF,
        pathD: d,
        continuumD: contD,
        pointsWithCoords: coords,
      };
    }, [points]);

  const handleMouseMove = (e: MouseEvent<SVGSVGElement>) => {
    if (!svgRef.current || pointsWithCoords.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const svgWidth = rect.width;
    const scaleX = 800 / svgWidth;
    const targetX = clientX * scaleX;

    let closestIdx = 0;
    const firstCoord = pointsWithCoords[0];
    let closestDist = firstCoord
      ? Math.abs(firstCoord.x - targetX)
      : Number.POSITIVE_INFINITY;
    for (let i = 1; i < pointsWithCoords.length; i++) {
      const pt = pointsWithCoords[i];
      if (pt) {
        const dist = Math.abs(pt.x - targetX);
        if (dist < closestDist) {
          closestDist = dist;
          closestIdx = i;
        }
      }
    }
    setHoveredIndex(closestIdx);
  };

  const hoveredPoint =
    hoveredIndex !== null ? pointsWithCoords[hoveredIndex] : null;

  // X Axis ticks
  const xTicks = useMemo(() => {
    const ticks: number[] = [];
    const step = (maxW - minW) / 5;
    for (let i = 0; i <= 5; i++) {
      ticks.push(minW + i * step);
    }
    return ticks;
  }, [minW, maxW]);

  // Y Axis ticks
  const yTicks = useMemo(() => {
    const ticks: number[] = [];
    const step = (maxF - minF) / 4;
    for (let i = 0; i <= 4; i++) {
      ticks.push(minF + i * step);
    }
    return ticks;
  }, [minF, maxF]);

  return (
    <div className="spectrum-plot-wrapper space-y-3">
      <div className="scientific-plot__header flex flex-wrap items-center justify-between gap-2 pb-3">
        <div>
          <h4 className="text-sm font-semibold">
            光谱通量与特征谱线 (Spectrum Display)
          </h4>
          <p className="scientific-plot__caption">
            波长范围 {formatNumber(minW, 1)} – {formatNumber(maxW, 1)}{" "}
            {wavelengthUnit} · 检测到 {lines.length} 条特征谱线
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="scientific-plot__legend-item">
            <span className="scientific-plot__legend-line" aria-hidden="true" />{" "}
            光谱通量显示序列
          </span>
          {continuumD ? (
            <span className="scientific-plot__legend-item">
              <span
                className="scientific-plot__legend-line scientific-plot__legend-line--baseline"
                aria-hidden="true"
              />{" "}
              连续谱基准
            </span>
          ) : null}
        </div>
      </div>

      <div className="relative w-full overflow-hidden">
        <svg
          ref={svgRef}
          viewBox="0 0 800 320"
          className="w-full select-none"
          role="img"
          aria-labelledby={`${plotId}-title ${plotId}-description`}
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <title id={`${plotId}-title`}>光谱通量与特征谱线</title>
          <desc id={`${plotId}-description`}>
            横轴为波长（{wavelengthUnit}），纵轴为通量（{fluxUnit}）；包含{" "}
            {points.length} 个采样点与 {lines.length} 条检测谱线。谱线可用 Enter
            或空格选择。
          </desc>
          {/* Background Grid */}
          {xTicks.map((tick, i) => {
            const x = 60 + ((tick - minW) / (maxW - minW || 1)) * 710;
            return (
              <g key={`xtick-${i}`}>
                <line
                  x1={x}
                  y1={24}
                  x2={x}
                  y2={280}
                  stroke="currentColor"
                  strokeOpacity="0.08"
                  strokeDasharray="2 2"
                />
                <text
                  x={x}
                  y={298}
                  className="scientific-plot__tick-label"
                  textAnchor="middle"
                  fill="currentColor"
                >
                  {Math.round(tick)}
                </text>
              </g>
            );
          })}

          {yTicks.map((tick, i) => {
            const y = 24 + (1 - (tick - minF) / (maxF - minF || 1)) * 256;
            return (
              <g key={`ytick-${i}`}>
                <line
                  x1={60}
                  y1={y}
                  x2={770}
                  y2={y}
                  stroke="currentColor"
                  strokeOpacity="0.08"
                  strokeDasharray="2 2"
                />
                <text
                  x={52}
                  y={y + 3}
                  className="scientific-plot__tick-label"
                  textAnchor="end"
                  fill="currentColor"
                >
                  {tick.toFixed(2)}
                </text>
              </g>
            );
          })}

          {/* Continuum Baseline */}
          {continuumD ? (
            <path
              d={continuumD}
              fill="none"
              stroke="currentColor"
              strokeOpacity="0.35"
              strokeWidth="1.2"
              strokeDasharray="4 4"
            />
          ) : null}

          {/* Spectrum Line */}
          {pathD ? (
            <path
              d={pathD}
              fill="none"
              stroke="var(--color-brand)"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          ) : null}

          {/* Detected Absorption Lines Markers */}
          {lines.map((line) => {
            const x =
              60 +
              ((line.observedWavelength - minW) / (maxW - minW || 1)) * 710;
            const y =
              24 +
              (1 - (line.normalizedFlux - minF) / (maxF - minF || 1)) * 256;
            const isSelected = selectedLineId === line.lineId;

            return (
              <g
                key={line.lineId}
                className="scientific-plot__line-control"
                tabIndex={0}
                role="button"
                aria-pressed={isSelected}
                aria-label={`选择${line.kind === "absorption" ? "吸收" : "发射"}谱线 ${formatNumber(line.observedWavelength, 2)} ${wavelengthUnit}，显著性 ${formatNumber(line.significanceSigma, 2)} sigma`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedLineId(isSelected ? null : line.lineId);
                  }
                }}
                onClick={() =>
                  setSelectedLineId(isSelected ? null : line.lineId)
                }
              >
                {/* Vertical Marker Line */}
                <line
                  x1={x}
                  y1={24}
                  x2={x}
                  y2={y}
                  stroke={
                    isSelected ? "var(--color-error)" : "var(--color-warning)"
                  }
                  strokeWidth={isSelected ? "1.8" : "1.2"}
                  strokeDasharray={isSelected ? "none" : "3 3"}
                  strokeOpacity={isSelected ? "1" : "0.75"}
                />
                {/* Marker Point */}
                <circle
                  cx={x}
                  cy={y}
                  r={isSelected ? 4.5 : 3.5}
                  fill={
                    isSelected ? "var(--color-error)" : "var(--color-warning)"
                  }
                  stroke="var(--color-surface)"
                  strokeWidth="1"
                />
                {/* Label on top */}
                <rect
                  x={x - 28}
                  y={10}
                  width={56}
                  height={14}
                  rx={3}
                  fill={
                    isSelected ? "var(--color-error)" : "var(--color-surface)"
                  }
                  stroke={isSelected ? "var(--color-error)" : "currentColor"}
                  strokeOpacity={isSelected ? "1" : "0.2"}
                />
                <text
                  x={x}
                  y={20}
                  className="scientific-plot__annotation-label"
                  textAnchor="middle"
                  fill={isSelected ? "var(--color-brand-on)" : "currentColor"}
                >
                  {formatNumber(line.observedWavelength, 1)}
                </text>
              </g>
            );
          })}

          {/* Hover Crosshair & Tooltip Point */}
          {hoveredPoint ? (
            <g>
              <line
                x1={hoveredPoint.x}
                y1={24}
                x2={hoveredPoint.x}
                y2={280}
                stroke="currentColor"
                strokeOpacity="0.4"
                strokeWidth="1"
              />
              <circle
                cx={hoveredPoint.x}
                cy={hoveredPoint.y}
                r={4}
                fill="var(--color-brand)"
                stroke="var(--color-surface)"
                strokeWidth="1.5"
              />
            </g>
          ) : null}

          {/* Axis Titles */}
          <text
            x={415}
            y={314}
            className="scientific-plot__axis-label"
            textAnchor="middle"
            fill="currentColor"
          >
            波长 Wavelength ({wavelengthUnit})
          </text>
          <text
            x={-152}
            y={18}
            className="scientific-plot__axis-label"
            textAnchor="middle"
            fill="currentColor"
            transform="rotate(-90)"
          >
            通量 Flux ({fluxUnit})
          </text>
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredPoint ? (
          <div
            className="scientific-plot__tooltip"
            style={{
              left: `${Math.min(Math.max((hoveredPoint.x / 800) * 100, 10), 85)}%`,
              transform: "translateX(-50%)",
            }}
          >
            <div className="scientific-plot__tooltip-title">
              波长: {formatNumber(hoveredPoint.wavelength, 2)} {wavelengthUnit}
            </div>
            <div>
              通量: {formatNumber(hoveredPoint.flux, 4)} {fluxUnit}
            </div>
            {hoveredPoint.continuum != null ? (
              <div>连续谱: {formatNumber(hoveredPoint.continuum, 4)}</div>
            ) : null}
            {hoveredPoint.uncertainty != null ? (
              <div>不确定度: ±{formatNumber(hoveredPoint.uncertainty, 4)}</div>
            ) : null}
          </div>
        ) : null}
      </div>
      {selectedLine ? (
        <dl
          className="scientific-plot__selection"
          aria-label="选中谱线详情"
          aria-live="polite"
        >
          <div>
            <dt>谱线类型</dt>
            <dd>
              {selectedLine.kind === "absorption" ? "吸收谱线" : "发射谱线"}
            </dd>
          </div>
          <div>
            <dt>观测波长</dt>
            <dd>
              {formatNumber(selectedLine.observedWavelength, 2)}{" "}
              {wavelengthUnit}
            </dd>
          </div>
          <div>
            <dt>归一化通量</dt>
            <dd>{formatNumber(selectedLine.normalizedFlux, 4)}</dd>
          </div>
          <div>
            <dt>显著性</dt>
            <dd>{formatNumber(selectedLine.significanceSigma, 2)} sigma</dd>
          </div>
          <div>
            <dt>等效宽度</dt>
            <dd>
              {formatNumber(selectedLine.equivalentWidth, 4)} {wavelengthUnit}
            </dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}

function SpectrumPointTable({
  points,
  surface,
  wavelengthUnit,
  fluxUnit,
}: {
  readonly points: readonly SpectrumPoint[];
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
              <td>
                {point.continuum !== undefined
                  ? formatNumber(point.continuum)
                  : "—"}
              </td>
              <td>
                {point.normalizedFlux !== undefined
                  ? formatNumber(point.normalizedFlux)
                  : "—"}
              </td>
              <td>
                {point.uncertainty !== undefined
                  ? formatNumber(point.uncertainty)
                  : "—"}
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

function SpectrumLineTable({
  lines,
  surface,
  wavelengthUnit,
}: {
  readonly lines: readonly DetectedLine[];
  readonly surface: ScientificContentSurface;
  readonly wavelengthUnit: string;
}) {
  const visible = lines.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">检测到的特征谱线</caption>
        <thead>
          <tr>
            <th scope="col">谱线编号</th>
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
                <span className="font-semibold">
                  {formatNumber(line.significanceSigma, 1)} σ
                </span>
                <small className="ml-1.5">
                  等效宽度 {formatNumber(line.equivalentWidth, 3)}
                </small>
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
  enhancementOnly = false,
}: {
  readonly content: SpectrumArtifactReviewContent;
  readonly title: string;
  readonly sourceMode: string;
  readonly surface: ScientificContentSurface;
  readonly enhancementOnly?: boolean;
}) {
  const fluxUnit =
    content.fluxUnit === "continuum_normalized"
      ? "连续谱归一化"
      : content.fluxUnit;
  return (
    <article
      className="scientific-artifact scientific-artifact--spectrum space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`高分辨率光谱 · 目标天体: ${content.objectName}`}
          />

          <dl
            className="spectrum-summary grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6"
            aria-label="光谱特征参数"
          >
            <div>
              <dt>采样点数</dt>
              <dd>{content.sampleCount} 点</dd>
            </div>
            <div>
              <dt>信噪比 (S/N)</dt>
              <dd>{formatNumber(content.signalToNoise, 1)}</dd>
            </div>
            <div>
              <dt>检出谱线</dt>
              <dd>{content.detectedLines.length} 条</dd>
            </div>
            <div>
              <dt>静止参考波长</dt>
              <dd>
                {content.restWavelength === null
                  ? "未提供"
                  : `${formatNumber(content.restWavelength, 1)} ${content.wavelengthUnit}`}
              </dd>
            </div>
            <div>
              <dt>视向速度</dt>
              <dd>
                {content.radialVelocityKmS === null
                  ? "未提供"
                  : `${formatNumber(content.radialVelocityKmS, 2)} km/s`}
              </dd>
            </div>
            <div>
              <dt>数据源模式</dt>
              <dd>{sourceModeLabel(sourceMode)}</dd>
            </div>
          </dl>
        </>
      ) : null}

      {/* Primary Visual Spectrum Plot */}
      {content.points.length > 0 ? (
        <SpectrumPlot
          points={content.points}
          lines={content.detectedLines}
          wavelengthUnit={content.wavelengthUnit}
          fluxUnit={fluxUnit}
        />
      ) : null}

      <section className="scientific-artifact__section">
        <h4 className="mb-2 font-medium">检出的关键特征谱线</h4>
        {content.detectedLines.length > 0 ? (
          <SpectrumLineTable
            lines={content.detectedLines}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
          />
        ) : (
          <p className="scientific-artifact__empty text-sm">
            当前版本未检测到特征谱线。
          </p>
        )}
      </section>

      <section className="scientific-artifact__section">
        <h4 className="mb-2 font-medium">光谱采样点测量表</h4>
        {content.points.length > 0 ? (
          <SpectrumPointTable
            points={content.points}
            surface={surface}
            wavelengthUnit={content.wavelengthUnit}
            fluxUnit={fluxUnit}
          />
        ) : (
          <p className="scientific-artifact__empty text-sm">
            未提供光谱采样点数据。
          </p>
        )}
      </section>
    </article>
  );
}
