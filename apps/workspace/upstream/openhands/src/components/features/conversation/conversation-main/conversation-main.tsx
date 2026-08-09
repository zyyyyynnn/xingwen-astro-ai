import React from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";

import { ActivitySurface } from "../../../conversation-events/chat/messages";
import { ChatInterfaceWrapper } from "./chat-interface-wrapper";
import { ConversationNameWithStatus } from "../conversation-name-with-status";
import { ConversationTabs } from "../conversation-tabs/conversation-tabs";
import { TabContentArea } from "../conversation-tabs/conversation-tab-content/tab-content-area";
import { ResizeHandle } from "../../../ui/resize-handle";
import { useResizablePanels } from "../../../../hooks/use-resizable-panels";
import type { AgentWorkspaceRuntime } from "../../../../root";
import { cn } from "../../../../utils/utils";

type WorkspacePanel = "activity" | "context";

const DEFAULT_LEFT_PANEL_WIDTH = 58;
const MIN_LEFT_PANEL_WIDTH = 38;
const MAX_LEFT_PANEL_WIDTH = 72;

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
    defaultLeftWidth: DEFAULT_LEFT_PANEL_WIDTH,
    minLeftWidth: MIN_LEFT_PANEL_WIDTH,
    maxLeftWidth: MAX_LEFT_PANEL_WIDTH,
    storageKey: "xingwen-agent-panel-width",
  });

  const toggleRightPanel = React.useCallback(() => {
    setIsRightPanelShown((shown) => !shown);
  }, []);
  const RightPanelToggleIcon = isRightPanelShown
    ? PanelRightClose
    : PanelRightOpen;
  const contextSurface = (
    <div className="h-full overflow-y-auto p-5">
      <div className="oh-empty-state">
        <p className="text-sm font-semibold">暂无上下文</p>
        <p>当前任务没有可展示的工作区上下文。</p>
      </div>
    </div>
  );

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
            <div className="flex min-w-0 flex-1 items-center">
              <ConversationNameWithStatus runtime={runtime} />
            </div>
          </header>
          <div className="flex min-h-0 flex-1 flex-col">
            <ChatInterfaceWrapper runtime={runtime} />
          </div>
        </div>

        {isRightPanelShown ? (
          <ResizeHandle
            value={leftWidth}
            min={MIN_LEFT_PANEL_WIDTH}
            max={MAX_LEFT_PANEL_WIDTH}
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
            <TabContentArea activeTab={activePanel}>
              {activePanel === "activity" ? (
                <ActivitySurface events={runtime.activityEvents} />
              ) : (
                contextSurface
              )}
            </TabContentArea>
          </div>
        </aside>
      </div>
    </section>
  );
}

export default ConversationMain;
