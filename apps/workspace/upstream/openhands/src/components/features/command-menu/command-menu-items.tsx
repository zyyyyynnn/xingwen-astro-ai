import type React from "react";
import { PanelLeft } from "@xingwen/ui/icons";

export type CommandMenuGroupId = "workspace" | "view";
export type CommandMenuItemId = "toggle-sidebar";

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
  toggleSidebar,
}: {
  readonly toggleSidebar: () => void;
}): CommandMenuItemDefinition[] {
  return [
    {
      id: "toggle-sidebar",
      group: "view",
      title: "切换侧栏",
      description: "展开或收起工作台导航",
      keywords: "侧栏 导航 展开 收起",
      icon: <PanelLeft className="size-[var(--oh-icon-size-md)]" />,
      perform: toggleSidebar,
    },
  ];
}
