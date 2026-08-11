import { BrandMark } from "@xingwen/ui";
import { LogOut, Plus } from "@xingwen/ui/icons";

import type { ResearchNavigationItem } from "../../../root";
import { cn } from "../../../utils/utils";

import { CommandMenuTrigger } from "../command-menu/command-menu-trigger";

import {
  SIDEBAR_ICON_SLOT_CLASS,
  sidebarNavLabelClassName,
  sidebarNavListClassName,
  sidebarNavRowClassName,
} from "./sidebar-layout";

interface SidebarRailBodyProps {
  readonly collapsed: boolean;
  readonly projects: readonly ResearchNavigationItem[];
  readonly onOpenProject: (projectId: string) => void;
  readonly onNewResearch: () => void;
  readonly onLogout: () => void;
}

export function SidebarRailBody({
  collapsed,
  projects,
  onOpenProject,
  onNewResearch,
  onLogout,
}: SidebarRailBodyProps) {
  return (
    <div className="flex h-full min-h-0 flex-col pb-[var(--oh-space-3)]">
      <header className="relative flex h-[var(--oh-header-block-size)] shrink-0 items-center border-b border-[var(--oh-border)] px-[var(--oh-header-inline-padding)]">
        <span
          className={cn(
            "min-w-0 overflow-hidden whitespace-nowrap",
            collapsed && "invisible",
          )}
        >
          <BrandMark className="text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]" />
        </span>
      </header>

      <nav
        className={cn("mt-[var(--oh-space-4)]", sidebarNavListClassName())}
        aria-label="工作台导航"
      >
        <button
          type="button"
          className={sidebarNavRowClassName()}
          aria-label="新建研究"
          onClick={onNewResearch}
        >
          <span className={SIDEBAR_ICON_SLOT_CLASS} aria-hidden="true">
            <Plus className="size-[var(--oh-icon-size-md)]" />
          </span>
          <span className={sidebarNavLabelClassName(collapsed)}>新建研究</span>
        </button>
        <CommandMenuTrigger collapsed={collapsed} />
      </nav>

      <section
        className={cn(
          "mt-[var(--oh-space-6)] min-h-0 flex-1 overflow-y-auto px-[var(--oh-space-3)]",
          collapsed && "invisible",
        )}
        aria-label="研究项目列表"
      >
        <h2 className="px-[var(--oh-space-2)] text-[length:var(--oh-font-size-label)] font-semibold text-[var(--oh-muted)]">
          研究项目
        </h2>
        <div className="mt-[var(--oh-space-2)] flex flex-col gap-[var(--oh-space-1)]">
          {projects.length === 0 ? (
            <p className="px-[var(--oh-space-2)] py-[var(--oh-space-3)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
              暂无研究项目
            </p>
          ) : null}
          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              className={cn(
                "w-full rounded-[var(--oh-radius-sm)] px-[var(--oh-space-2)] py-[var(--oh-space-2)] text-left transition-colors motion-reduce:transition-none",
                project.current
                  ? "bg-[var(--oh-accent-muted)] text-[var(--oh-text)]"
                  : "text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]",
              )}
              aria-current={project.current ? "page" : undefined}
              onClick={() => onOpenProject(project.id)}
            >
              <span className="block truncate text-[length:var(--oh-font-size-body)] font-medium leading-[var(--oh-line-height-body)]">
                {project.title}
              </span>
              <span className="mt-[var(--oh-space-1)] block truncate text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
                {project.status}
              </span>
            </button>
          ))}
        </div>
      </section>

      <footer className="mt-[var(--oh-space-3)] px-[var(--oh-space-2)]">
        <button
          type="button"
          className={sidebarNavRowClassName()}
          onClick={onLogout}
        >
          <span className={SIDEBAR_ICON_SLOT_CLASS} aria-hidden="true">
            <LogOut className="size-[var(--oh-icon-size-md)]" />
          </span>
          <span className={sidebarNavLabelClassName(collapsed)}>退出系统</span>
        </button>
      </footer>
    </div>
  );
}
