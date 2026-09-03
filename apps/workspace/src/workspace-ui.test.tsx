import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { parseEntityId, type DomainEntityId } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  WorkspaceMechanicsRoot,
  type ResearchWorkspaceRuntime,
} from "./mechanics/root";
import { useCommandMenuStore } from "./mechanics/stores/command-menu-store";
import { useSidebarStore } from "./mechanics/stores/sidebar-store";
import { createTestRuntime } from "./test/runtime";
import { WorkspaceEntry } from "./workspace-host";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  useCommandMenuStore.setState({ isOpen: false });
  useSidebarStore.setState({ collapsed: false });
});

describe("Workspace product UI", () => {
  it("teaches the empty workspace entry: one send creates the Project and first turn", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    const submitTurn = vi
      .spyOn(runtime.repositories.researchThread, "submit")
      .mockResolvedValue({
        outcome: "draft_ready",
        entries: [],
        activeDraftId: null,
        modelExecutionId: parseEntityId("mexec_entry_test") as DomainEntityId,
      });
    const onOpenProject = vi.fn();
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <WorkspaceEntry runtime={runtime} onOpenProject={onOpenProject} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("开始你的研究")).toBeInTheDocument();
    expect(screen.getByTestId("root-layout")).toBeInTheDocument();
    expect(screen.getByLabelText("工作台侧栏")).toBeInTheDocument();

    const composer = screen.getByRole("textbox", { name: "输入研究消息" });
    composer.textContent = "比较近邻宿主恒星的行星统计特征";
    fireEvent.input(composer);
    fireEvent.keyDown(composer, { key: "Enter" });

    await waitFor(() => expect(onOpenProject).toHaveBeenCalledOnce());
    expect(submitTurn).toHaveBeenCalledOnce();
    expect(submitTurn.mock.calls[0]?.[1]?.message).toBe(
      "比较近邻宿主恒星的行星统计特征",
    );
  });

  it("creates a real Project before uploading the first Composer attachment", async () => {
    const runtime = createTestRuntime();
    vi.spyOn(runtime.repositories.projects, "list").mockResolvedValue({
      items: [],
      nextCursor: null,
    });
    const upload = vi.spyOn(runtime.repositories.researchInputs, "create");
    const onOpenProject = vi.fn();
    render(
      <QueryClientProvider client={runtime.queryClient}>
        <WorkspaceEntry runtime={runtime} onOpenProject={onOpenProject} />
      </QueryClientProvider>,
    );

    const input = await screen.findByLabelText("选择研究资料");
    fireEvent.change(input, {
      target: {
        files: [
          new File(["%PDF-1.7"], "observations.pdf", {
            type: "application/pdf",
          }),
        ],
      },
    });

    await waitFor(() => expect(upload).toHaveBeenCalledOnce());
    await waitFor(() => expect(onOpenProject).toHaveBeenCalledOnce());
    expect(upload.mock.calls[0]?.[0].type).toBe("pdf");
    expect(upload.mock.calls[0]?.[0].filename).toBe("observations.pdf");
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
      threadItemCount: 0,
      threadPanel: <p>研究 Thread 内容</p>,
      inspectorPanel: <p>Research Inspector 内容</p>,
    };
    render(<WorkspaceMechanicsRoot runtime={runtime} />);

    expect(screen.getByText("研究 Thread 内容")).toBeInTheDocument();
    expect(screen.getByText("Research Inspector 内容")).toBeInTheDocument();
    const inspectorControl = screen.getByRole("button", {
      name: "关闭右侧研究栏",
    });
    expect(inspectorControl).toHaveAttribute("aria-expanded", "true");
    const inspector = screen.getByLabelText("右侧研究栏");
    expect(inspector).toBeInTheDocument();
    expect(inspector.parentElement).toBe(
      screen.getByTestId("conversation-main"),
    );
    expect(screen.getByTestId("workspace-main-column")).toContainElement(
      screen.getByTestId("workspace-topbar"),
    );
    fireEvent.click(inspectorControl);
    expect(inspector).toHaveAttribute("data-collapsed", "true");
    expect(inspector).toHaveStyle({ width: "0px" });
    expect(
      screen.getByRole("button", { name: "打开右侧研究栏" }),
    ).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: "打开右侧研究栏" }));
    expect(inspector).toHaveAttribute("data-collapsed", "false");
    const openControl = screen.getByRole("button", { name: "关闭右侧研究栏" });
    expect(screen.getByTestId("conversation-main")).toContainElement(
      openControl,
    );
    expect(inspector).not.toContainElement(openControl);
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
