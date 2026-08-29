import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import type { ChartVisualizationReview } from "@xingwen/domain";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

const embed = vi.fn();
vi.mock("vega-embed", () => ({ default: embed }));

import { ScientificChart } from "./scientific-chart";

beforeAll(() => {
  document.documentElement.style.setProperty("--color-brand", "rgb(1,2,3)");
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
    fillStyle: "",
    fillRect: () => undefined,
    getImageData: () => ({ data: [1, 2, 3, 255] }),
  } as never);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
    width: 640,
    height: 320,
    top: 0,
    right: 640,
    bottom: 320,
    left: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  embed.mockReset();
});

const chart: ChartVisualizationReview = {
  mode: "chart",
  datasetArtifactVersionId: asEntityId("dataset-version-1"),
  sourceSnapshotId: null,
  xAxis: {
    field: asEntityId("teff"),
    label: "有效温度",
    unit: "K",
    scale: "linear",
  },
  yAxis: {
    field: asEntityId("feh"),
    label: "金属丰度",
    unit: "dex",
    scale: "linear",
  },
  series: [
    {
      seriesId: asEntityId("series-1"),
      label: "候选样本",
      xField: asEntityId("teff"),
      yField: asEntityId("feh"),
      mark: "point",
      colorToken: "brand",
      points: [
        { x: 5800, y: 0.12 },
        { x: 6100, y: 0.21 },
      ],
    },
  ],
};

describe("ScientificChart", () => {
  it("builds a Vega-Lite spec only from the typed chart contract", async () => {
    embed.mockResolvedValue({ finalize: vi.fn() });
    render(<ScientificChart chart={chart} title="相关图" />);

    await waitFor(() => expect(embed).toHaveBeenCalledTimes(1));
    const [container, spec, options] = embed.mock.calls[0] ?? [];
    expect(container).toBeInstanceOf(HTMLElement);
    expect(options).toEqual({ actions: false, renderer: "svg" });
    const serialized = JSON.stringify(spec);
    // Safety boundary: no raw expressions may reach the renderer.
    expect(serialized).not.toContain('"expr"');
    expect(serialized).not.toContain("javascript:");
    const built = spec as {
      width: number;
      layer: readonly { mark: { type: string } }[];
    };
    expect(built.width).toBe(640);
    expect(built.layer).toHaveLength(1);
    expect(built.layer[0]?.mark.type).toBe("point");

    expect(screen.getByRole("list", { name: "图例" })).toHaveTextContent(
      "候选样本",
    );
    expect(await screen.findByText("5800")).toBeInTheDocument();
  });

  it("keeps the table fallback available for accessibility", () => {
    embed.mockReturnValue(new Promise(() => undefined));
    render(<ScientificChart chart={chart} title="相关图" />);
    expect(screen.getByText("查看表格替代视图")).toBeInTheDocument();
    expect(screen.getByText(/候选样本 · 散点/)).toBeInTheDocument();
    expect(screen.getByText("0.21")).toBeInTheDocument();
  });

  it("reports render failures and keeps the fallback readable", async () => {
    embed.mockRejectedValue(new Error("Vega 渲染失败"));
    render(<ScientificChart chart={chart} title="相关图" />);
    expect(
      await screen.findByText(/Vega 渲染失败，请查看下方表格替代视图。/),
    ).toBeInTheDocument();
    expect(screen.getByText("查看表格替代视图")).toBeInTheDocument();
  });

  it("finalizes the renderer when the component unmounts", async () => {
    const finalize = vi.fn();
    embed.mockResolvedValue({ finalize });
    const { unmount } = render(
      <ScientificChart chart={chart} title="相关图" />,
    );
    await waitFor(() => expect(embed).toHaveBeenCalledTimes(1));
    unmount();
    expect(finalize).toHaveBeenCalledTimes(1);
  });
});
