import React from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  LoaderCircle,
} from "lucide-react";

import type { ActivityPresentationEvent } from "../group-events";

interface EventGroupProps {
  readonly events: readonly ActivityPresentationEvent[];
  readonly isFinalized?: boolean;
  readonly children: React.ReactNode;
}

/** OpenHands event-group disclosure mechanics adapted to public activity data. */
export function EventGroup({
  events,
  isFinalized = false,
  children,
}: EventGroupProps) {
  const [expanded, setExpanded] = React.useState(false);
  const contentId = React.useId();
  const buttonId = `${contentId}-toggle`;

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
      ? `错误 ${errorCount}/${events.length}`
      : `${events.length} 项已完成`;
  const Chevron = expanded ? ChevronUp : ChevronDown;

  return (
    <div
      className="my-[var(--oh-space-1)] w-full py-[var(--oh-space-1)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]"
      data-testid="event-group"
    >
      <button
        id={buttonId}
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-controls={contentId}
        aria-expanded={expanded}
        aria-label={expanded ? "收起活动组" : "展开活动组"}
        data-testid="event-group-toggle"
        className="flex w-full cursor-pointer items-center justify-between gap-[var(--oh-space-2)] text-left"
      >
        {isFinalized ? (
          <span className="flex min-w-0 items-center gap-[var(--oh-space-2)] font-normal text-[var(--oh-muted)]">
            <Chevron
              className="size-[var(--oh-icon-size-md)] shrink-0"
              aria-hidden="true"
            />
            <span className="truncate">{countSummary}</span>
          </span>
        ) : (
          <>
            <span className="flex min-w-0 items-center gap-[var(--oh-space-2)] font-normal text-[var(--oh-muted)]">
              <Chevron
                className="size-[var(--oh-icon-size-md)] shrink-0"
                aria-hidden="true"
              />
              <span className="truncate">
                {latestEvent?.title ?? countSummary}
              </span>
            </span>
            <span className="flex shrink-0 items-center font-normal text-[var(--oh-muted)]">
              <span className="truncate">{countSummary}</span>
              {isRunning ? (
                <LoaderCircle
                  data-testid="spinner-icon"
                  className="ml-[var(--oh-space-2)] size-[var(--oh-icon-size-md)] animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
              ) : errorCount > 0 ? (
                <AlertCircle
                  className="ml-[var(--oh-space-2)] size-[var(--oh-icon-size-md)]"
                  aria-hidden="true"
                />
              ) : (
                <Check
                  className="ml-[var(--oh-space-2)] size-[var(--oh-icon-size-md)]"
                  aria-hidden="true"
                />
              )}
            </span>
          </>
        )}
      </button>
      {expanded ? (
        <div
          id={contentId}
          role="region"
          aria-labelledby={buttonId}
          className="mt-[var(--oh-space-2)] flex flex-col"
          data-testid="event-group-content"
        >
          {children}
        </div>
      ) : null}
    </div>
  );
}
