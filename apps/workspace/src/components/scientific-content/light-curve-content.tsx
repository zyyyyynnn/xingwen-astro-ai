import { useMemo, useState, useRef, type MouseEvent } from "react";
import type { LightCurveArtifactReviewContent } from "@xingwen/domain";
import { ChevronRight } from "@xingwen/ui/icons";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";

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
}: {
  readonly points: readonly LightCurvePoint[];
}) {
  const [hoveredPoint, setHoveredPoint] = useState<{
    x: number;
    y: number;
    phase: number;
    flux: number;
  } | null>(null);

  // The artifact carries the authoritative orbital phase per point; the plot
  // only projects existing values, it never re-derives or fits them.
  const { foldedPoints } = useMemo(() => {
    const withPhase = points
      .filter((p) => typeof p.phase === "number")
      .map((p) => ({
        orbitalPhase: p.phase as number,
        flux: p.normalizedValue ?? p.value,
      }))
      .sort((a, b) => a.orbitalPhase - b.orbitalPhase);

    const width = 800;
    const height = 280;
    const margin = { top: 20, right: 24, bottom: 40, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const minPhase = -0.5;
    const maxPhase = 0.5;
    const fMin =
      withPhase.length > 0 ? Math.min(...withPhase.map((p) => p.flux)) : 0;
    const fMax =
      withPhase.length > 0 ? Math.max(...withPhase.map((p) => p.flux)) : 1;
    const fPad = (fMax - fMin) * 0.08 || 0.01;
    const lo = fMin - fPad;
    const hi = fMax + fPad;

    const getX = (ph: number) =>
      margin.left + ((ph - minPhase) / (maxPhase - minPhase)) * innerW;
    const getY = (f: number) =>
      margin.top + (1 - (f - lo) / (hi - lo)) * innerH;

    const projected = withPhase.map((p) => ({
      ...p,
      x: getX(p.orbitalPhase),
      y: getY(p.flux),
    }));

    return { foldedPoints: projected };
  }, [points]);

  return (
    <div className="relative w-full overflow-hidden">
      <svg viewBox="0 0 800 280" className="w-full select-none">
        {/* Phase Folded Points — authoritative per-point phase */}
        {foldedPoints.map((pt, idx) => (
          <circle
            key={idx}
            cx={pt.x}
            cy={pt.y}
            r={2}
            fill="var(--color-primary)"
            opacity={0.7}
            className="cursor-pointer transition-transform hover:scale-150"
            onMouseEnter={() =>
              setHoveredPoint({
                x: pt.x,
                y: pt.y,
                phase: pt.orbitalPhase,
                flux: pt.flux,
              })
            }
            onMouseLeave={() => setHoveredPoint(null)}
          />
        ))}

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
          轨道相位 Orbital Phase
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

/** Periodogram Peak Plot — authoritative peaks only, no simulated spectrum */
function PeriodogramPlot({
  peaks,
  timeUnit,
  falseAlarmProbability,
}: {
  readonly peaks: readonly PeriodPeak[];
  readonly timeUnit: string;
  readonly falseAlarmProbability: number | null;
}) {
  const { projected, maxPower } = useMemo(() => {
    if (peaks.length === 0) {
      return { projected: [], minP: 0, maxP: 1, maxPower: 1 };
    }

    const width = 800;
    const height = 280;
    const margin = { top: 20, right: 24, bottom: 40, left: 60 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const lo = Math.min(...peaks.map((p) => p.period));
    const hi = Math.max(...peaks.map((p) => p.period));
    const span = hi - lo || 1;
    const pad = span * 0.15;
    const pMin = Math.max(0, lo - pad);
    const pMax = hi + pad;
    const powerMax = Math.max(...peaks.map((p) => p.power)) * 1.15 || 1;

    const getX = (p: number) =>
      margin.left + ((p - pMin) / (pMax - pMin)) * innerW;
    const getY = (pow: number) => margin.top + (1 - pow / powerMax) * innerH;

    return {
      projected: peaks.map((pk) => ({
        ...pk,
        x: getX(pk.period),
        y: getY(pk.power),
      })),
      maxPower: powerMax,
    };
  }, [peaks]);

  const fapY =
    falseAlarmProbability !== null && maxPower > 0
      ? 20 + (1 - falseAlarmProbability / maxPower) * 220
      : null;

  return (
    <div className="relative w-full overflow-hidden">
      <svg viewBox="0 0 800 280" className="w-full select-none">
        {/* Authoritative FAP threshold, only when the artifact states one */}
        {fapY !== null ? (
          <>
            <line
              x1={60}
              y1={fapY}
              x2={776}
              y2={fapY}
              stroke="var(--color-warning)"
              strokeOpacity="0.6"
              strokeDasharray="4 4"
            />
            <text
              x={770}
              y={fapY - 5}
              fontSize="9"
              textAnchor="end"
              fill="var(--color-warning)"
            >
              FAP 检出阈值
            </text>
          </>
        ) : null}

        {/* Peak Pins — the artifact's periodogram output */}
        {projected.map((pk, idx) => (
          <g key={idx}>
            <line
              x1={pk.x}
              y1={240}
              x2={pk.x}
              y2={pk.y}
              stroke="var(--color-destructive)"
              strokeWidth="1.5"
            />
            <circle
              cx={pk.x}
              cy={pk.y}
              r={4}
              fill="var(--color-destructive)"
              stroke="var(--color-background)"
              strokeWidth="1"
            />
            <text
              x={pk.x}
              y={pk.y - 8}
              fontSize="9"
              fontWeight="600"
              textAnchor="middle"
              fill="currentColor"
            >
              P = {pk.period.toFixed(3)} {timeUnit}
            </text>
          </g>
        ))}

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

  const bestPeriod = content.bestPeriod;

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

          <dl
            className="flex flex-wrap items-baseline gap-x-6 gap-y-1 border-b border-border/70 pb-3 text-sm"
            aria-label="光变测量摘要"
          >
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">采样</dt>
              <dd className="font-semibold tabular-nums text-foreground">
                {content.sampleCount}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">已接受</dt>
              <dd className="font-semibold tabular-nums text-foreground">
                {content.acceptedSampleCount}
              </dd>
            </div>
            {content.rejectedSampleCount > 0 ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-muted-foreground">已剔除</dt>
                <dd className="font-semibold tabular-nums text-foreground">
                  {content.rejectedSampleCount}
                </dd>
              </div>
            ) : null}
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">主周期</dt>
              <dd className="font-semibold tabular-nums text-foreground">
                {bestPeriod.toFixed(4)} {content.timeUnit}
              </dd>
            </div>
            {content.falseAlarmProbability !== null ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs text-muted-foreground">FAP</dt>
                <dd className="font-semibold tabular-nums text-foreground">
                  {formatNumber(content.falseAlarmProbability, 6)}
                </dd>
              </div>
            ) : null}
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">中位采样间隔</dt>
              <dd className="font-semibold tabular-nums text-foreground">
                {formatNumber(content.medianCadence, 2)} {content.timeUnit}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">测量</dt>
              <dd className="font-semibold text-foreground">
                {VALUE_KIND_LABELS[content.valueKind] ?? content.valueKind}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs text-muted-foreground">数据等级</dt>
              <dd className="font-semibold text-foreground">
                {sourceModeLabel(sourceMode)}
              </dd>
            </div>
          </dl>
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
              <span className="flex items-center gap-1.5">
                <span className="inline-block size-2 rounded-full bg-primary" />{" "}
                观测折叠点（按结果记录的轨道相位）
              </span>
            ) : activeTab === "periodogram" ? (
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-4 border-b border-dashed border-[var(--color-warning)]" />{" "}
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

        {activeTab === "folded" && <PhaseFoldedPlot points={content.points} />}

        {activeTab === "periodogram" && (
          <PeriodogramPlot
            peaks={content.periodPeaks}
            timeUnit={content.timeUnit}
            falseAlarmProbability={content.falseAlarmProbability}
          />
        )}
      </div>

      {/* Tables — secondary detail, collapsed by default (spec §48) */}
      <Collapsible defaultOpen={false}>
        <CollapsibleTrigger className="group flex w-full items-center gap-1.5 py-2 text-sm text-muted-foreground hover:text-foreground">
          <ChevronRight
            className="size-3.5 transition-transform group-data-[state=open]:rotate-90"
            aria-hidden="true"
          />
          <span className="font-medium">
            周期图谱峰值候选（{content.periodPeaks.length} 个）
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {content.periodPeaks.length > 0 ? (
            <div className="scientific-artifact__table-scroll mt-1">
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
                      <td>
                        {content.falseAlarmProbability === null
                          ? "—"
                          : formatNumber(content.falseAlarmProbability, 6)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="py-2 text-sm text-muted-foreground">
              未检出周期峰值。
            </p>
          )}
        </CollapsibleContent>
      </Collapsible>
    </article>
  );
}
