import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SessionManager } from "@xingwen/data-access";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { createAppRouter } from "./router";
import { createWorkspaceRuntime } from "./runtime";

afterEach(cleanup);

function fixtureRuntime(): Extract<
  WorkspaceRuntimeBoundaries,
  { adapterKind: "fixture" }
> {
  const runtime = createWorkspaceRuntime({ apiBaseUrl: "" });
  if (runtime.adapterKind !== "fixture") {
    throw new Error("Expected Fixture runtime.");
  }
  return runtime;
}

function renderRoute(path: string, boundaries: WorkspaceRuntimeBoundaries) {
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createAppRouter(boundaries, history);
  render(<RouterProvider router={router} />);
  return { router, history };
}

function httpShapedRuntime(
  fixture = fixtureRuntime(),
): WorkspaceRuntimeBoundaries & { readonly session: SessionManager } {
  const sessionInfo: Awaited<ReturnType<SessionManager["ensureSession"]>> = {
    status: "active",
    createdAt: "2026-07-22T00:00:00Z",
    expiresAt: "2026-07-22T01:00:00Z",
    quota: {},
    csrfToken: "csrf-test-only",
  };
  const session: SessionManager = {
    ensureSession: vi.fn(async () => sessionInfo),
    getCurrent: () => null,
    revokeSession: vi.fn(async () => {}),
    attachCsrf: vi.fn(),
    onSessionExpired: vi.fn(() => () => {}),
    notifyExpired: vi.fn(),
  };

  return {
    adapterKind: "http",
    repositories: fixture.repositories,
    workspaceController: fixture.workspaceController,
    session,
  };
}

describe("Workspace routes", () => {
  it("redirects / to /workspace by replacing the history entry", async () => {
    const { history } = renderRoute("/", fixtureRuntime());

    await screen.findByRole("heading", { name: "研究工作台" });
    expect(history.location.pathname).toBe("/workspace");

    act(() => {
      history.back();
    });
    await waitFor(() => {
      expect(history.location.pathname).toBe("/workspace");
    });
    expect(history.location.pathname).not.toBe("/");
  });

  it("redirects /tour to /workspace preserving only the validated identifiers", async () => {
    const search = new URLSearchParams({
      projectId: "proj_01JEXAMPLE",
      draftId: "rcd_01JEXAMPLE",
      contractId: "rc_01JEXAMPLE",
      runId: "run_01JEXAMPLE",
    });
    const { history } = renderRoute(
      `/tour?${search.toString()}`,
      fixtureRuntime(),
    );

    await screen.findByRole("heading", { name: "研究工作台" });
    expect(history.location.pathname).toBe("/workspace");

    const redirected = new URLSearchParams(history.location.search);
    expect(redirected.get("projectId")).toBe("proj_01JEXAMPLE");
    expect(redirected.get("draftId")).toBe("rcd_01JEXAMPLE");
    expect(redirected.get("contractId")).toBe("rc_01JEXAMPLE");
    expect(redirected.get("runId")).toBe("run_01JEXAMPLE");
  });

  it("drops unknown query parameters while redirecting /tour", async () => {
    const { history } = renderRoute(
      "/tour?projectId=proj_01JEXAMPLE&utm_source=external",
      fixtureRuntime(),
    );

    await screen.findByRole("heading", { name: "研究工作台" });
    expect(history.location.pathname).toBe("/workspace");

    const redirected = new URLSearchParams(history.location.search);
    expect(redirected.get("projectId")).toBe("proj_01JEXAMPLE");
    expect(redirected.get("utm_source")).toBeNull();
  });

  it("rejects an invalid /tour identifier without appending it to /workspace", async () => {
    const { history } = renderRoute(
      `/tour?projectId=${"a".repeat(129)}`,
      fixtureRuntime(),
    );

    await screen.findByRole("heading", { name: "页面载入失败" });
    expect(history.location.pathname).toBe("/tour");
    expect(history.location.pathname).not.toBe("/workspace");
  });

  it("renders the minimal Workspace host with brand, skip link and title", async () => {
    renderRoute("/workspace", fixtureRuntime());

    await screen.findByRole("heading", { name: "研究工作台" });
    const skipLink = screen.getByRole("link", { name: "跳到主要内容" });
    expect(skipLink).toHaveAttribute("href", "#main-content");

    expect(screen.getByRole("link", { name: "星文智析" })).toHaveAttribute(
      "href",
      "/workspace",
    );
    const navigation = screen.getByRole("navigation", { name: "主要导航" });
    expect(
      within(navigation).getByRole("link", { name: "研究工作台" }),
    ).toHaveAttribute("aria-current", "page");
    expect(
      screen.getByRole("heading", { name: "研究工作台" }),
    ).toBeInTheDocument();
  });

  it("accepts valid identifiers on /workspace without error", async () => {
    const { history } = renderRoute(
      "/workspace?projectId=proj_01JEXAMPLE&runId=run_01JEXAMPLE",
      fixtureRuntime(),
    );

    await screen.findByRole("heading", { name: "研究工作台" });
    expect(history.location.pathname).toBe("/workspace");
    const search = new URLSearchParams(history.location.search);
    expect(search.get("projectId")).toBe("proj_01JEXAMPLE");
    expect(search.get("runId")).toBe("run_01JEXAMPLE");
  });

  it("renders the fixed share boundary without creating a private session", async () => {
    const runtime = httpShapedRuntime();
    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    expect(
      screen.getByText("该链接可能无效、已撤销或已过期。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回首页" })).toHaveAttribute(
      "href",
      "/",
    );
    expect(screen.queryByText("demo-token")).not.toBeInTheDocument();
    expect(runtime.session.ensureSession).not.toHaveBeenCalled();
  });

  it("disables the share retry while a check is in flight", async () => {
    const runtime = httpShapedRuntime();
    let resolveCheck: ((value: null) => void) | undefined;
    vi.spyOn(runtime.repositories.shares, "getPublic").mockReturnValue(
      new Promise<null>((resolve) => {
        resolveCheck = resolve;
      }),
    );

    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    const retry = screen.getByRole("button", { name: "重试" });
    expect(retry).toBeDisabled();
    expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "true");

    await act(async () => {
      resolveCheck?.(null);
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
    });
  });

  it("keeps the fixed share boundary when the public read fails", async () => {
    const runtime = httpShapedRuntime();
    vi.spyOn(runtime.repositories.shares, "getPublic").mockRejectedValue(
      new Error("network"),
    );

    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
    });
    expect(screen.getByRole("main")).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByText("network")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders the not-found boundary for unknown routes", async () => {
    renderRoute("/not-a-route", fixtureRuntime());

    await screen.findByRole("heading", { name: "页面未找到" });
    expect(
      screen.getByRole("link", { name: "返回工作台入口" }),
    ).toHaveAttribute("href", "/");
  });

  it("renders the route error boundary for invalid /workspace identifiers", async () => {
    const { history } = renderRoute(
      `/workspace?draftId=${"b".repeat(129)}`,
      fixtureRuntime(),
    );

    await screen.findByRole("heading", { name: "页面载入失败" });
    expect(history.location.pathname).toBe("/workspace");
    const retry = screen.getByRole("button", { name: "重试" });

    fireEvent.click(retry);
    await screen.findByRole("heading", { name: "页面载入失败" });
  });
});
