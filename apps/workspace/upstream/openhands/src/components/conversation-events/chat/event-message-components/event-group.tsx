import React from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import {
  AlertCircle,
  Check,
  ChevronDown,
  LoaderCircle,
} from "@xingwen/ui/icons";

import type { ActivityPresentationEvent } from "../group-events";

interface EventGroupProps {
  readonly events: readonly ActivityPresentationEvent[];
  readonly isFinalized?: boolean;
  readonly children: React.ReactNode;
}

/** OpenHands consecutive action/observation group presentation. */
export function EventGroup({
  events,
  isFinalized = false,
  children,
}: EventGroupProps) {
  if (events.length === 0) return null;
  const pendingCount = events.filter(
    (event) => event.status === "pending" || event.status === "running",
  ).length;
  const completedCount = events.filter(
    (event) => event.status === "success",
  ).length;
  const errorCount = events.filter((event) => event.status === "error").length;
  const isRunning = pendingCount > 0;
  const latestEvent = events.at(-1);
  const countSummary = isRunning
    ? `进行中 ${completedCount}/${events.length}`
    : errorCount > 0
      ? `需要处理 ${errorCount}/${events.length}`
      : `${events.length} 项已完成`;
  return (
    <Collapsible className="oh-narrative-node" data-testid="event-group">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          data-testid="event-group-toggle"
          className="oh-narrative-row oh-narrative-trigger"
        >
          <ChevronDown
            className="oh-narrative-chevron xw-disclosure-chevron"
            aria-hidden="true"
          />
          <span className="oh-narrative-title flex items-center gap-[var(--oh-space-2)]">
            <span className="truncate">
              {isFinalized
                ? countSummary
                : (latestEvent?.title ?? countSummary)}
            </span>
            {!isFinalized ? (
              <span className="shrink-0 text-xs">{countSummary}</span>
            ) : null}
          </span>
          {!isFinalized ? (
            isRunning ? (
              <LoaderCircle className="oh-narrative-icon animate-spin motion-reduce:animate-none" />
            ) : errorCount > 0 ? (
              <AlertCircle className="oh-narrative-icon" />
            ) : (
              <Check className="oh-narrative-icon" />
            )
          ) : null}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent
        className="oh-narrative-content flex flex-col"
        data-testid="event-group-content"
      >
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
