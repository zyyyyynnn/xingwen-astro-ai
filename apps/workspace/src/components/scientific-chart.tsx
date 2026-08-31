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

function resolveCssColor(variable: string): string {
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
  const rgba = context.getImageData(0, 0, 1, 1).data;
  return `#${Array.from(rgba, (channel) => channel.toString(16).padStart(2, "0")).join("")}`;
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
function buildVegaLiteSpec(
  chart: ChartVisualizationReview,
  containerWidth: number,
  container: HTMLElement,
): TopLevelSpec {
  const style = getComputedStyle(container);
  const height = Number.parseFloat(style.minHeight);
  const fontSize = Number.parseFloat(style.fontSize);
  const requestedWeight = Number(
    getComputedStyle(document.documentElement).getPropertyValue(
      "--font-weight-ui-emphasis",
    ),
  );
  const titleFontWeight = (
    [100, 200, 300, 400, 500, 600, 700, 800, 900] as const
  ).find((weight) => weight === requestedWeight);
  if (
    titleFontWeight === undefined ||
    ![height, fontSize].every((value) => Number.isFinite(value) && value > 0)
  ) {
    throw new Error("主题缺少图表尺寸或字体 Token");
  }
  const border = resolveCssColor("--color-border");
  return {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    autosize: { type: "fit", contains: "padding", resize: true },
    width: Math.max(1, Math.floor(containerWidth)),
    height,
    background: "transparent",
    config: {
      font: style.fontFamily,
      view: { stroke: null },
      axis: {
        domain: false,
        gridColor: border,
        tickColor: border,
        labelColor: resolveCssColor("--color-ink-secondary"),
        titleColor: resolveCssColor("--color-ink-primary"),
        labelFontSize: fontSize,
        titleFontSize: fontSize,
        titleFontWeight,
      },
    },
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
        color: { value: resolveCssColor(TOKEN_VARIABLES[series.colorToken]) },
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
    let renderRevision = 0;
    let animationFrame = 0;
    setState("loading");

    const render = async (containerWidth: number) => {
      const revision = ++renderRevision;
      try {
        const [{ default: embed }, spec] = await Promise.all([
          import("vega-embed"),
          Promise.resolve(buildVegaLiteSpec(chart, containerWidth, container)),
        ]);
        if (!active || revision !== renderRevision) return;
        finalized?.finalize();
        container.replaceChildren();
        const result = await embed(container, spec, {
          actions: false,
          renderer: "svg",
        });
        if (!active || revision !== renderRevision) {
          result.finalize();
          return;
        }
        finalized = result;
        setState("ready");
      } catch (error) {
        if (!active || revision !== renderRevision) return;
        setState("error");
        setMessage(error instanceof Error ? error.message : "科学图表渲染失败");
      }
    };

    const scheduleRender = () => {
      cancelAnimationFrame(animationFrame);
      animationFrame = requestAnimationFrame(() => {
        const width = container.getBoundingClientRect().width;
        if (width <= 0) return;
        setState("loading");
        setMessage("正在渲染科学图表");
        void render(width);
      });
    };

    const observer = new ResizeObserver(scheduleRender);
    observer.observe(container);
    scheduleRender();
    return () => {
      active = false;
      observer.disconnect();
      cancelAnimationFrame(animationFrame);
      finalized?.finalize();
    };
  }, [chart]);

  const totalPoints = chart.series.reduce(
    (count, series) => count + series.points.length,
    0,
  );
  return (
    <figure className="scientific-chart" aria-label={title}>
      <ul className="scientific-chart__legend" aria-label="图例">
        {chart.series.map((series) => (
          <li key={series.seriesId}>
            <span
              className="scientific-chart__legend-swatch"
              data-mark={series.mark}
              style={{ color: `var(${TOKEN_VARIABLES[series.colorToken]})` }}
              aria-hidden="true"
            />
            <span>{series.label}</span>
          </li>
        ))}
      </ul>
      <div
        ref={containerRef}
        className="scientific-chart__canvas"
        data-state={state}
        role="img"
        aria-label={`${title}：${chart.series.length} 条序列，共 ${totalPoints} 个数据点`}
        aria-busy={state === "loading"}
      />
      {state === "loading" ? (
        <figcaption className="scientific-chart__status" role="status">
          {message}
        </figcaption>
      ) : null}
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
