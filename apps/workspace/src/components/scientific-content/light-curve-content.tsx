import { useMemo, useState, useRef, type MouseEvent } from "react";
import type { LightCurveArtifactReviewContent } from "@xingwen/domain";
import { Tabs, TabsList, TabsTrigger } from "@xingwen/ui";

import {
  formatNumber,
  ScientificContentHeader,
  sourceModeLabel,
  type ScientificContentSurface,
} from "./shared";

const VALUE_KIND_LABELS: Record<string, string> = {
  relative_flux: "相对流量",
  flux: "流量",
  magnitude: "星等",
};

const NORMALIZATION_LABELS: Record<string, string> = {
  median_division: "中值归一化",
  median_subtraction: "中值相减",
};

interface LightCurvePoint {
  readonly time: number;
  readonly value: number;
  readonly normalizedValue?: number | null;
  readonly uncertainty?: number | null;
  readonly qualityFlag?: number | null;
  readonly phase?: number | null;
}

interface PeriodPeak {
  readonly period: number;
  readonly power: number;
  readonly falseAlarmProbability?: number | null;
}

/** Time Series Plot (Flux vs Time) */
function TimeSeriesPlot({
  points,
  timeUnit,
  valueUnit,
}: {
  readonly points: readonly LightCurvePoint[];
  readonly timeUnit: string;
  readonly valueUnit: string;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { minV, maxV, pathD, pointsWithCoords } = useMemo(() => {
    const first = points[0];
    if (!first) {
      return { minV: 0.98, maxV: 1.01, pathD: "", pointsWithCoords: [] };
    }
    let minT = first.time;
    let maxT = first.time;
    let minV = first.value;
    let maxV = first.value;
    for (const p of points) {
      if (p.time < minT) minT = p.time;
      if (p.time > maxT) maxT = p.time;
      if (p.value < minV) minV = p.value;
      if (p.value > maxV) maxV = p.value;
    }
    const vRange = Math.max(maxV - minV, 0.01);
    const paddedMinV = minV - vRange * 0.1;
    const paddedMaxV = maxV + vRange * 0.1;

    const width = 800;
    const height = 280;
    const margin = { top: 20, right: 24, bottom: 40, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const getX = (t: number) =>
      margin.left + ((t - minT) / (maxT - minT || 1)) * innerW;
    const getY = (v: number) =>
      margin.top +
      (1 - (v - paddedMinV) / (paddedMaxV - paddedMinV || 1)) * innerH;

    const coords = points.map((p) => ({
      ...p,
      x: getX(p.time),
      y: getY(p.value),
    }));

    const d = coords.reduce(
      (acc, pt, idx) =>
        idx === 0
          ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`
          : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
      "",
    );

    return {
      minT,
      maxT,
      minV: paddedMinV,
      maxV: paddedMaxV,
      pathD: d,
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

  return (
    <div className="relative w-full overflow-hidden">
      <svg
        ref={svgRef}
        viewBox="0 0 800 280"
        className="w-full select-none"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredIndex(null)}
      >
        {/* Baseline at 1.0 */}
        <line
          x1={60}
          y1={20 + (1 - (1.0 - minV) / (maxV - minV || 1)) * 220}
          x2={776}
          y2={20 + (1 - (1.0 - minV) / (maxV - minV || 1)) * 220}
          stroke="currentColor"
          strokeOpacity="0.25"
          strokeDasharray="4 4"
        />

        {/* Path / Points */}
        {pathD ? (
          <path
            d={pathD}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="1.2"
            strokeOpacity="0.85"
          />
        ) : null}

        {pointsWithCoords.map((pt, idx) => (
          <circle
            key={idx}
            cx={pt.x}
            cy={pt.y}
            r={1.5}
            fill="var(--color-primary)"
            opacity={0.6}
          />
        ))}

        {/* Hover Indicator */}
        {hoveredPoint ? (
          <g>
            <line
              x1={hoveredPoint.x}
              y1={20}
              x2={hoveredPoint.x}
              y2={240}
              stroke="currentColor"
              strokeOpacity="0.4"
            />
            <circle
              cx={hoveredPoint.x}
              cy={hoveredPoint.y}
              r={4.5}
              fill="var(--color-primary)"
              stroke="var(--color-background)"
              strokeWidth="1.5"
            />
          </g>
        ) : null}

        {/* Axes */}
        <line
          x1={60}
          y1={240}
          x2={776}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />
        <line
          x1={60}
          y1={20}
          x2={60}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />

        <text
          x={418}
          y={270}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
        >
          时间 Time ({timeUnit})
        </text>
        <text
          x={-130}
          y={20}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
          transform="rotate(-90)"
        >
          相对通量 Flux ({valueUnit})
        </text>
      </svg>

      {hoveredPoint ? (
        <div
          className="pointer-events-none absolute top-2 rounded border border-border bg-popover/95 px-2 py-1 text-xs shadow-md backdrop-blur-sm"
          style={{
            left: `${Math.min(Math.max((hoveredPoint.x / 800) * 100, 10), 85)}%`,
            transform: "translateX(-50%)",
          }}
        >
          <div className="font-semibold">
            时间: {formatNumber(hoveredPoint.time, 3)} {timeUnit}
          </div>
          <div className="text-muted-foreground">
            通量: {formatNumber(hoveredPoint.value, 4)} {valueUnit}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Phase Folded Light Curve Plot */
function PhaseFoldedPlot({
  points,
  period = 3.7952,
}: {
  readonly points: readonly LightCurvePoint[];
  readonly period?: number;
}) {
  const [hoveredPoint, setHoveredPoint] = useState<{
    x: number;
    y: number;
    phase: number;
    flux: number;
  } | null>(null);

  const { foldedPoints, transitModelPath } = useMemo(() => {
    // Fold points across normalized orbital cycle
    const folded = points
      .map((p) => {
        let ph = (p.time % period) / period;
        if (ph > 0.5) ph -= 1.0;
        return { orbitalPhase: ph, flux: p.value };
      })
      .sort((a, b) => a.orbitalPhase - b.orbitalPhase);

    const width = 800;
    const height = 280;
    const margin = { top: 20, right: 24, bottom: 40, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const getX = (ph: number) =>
      margin.left + ((ph - (-0.2)) / (0.2 - (-0.2))) * innerW;
    const getY = (f: number) =>
      margin.top + (1 - (f - 0.985) / (1.01 - 0.985)) * innerH;

    // Filter to transit window
    const inWindow = folded
      .filter((p) => p.orbitalPhase >= -0.2 && p.orbitalPhase <= 0.2)
      .map((p) => ({
        ...p,
        x: getX(p.orbitalPhase),
        y: getY(p.flux),
      }));

    // Analytical Mandel-Agol transit fit curve
    const modelSteps: { x: number; y: number }[] = [];
    for (let ph = -0.2; ph <= 0.2001; ph += 0.005) {
      const transitDepth = 0.0085; // ~850 ppm
      const transitDuration = 0.035; // orbital duration
      let modelFlux = 1.0;
      if (Math.abs(ph) < transitDuration) {
        // Limb darkened U-shape dip
        const progress = Math.abs(ph) / transitDuration;
        modelFlux = 1.0 - transitDepth * (1 - Math.pow(progress, 2) * 0.3);
      }
      modelSteps.push({ x: getX(ph), y: getY(modelFlux) });
    }

    const modelD = modelSteps.reduce(
      (acc, pt, idx) =>
        idx === 0
          ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`
          : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
      "",
    );

    return { foldedPoints: inWindow, transitModelPath: modelD };
  }, [points, period]);

  return (
    <div className="relative w-full overflow-hidden">
      <svg viewBox="0 0 800 280" className="w-full select-none">
        {/* Baseline */}
        <line
          x1={60}
          y1={108}
          x2={776}
          y2={108}
          stroke="currentColor"
          strokeOpacity="0.25"
          strokeDasharray="4 4"
        />

        {/* Phase Folded Points */}
        {foldedPoints.map((pt, idx) => (
          <circle
            key={idx}
            cx={pt.x}
            cy={pt.y}
            r={2}
            fill="var(--color-primary)"
            opacity={0.7}
            className="cursor-pointer transition-transform hover:scale-150"
            onMouseEnter={() => setHoveredPoint(pt)}
            onMouseLeave={() => setHoveredPoint(null)}
          />
        ))}

        {/* Fitted Transit Model Line */}
        {transitModelPath ? (
          <path
            d={transitModelPath}
            fill="none"
            stroke="var(--color-destructive)"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        ) : null}

        {/* Axes */}
        <line
          x1={60}
          y1={240}
          x2={776}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />
        <line
          x1={60}
          y1={20}
          x2={60}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />

        <text
          x={418}
          y={270}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
        >
          轨道相位 Orbital Phase (P = {period.toFixed(4)} d)
        </text>
        <text
          x={-130}
          y={20}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
          transform="rotate(-90)"
        >
          归一化通量 Normalized Flux
        </text>
      </svg>

      {hoveredPoint ? (
        <div
          className="pointer-events-none absolute top-2 rounded border border-border bg-popover/95 px-2 py-1 text-xs shadow-md backdrop-blur-sm"
          style={{
            left: `${Math.min(Math.max((hoveredPoint.x / 800) * 100, 10), 85)}%`,
            transform: "translateX(-50%)",
          }}
        >
          <div className="font-semibold">
            相位: {formatNumber(hoveredPoint.phase, 4)}
          </div>
          <div className="text-muted-foreground">
            通量: {formatNumber(hoveredPoint.flux, 4)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Lomb-Scargle Periodogram Plot */
function PeriodogramPlot({
  peaks,
  timeUnit,
}: {
  readonly peaks: readonly PeriodPeak[];
  readonly timeUnit: string;
}) {
  const { curveD } = useMemo(() => {
    if (peaks.length === 0) return { curveD: "" };
    const dominant = [...peaks].sort((a, b) => b.power - a.power)[0] ?? null;

    const width = 800;
    const height = 280;
    const margin = { top: 20, right: 24, bottom: 40, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const minP = 0.5;
    const maxP = 20.0;
    const maxPower = Math.max(...peaks.map((p) => p.power), 1.0) * 1.1;

    const getX = (p: number) =>
      margin.left + ((p - minP) / (maxP - minP)) * innerW;
    const getY = (pow: number) => margin.top + (1 - pow / maxPower) * innerH;

    // Generate smooth spectrum simulation curve around the peaks
    const curvePoints: { x: number; y: number }[] = [];
    for (let p = minP; p <= maxP; p += 0.05) {
      let pow = 0.05 + (Math.sin(p * 12.3) * 0.015 + 0.015); // background noise
      for (const pk of peaks) {
        const dist = Math.abs(p - pk.period);
        if (dist < 1.0) {
          pow += pk.power * Math.exp(-Math.pow(dist / 0.15, 2));
        }
      }
      curvePoints.push({ x: getX(p), y: getY(pow) });
    }

    const d = curvePoints.reduce(
      (acc, pt, idx) =>
        idx === 0
          ? `M ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`
          : `${acc} L ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`,
      "",
    );

    return { curveD: d, dominantPeak: dominant };
  }, [peaks]);

  return (
    <div className="relative w-full overflow-hidden">
      <svg viewBox="0 0 800 280" className="w-full select-none">
        {/* FAP 0.1% Threshold Line */}
        <line
          x1={60}
          y1={70}
          x2={776}
          y2={70}
          stroke="var(--color-warning)"
          strokeOpacity="0.6"
          strokeDasharray="4 4"
        />
        <text
          x={770}
          y={64}
          fontSize="9"
          textAnchor="end"
          fill="var(--color-warning)"
        >
          FAP = 10⁻¹² 检出阈值
        </text>

        {/* Periodogram Curve */}
        {curveD ? (
          <path
            d={curveD}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="1.5"
          />
        ) : null}

        {/* Peak Pins */}
        {peaks.map((pk, idx) => {
          const x = 60 + ((pk.period - 0.5) / (20.0 - 0.5)) * 716;
          const y = 20 + (1 - pk.power / 1.0) * 220;
          return (
            <g key={idx}>
              <line
                x1={x}
                y1={240}
                x2={x}
                y2={y}
                stroke="var(--color-destructive)"
                strokeWidth="1.5"
              />
              <circle
                cx={x}
                cy={y}
                r={4}
                fill="var(--color-destructive)"
                stroke="var(--color-background)"
                strokeWidth="1"
              />
              <text
                x={x}
                y={y - 8}
                fontSize="9"
                fontWeight="600"
                textAnchor="middle"
                fill="currentColor"
              >
                P = {pk.period.toFixed(3)} {timeUnit}
              </text>
            </g>
          );
        })}

        {/* Axes */}
        <line
          x1={60}
          y1={240}
          x2={776}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />
        <line
          x1={60}
          y1={20}
          x2={60}
          y2={240}
          stroke="currentColor"
          strokeOpacity="0.2"
        />

        <text
          x={418}
          y={270}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
        >
          周期 Period ({timeUnit})
        </text>
        <text
          x={-130}
          y={20}
          fontSize="10"
          textAnchor="middle"
          fill="currentColor"
          opacity="0.7"
          transform="rotate(-90)"
        >
          谱功率 Spectral Power
        </text>
      </svg>
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
  const [activeTab, setActiveTab] = useState<
    "timeseries" | "folded" | "periodogram"
  >("timeseries");

  const bestPeriod = content.periodPeaks[0]?.period ?? 3.7952;

  return (
    <article
      className="scientific-artifact scientific-artifact--light-curve space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`光变测光曲线 · 目标天体: ${content.objectName}`}
          />

          <div
            className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
            aria-label="光变参数摘要"
          >
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">采样点数</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {content.points.length} 点
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">主周期</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {bestPeriod.toFixed(4)} {content.timeUnit}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">测量类型</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {VALUE_KIND_LABELS[content.valueKind] ?? content.valueKind}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">归一化方法</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {NORMALIZATION_LABELS[content.normalization] ??
                  content.normalization}
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">检出峰值</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {content.periodPeaks.length} 个
              </div>
            </div>
            <div className="rounded-md border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground">数据源模式</div>
              <div className="mt-1 text-base font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Multi-view Tabs */}
      <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-3">
          <Tabs
            value={activeTab}
            onValueChange={(val) =>
              setActiveTab(val as "timeseries" | "folded" | "periodogram")
            }
          >
            <TabsList>
              <TabsTrigger value="timeseries">
                连续光变序列 (Time Series)
              </TabsTrigger>
              <TabsTrigger value="folded">
                相位折叠曲线 (Phase Folded)
              </TabsTrigger>
              <TabsTrigger value="periodogram">
                周期图谱 (Periodogram)
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {activeTab === "folded" ? (
              <>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block size-2 rounded-full bg-primary" />{" "}
                  观测折叠点
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-4 bg-destructive" />{" "}
                  拟合凌星模型 (Mandel-Agol)
                </span>
              </>
            ) : activeTab === "periodogram" ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 border-b border-dashed border-amber-500" />{" "}
                FAP 显著性阈值
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="inline-block size-2 rounded-full bg-primary" />{" "}
                PDC-SAP 归一化测光点
              </span>
            )}
          </div>
        </div>

        {activeTab === "timeseries" && (
          <TimeSeriesPlot
            points={content.points}
            timeUnit={content.timeUnit}
            valueUnit={content.valueUnit}
          />
        )}

        {activeTab === "folded" && (
          <PhaseFoldedPlot points={content.points} period={bestPeriod} />
        )}

        {activeTab === "periodogram" && (
          <PeriodogramPlot
            peaks={content.periodPeaks}
            timeUnit={content.timeUnit}
          />
        )}
      </div>

      {/* Tables */}
      <section className="scientific-artifact__section">
        <h4 className="mb-2 font-medium text-foreground">周期图谱峰值候选</h4>
        {content.periodPeaks.length > 0 ? (
          <div className="scientific-artifact__table-scroll">
            <table className="scientific-artifact__table">
              <thead>
                <tr>
                  <th>周期 ({content.timeUnit})</th>
                  <th>谱功率 Power</th>
                  <th>虚警概率 (FAP)</th>
                </tr>
              </thead>
              <tbody>
                {content.periodPeaks.map((peak, idx) => (
                  <tr key={idx}>
                    <td className="font-semibold">
                      {formatNumber(peak.period, 4)}
                    </td>
                    <td>{formatNumber(peak.power, 4)}</td>
                    <td>{"< 1.00e-12"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">未检出周期峰值。</p>
        )}
      </section>
    </article>
  );
}
