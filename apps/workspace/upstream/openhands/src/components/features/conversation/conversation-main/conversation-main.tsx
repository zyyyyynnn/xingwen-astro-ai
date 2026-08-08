import React from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { CollapsibleRationale } from "../../../conversation-events/chat/event-message-components/collapsible-thinking";
import { ChatInterface } from "../../chat/chat-interface";
import { ConversationTabs } from "../conversation-tabs/conversation-tabs";
import { ResizeHandle } from "../../../ui/resize-handle";
import { useResizablePanels } from "../../../../hooks/use-resizable-panels";
import type { AgentWorkspaceRuntime } from "../../../../root";
import { cn } from "../../../../utils/utils";

type WorkspacePanel = "activity" | "context";

interface ConversationMainProps {
  readonly runtime: AgentWorkspaceRuntime;
}

/**
 * OpenHands ConversationMain with the coding/mobile content removed.
 * The split-panel, resize, panel visibility and header composition remain in
 * the upstream component boundary; Xingwen only supplies neutral surfaces and
 * the thin runtime seam.
 */
export function ConversationMain({ runtime }: ConversationMainProps) {
  const [isRightPanelShown, setIsRightPanelShown] = React.useState(true);
  const [activePanel, setActivePanel] =
    React.useState<WorkspacePanel>("activity");
  const {
    leftWidth,
    rightWidth,
    isDragging,
    containerRef,
    handleMouseDown,
    handleKeyboardResize,
  } = useResizablePanels({
    defaultLeftWidth: 58,
    minLeftWidth: 38,
    maxLeftWidth: 72,
    storageKey: "xingwen-agent-panel-width",
  });

  const toggleRightPanel = React.useCallback(() => {
    setIsRightPanelShown((shown) => !shown);
  }, []);
  const RightPanelToggleIcon = isRightPanelShown
    ? PanelRightClose
    : PanelRightOpen;

  return (
    <section
      className="relative flex h-full min-h-0 flex-col"
      aria-label="Agent 工作区"
      data-testid="conversation-main"
    >
      <button
        type="button"
        className="oh-icon-button absolute right-2 top-2 z-30"
        aria-label={isRightPanelShown ? "收起活动面板" : "展开活动面板"}
        aria-controls="workspace-activity-panel"
        aria-expanded={isRightPanelShown}
        onClick={toggleRightPanel}
      >
        <RightPanelToggleIcon className="size-4" aria-hidden="true" />
      </button>

      <div
        ref={containerRef}
        className="relative flex min-h-0 flex-1 overflow-hidden [container-type:inline-size]"
      >
        <div
          className={cn(
            "flex min-w-0 flex-col overflow-hidden bg-[var(--oh-surface)]",
            isDragging
              ? "transition-none"
              : "transition-[width] duration-200 ease-out motion-reduce:transition-none",
          )}
          aria-labelledby="agent-task-heading"
          style={{ width: isRightPanelShown ? `${leftWidth}%` : "100%" }}
        >
          <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[var(--oh-border)] py-0 pl-4 pr-12">
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <h1
                id="agent-task-heading"
                className="shrink-0 text-sm font-semibold"
              >
                研究工作台
              </h1>
              <p className="truncate text-xs text-[var(--oh-muted)]">
                {runtime.availability === "ready"
                  ? "运行服务已连接"
                  : "运行服务未连接"}
              </p>
            </div>
          </header>
          <div className="flex min-h-0 flex-1 flex-col">
            <ChatInterface runtime={runtime} />
          </div>
        </div>

        {isRightPanelShown ? (
          <ResizeHandle
            value={leftWidth}
            min={38}
            max={72}
            onMouseDown={handleMouseDown}
            onKeyboardResize={handleKeyboardResize}
            isDragging={isDragging}
          />
        ) : null}

        <aside
          id="workspace-activity-panel"
          className={cn(
            "relative min-w-0 shrink-0 overflow-hidden border-l border-[var(--oh-border)] bg-[var(--oh-surface-muted)]",
            isDragging
              ? "transition-none"
              : "transition-[width] duration-200 ease-out motion-reduce:transition-none",
            !isRightPanelShown && "pointer-events-none",
          )}
          aria-label="活动面板"
          aria-hidden={!isRightPanelShown}
          inert={!isRightPanelShown}
          style={{ width: isRightPanelShown ? `${rightWidth}%` : "0%" }}
        >
          <div
            className="absolute inset-y-0 right-0 flex min-w-0 flex-col"
            style={{ width: `${rightWidth}cqw` }}
          >
            <div className="flex h-12 shrink-0 items-center border-b border-[var(--oh-border)] pr-12">
              <ConversationTabs
                activeTab={activePanel}
                onSelect={setActivePanel}
              />
            </div>
            <div
              id={`workspace-panel-${activePanel}`}
              role="tabpanel"
              aria-labelledby={`workspace-tab-${activePanel}`}
              tabIndex={0}
              className="min-h-0 flex-1 overflow-y-auto p-5 focus:outline-none"
            >
              {activePanel === "activity" ? (
                <div className="space-y-5">
                  <div className="oh-empty-state">
                    <p className="text-sm font-semibold">尚无 Agent 活动</p>
                    <p>提交任务后，公开可审计的操作与进度会显示在这里。</p>
                  </div>
                  <CollapsibleRationale summary="查看活动公开范围">
                    这里只展示公开操作、进度、限制与可审计依据，不接收模型私有推理。
                  </CollapsibleRationale>
                </div>
              ) : (
                <div className="oh-empty-state">
                  <p className="text-sm font-semibold">暂无上下文</p>
                  <p>当前任务没有可展示的工作区上下文。</p>
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}

export default ConversationMain;
