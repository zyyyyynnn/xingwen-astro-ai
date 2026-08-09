import { BrandMark } from "@xingwen/ui";
import { Plus } from "lucide-react";

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
  readonly onNewTask: () => void;
  readonly canStartTask: boolean;
}

export function SidebarRailBody({
  collapsed,
  onNewTask,
  canStartTask,
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
          <BrandMark className="text-[length:var(--oh-font-size-heading)] leading-[var(--oh-line-height-heading)]" />
        </span>
      </header>

      <nav
        className={cn("mt-[var(--oh-space-4)]", sidebarNavListClassName())}
        aria-label="工作台导航"
      >
        <button
          type="button"
          className={sidebarNavRowClassName()}
          aria-label="新建任务"
          disabled={!canStartTask}
          onClick={onNewTask}
        >
          <span className={SIDEBAR_ICON_SLOT_CLASS} aria-hidden="true">
            <Plus className="size-[var(--oh-icon-size-md)]" />
          </span>
          <span className={sidebarNavLabelClassName(collapsed)}>新建任务</span>
        </button>
        <CommandMenuTrigger collapsed={collapsed} />
      </nav>

      <section
        className={cn(
          "mt-[var(--oh-space-6)] min-h-0 flex-1 overflow-y-auto px-[var(--oh-space-4)]",
          collapsed && "invisible",
        )}
        aria-label="任务列表"
      >
        <h2 className="truncate text-[length:var(--oh-font-size-label)] font-semibold tracking-wide text-[var(--oh-muted)]">
          任务
        </h2>
        <p className="mt-[var(--oh-space-3)] truncate text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-text-dim)]">
          没有任务记录
        </p>
      </section>
    </div>
  );
}
