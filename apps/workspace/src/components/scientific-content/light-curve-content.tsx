import {
  useId,
  useMemo,
  useState,
  useRef,
  type MouseEvent,
  type KeyboardEvent,
} from "react";
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
  relative_flux: "相对通量",
  flux: "通量",
  magnitude: "星等",
};

type LightCurvePoint = LightCurveArtifactReviewContent["points"][number];

interface PeriodPeak {
  readonly period: number;
  readonly power: number;
}

const PLOT = {
  width: 800,
  height: 300,
  left: 100,
  right: 752,
  top: 20,
  bottom: 240,
};

function formatProbability(value: number): string {
  return Math.abs(value) < 0.001 && value !== 0
    ? value.toExponential(2)
    : formatNumber(value, 6);
}

function formatCadence(value: number, timeUnit: string): string {
  if (["d", "day", "days"].includes(timeUnit.toLowerCase()) && value < 1) {
    return `${formatNumber(value * 24 * 60, 2)} min`;
  }
  return `${formatNumber(value, 2)} ${timeUnit}`;
}

function axisNumber(value: number, span: number): string {
  if (value === 0) return "0";
  const decimals = Math.max(0, Math.ceil(-Math.log10(Math.abs(span) / 4)) + 1);
  return Math.abs(value) < 0.0001
    ? value.toExponential(2)
    : value.toFixed(Math.min(decimals, 6));
}

/** Shared coordinates match all three light-curve projections. */
function PlotTicks({
  xMin,
  xMax,
  yMin,
  yMax,
}: {
  readonly xMin: number;
  readonly xMax: number;
  readonly yMin: number;
  readonly yMax: number;
}) {
  return (
    <g className="scientific-plot__ticks">
      {Array.from({ length: 5 }, (_, index) => {
        const fraction = index / 4;
        const x = PLOT.left + fraction * (PLOT.right - PLOT.left);
        const y = PLOT.bottom - fraction * (PLOT.bottom - PLOT.top);
        return (
          <g key={index}>
            <line
              x1={PLOT.left}
              x2={PLOT.right}
              y1={y}
              y2={y}
              className="scientific-plot__grid-line"
            />
            <text
              x={PLOT.left - 8}
              y={y}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {axisNumber(yMin + fraction * (yMax - yMin), yMax - yMin)}
            </text>
            <text x={x} y={PLOT.bottom + 14} textAnchor="middle">
              {axisNumber(xMin + fraction * (xMax - xMin), xMax - xMin)}
            </text>
          </g>
        );
      })}
    </g>
  );
}

function PlotAxes({
  xLabel,
  yLabel,
}: {
  readonly xLabel: string;
  readonly yLabel: string;
}) {
  return (
    <g>
      <path
        d={`M ${PLOT.left} ${PLOT.top} V ${PLOT.bottom} H ${PLOT.right}`}
        fill="none"
        stroke="var(--color-border)"
      />
      <text
        x={(PLOT.left + PLOT.right) / 2}
        y={PLOT.height - 10}
        className="scientific-plot__axis-label"
        textAnchor="middle"
        fill="currentColor"
      >
        {xLabel}
      </text>
      <text
        x={-(PLOT.top + PLOT.bottom) / 2}
        y={20}
        className="scientific-plot__axis-label"
        textAnchor="middle"
        fill="currentColor"
        transform="rotate(-90)"
      >
        {yLabel}
      </text>
    </g>
  );
}

function navigatePoint(
  event: KeyboardEvent<SVGSVGElement>,
  index: number | null,
  count: number,
  select: (index: number) => void,
) {
  if (count === 0) return;
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? count - 1
        : event.key === "ArrowRight"
          ? Math.min((index ?? -1) + 1, count - 1)
          : event.key === "ArrowLeft"
            ? Math.max((index ?? 1) - 1, 0)
            : null;
  if (next !== null) {
    event.preventDefault();
    select(next);
  }
}

