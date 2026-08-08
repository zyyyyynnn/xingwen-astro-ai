import React from "react";
import { Activity, Layers3, MoreHorizontal } from "lucide-react";

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

const TAB_STORAGE_KEY = "xingwen-workspace-panel-tab";

function readStoredTab(): WorkspacePanelTab {
  if (typeof window === "undefined") return "activity";
  const stored = window.localStorage.getItem(TAB_STORAGE_KEY);
  return stored === "context" ? "context" : "activity";
}

export function ConversationTabs({
  activeTab,
  onSelect,
}: ConversationTabsProps) {
  const refs = React.useRef(new Map<WorkspacePanelTab, HTMLButtonElement>());
  const rowRef = React.useRef<HTMLDivElement>(null);
  const measureRowRef = React.useRef<HTMLDivElement>(null);
  const [inlineTabCount, setInlineTabCount] = React.useState(TABS.length);
  const [isMoreOpen, setIsMoreOpen] = React.useState(false);

  React.useEffect(() => {
    const stored = readStoredTab();
    if (stored !== activeTab) onSelect(stored);
    // The parent owns the active tab; restoring it once is the only side effect
    // this adopted tab strip needs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  React.useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(TAB_STORAGE_KEY, activeTab);
    }
  }, [activeTab]);

  React.useLayoutEffect(() => {
    const row = rowRef.current;
    const measureRow = measureRowRef.current;
    if (!row || !measureRow) return undefined;

    const measure = () => {
      const width = row.getBoundingClientRect().width;
      const buttons = Array.from(
        measureRow.querySelectorAll<HTMLButtonElement>(
          '[data-tab-measure="true"]',
        ),
      );
      if (width === 0 || buttons.length === 0) return;
      const moreWidth = 36;
      const gap = 4;
      let count = buttons.length;
      let used = moreWidth;
      for (let index = 0; index < buttons.length; index += 1) {
        const button = buttons[index];
        if (!button) break;
        used += button.getBoundingClientRect().width;
        if (index > 0) used += gap;
        if (used > width) {
          count = Math.max(1, index);
          break;
        }
      }
      setInlineTabCount((current) => (current === count ? current : count));
    };

    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, []);

  const inlineTabs = TABS.slice(0, inlineTabCount);
  const overflowTabs = TABS.slice(inlineTabCount);

  const selectAt = (index: number) => {
    const tab = TABS[index];
    if (!tab) return;
    onSelect(tab.id);
    setIsMoreOpen(false);
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
      ref={rowRef}
      role="tablist"
      aria-label="工作区面板"
      className="relative flex h-full min-w-0 flex-1 items-stretch px-2"
    >
      <div
        ref={measureRowRef}
        aria-hidden="true"
        className="pointer-events-none absolute left-[-10000px] top-0 flex items-center gap-1"
      >
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            data-tab-measure="true"
            className="flex gap-2 px-3 text-sm font-medium"
          >
            <Icon className="size-4" aria-hidden="true" />
            {label}
          </button>
        ))}
      </div>

      {inlineTabs.map((tab) => {
        const index = TABS.indexOf(tab);
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

      {overflowTabs.length > 0 ? (
        <div className="relative shrink-0">
          <button
            type="button"
            className="oh-icon-button h-full"
            aria-label="更多面板"
            aria-expanded={isMoreOpen}
            onClick={() => setIsMoreOpen((open) => !open)}
          >
            <MoreHorizontal className="size-4" aria-hidden="true" />
          </button>
          {isMoreOpen ? (
            <div
              className="absolute right-0 top-full z-20 min-w-32 border border-[var(--oh-border-strong)] bg-[var(--oh-surface)] p-1 shadow-[var(--oh-shadow-float)]"
              role="menu"
            >
              {overflowTabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={tab.id === activeTab}
                    className="flex w-full items-center gap-2 rounded-[var(--oh-radius-sm)] px-2 py-1.5 text-left text-sm text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]"
                    onClick={() => onSelect(tab.id)}
                  >
                    <Icon className="size-4" aria-hidden="true" />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
