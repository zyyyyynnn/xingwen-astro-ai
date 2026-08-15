import { asEntityId } from "@xingwen/domain";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { DataArtifactRenderer } from "./data-artifact-renderer";

afterEach(cleanup);

describe("Data Artifact renderer", () => {
  it("renders a compact normalized Dataset table", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.dataArtifacts.getDataset(
      asEntityId("artv_dataset_01"),
    );

    render(
      <DataArtifactRenderer
        review={runtime.researchAdapter.toDataArtifactViewModel(review)}
        title="Exoplanet host-star dataset"
        versionNumber={1}
        surface="docked"
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Exoplanet host-star dataset" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "研究数据集中的规范化字段与数据行" }),
    ).toBeInTheDocument();
    expect(screen.getByText("TOI-1234")).toBeInTheDocument();
    expect(screen.getByText("5800")).toBeInTheDocument();
  });

  it("renders field definitions from the formal read contract", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.dataArtifacts.getFieldDictionary(
      asEntityId("artv_fdict_01"),
    );

    render(
      <DataArtifactRenderer
        review={runtime.researchAdapter.toDataArtifactViewModel(review)}
        title="Canonical field dictionary"
        versionNumber={1}
        surface="fullscreen"
      />,
    );

    expect(
      screen.getByRole("table", { name: "规范字段定义、单位与来源映射" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Stable identifier assigned by the TESS Object of Interest catalog.",
      ).length,
    ).toBeGreaterThan(0);
  });

  it("renders source members from the formal read contract", async () => {
    const runtime = createTestRuntime();
    const review = await runtime.repositories.dataArtifacts.getSourceCollection(
      asEntityId("artv_srccol_01"),
    );

    render(
      <DataArtifactRenderer
        review={runtime.researchAdapter.toDataArtifactViewModel(review)}
        title="Source snapshots"
        versionNumber={1}
        surface="thread"
      />,
    );

    expect(screen.getByText(/来源集合 · \d+ 个来源成员/)).toBeInTheDocument();
    expect(screen.queryByText("snap_01")).not.toBeInTheDocument();
    expect(
      screen.getAllByText("nasa_exoplanet_archive").length,
    ).toBeGreaterThan(0);
  });
});
