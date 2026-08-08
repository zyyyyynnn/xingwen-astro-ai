import React from "react";
import { Activity, Layers3 } from "lucide-react";

import { cn } from "../../../../utils/utils";

export type WorkspacePanelTab = "activity" | "context";

interface ConversationTabsProps {
  readonly activeTab: WorkspacePanelTab;
  readonly onSelect: (tab: WorkspacePanelTab) => void;
}

const TABS: ReadonlyArray<{
  readonly id: WorkspacePanelTab;
  readonly label: string;
  readonly icon: typeof Activity;
}> = [
  { id: "activity", label: "活动", icon: Activity },
  { id: "context", label: "上下文", icon: Layers3 },
];

export function ConversationTabs({
  activeTab,
  onSelect,
}: ConversationTabsProps) {
  const refs = React.useRef(new Map<WorkspacePanelTab, HTMLButtonElement>());

  const selectAt = (index: number) => {
    const tab = TABS[index];
    if (!tab) return;
    onSelect(tab.id);
    refs.current.get(tab.id)?.focus();
  };

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectAt((index + 1) % TABS.length);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectAt((index - 1 + TABS.length) % TABS.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      selectAt(0);
    } else if (event.key === "End") {
      event.preventDefault();
      selectAt(TABS.length - 1);
    }
  };

  return (
    <div
      role="tablist"
      aria-label="工作区面板"
      className="flex h-full min-w-0 items-stretch px-2"
    >
      {TABS.map((tab, index) => {
        const selected = tab.id === activeTab;
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            ref={(node) => {
              if (node) refs.current.set(tab.id, node);
              else refs.current.delete(tab.id);
            }}
            id={`workspace-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={`workspace-panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            className={cn(
              "relative flex min-w-0 items-center gap-2 border-0 border-b-2 px-3 text-sm font-medium",
              selected
                ? "border-[var(--oh-accent)] text-[var(--oh-text)]"
                : "border-transparent text-[var(--oh-muted)] hover:text-[var(--oh-text)]",
            )}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            <span className="truncate">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
