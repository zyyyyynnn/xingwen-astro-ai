import { RouterProvider, createMemoryHistory } from "@tanstack/react-router";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
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
    researchAdapter: fixture.researchAdapter,
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

  it("renders the OpenHands workspace shell inside the Xingwen host", async () => {
    renderRoute("/workspace", fixtureRuntime());

    await screen.findByRole("heading", { name: "研究工作台" });
    const skipLink = screen.getByRole("link", { name: "跳到主要内容" });
    expect(skipLink).toHaveAttribute("href", "#main-content");

    expect(screen.getByText("星文智析")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "研究工作台" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        level: 2,
        name: "从一条明确指令开始",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "工作台导航" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "打开命令菜单" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("tablist", { name: "工作区面板" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "向 Agent 发送指令" }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "新建任务" })).toBeDisabled();
    expect(screen.getByText("运行服务未连接")).toBeInTheDocument();
  });

  it("renders the fixed share boundary without creating a private session", async () => {
    const runtime = httpShapedRuntime();
    renderRoute("/share/demo-token", runtime);

    await screen.findByRole("heading", { name: "共享结果当前不可用" });
    expect(
      screen.getByText("该链接可能无效、已撤销或已过期。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试" })).toHaveAttribute(
      "data-slot",
      "button",
    );
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
});
