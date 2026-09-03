import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { asEntityId, type DatasetCellReview } from "@xingwen/domain";
import { afterEach, expect, it, vi } from "vitest";
import { createTestRuntime } from "../test/runtime";
import { DataArtifactRenderer } from "./data-artifact-renderer";

afterEach(cleanup);

it("groups entity rows by applicable fields while retaining source nulls and evidence", async () => {
  const runtime = createTestRuntime();
  const review = await runtime.repositories.dataArtifacts.getDataset(
    asEntityId("artv_dataset_01"),
  );
  const firstField = review.columns[0];
  if (!firstField) throw new Error("Dataset fixture has no fields");
  const field = (fieldId: string, meaningZh: string) => ({
    ...firstField,
    fieldId: asEntityId(fieldId),
    meaningZh,
    canonicalUnit: "none",
    dataType: "number",
  });
  const cell = (fieldId: string, value: string | null): DatasetCellReview => ({
    canonicalFieldId: asEntityId(fieldId),
    value,
    status: value === null ? "declared_null" : "mapped",
    unit: null,
    reason: value === null ? "源目录未提供" : null,
    conflictIds: [],
    evidenceIds: [asEntityId("ev.dataset.cell")],
  });
  const row = (
    identity: string,
    entityLevel: string,
    cells: readonly DatasetCellReview[],
  ) => ({
    rowId: identity,
    identity,
    entityLevel,
    cells,
    alignmentStatus: "matched",
    evidenceIds: [],
    sourceSnapshotIds: [],
  });
  const onSelectEvidence = vi.fn();
  render(
    <DataArtifactRenderer
      title="研究数据集"
      surface="fullscreen"
      onSelectEvidence={onSelectEvidence}
      review={{
        ...review,
        rowCount: 4,
        fieldCount: 4,
        columns: [
          field("planet.period", "轨道周期"),
          field("planet.radius", "行星半径"),
          field("star.temperature", "恒星温度"),
          field("planet.disposition", "处置状态"),
        ],
        rows: [
          row("GJ 806", "host_star", [cell("star.temperature", "3600")]),
          row("GJ 3929 b", "planet_assertion", [
            cell("planet.period", "2.616235"),
            cell("planet.radius", null),
          ]),
          row("另一条行星记录", "planet_assertion", [
            cell("planet.period", "11.5301"),
          ]),
          row("TOI 候选体", "planet_candidate", [
            cell("planet.period", "3.5"),
            cell("planet.disposition", "PC"),
          ]),
        ],
      }}
    />,
  );

  expect(screen.getByRole("tab", { name: "宿主恒星 1" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(
    screen.getByRole("columnheader", { name: "恒星温度" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("columnheader", { name: "轨道周期" }),
  ).not.toBeInTheDocument();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "行星记录 2" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.queryByRole("columnheader", { name: "恒星温度" }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "行星半径" }),
  ).toBeInTheDocument();
  const planet = screen
    .getByRole("rowheader", { name: "GJ 3929 b" })
    .closest("tr");
  if (!planet) throw new Error("Planet row was not rendered");
  expect(within(planet).getByText("—")).toBeInTheDocument();
  expect(screen.getByText("不适用")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /2\.616235/ }));
  expect(onSelectEvidence).toHaveBeenCalledWith([
    asEntityId("ev.dataset.cell"),
  ]);
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "不存在" },
  });
  fireEvent.mouseDown(screen.getByRole("tab", { name: "候选体 1" }), {
    button: 0,
    ctrlKey: false,
  });
  expect(
    screen.getByRole("rowheader", { name: "TOI 候选体" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("columnheader", { name: "处置状态" }),
  ).toBeInTheDocument();
});
