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
      className="relative z-[var(--oh-layer-sidebar)] h-full shrink-0 overflow-hidden border-r border-[var(--oh-border)] bg-[var(--oh-surface-muted)] transition-[width] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none"
      style={{
        width: collapsed
          ? "var(--oh-sidebar-collapsed-inline-size)"
          : "var(--oh-sidebar-expanded-inline-size)",
      }}
      aria-label="工作台侧栏"
    >
      <div className="h-full w-[var(--oh-sidebar-inner-inline-size)]">
        <SidebarRailBody
          collapsed={collapsed}
          onNewTask={onNewTask}
          canStartTask={canStartTask}
        />
      </div>
      <button
        type="button"
        className={`${SIDEBAR_ICON_BUTTON_CLASS} absolute right-[var(--oh-header-control-inset-inline)] top-[var(--oh-header-control-inset-block)] z-[var(--oh-layer-header-toggle)]`}
        aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
        aria-expanded={!collapsed}
        onClick={toggleCollapsed}
      >
        <CollapseIcon
          className="size-[var(--oh-icon-size-md)]"
          aria-hidden="true"
        />
      </button>
    </aside>
  );
}
