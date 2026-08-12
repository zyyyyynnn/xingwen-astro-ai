import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  OpenHandsWorkspaceRoot,
  type ResearchWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import { useCommandMenuStore } from "../upstream/openhands/src/stores/command-menu-store";
import { useSidebarStore } from "../upstream/openhands/src/stores/sidebar-store";
import { createTestRuntime } from "./test/runtime";
import { WorkspaceEntry } from "./workspace-host";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  useCommandMenuStore.setState({ isOpen: false });
  useSidebarStore.setState({ collapsed: false });
});

describe("Workspace product UI", () => {
  it("teaches the empty Project state and creates through the real mutation", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    const onOpenProject = vi.fn();
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <WorkspaceEntry runtime={runtime} onOpenProject={onOpenProject} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("建立第一个研究项目")).toBeInTheDocument();
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
    expect(screen.getByLabelText("工作台侧栏")).toBeInTheDocument();
    expect(screen.queryByLabelText("悬浮研究概览")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "展示悬浮概览" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "展开右侧栏" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "新建研究项目" }));
    fireEvent.change(screen.getByLabelText("项目名称"), {
      target: { value: "近邻宿主星比较" },
    });
    fireEvent.change(screen.getByLabelText("研究说明"), {
      target: { value: "比较关键恒星参数" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建并进入项目" }));

    await waitFor(() => expect(onOpenProject).toHaveBeenCalledOnce());
  });

  it("renders the Research Thread and Inspector while keeping OpenHands mechanics", async () => {
    const runtime: ResearchWorkspaceRuntime = {
      project: { name: "宿主星研究", statusLabel: "等待开始" },
      navigation: {
        projects: [],
        onOpenProject: vi.fn(),
        onNewResearch: vi.fn(),
        onReturnHome: vi.fn(),
        onToggleProjectPinned: vi.fn(),
        onRequestProjectRename: vi.fn(),
        onRequestProjectDelete: vi.fn(),
      },
      composer: {
        submitting: false,
        value: "",
        placeholder: "描述研究问题",
        hasStartedConversation: true,
        leadingActions: null,
        beforeInput: null,
        onValueChange: vi.fn(),
        onSubmit: vi.fn(async () => undefined),
      },
      activation: null,
      threadPanel: <p>研究 Thread 内容</p>,
      inspectorPanel: <p>Research Inspector 内容</p>,
    };
    render(<OpenHandsWorkspaceRoot runtime={runtime} />);

    expect(screen.getByText("研究 Thread 内容")).toBeInTheDocument();
    expect(screen.getByText("Research Inspector 内容")).toBeInTheDocument();
    expect(screen.getByLabelText("悬浮研究概览")).toBeInTheDocument();
    const floatingControl = screen.getByRole("button", {
      name: "收起悬浮概览",
    });
    const dockedControl = screen.getByRole("button", {
      name: "展开右侧栏",
    });
    expect(floatingControl).toHaveAttribute("aria-pressed", "true");
    expect(dockedControl).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByTestId("floating-inspector-safe-track")).toHaveStyle({
      width: "min(var(--oh-inspector-floating-track-inline-size), 40cqw)",
    });

    fireEvent.click(floatingControl);
    expect(screen.getByLabelText("悬浮研究概览")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
    expect(screen.getByTestId("floating-inspector-safe-track")).toHaveStyle({
      width: "0px",
    });
    expect(screen.getByRole("button", { name: "展示悬浮概览" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "展开右侧栏" }));
    expect(screen.getByLabelText("右侧研究栏")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "展示悬浮概览" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "收起右侧栏" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("workspace-topbar")).toContainElement(
      screen.getByRole("button", { name: "收起右侧栏" }),
    );
    expect(screen.queryByRole("tab", { name: "活动" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "上下文" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "返回首页" }));
    expect(runtime.navigation.onReturnHome).toHaveBeenCalledOnce();

    const trigger = screen.getByRole("button", { name: "打开命令菜单" });
    trigger.focus();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const search = await screen.findByRole("combobox", { name: "搜索命令" });
    await waitFor(() => expect(search).toHaveFocus());
  });
});
