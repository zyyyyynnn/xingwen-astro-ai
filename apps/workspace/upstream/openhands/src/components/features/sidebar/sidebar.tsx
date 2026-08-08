import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { SidebarRailBody } from "./sidebar-rail-body";
import { useSidebarStore } from "../../../stores/sidebar-store";
import { SIDEBAR_ICON_BUTTON_CLASS } from "./sidebar-layout";

interface SidebarProps {
  readonly onNewTask: () => void;
  readonly canStartTask: boolean;
}

export function Sidebar({ onNewTask, canStartTask }: SidebarProps) {
  const collapsed = useSidebarStore((state) => state.collapsed);
  const toggleCollapsed = useSidebarStore((state) => state.toggleCollapsed);
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      className="relative z-20 h-full shrink-0 overflow-hidden border-r border-[var(--oh-border)] bg-[var(--oh-surface-muted)] transition-[width] duration-200 ease-out motion-reduce:transition-none"
      style={{ width: collapsed ? "3.5rem" : "15rem" }}
      aria-label="工作台侧栏"
    >
      <div className="h-full w-60">
        <SidebarRailBody
          collapsed={collapsed}
          onNewTask={onNewTask}
          canStartTask={canStartTask}
        />
      </div>
      <button
        type="button"
        className={`${SIDEBAR_ICON_BUTTON_CLASS} absolute right-3 top-2 z-10`}
        aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
        aria-expanded={!collapsed}
        onClick={toggleCollapsed}
      >
        <CollapseIcon className="size-4" aria-hidden="true" />
      </button>
    </aside>
  );
}
