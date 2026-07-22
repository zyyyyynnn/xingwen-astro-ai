import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { createAppRouter } from "./router";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";

const mockBoundaries = {} as WorkspaceRuntimeBoundaries;

afterEach(cleanup);

test("renders a shared deep link without business data access", async () => {
  const history = createMemoryHistory({
    initialEntries: ["/share/demo-token"],
  });
  const testRouter = createAppRouter(mockBoundaries, history);

  render(<RouterProvider router={testRouter} />);

  expect(
    await screen.findByRole("heading", { name: "共享入口" }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/demo-token/u)).not.toBeInTheDocument();
});

test.each([
  ["/", "科研工作台入口", "入口"],
  ["/tour", "引导入口", "引导"],
  ["/workspace", "科研工作区", "工作区"],
  ["/share/demo-token", "共享入口", null],
  ["/not-a-route", "页面未找到", null],
] as const)(
  "marks only the intended primary navigation item for %s",
  async (path, pageHeading, activeLabel) => {
    const history = createMemoryHistory({ initialEntries: [path] });
    const testRouter = createAppRouter(mockBoundaries, history);

    render(<RouterProvider router={testRouter} />);

    await screen.findByRole("heading", { name: pageHeading });
    const navigation = screen.getByRole("navigation", {
      name: "主要导航",
    });
    const activeLinks = within(navigation)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");

    if (activeLabel) {
      expect(activeLinks).toHaveLength(1);
      expect(activeLinks[0]).toHaveTextContent(activeLabel);
    } else {
      expect(activeLinks).toHaveLength(0);
    }
  },
);
