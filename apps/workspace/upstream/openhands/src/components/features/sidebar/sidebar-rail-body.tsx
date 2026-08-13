import {
  BrandMark,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  buttonClassName,
} from "@xingwen/ui";
import {
  Home,
  MoreHorizontal,
  Pencil,
  Pin,
  Plus,
  Trash2,
} from "@xingwen/ui/icons";

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
  readonly onReturnHome: () => void;
  readonly onToggleProjectPinned: (projectId: string) => void;
  readonly onRequestProjectRename: (projectId: string) => void;
  readonly onRequestProjectDelete: (projectId: string) => void;
}

export function SidebarRailBody({
  collapsed,
  projects,
  onOpenProject,
  onNewResearch,
  onReturnHome,
  onToggleProjectPinned,
  onRequestProjectRename,
  onRequestProjectDelete,
}: SidebarRailBodyProps) {
  const pinnedProjects = projects.filter((project) => project.pinned);
  const recentProjects = projects.filter((project) => !project.pinned);
  const projectGroups = [
    { label: "已置顶", projects: pinnedProjects },
    { label: "最近", projects: recentProjects },
  ].filter((group) => group.projects.length > 0);
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
        <div className="mt-[var(--oh-space-2)] flex flex-col gap-[var(--oh-space-3)]">
          {projects.length === 0 ? (
            <p className="px-[var(--oh-space-2)] py-[var(--oh-space-3)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
              暂无研究项目
            </p>
          ) : null}
          {projectGroups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h3 className="px-[var(--oh-space-2)] pb-[var(--oh-space-1)] text-[length:var(--oh-font-size-label)] font-medium text-[var(--oh-text-dim)]">
                {group.label}
              </h3>
              <div className="flex flex-col gap-[var(--oh-space-1)]">
                {group.projects.map((project) => (
                  <div
                    key={project.id}
                    className={cn(
                      "group/project flex w-full items-center rounded-[var(--oh-radius-sm)] transition-colors motion-reduce:transition-none",
                      project.current
                        ? "bg-[var(--oh-accent-muted)] text-[var(--oh-text)]"
                        : "text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]",
                    )}
                  >
                    <button
                      type="button"
                      className="min-w-0 flex-1 px-[var(--oh-space-2)] py-[var(--oh-space-2)] text-left"
                      aria-current={project.current ? "page" : undefined}
                      onClick={() => onOpenProject(project.id)}
                    >
                      <span className="flex min-w-0 items-center gap-[var(--oh-space-2)]">
                        <span className="truncate text-[length:var(--oh-font-size-body)] font-medium leading-[var(--oh-line-height-body)]">
                          {project.title}
                        </span>
                        {project.pinned ? (
                          <Pin
                            className="size-[var(--oh-icon-size-xs)] shrink-0"
                            aria-label="已置顶"
                          />
                        ) : null}
                      </span>
                      <span className="mt-[var(--oh-space-1)] flex min-w-0 items-center gap-[var(--oh-space-2)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
                        <span className="min-w-0 flex-1 truncate">
                          {project.status}
                        </span>
                        <time className="shrink-0" dateTime={project.updatedAt}>
                          {formatProjectUpdatedAt(project.updatedAt)}
                        </time>
                      </span>
                    </button>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        className={buttonClassName({
                          variant: "ghost",
                          size: "icon",
                          className:
                            "shrink-0 opacity-0 transition-opacity group-hover/project:opacity-100 group-focus-within/project:opacity-100 focus-visible:opacity-100 motion-reduce:transition-none",
                        })}
                        aria-label={`${project.title} 项目操作`}
                      >
                        <MoreHorizontal aria-hidden="true" />
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuGroup>
                          <DropdownMenuItem
                            onSelect={() => onToggleProjectPinned(project.id)}
                          >
                            <Pin aria-hidden="true" />
                            {project.pinned ? "取消置顶" : "置顶"}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => onRequestProjectRename(project.id)}
                          >
                            <Pencil aria-hidden="true" />
                            重命名
                          </DropdownMenuItem>
                        </DropdownMenuGroup>
                        <DropdownMenuSeparator />
                        <DropdownMenuGroup>
                          <DropdownMenuItem
                            variant="destructive"
                            onSelect={() => onRequestProjectDelete(project.id)}
                          >
                            <Trash2 aria-hidden="true" />
                            删除项目
                          </DropdownMenuItem>
                        </DropdownMenuGroup>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>

      <footer className="mt-[var(--oh-space-3)] px-[var(--oh-space-2)]">
        <button
          type="button"
          className={sidebarNavRowClassName()}
          onClick={onReturnHome}
        >
          <span className={SIDEBAR_ICON_SLOT_CLASS} aria-hidden="true">
            <Home className="size-[var(--oh-icon-size-md)]" />
          </span>
          <span className={sidebarNavLabelClassName(collapsed)}>返回首页</span>
        </button>
      </footer>
    </div>
  );
}

function formatProjectUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
  }).format(date);
}
