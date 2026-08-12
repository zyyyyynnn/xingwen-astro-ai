import React from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import { ChevronDown, FileSearch, type LucideIcon } from "@xingwen/ui/icons";

interface NarrativeDisclosureProps {
  readonly summary: string;
  readonly meta?: string;
  readonly icon: LucideIcon;
  readonly defaultOpen?: boolean;
  readonly open?: boolean;
  readonly onOpenChange?: (open: boolean) => void;
  readonly triggerRef?: React.Ref<HTMLButtonElement>;
  readonly children: React.ReactNode;
}

/** OpenHands disclosure mechanics shared by public Agent narrative nodes. */
export function NarrativeDisclosure({
  summary,
  meta,
  icon: Icon,
  defaultOpen = false,
  open,
  onOpenChange,
  triggerRef,
  children,
}: NarrativeDisclosureProps) {
  return (
    <Collapsible
      asChild
      defaultOpen={defaultOpen}
      open={open}
      onOpenChange={onOpenChange}
    >
      <section className="oh-narrative-node">
        <CollapsibleTrigger asChild>
          <button
            ref={triggerRef}
            type="button"
            className="oh-narrative-row oh-narrative-trigger"
          >
            <ChevronDown className="oh-narrative-chevron" aria-hidden="true" />
            <Icon className="oh-narrative-icon" aria-hidden="true" />
            <span className="oh-narrative-title flex items-center gap-[var(--oh-space-2)]">
              <span className="truncate">{summary}</span>
              {meta ? (
                <span className="shrink-0 text-xs text-[var(--oh-muted)]">
                  {meta}
                </span>
              ) : null}
            </span>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent className="oh-narrative-content">
          {children}
        </CollapsibleContent>
      </section>
    </Collapsible>
  );
}

interface CollapsibleRationaleProps {
  readonly summary: string;
  readonly children: React.ReactNode;
}

/** Disclosure for public, auditable rationale only. */
export function CollapsibleRationale({
  summary,
  children,
}: CollapsibleRationaleProps) {
  return (
    <NarrativeDisclosure summary={summary} icon={FileSearch}>
      {children}
    </NarrativeDisclosure>
  );
}
