import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { ScientificDiffView } from "./scientific-diff-view";

afterEach(cleanup);

it("keeps large diagnostic comparisons bounded and every change reachable", () => {
  render(
    <ScientificDiffView
      results={[
        {
          category: "conclusions",
          changes: Array.from({ length: 51 }, (_, index) => ({
            key: `forecast:${index + 1}`,
            kind: "changed",
            before: `未来第 ${index + 1} 步：1`,
            after: `未来第 ${index + 1} 步：2`,
          })),
        },
      ]}
    />,
  );
  expect(screen.getAllByRole("listitem")).toHaveLength(50);
  expect(screen.queryByText("未来第 51 步：2")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "上一页" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
  expect(screen.getByText("未来第 51 步：2")).toBeVisible();
  expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "上一页" }));
  expect(screen.getByText("未来第 1 步：1")).toBeVisible();
});
