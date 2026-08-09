import type React from "react";
import type { LucideIcon } from "lucide-react";

import { cn } from "../../../../utils/utils";

interface ConversationTabNavProps {
  readonly id: string;
  readonly label: string;
  readonly icon: LucideIcon;
  readonly isActive: boolean;
  readonly onClick: () => void;
  readonly onKeyDown: (event: React.KeyboardEvent<HTMLButtonElement>) => void;
  readonly buttonRef: (node: HTMLButtonElement | null) => void;
  readonly measureOnly?: boolean;
}

/** OpenHands tab-nav boundary with neutral Xingwen tab definitions. */
export function ConversationTabNav({
  id,
  label,
  icon: Icon,
  isActive,
  onClick,
  onKeyDown,
  buttonRef,
  measureOnly = false,
}: ConversationTabNavProps) {
  return (
    <button
      ref={buttonRef}
      type="button"
      role={measureOnly ? undefined : "tab"}
      aria-selected={measureOnly ? undefined : isActive}
      aria-controls={measureOnly ? undefined : `workspace-panel-${id}`}
      tabIndex={measureOnly ? -1 : isActive ? 0 : -1}
      data-tab-measure={measureOnly ? "true" : undefined}
      id={measureOnly ? undefined : `workspace-tab-${id}`}
      className={cn(
        "relative flex min-w-0 items-center gap-[var(--oh-space-2)] border-0 border-b-2 px-[var(--oh-space-3)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] font-medium",
        isActive
          ? "border-[var(--oh-accent)] text-[var(--oh-text)]"
          : "border-transparent text-[var(--oh-muted)] hover:text-[var(--oh-text)]",
      )}
      onClick={onClick}
      onKeyDown={onKeyDown}
    >
      <Icon
        className="size-[var(--oh-icon-size-md)] shrink-0"
        aria-hidden="true"
      />
      <span className="truncate">{label}</span>
    </button>
  );
}
