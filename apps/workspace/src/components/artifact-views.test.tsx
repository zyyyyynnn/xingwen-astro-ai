import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScientificArtifactView } from "./scientific-artifact-view";

afterEach(cleanup);

const repositories = createFixtureRepositories(exoplanetHostStarFixture);
const loadContent = vi.fn(async () => new ArrayBuffer(0));

describe("ScientificArtifactView", () => {
  it("renders analysis metrics, bounded rows, findings, and review warnings", async () => {
    const artifact = await repositories.scientificArtifacts.getReview(
      "artv_scientific_analysis" as never,
    );
    render(
      <ScientificArtifactView artifact={artifact} loadContent={loadContent} />,
    );

    expect(
      screen.getByRole("article", { name: "宿主星样本数据剖析" }),
    ).toBeInTheDocument();
    expect(screen.getByText("平均有效温度")).toBeInTheDocument();
    expect(screen.getByText("TOI-1234.01")).toBeInTheDocument();
    expect(screen.getByText("字段覆盖完整")).toBeInTheDocument();
    expect(screen.getByText("需要人工确认")).toBeInTheDocument();
  });

  it("renders model identity, frozen split, metrics, baseline, and limitations", async () => {
    const artifact = await repositories.scientificArtifacts.getReview(
      "artv_scientific_model" as never,
    );
    render(
      <ScientificArtifactView artifact={artifact} loadContent={loadContent} />,
    );

    expect(screen.getByText("random_forest")).toBeInTheDocument();
    expect(screen.getByText("训练 70%")).toBeInTheDocument();
    expect(screen.getByText("验证 10%")).toBeInTheDocument();
    expect(screen.getByText("测试 20%")).toBeInTheDocument();
    expect(screen.getByText("基线 0.62")).toBeInTheDocument();
    expect(screen.getByText(/指标不得外推/u)).toBeInTheDocument();
  });

  it("renders token-colored chart series with publication-owned points", async () => {
    const artifact = await repositories.scientificArtifacts.getReview(
      "artv_scientific_chart" as never,
    );
    const { container } = render(
      <ScientificArtifactView artifact={artifact} loadContent={loadContent} />,
    );

    expect(
      screen.getByRole("img", { name: "恒星半径 随 有效温度 变化" }),
    ).toBeInTheDocument();
    expect(screen.getByText("宿主星 · 3 点")).toBeInTheDocument();
    expect(screen.getByText("趋势 · 3 点")).toBeInTheDocument();
    expect(container.querySelectorAll(".scientific-chart__point")).toHaveLength(
      6,
    );
    expect(container.querySelector(".scientific-chart__line")).toHaveAttribute(
      "points",
    );
  });
});
