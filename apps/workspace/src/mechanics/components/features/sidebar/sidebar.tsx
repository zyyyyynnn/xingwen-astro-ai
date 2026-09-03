import { PanelLeftClose, PanelLeftOpen } from "@xingwen/ui/icons";

import { SidebarRailBody } from "./sidebar-rail-body";
import { useSidebarStore } from "../../../stores/sidebar-store";
import {
  SIDEBAR_ICON_BUTTON_CLASS,
  SIDEBAR_RAIL_TRANSITION_CLASS,
} from "./sidebar-layout";
import type { ResearchNavigationItem } from "../../../root";

interface SidebarProps {
  readonly projects: readonly ResearchNavigationItem[];
  readonly onOpenProject: (projectId: string) => void;
  readonly onNewResearch: () => void;
  readonly onReturnHome: () => void;
  readonly onToggleProjectPinned: (projectId: string) => void;
  readonly onRequestProjectRename: (projectId: string) => void;
  readonly onRequestProjectDelete: (projectId: string) => void;
}

export function Sidebar({
  projects,
  onOpenProject,
  onNewResearch,
  onReturnHome,
  onToggleProjectPinned,
  onRequestProjectRename,
  onRequestProjectDelete,
}: SidebarProps) {
  const collapsed = useSidebarStore((state) => state.collapsed);
  const toggleCollapsed = useSidebarStore((state) => state.toggleCollapsed);
  const CollapseIcon = collapsed ? PanelLeftOpen : PanelLeftClose;

  return (
    <aside
      className={`relative z-[var(--workspace-layer-sidebar)] h-full shrink-0 overflow-hidden border-r border-[var(--color-border)] bg-[var(--color-surface-muted)] ${SIDEBAR_RAIL_TRANSITION_CLASS}`}
      style={{
        width: collapsed
          ? "var(--workspace-sidebar-collapsed-inline-size)"
          : "var(--workspace-sidebar-expanded-inline-size)",
      }}
      aria-label="工作台侧栏"
    >
      <div className="h-full w-[var(--workspace-sidebar-inner-inline-size)]">
        <SidebarRailBody
          collapsed={collapsed}
          projects={projects}
          onOpenProject={onOpenProject}
          onNewResearch={onNewResearch}
          onReturnHome={onReturnHome}
          onToggleProjectPinned={onToggleProjectPinned}
          onRequestProjectRename={onRequestProjectRename}
          onRequestProjectDelete={onRequestProjectDelete}
        />
      </div>
      <button
        type="button"
        className={`${SIDEBAR_ICON_BUTTON_CLASS} absolute right-[var(--workspace-header-control-inset-inline)] top-[var(--workspace-header-control-inset-block)] z-[var(--workspace-layer-header-toggle)]`}
        aria-label={collapsed ? "展开侧栏" : "收起侧栏"}
        aria-expanded={!collapsed}
        onClick={toggleCollapsed}
      >
        <CollapseIcon
          className="size-[var(--icon-size-md)]"
          aria-hidden="true"
        />
      </button>
    </aside>
  );
}
