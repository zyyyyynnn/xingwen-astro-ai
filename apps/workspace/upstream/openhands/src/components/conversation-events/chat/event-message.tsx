import React from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  LoaderCircle,
} from "lucide-react";

import type { ActivityPresentationEvent } from "./group-events";

interface EventMessageProps {
  readonly event: ActivityPresentationEvent;
}

/** OpenHands event-item composition adapted to public Xingwen activity events. */
export function EventMessage({ event }: EventMessageProps) {
  const [expanded, setExpanded] = React.useState(false);
  const detailsId = React.useId();
  const isError = event.status === "error";
  const isRunning = event.status === "pending" || event.status === "running";
  const isSuccess = event.status === "success";
  const hasDetails = Boolean(event.detail?.trim());
  const Chevron = expanded ? ChevronUp : ChevronDown;
  const StatusIcon = isError
    ? AlertCircle
    : isRunning
      ? LoaderCircle
      : isSuccess
        ? CheckCircle2
        : Circle;

  const content = (
    <>
      <StatusIcon
        className={`size-[var(--oh-icon-size-md)] shrink-0 ${isRunning ? "animate-spin motion-reduce:animate-none" : ""}`}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1 truncate">{event.title}</span>
      {hasDetails ? (
        <Chevron
          className="size-[var(--oh-icon-size-md)] shrink-0"
          aria-hidden="true"
        />
      ) : null}
    </>
  );

  return (
    <div
      className="my-[var(--oh-space-1)] w-full text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]"
      data-testid="event-message"
      data-event-kind={event.kind}
      data-event-status={event.status}
      role={isError ? "alert" : undefined}
    >
      {hasDetails ? (
        <button
          type="button"
          className="flex w-full items-center gap-[var(--oh-space-2)] rounded-[var(--oh-radius-sm)] py-[var(--oh-space-1)] text-left text-[var(--oh-muted)] hover:text-[var(--oh-text)]"
          aria-controls={detailsId}
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          {content}
        </button>
      ) : (
        <div className="flex w-full items-center gap-[var(--oh-space-2)] py-[var(--oh-space-1)] text-[var(--oh-muted)]">
          {content}
        </div>
      )}
      {expanded ? (
        <div
          id={detailsId}
          role="region"
          className="ml-[var(--oh-space-6)] mt-[var(--oh-space-1)] border-l border-[var(--oh-border)] pl-[var(--oh-space-3)] text-[var(--oh-muted)]"
        >
          {event.detail}
        </div>
      ) : null}
    </div>
  );
}
