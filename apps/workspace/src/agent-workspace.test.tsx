import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CollapsibleRationale } from "../upstream/openhands/src/components/conversation-events/chat/event-message-components/collapsible-thinking";
import {
  OpenHandsWorkspaceRoot,
  type AgentWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import { useCommandMenuStore } from "../upstream/openhands/src/stores/command-menu-store";
import { useSidebarStore } from "../upstream/openhands/src/stores/sidebar-store";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
  useCommandMenuStore.setState({ isOpen: false });
  useSidebarStore.setState({ collapsed: false });
});

function readyRuntime(
  execute: AgentWorkspaceRuntime["execute"],
): AgentWorkspaceRuntime {
  return { availability: "ready", execute };
}

function enterCommand(command: string) {
  const input = screen.getByRole("textbox", { name: "向 Agent 发送指令" });
  input.textContent = command;
  fireEvent.input(input);
  return input;
}

describe("source-adopted Agent workspace mechanics", () => {
  it("opens the command menu from the keyboard and returns focus on Escape", async () => {
    render(<OpenHandsWorkspaceRoot />);
    const trigger = screen.getByRole("button", { name: "打开命令菜单" });
    trigger.focus();

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });

    const search = await screen.findByRole("combobox", { name: "搜索命令" });
    await waitFor(() => expect(search).toHaveFocus());
    fireEvent.keyDown(search, { key: "Escape" });

    await waitFor(() => {
      expect(
        screen.queryByRole("dialog", { name: "命令菜单" }),
      ).not.toBeInTheDocument();
    });
    expect(trigger).toHaveFocus();
  });

  it("switches activity tabs and resizes the split panel with the keyboard", () => {
    render(<OpenHandsWorkspaceRoot />);
    const activityTab = screen.getByRole("tab", { name: "活动" });
    activityTab.focus();
    fireEvent.keyDown(activityTab, { key: "ArrowRight" });

    const contextTab = screen.getByRole("tab", { name: "上下文" });
    expect(contextTab).toHaveAttribute("aria-selected", "true");
    expect(contextTab).toHaveFocus();
    expect(screen.getByText("暂无上下文")).toBeInTheDocument();

    const separator = screen.getByRole("separator", {
      name: "调整任务与活动面板宽度",
    });
    expect(separator).toHaveAttribute("aria-valuenow", "58");
    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(separator).toHaveAttribute("aria-valuenow", "60");
  });

  it("runs and cancels through the thin execution boundary", async () => {
    const execute = vi.fn(
      (_command: string, signal: AbortSignal) =>
        new Promise<void>((resolve) => {
          signal.addEventListener("abort", () => resolve(), { once: true });
        }),
    );
    render(<OpenHandsWorkspaceRoot runtime={readyRuntime(execute)} />);

    enterCommand("梳理公开资料");
    fireEvent.click(screen.getByRole("button", { name: "发送指令" }));

    expect(execute).toHaveBeenCalledWith(
      "梳理公开资料",
      expect.any(AbortSignal),
    );
    expect(
      await screen.findByRole("button", { name: "取消任务" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "取消任务" }));

    expect(await screen.findByText("任务已取消")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "取消任务" }),
    ).not.toBeInTheDocument();
  });

  it("surfaces an execution error and retries without duplicating the command", async () => {
    const execute = vi
      .fn<AgentWorkspaceRuntime["execute"]>()
      .mockRejectedValueOnce(new Error("连接中断"))
      .mockResolvedValueOnce();
    render(<OpenHandsWorkspaceRoot runtime={readyRuntime(execute)} />);

    enterCommand("生成任务提纲");
    fireEvent.click(screen.getByRole("button", { name: "发送指令" }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(await screen.findByText("任务已结束")).toBeInTheDocument();
    expect(execute).toHaveBeenCalledTimes(2);
    expect(screen.queryByText("生成任务提纲")).not.toBeInTheDocument();
  });

  it("keeps public rationale collapsed until explicitly disclosed", () => {
    render(
      <CollapsibleRationale summary="查看公开依据">
        <p>依据来自可审计来源。</p>
      </CollapsibleRationale>,
    );

    const toggle = screen.getByRole("button", { name: "查看公开依据" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("依据来自可审计来源。")).not.toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("依据来自可审计来源。")).toBeInTheDocument();
  });
});
