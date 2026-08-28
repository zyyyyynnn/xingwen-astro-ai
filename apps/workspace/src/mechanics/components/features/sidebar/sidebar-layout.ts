import { buttonClassName } from "@xingwen/ui";

import { cn } from "../../../utils/utils";

export const navInteractiveTransitionClassName =
  "transition-colors duration-[var(--workspace-motion-navigation)] motion-reduce:transition-none";

export const SIDEBAR_RAIL_TRANSITION_CLASS =
  "transition-[width,border-color] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none";

export const SIDEBAR_ICON_SLOT_CLASS =
  "flex h-[var(--workspace-sidebar-row-block-size)] w-[var(--workspace-sidebar-icon-slot-inline-size)] shrink-0 items-center justify-center";

export const SIDEBAR_COLLAPSED_ICON_SLOT_CLASS =
  "relative h-[var(--workspace-sidebar-row-block-size)] min-h-[var(--workspace-sidebar-row-block-size)] w-[var(--workspace-sidebar-icon-slot-inline-size)] shrink-0";

export function sidebarNavListClassName(): string {
  return "flex w-full shrink-0 flex-col gap-[var(--space-1)] px-[var(--space-2)]";
}

export function sidebarNavRowClassName(): string {
  return cn(
    "group flex h-[var(--workspace-sidebar-row-block-size)] min-h-[var(--workspace-sidebar-row-block-size)] w-full min-w-0 items-center gap-[var(--space-2)] rounded-[var(--radius-sm)] px-[var(--space-3)] text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)]",
    navInteractiveTransitionClassName,
    "text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink-primary)]",
    "disabled:text-[var(--color-ink-tertiary)] disabled:hover:bg-transparent disabled:hover:text-[var(--color-ink-tertiary)]",
  );
}

export function sidebarCollapsedIconBgClassName(active: boolean): string {
  return cn(
    "pointer-events-none absolute inset-0 rounded-[var(--radius-sm)]",
    active
      ? "bg-[var(--color-brand-muted)]"
      : "bg-transparent group-hover:bg-[var(--color-surface-hover)]",
  );
}

export function sidebarCollapsedIconGlyphClassName(active: boolean): string {
  return cn(
    "relative z-[1] flex h-full w-full items-center justify-center",
    active
      ? "text-[var(--color-ink-primary)]"
      : "text-[var(--color-ink-secondary)]",
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
