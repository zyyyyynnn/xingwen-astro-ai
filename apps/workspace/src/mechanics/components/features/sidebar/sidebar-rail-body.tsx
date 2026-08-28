import { useMemo, useState } from "react";

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
  Search,
  Trash2,
} from "@xingwen/ui/icons";

import type {
  ResearchNavigationItem,
  ResearchNavigationStatus,
} from "../../../root";
import { cn } from "../../../utils/utils";

import { CommandMenuTrigger } from "../command-menu/command-menu-trigger";

import {
  SIDEBAR_ICON_SLOT_CLASS,
  sidebarNavLabelClassName,
  sidebarNavListClassName,
  sidebarNavRowClassName,
} from "./sidebar-layout";

const STATUS_DOT_CLASS: Record<ResearchNavigationStatus, string> = {
  idle: "bg-muted-foreground/40",
  running: "bg-blue-500 animate-pulse",
  waiting: "bg-amber-500",
  error: "bg-red-500",
};

const STATUS_LABEL: Record<ResearchNavigationStatus, string> = {
  idle: "空闲",
  running: "运行中",
  waiting: "等待输入",
  error: "出错",
};

function statusDot(status: ResearchNavigationStatus): string {
  return STATUS_DOT_CLASS[status] ?? STATUS_DOT_CLASS.idle;
}

function statusText(status: ResearchNavigationStatus): string {
  return STATUS_LABEL[status] ?? STATUS_LABEL.idle;
}

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
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const visibleProjects = useMemo(
    () =>
      normalizedQuery === ""
        ? projects
        : projects.filter((project) =>
            project.title.toLowerCase().includes(normalizedQuery),
          ),
    [projects, normalizedQuery],
  );
  const pinnedProjects = visibleProjects
    .filter((project) => project.pinned)
    .sort((left, right) => left.title.localeCompare(right.title));
  // Recent means recent access, never updatedAt display ordering.
  const recentProjects = visibleProjects
    .filter((project) => !project.pinned)
    .sort((left, right) =>
      right.lastAccessedAt.localeCompare(left.lastAccessedAt),
    );
  const projectGroups = [
    { label: "置顶研究", projects: pinnedProjects },
    { label: "最近研究", projects: recentProjects },
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
        <div className="flex flex-col gap-[var(--oh-space-4)]">
          <div className="flex items-center gap-2 px-[var(--oh-space-2)]">
            <Search
              className="size-[var(--oh-icon-size-sm)] shrink-0 text-[var(--oh-muted)]"
              aria-hidden="true"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索研究"
              aria-label="搜索研究项目"
              data-testid="sidebar-project-search"
              className="min-w-0 flex-1 bg-transparent text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text)] outline-none placeholder:text-[var(--oh-text-dim)]"
            />
          </div>
          {projects.length === 0 ? (
            <p className="px-[var(--oh-space-2)] py-[var(--oh-space-3)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
              暂无研究项目
            </p>
          ) : visibleProjects.length === 0 ? (
            <p className="px-[var(--oh-space-2)] py-[var(--oh-space-3)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
              没有匹配的研究
            </p>
          ) : null}
          {projectGroups.map((group) => (
            <section key={group.label} aria-label={group.label}>
              <h3 className="px-[var(--oh-space-2)] pb-[var(--oh-space-1)] text-[length:var(--oh-font-size-label)] font-semibold text-[var(--oh-muted)]">
                {group.label}
              </h3>
              <div className="flex flex-col gap-[var(--oh-space-1)]">
                {group.projects.map((project) => (
                  <div
                    key={project.id}
                    className={cn(
                      "group/project flex w-full items-center rounded-[var(--oh-radius-sm)] transition-colors motion-reduce:transition-none",
                      project.current
                        ? "bg-[var(--oh-accent-muted)] text-[var(--oh-text)] font-medium"
                        : "text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]",
                    )}
                  >
                    <button
                      type="button"
                      className="flex min-w-0 flex-1 items-center gap-2 px-[var(--oh-space-2)] py-[var(--oh-space-2)] text-left"
                      aria-current={project.current ? "page" : undefined}
                      onClick={() => onOpenProject(project.id)}
                    >
                      <span
                        className={cn(
                          "size-2 shrink-0 rounded-full",
                          statusDot(project.status),
                        )}
                        aria-hidden="true"
                      />
                      <span className="sr-only">{`研究状态：${statusText(project.status)}`}</span>
                      <span className="min-w-0 flex-1 truncate text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]">
                        {project.title}
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
