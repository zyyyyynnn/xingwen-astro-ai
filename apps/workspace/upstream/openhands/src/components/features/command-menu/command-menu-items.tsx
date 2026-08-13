import type React from "react";
import { PanelLeft, Plus } from "@xingwen/ui/icons";

export type CommandMenuGroupId = "workspace" | "view";
export type CommandMenuItemId = "new-research" | "toggle-sidebar";

export interface CommandMenuItemDefinition {
  readonly id: CommandMenuItemId;
  readonly group: CommandMenuGroupId;
  readonly title: string;
  readonly description: string;
  readonly keywords: string;
  readonly icon: React.ReactElement;
  readonly perform: () => void;
}

export const COMMAND_MENU_GROUP_LABELS: Record<CommandMenuGroupId, string> = {
  workspace: "工作区",
  view: "视图",
};

export const COMMAND_MENU_GROUP_ORDER: CommandMenuGroupId[] = [
  "workspace",
  "view",
];

export function createCommandMenuItems({
  newResearch,
  toggleSidebar,
}: {
  readonly newResearch?: () => void;
  readonly toggleSidebar: () => void;
}): CommandMenuItemDefinition[] {
  const items: CommandMenuItemDefinition[] = [];
  if (newResearch) {
    items.push({
      id: "new-research",
      group: "workspace",
      title: "新建研究项目",
      description: "在当前工作台创建并进入新研究",
      keywords: "新建 研究 项目",
      icon: <Plus className="size-[var(--oh-icon-size-md)]" />,
      perform: newResearch,
    });
  }
  items.push({
    id: "toggle-sidebar",
    group: "view",
    title: "切换侧栏",
    description: "展开或收起工作台导航",
    keywords: "侧栏 导航 展开 收起",
    icon: <PanelLeft className="size-[var(--oh-icon-size-md)]" />,
    perform: toggleSidebar,
  });
  return items;
}
