import { CollapsibleRationale } from "../../../../conversation-events/chat/event-message-components/collapsible-thinking";

import type { WorkspacePanelTab } from "../conversation-tabs";

interface TabContentAreaProps {
  readonly activeTab: WorkspacePanelTab;
}

/** OpenHands tab-content boundary with only public activity/context surfaces retained. */
export function TabContentArea({ activeTab }: TabContentAreaProps) {
  return (
    <div
      id={`workspace-panel-${activeTab}`}
      role="tabpanel"
      aria-labelledby={`workspace-tab-${activeTab}`}
      tabIndex={0}
      className="min-h-0 flex-1 overflow-y-auto p-5 focus:outline-none"
    >
      {activeTab === "activity" ? (
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
  );
}