/** Time Series Plot (Flux vs Time) */
function TimeSeriesPlot({
  points,
  timeUnit,
  valueUnit,
  valueKind,
}: {
  readonly points: readonly LightCurvePoint[];
  readonly timeUnit: string;
  readonly valueUnit: string;
  readonly valueKind: string;
}) {
  const plotId = useId();
  const valueLabel = VALUE_KIND_LABELS[valueKind] ?? "测量值";
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const { minT, maxT, minV, maxV, pathD, pointsWithCoords } = useMemo(() => {
    const first = points[0];
    if (!first) {
      return {
        minT: 0,
        maxT: 1,
        minV: 0,
        maxV: 1,
        pathD: "",
        pointsWithCoords: [],
      };
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
    const vRange = maxV - minV || Math.abs(minV) * 0.01 || 1;
    const paddedMinV = minV - vRange * 0.1;
    const paddedMaxV = maxV + vRange * 0.1;

    const innerW = PLOT.right - PLOT.left;
    const innerH = PLOT.bottom - PLOT.top;

    const getX = (t: number) =>
      PLOT.left + ((t - minT) / (maxT - minT || 1)) * innerW;
    const getY = (v: number) =>
      PLOT.top +
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
    const scaleX = PLOT.width / svgWidth;
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

  if (pointsWithCoords.length === 0)
    return (
      <p className="scientific-artifact__empty">当前结果没有可显示的测量点。</p>
    );

  return (
    <div className="relative w-full overflow-hidden">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${PLOT.width} ${PLOT.height}`}
        className="w-full select-none"
        role="img"
        tabIndex={0}
        aria-labelledby={`${plotId}-title ${plotId}-description`}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoveredIndex(null)}
        onFocus={() => setHoveredIndex(0)}
        onBlur={() => setHoveredIndex(null)}
        onKeyDown={(event) =>
          navigatePoint(
            event,
            hoveredIndex,
            pointsWithCoords.length,
            setHoveredIndex,
          )
        }
      >
        <title id={`${plotId}-title`}>光变时间序列</title>
        <desc id={`${plotId}-description`}>
          横轴为时间（{timeUnit}），纵轴为{valueLabel}（{valueUnit}），包含{" "}
          {points.length} 个测量点。聚焦后可用左右方向键逐点检查，Home 和 End
          跳至首尾。
        </desc>
        <PlotTicks xMin={minT} xMax={maxT} yMin={minV} yMax={maxV} />
        {valueKind === "relative_flux" && minV <= 1 && maxV >= 1 ? (
          <line
            x1={PLOT.left}
            y1={
              PLOT.top +
              (1 - (1.0 - minV) / (maxV - minV || 1)) * (PLOT.bottom - PLOT.top)
            }
            x2={PLOT.right}
            y2={
              PLOT.top +
              (1 - (1.0 - minV) / (maxV - minV || 1)) * (PLOT.bottom - PLOT.top)
            }
            stroke="currentColor"
            strokeOpacity="0.25"
            strokeDasharray="4 4"
          />
        ) : null}

        {/* Path / Points */}
        {pathD ? (
          <path
            d={pathD}
            fill="none"
            stroke="var(--color-brand)"
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
            fill="var(--color-brand)"
            opacity={0.6}
          />
        ))}

        {/* Hover Indicator */}
        {hoveredPoint ? (
          <g>
            <line
              x1={hoveredPoint.x}
              y1={PLOT.top}
              x2={hoveredPoint.x}
              y2={PLOT.bottom}
              stroke="currentColor"
              strokeOpacity="0.4"
            />
            <circle
              cx={hoveredPoint.x}
              cy={hoveredPoint.y}
              r={4.5}
              fill="var(--color-brand)"
              stroke="var(--color-surface)"
              strokeWidth="1.5"
            />
          </g>
        ) : null}

        <PlotAxes
          xLabel={`时间 Time (${timeUnit})`}
          yLabel={`${valueLabel} (${valueUnit})`}
        />
      </svg>

      {hoveredPoint ? (
        <div
          className="scientific-plot__tooltip"
          role="status"
          style={{
            left: `${Math.min(Math.max((hoveredPoint.x / PLOT.width) * 100, 10), 85)}%`,
            transform: "translateX(-50%)",
          }}
        >
          <div className="scientific-plot__tooltip-title">
            时间: {formatNumber(hoveredPoint.time, 3)} {timeUnit}
          </div>
          <div>
            {valueLabel}: {formatNumber(hoveredPoint.value, 4)} {valueUnit}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Phase Folded Light Curve Plot */
function PhaseFoldedPlot({
  points,
  valueLabel,
}: {
  readonly points: readonly LightCurvePoint[];
  readonly valueLabel: string;
}) {
  const plotId = useId();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // The artifact carries the authoritative orbital phase per point; the plot
  // only projects existing values, it never re-derives or fits them.
  const { foldedPoints, minPhase, maxPhase, lo, hi } = useMemo(() => {
    const withPhase = points
      .map((p) => ({
        orbitalPhase: p.phase,
        flux: p.normalizedValue,
      }))
      .sort((a, b) => a.orbitalPhase - b.orbitalPhase);

    const innerW = PLOT.right - PLOT.left;
    const innerH = PLOT.bottom - PLOT.top;

    const minPhase = Math.min(-0.5, ...withPhase.map((p) => p.orbitalPhase));
    const maxPhase = Math.max(0.5, ...withPhase.map((p) => p.orbitalPhase));
    const fMin =
      withPhase.length > 0 ? Math.min(...withPhase.map((p) => p.flux)) : 0;
    const fMax =
      withPhase.length > 0 ? Math.max(...withPhase.map((p) => p.flux)) : 1;
    const fPad = (fMax - fMin) * 0.08 || 0.01;
    const lo = fMin - fPad;
    const hi = fMax + fPad;

    const getX = (ph: number) =>
      PLOT.left + ((ph - minPhase) / (maxPhase - minPhase)) * innerW;
    const getY = (f: number) => PLOT.top + (1 - (f - lo) / (hi - lo)) * innerH;

    const projected = withPhase.map((p) => ({
      ...p,
      x: getX(p.orbitalPhase),
      y: getY(p.flux),
    }));

    return { foldedPoints: projected, minPhase, maxPhase, lo, hi };
  }, [points]);

  const hoveredPoint =
    hoveredIndex === null ? null : foldedPoints[hoveredIndex];
  if (foldedPoints.length === 0)
    return (
      <p className="scientific-artifact__empty">
        当前结果没有记录轨道相位，无法显示相位折叠图。
      </p>
    );

  return (
    <div className="relative w-full overflow-hidden">
      <svg
        viewBox={`0 0 ${PLOT.width} ${PLOT.height}`}
        className="w-full select-none"
        role="img"
        tabIndex={0}
        onFocus={() => setHoveredIndex(0)}
        onBlur={() => setHoveredIndex(null)}
        onKeyDown={(event) =>
          navigatePoint(
            event,
            hoveredIndex,
            foldedPoints.length,
            setHoveredIndex,
          )
        }
        aria-labelledby={`${plotId}-title ${plotId}-description`}
      >
        <title id={`${plotId}-title`}>光变相位折叠图</title>
        <desc id={`${plotId}-description`}>
          横轴为结果记录的轨道相位，纵轴为{valueLabel}，包含{" "}
          {foldedPoints.length}{" "}
          个带相位的测量点。聚焦后可用左右方向键逐点检查，Home 和 End 跳至首尾。
        </desc>
        <PlotTicks xMin={minPhase} xMax={maxPhase} yMin={lo} yMax={hi} />
        {/* Phase Folded Points — authoritative per-point phase */}
        {foldedPoints.map((pt, idx) => (
          <circle
            key={idx}
            cx={pt.x}
            cy={pt.y}
            r={2}
            fill="var(--color-brand)"
            opacity={0.7}
            onMouseEnter={() => setHoveredIndex(idx)}
            onMouseLeave={() => setHoveredIndex(null)}
          />
        ))}

        <PlotAxes xLabel="轨道相位 Orbital Phase" yLabel={valueLabel} />
      </svg>

      {hoveredPoint ? (
        <div
          className="scientific-plot__tooltip"
          role="status"
          style={{
            left: `${Math.min(Math.max((hoveredPoint.x / PLOT.width) * 100, 10), 85)}%`,
            transform: "translateX(-50%)",
          }}
        >
          <div className="scientific-plot__tooltip-title">
            相位: {formatNumber(hoveredPoint.orbitalPhase, 4)}
          </div>
          <div>
            {valueLabel}: {formatNumber(hoveredPoint.flux, 4)}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PeriodogramPlot({
  peaks,
  timeUnit,
  fixtureMode,
}: {
  readonly peaks: readonly PeriodPeak[];
  readonly timeUnit: string;
  readonly fixtureMode: boolean;
}) {
  const plotId = useId();
  const { projected, pMin, pMax, powerMax } = useMemo(() => {
    if (peaks.length === 0) {
      return { projected: [], pMin: 0, pMax: 1, powerMax: 1 };
    }

    const innerW = PLOT.right - PLOT.left;
    const innerH = PLOT.bottom - PLOT.top;

    const lo = Math.min(...peaks.map((p) => p.period));
    const hi = Math.max(...peaks.map((p) => p.period));
    const span = hi - lo || 1;
    const pad = span * 0.15;
    const pMin = Math.max(0, lo - pad);
    const pMax = hi + pad;
    const powerMax = Math.max(...peaks.map((p) => p.power)) * 1.15 || 1;

    const getX = (p: number) =>
      PLOT.left + ((p - pMin) / (pMax - pMin)) * innerW;
    const getY = (pow: number) => PLOT.top + (1 - pow / powerMax) * innerH;

    return {
      pMin,
      pMax,
      powerMax,
      projected: peaks.map((pk) => ({
        ...pk,
        x: getX(pk.period),
        y: getY(pk.power),
      })),
    };
  }, [peaks]);

  if (projected.length === 0)
    return (
      <p className="scientific-artifact__empty">当前结果没有周期峰值记录。</p>
    );

  return (
    <div className="relative w-full overflow-hidden">
      <svg
        viewBox={`0 0 ${PLOT.width} ${PLOT.height}`}
        className="w-full select-none"
        role="img"
        aria-labelledby={`${plotId}-title ${plotId}-description`}
      >
        <title id={`${plotId}-title`}>
          {fixtureMode ? "目录周期标记" : "光变周期峰值"}
        </title>
        <desc id={`${plotId}-description`}>
          横轴为周期（{timeUnit}），纵轴为{fixtureMode ? "展示权重" : "谱功率"}
          ，展示结果中的 {peaks.length} 个峰值记录。
        </desc>
        <PlotTicks xMin={pMin} xMax={pMax} yMin={0} yMax={powerMax} />
        {/* Peak Pins — the artifact's periodogram output */}
        {projected.map((pk, idx) => (
          <g key={idx}>
            <line
              x1={pk.x}
              y1={PLOT.bottom}
              x2={pk.x}
              y2={pk.y}
              stroke="var(--color-brand)"
              strokeWidth="1.5"
            />
            <circle
              cx={pk.x}
              cy={pk.y}
              r={4}
              fill="var(--color-brand)"
              stroke="var(--color-surface)"
              strokeWidth="1"
            />
            <text
              x={pk.x}
              y={pk.y - 8}
              className="scientific-plot__annotation-label"
              textAnchor="middle"
              fill="currentColor"
            >
              P = {pk.period.toFixed(3)} {timeUnit}
            </text>
          </g>
        ))}

        <PlotAxes
          xLabel={`周期 Period (${timeUnit})`}
          yLabel={
            fixtureMode ? "展示权重 Display Weight" : "谱功率 Spectral Power"
          }
        />
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
  const fixtureMode = sourceMode === "fixture";

  return (
    <article
      className="scientific-artifact scientific-artifact--light-curve space-y-6"
      data-surface={surface}
    >
      {!enhancementOnly ? (
        <>
          <ScientificContentHeader
            title={content.title || title}
            subtitle={`${fixtureMode ? "光变交互界面样例" : "光变测光曲线"} · 目标天体: ${content.objectName}`}
          />

          <dl
            className="light-curve-workspace__summary"
            aria-label="光变测量摘要"
          >
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">采样</dt>
              <dd className="font-semibold tabular-nums">
                {content.sampleCount}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">已接受</dt>
              <dd className="font-semibold tabular-nums">
                {content.acceptedSampleCount}
              </dd>
            </div>
            {content.rejectedSampleCount > 0 ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs">已剔除</dt>
                <dd className="font-semibold tabular-nums">
                  {content.rejectedSampleCount}
                </dd>
              </div>
            ) : null}
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">
                {fixtureMode ? "目录参考周期" : "主周期"}
              </dt>
              <dd className="font-semibold tabular-nums">
                {bestPeriod.toFixed(4)} {content.timeUnit}
              </dd>
            </div>
            {content.falseAlarmProbability !== null ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="text-xs">全局 FAP</dt>
                <dd className="font-semibold tabular-nums">
                  {formatProbability(content.falseAlarmProbability)}
                </dd>
              </div>
            ) : null}
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">中位采样间隔</dt>
              <dd className="font-semibold tabular-nums">
                {formatCadence(content.medianCadence, content.timeUnit)}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">测量</dt>
              <dd className="font-semibold">
                {fixtureMode
                  ? "确定性演示相对流量"
                  : (VALUE_KIND_LABELS[content.valueKind] ?? content.valueKind)}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">时间基准</dt>
              <dd className="font-semibold">
                {content.timeScale.toUpperCase()}
                {fixtureMode ? " 坐标约定（演示）" : ""}
              </dd>
            </div>
            <div className="flex items-baseline gap-1.5">
              <dt className="text-xs">数据等级</dt>
              <dd className="font-semibold">{sourceModeLabel(sourceMode)}</dd>
            </div>
          </dl>
        </>
      ) : null}

      {/* Multi-view Tabs */}
      <div className="light-curve-workspace">
        <div className="light-curve-workspace__toolbar">
          <Tabs
            value={activeTab}
            onValueChange={(val) =>
              setActiveTab(val as "timeseries" | "folded" | "periodogram")
            }
          >
            <TabsList variant="line">
              <TabsTrigger value="timeseries">
                {fixtureMode
                  ? "确定性演示序列 (UI Sequence)"
                  : "连续光变序列 (Time Series)"}
              </TabsTrigger>
              <TabsTrigger value="folded">
                {fixtureMode
                  ? "相位展示 (Phase View)"
                  : "相位折叠曲线 (Phase Folded)"}
              </TabsTrigger>
              <TabsTrigger value="periodogram">
                {fixtureMode
                  ? "目录周期标记 (Catalog Periods)"
                  : "周期图谱 (Periodogram)"}
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="scientific-plot__legend">
            {activeTab === "folded" ? (
              <span className="flex items-center gap-1.5">
                <span className="scientific-plot__legend-dot" />{" "}
                {fixtureMode
                  ? "演示序列折叠点（非观测拟合）"
                  : "观测折叠点（按结果记录的轨道相位）"}
              </span>
            ) : activeTab === "periodogram" ? (
              <span className="flex items-center gap-1.5">
                <span className="scientific-plot__legend-dot" />{" "}
                {fixtureMode ? "目录周期标记（非功率谱推断）" : "周期峰值"}
              </span>
            ) : (
              <span className="flex items-center gap-1.5">
                <span className="scientific-plot__legend-dot" />{" "}
                {fixtureMode ? "目录参数驱动的确定性界面序列" : "原始测量点"}
              </span>
            )}
          </div>
        </div>

        <div className="light-curve-workspace__plot">
          {activeTab === "timeseries" && (
            <TimeSeriesPlot
              points={content.points}
              timeUnit={content.timeUnit}
              valueUnit={content.valueUnit}
              valueKind={content.valueKind}
            />
          )}

          {activeTab === "folded" && (
            <PhaseFoldedPlot
              points={content.points}
              valueLabel="归一化测量值"
            />
          )}

          {activeTab === "periodogram" && (
            <PeriodogramPlot
              peaks={content.periodPeaks}
              timeUnit={content.timeUnit}
              fixtureMode={fixtureMode}
            />
          )}
        </div>
      </div>

      {/* Tables — secondary detail, collapsed by default (spec §48) */}
      <Collapsible defaultOpen={false}>
        <CollapsibleTrigger className="group light-curve-workspace__peaks-trigger">
          <ChevronRight
            className="size-[var(--icon-size-sm)] transition-transform group-data-[state=open]:rotate-90"
            aria-hidden="true"
          />
          <span className="font-medium">
            {fixtureMode ? "目录周期记录" : "周期图谱峰值候选"}（
            {content.periodPeaks.length} 个）
          </span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {content.periodPeaks.length > 0 ? (
            <div className="scientific-artifact__table-scroll mt-1">
              <table className="scientific-artifact__table">
                <thead>
                  <tr>
                    <th>周期 ({content.timeUnit})</th>
                    <th>{fixtureMode ? "展示权重" : "谱功率 Power"}</th>
                  </tr>
                </thead>
                <tbody>
                  {content.periodPeaks.map((peak, idx) => (
                    <tr key={idx}>
                      <td className="font-semibold">
                        {formatNumber(peak.period, 4)}
                      </td>
                      <td>{formatNumber(peak.power, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="scientific-artifact__empty">未检出周期峰值。</p>
          )}
        </CollapsibleContent>
      </Collapsible>
    </article>
  );
}
