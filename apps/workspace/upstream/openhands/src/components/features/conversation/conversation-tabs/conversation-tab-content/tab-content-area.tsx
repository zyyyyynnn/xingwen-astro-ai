import type React from "react";

import type { WorkspacePanelTab } from "../conversation-tabs";

interface TabContentAreaProps {
  readonly activeTab: WorkspacePanelTab;
  readonly children: React.ReactNode;
}

/** OpenHands tab-content boundary; callers compose the active surface. */
export function TabContentArea({ activeTab, children }: TabContentAreaProps) {
  return (
    <div
      id={`workspace-panel-${activeTab}`}
      role="tabpanel"
      aria-labelledby={`workspace-tab-${activeTab}`}
      tabIndex={0}
      className="min-h-0 flex-1 overflow-hidden focus:outline-none"
    >
      {children}
    </div>
  );
}
