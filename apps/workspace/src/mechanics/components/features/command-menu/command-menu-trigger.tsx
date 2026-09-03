import { Search } from "@xingwen/ui/icons";

import { cn } from "../../../utils/utils";
import {
  SIDEBAR_ICON_SLOT_CLASS,
  sidebarNavLabelClassName,
  sidebarNavRowClassName,
} from "../sidebar/sidebar-layout";
import { useCommandMenuStore } from "../../../stores/command-menu-store";

interface CommandMenuTriggerProps {
  readonly collapsed: boolean;
}

export function CommandMenuTrigger({ collapsed }: CommandMenuTriggerProps) {
  const open = useCommandMenuStore((state) => state.open);

  return (
    <button
      type="button"
      data-testid="command-menu-trigger"
      aria-label="打开命令菜单"
      onClick={open}
      className={sidebarNavRowClassName()}
    >
      <span className={SIDEBAR_ICON_SLOT_CLASS} aria-hidden="true">
        <Search className="size-[var(--icon-size-md)]" />
      </span>
      <span className={sidebarNavLabelClassName(collapsed)}>命令菜单</span>
      <kbd
        className={cn(
          "ml-auto rounded-[var(--radius-xs)] border border-[var(--color-border)] px-[var(--space-2)] py-[var(--space-1)] text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] text-[var(--color-ink-tertiary)]",
          collapsed && "invisible",
        )}
      >
        Ctrl K
      </kbd>
    </button>
  );
}
