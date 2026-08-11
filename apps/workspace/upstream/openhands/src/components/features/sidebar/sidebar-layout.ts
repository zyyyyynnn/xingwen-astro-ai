import { buttonClassName } from "@xingwen/ui";

import { cn } from "../../../utils/utils";

export const navInteractiveTransitionClassName =
  "transition-colors duration-[var(--oh-motion-navigation)] motion-reduce:transition-none";

export const SIDEBAR_ICON_SLOT_CLASS =
  "flex h-[var(--oh-sidebar-row-block-size)] w-[var(--oh-sidebar-icon-slot-inline-size)] shrink-0 items-center justify-center";

export const SIDEBAR_COLLAPSED_ICON_SLOT_CLASS =
  "relative h-[var(--oh-sidebar-row-block-size)] min-h-[var(--oh-sidebar-row-block-size)] w-[var(--oh-sidebar-icon-slot-inline-size)] shrink-0";

export function sidebarNavListClassName(): string {
  return "flex w-full shrink-0 flex-col gap-[var(--oh-space-1)] px-[var(--oh-space-2)]";
}

export function sidebarNavRowClassName(): string {
  return cn(
    "group flex h-[var(--oh-sidebar-row-block-size)] min-h-[var(--oh-sidebar-row-block-size)] w-full min-w-0 items-center gap-[var(--oh-space-2)] rounded-[var(--oh-radius-sm)] px-[var(--oh-space-3)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]",
    navInteractiveTransitionClassName,
    "text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]",
    "disabled:text-[var(--oh-text-dim)] disabled:hover:bg-transparent disabled:hover:text-[var(--oh-text-dim)]",
  );
}

export function sidebarCollapsedIconBgClassName(active: boolean): string {
  return cn(
    "pointer-events-none absolute inset-0 rounded-[var(--oh-radius-sm)]",
    active
      ? "bg-[var(--oh-accent-muted)]"
      : "bg-transparent group-hover:bg-[var(--oh-surface-raised)]",
  );
}

export function sidebarCollapsedIconGlyphClassName(active: boolean): string {
  return cn(
    "relative z-[1] flex h-full w-full items-center justify-center",
    active ? "text-[var(--oh-text)]" : "text-[var(--oh-muted)]",
  );
}

export function sidebarNavLabelClassName(collapsed: boolean): string {
  return cn("min-w-0 truncate whitespace-nowrap", collapsed && "invisible");
}

export const SIDEBAR_ICON_BUTTON_CLASS = buttonClassName({
  variant: "ghost",
  size: "icon",
  className: navInteractiveTransitionClassName,
});
