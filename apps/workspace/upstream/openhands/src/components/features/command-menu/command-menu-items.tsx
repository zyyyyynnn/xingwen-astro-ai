import type React from "react";
import { PanelLeft, Plus } from "lucide-react";

const ICON_SIZE = 18;

export type CommandMenuGroupId = "workspace" | "view";
export type CommandMenuItemId = "new-task" | "toggle-sidebar";

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
  newTask,
  toggleSidebar,
}: {
  readonly newTask?: () => void;
  readonly toggleSidebar: () => void;
}): CommandMenuItemDefinition[] {
  const items: CommandMenuItemDefinition[] = [];
  if (newTask) {
    items.push({
      id: "new-task",
      group: "workspace",
      title: "新建任务",
      description: "聚焦 Agent 指令输入区",
      keywords: "任务 指令 输入",
      icon: <Plus size={ICON_SIZE} />,
      perform: newTask,
    });
  }
  items.push({
    id: "toggle-sidebar",
    group: "view",
    title: "切换侧栏",
    description: "展开或收起工作台导航",
    keywords: "侧栏 导航 展开 收起",
    icon: <PanelLeft size={ICON_SIZE} />,
    perform: toggleSidebar,
  });
  return items;
}
