import type {
  ChartPointReview,
  ChartVisualizationReview,
} from "@xingwen/domain";
import { useId } from "react";

const WIDTH = 360;
const HEIGHT = 220;
const PLOT = { left: 48, right: 344, top: 16, bottom: 180 } as const;

function seriesColor(token: string): string {
  return (
    {
      brand: "var(--color-brand)",
      information: "var(--color-info)",
      success: "var(--color-success)",
      warning: "var(--color-warning)",
      error: "var(--color-error)",
      neutral: "var(--color-ink-secondary)",
    }[token] ?? "var(--color-brand)"
  );
}

function axisValue(
  value: number | string,
  scale: ChartVisualizationReview["xAxis"]["scale"],
  categories: ReadonlyMap<string, number>,
): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (scale === "time") {
    const timestamp = Date.parse(value);
    return Number.isFinite(timestamp) ? timestamp : null;
  }
  if (scale === "category") return categories.get(value) ?? null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function categoryRegistry(values: readonly (number | string)[]) {
  return new Map(
    [
      ...new Set(
        values.filter((item): item is string => typeof item === "string"),
      ),
    ].map((item, index) => [item, index] as const),
  );
}

function extent(values: readonly number[]): readonly [number, number] {
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  if (minimum === maximum) {
    const padding = minimum === 0 ? 1 : Math.abs(minimum) * 0.1;
    return [minimum - padding, maximum + padding];
  }
  return [minimum, maximum];
}

function formatAxisValue(value: number | string): string {
  if (typeof value === "string") return value;
  if (
    Math.abs(value) >= 10000 ||
    (Math.abs(value) > 0 && Math.abs(value) < 0.01)
  ) {
    return value.toExponential(2);
  }
  return Number(value.toFixed(3)).toString();
}

interface PlotPoint extends ChartPointReview {
  readonly px: number;
  readonly py: number;
}

export function ScientificChart({
  spec,
}: {
  readonly spec: ChartVisualizationReview;
}) {
  const reactId = useId();
  const titleId = `scientific-chart-${reactId.replace(/[^a-zA-Z0-9_-]/gu, "")}`;
  const allPoints = spec.series.flatMap((series) => series.points);
  const xCategories = categoryRegistry(allPoints.map((point) => point.x));
  const yCategories = categoryRegistry(allPoints.map((point) => point.y));
  const numeric = allPoints
    .map((point) => ({
      point,
      x: axisValue(point.x, spec.xAxis.scale, xCategories),
      y: axisValue(point.y, spec.yAxis.scale, yCategories),
    }))
    .filter(
      (item): item is { point: ChartPointReview; x: number; y: number } =>
        item.x !== null &&
        item.y !== null &&
        (spec.xAxis.scale !== "log" || item.x > 0) &&
        (spec.yAxis.scale !== "log" || item.y > 0),
    );
  if (numeric.length === 0) {
    return <p className="artifact-view__empty">当前点集没有可绘制的有限值。</p>;
  }
  const transformed = numeric.map((item) => ({
    ...item,
    tx: spec.xAxis.scale === "log" ? Math.log10(item.x) : item.x,
    ty: spec.yAxis.scale === "log" ? Math.log10(item.y) : item.y,
  }));
  const [xMin, xMax] = extent(transformed.map((item) => item.tx));
  const [yMin, yMax] = extent(transformed.map((item) => item.ty));
  const project = (point: (typeof transformed)[number]): PlotPoint => ({
    ...point.point,
    px:
      PLOT.left +
      ((point.tx - xMin) / (xMax - xMin)) * (PLOT.right - PLOT.left),
    py:
      PLOT.bottom -
      ((point.ty - yMin) / (yMax - yMin)) * (PLOT.bottom - PLOT.top),
  });
  const pointsBySeries = new Map(
    spec.series.map((series) => [
      series.seriesId,
      series.points
        .map((sourcePoint) =>
          transformed.find((item) => item.point === sourcePoint),
        )
        .filter(
          (item): item is (typeof transformed)[number] => item !== undefined,
        )
        .map(project),
    ]),
  );

  return (
    <figure className="scientific-chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
      >
        <title id={titleId}>
          {spec.yAxis.label} 随 {spec.xAxis.label} 变化
        </title>
        <line x1={PLOT.left} y1={PLOT.top} x2={PLOT.left} y2={PLOT.bottom} />
        <line
          x1={PLOT.left}
          y1={PLOT.bottom}
          x2={PLOT.right}
          y2={PLOT.bottom}
        />
        {spec.series.map((series) => {
          const points = pointsBySeries.get(series.seriesId) ?? [];
          const color = seriesColor(series.colorToken);
          const path = points
            .map((point) => `${point.px},${point.py}`)
            .join(" ");
          if (series.mark === "bar") {
            return (
              <g key={series.seriesId} style={{ color }}>
                {points.map((point, index) => (
                  <line
                    className="scientific-chart__bar"
                    key={`${point.px}-${index}`}
                    x1={point.px}
                    y1={PLOT.bottom}
                    x2={point.px}
                    y2={point.py}
                  />
                ))}
              </g>
            );
          }
          return (
            <g key={series.seriesId} style={{ color }}>
              {series.mark === "line" || series.mark === "area" ? (
                <polyline
                  className={
                    series.mark === "area"
                      ? "scientific-chart__area"
                      : "scientific-chart__line"
                  }
                  points={path}
                />
              ) : null}
              {points.map((point, index) => (
                <circle
                  className="scientific-chart__point"
                  key={`${point.px}-${point.py}-${index}`}
                  cx={point.px}
                  cy={point.py}
                  r={3}
                >
                  <title>
                    {formatAxisValue(point.x)}, {formatAxisValue(point.y)}
                  </title>
                </circle>
              ))}
            </g>
          );
        })}
        <text x={PLOT.left} y={PLOT.bottom + 18} textAnchor="start">
          {formatAxisValue(numeric[0]?.point.x ?? xMin)}
        </text>
        <text x={PLOT.right} y={PLOT.bottom + 18} textAnchor="end">
          {formatAxisValue(numeric.at(-1)?.point.x ?? xMax)}
        </text>
        <text
          x={(PLOT.left + PLOT.right) / 2}
          y={HEIGHT - 4}
          textAnchor="middle"
        >
          {spec.xAxis.label}
          {spec.xAxis.unit ? ` (${spec.xAxis.unit})` : ""}
        </text>
        <text
          x={12}
          y={(PLOT.top + PLOT.bottom) / 2}
          textAnchor="middle"
          transform={`rotate(-90 12 ${(PLOT.top + PLOT.bottom) / 2})`}
        >
          {spec.yAxis.label}
          {spec.yAxis.unit ? ` (${spec.yAxis.unit})` : ""}
        </text>
      </svg>
      <figcaption>
        {spec.series.map((series) => (
          <span key={series.seriesId}>
            <i style={{ backgroundColor: seriesColor(series.colorToken) }} />
            {series.label} · {series.points.length} 点
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
