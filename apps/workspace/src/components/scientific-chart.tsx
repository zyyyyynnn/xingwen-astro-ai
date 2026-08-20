import type { ChartVisualizationReview } from "@xingwen/domain";
import type { TopLevelSpec } from "vega-lite";
import { useEffect, useRef, useState } from "react";

const TOKEN_VARIABLES: Record<
  ChartVisualizationReview["series"][number]["colorToken"],
  string
> = {
  brand: "--color-brand",
  information: "--color-info",
  success: "--color-success",
  warning: "--color-warning",
  error: "--color-error",
  neutral: "--color-ink-secondary",
};

const MARK_TYPES = {
  line: "line",
  point: "point",
  bar: "bar",
  area: "area",
} as const;

function resolveTokenColor(
  token: ChartVisualizationReview["series"][number]["colorToken"],
): string {
  const variable = TOKEN_VARIABLES[token];
  const source = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  if (!source) throw new Error(`主题缺少图表颜色 Token：${variable}`);
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("浏览器无法解析图表颜色 Token");
  context.fillStyle = source;
  context.fillRect(0, 0, 1, 1);
  const [red = 0, green = 0, blue = 0] = context.getImageData(0, 0, 1, 1).data;
  return `${String.fromCodePoint(35)}${[red, green, blue]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

function axisLabel(
  axis: ChartVisualizationReview["xAxis"] | ChartVisualizationReview["yAxis"],
): string {
  return axis.unit ? `${axis.label} (${axis.unit})` : axis.label;
}

function axisEncoding(
  axis: ChartVisualizationReview["xAxis"] | ChartVisualizationReview["yAxis"],
  field: "x" | "y",
) {
  const title = axisLabel(axis);
  if (axis.scale === "category") {
    return { field, type: "nominal", axis: { title } } as const;
  }
  if (axis.scale === "time") {
    return { field, type: "temporal", axis: { title } } as const;
  }
  return {
    field,
    type: "quantitative",
    scale: { type: axis.scale === "log" ? "log" : "linear" },
    axis: { title },
  } as const;
}

/**
 * Build a Vega-Lite spec strictly from the typed XingWen chart contract.
 * Raw or user-provided Vega specs are never accepted; no expressions are
 * emitted, so the renderer cannot evaluate arbitrary code.
 */
function buildVegaLiteSpec(chart: ChartVisualizationReview): TopLevelSpec {
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    width: "container",
    height: 320,
    background: "transparent",
    layer: chart.series.map((series) => ({
      data: {
        values: series.points.map((point) => ({ x: point.x, y: point.y })),
      },
      mark: {
        type: MARK_TYPES[series.mark],
        tooltip: true,
      },
      encoding: {
        x: axisEncoding(chart.xAxis, "x"),
        y: axisEncoding(chart.yAxis, "y"),
        color: { value: resolveTokenColor(series.colorToken) },
      },
      name: series.label,
    })),
  };
}

const SERIES_MARK_LABELS: Record<string, string> = {
  line: "折线",
  point: "散点",
  bar: "柱状",
  area: "面积",
};

export function ScientificChart({
  chart,
  title,
}: {
  readonly chart: ChartVisualizationReview;
  readonly title: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("正在渲染科学图表");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let finalized: { finalize: () => void } | null = null;
    let active = true;
    setState("loading");
    void (async () => {
      try {
        const [{ default: embed }, spec] = await Promise.all([
          import("vega-embed"),
          Promise.resolve(buildVegaLiteSpec(chart)),
        ]);
        if (!active) return;
        container.textContent = "";
        const result = await embed(container, spec, {
          actions: false,
          renderer: "svg",
        });
        if (!active) {
          result.finalize();
          return;
        }
        finalized = result;
        setState("ready");
      } catch (error) {
        if (!active) return;
        setState("error");
        setMessage(error instanceof Error ? error.message : "科学图表渲染失败");
      }
    })();
    return () => {
      active = false;
      finalized?.finalize();
    };
  }, [chart]);

  const totalPoints = chart.series.reduce(
    (count, series) => count + series.points.length,
    0,
  );
  return (
    <figure className="scientific-chart" aria-label={title}>
      <div
        ref={containerRef}
        className="scientific-chart__canvas"
        role="img"
        aria-label={`${title}：${chart.series.length} 条序列，共 ${totalPoints} 个数据点`}
        aria-busy={state === "loading"}
      />
      {state === "error" ? (
        <figcaption role="alert">
          {message}，请查看下方表格替代视图。
        </figcaption>
      ) : null}
      <figcaption className="sr-only">
        {`${axisLabel(chart.xAxis)} 对 ${axisLabel(chart.yAxis)}，${chart.series
          .map(
            (series) =>
              `${series.label}（${SERIES_MARK_LABELS[series.mark] ?? series.mark}，${series.points.length} 点）`,
          )
          .join("；")}。`}
      </figcaption>
      <details className="scientific-chart__fallback">
        <summary>查看表格替代视图</summary>
        {chart.series.map((series) => (
          <div key={series.seriesId}>
            <h5>
              {series.label} · {SERIES_MARK_LABELS[series.mark] ?? series.mark}
            </h5>
            {series.points.length > 0 ? (
              <table>
                <caption className="sr-only">{series.label}数据点</caption>
                <thead>
                  <tr>
                    <th scope="col">{axisLabel(chart.xAxis)}</th>
                    <th scope="col">{axisLabel(chart.yAxis)}</th>
                  </tr>
                </thead>
                <tbody>
                  {series.points.slice(0, 80).map((point, index) => (
                    <tr key={`${String(point.x)}-${index}`}>
                      <th scope="row">{String(point.x)}</th>
                      <td>{String(point.y)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>未提供数据点。</p>
            )}
          </div>
        ))}
      </details>
    </figure>
  );
}
