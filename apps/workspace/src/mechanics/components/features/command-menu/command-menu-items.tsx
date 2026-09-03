import type React from "react";
import { PanelLeft } from "@xingwen/ui/icons";

import type {
  ResearchNavigationItem,
  ResearchNavigationStatus,
} from "../../../root";

export type CommandMenuGroupId = "workspace" | "view";
export type CommandMenuItemId = "toggle-sidebar";

export interface CommandMenuItemDefinition {
  readonly id: string;
  readonly group: CommandMenuGroupId;
  readonly title: string;
  readonly description: string;
  readonly keywords: string;
  readonly icon: React.ReactElement;
  readonly status?: ResearchNavigationStatus;
  readonly perform: () => void;
}

export const COMMAND_MENU_GROUP_LABELS: Record<CommandMenuGroupId, string> = {
  workspace: "研究项目",
  view: "视图",
};

export const COMMAND_MENU_GROUP_ORDER: CommandMenuGroupId[] = [
  "workspace",
  "view",
];

export const COMMAND_MENU_STATUS_LABELS: Record<
  ResearchNavigationStatus,
  string
> = {
  idle: "空闲",
  running: "运行中",
  waiting: "等待输入",
  error: "出错",
};

export function createCommandMenuItems({
  projects,
  onOpenProject,
  toggleSidebar,
}: {
  readonly projects: readonly ResearchNavigationItem[];
  readonly onOpenProject: (projectId: string) => void;
  readonly toggleSidebar: () => void;
}): CommandMenuItemDefinition[] {
  // Recent-first ordering mirrors the sidebar's Recent group.
  const orderedProjects = [...projects]
    .sort((a, b) => b.lastAccessedAt.localeCompare(a.lastAccessedAt))
    .slice(0, 12);

  const projectItems: CommandMenuItemDefinition[] = orderedProjects.map(
    (project) => ({
      id: `open-project:${project.id}`,
      group: "workspace",
      title: project.title,
      description: project.current
        ? "当前研究项目"
        : `切换到该项目 · ${COMMAND_MENU_STATUS_LABELS[project.status] ?? ""}`,
      keywords: `项目 切换 研究 ${project.title} ${COMMAND_MENU_STATUS_LABELS[project.status] ?? ""}`,
      icon: <span className="size-[var(--icon-size-md)]" aria-hidden="true" />,
      status: project.status,
      perform: () => onOpenProject(project.id),
    }),
  );

  return [
    ...projectItems,
    {
      id: "toggle-sidebar",
      group: "view",
      title: "切换侧栏",
      description: "展开或收起工作台导航",
      keywords: "侧栏 导航 展开 收起",
      icon: <PanelLeft className="size-[var(--icon-size-md)]" />,
      perform: toggleSidebar,
    },
  ];
}
