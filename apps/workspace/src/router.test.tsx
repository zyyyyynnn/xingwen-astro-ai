import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { createAppRouter } from "./router";
import { createTestRuntime } from "./test/runtime";

afterEach(cleanup);

function renderRoute(path: string, runtime: WorkspaceRuntimeBoundaries) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(runtime, history);
  render(
    <QueryClientProvider client={runtime.queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, history };
}

describe("Workspace routes", () => {
  it("gates /workspace, lists real repository projects, and replaces /", async () => {
    const runtime = createTestRuntime();
    const { history } = renderRoute("/", runtime);

    await screen.findByRole("heading", { name: "新研究", level: 1 });
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
    expect(runtime.session.ensureSession).toHaveBeenCalled();
    expect(history.location.pathname).toBe("/workspace");
    expect(
      await screen.findByText("Exoplanet host-star integration"),
    ).toBeInTheDocument();

    act(() => history.back());
    await waitFor(() => expect(history.location.pathname).toBe("/workspace"));
  });

  it("performs the project ownership read before rendering the OpenHands shell", async () => {
    const runtime = createTestRuntime();
    const getById = vi.spyOn(runtime.repositories.projects, "getById");
    renderRoute("/workspace/proj_01JEXAMPLE", runtime);

    await screen.findByRole("heading", {
      name: "Exoplanet host-star integration",
    });
    expect(getById).toHaveBeenCalled();
    expect(
      screen.getByRole("textbox", { name: "输入研究意图" }),
    ).toHaveAttribute("aria-disabled", "false");
    expect(screen.getByRole("button", { name: "新建研究" })).toBeEnabled();
    expect(screen.queryByText("运行服务未连接")).not.toBeInTheDocument();
  });

  it("keeps public share outside the private Session Gate", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.shares, "getPublic").mockResolvedValue(null);
    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
    expect(screen.queryByText("demo-token")).not.toBeInTheDocument();
  });

  it("fails closed for a missing or cross-session project", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "getById").mockResolvedValue(null);
    renderRoute("/workspace/hidden-project", runtime);

    await screen.findByRole("heading", { name: "页面载入失败" });
    expect(screen.getByText("资源不可用")).toBeInTheDocument();
    expect(screen.queryByText("hidden-project")).not.toBeInTheDocument();
  });
});
