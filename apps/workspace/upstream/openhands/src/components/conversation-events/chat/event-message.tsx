import React from "react";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Circle,
  LoaderCircle,
} from "lucide-react";

import type { PublicActivityEvent } from "./group-events";

interface EventMessageProps {
  readonly event: PublicActivityEvent;
}

/** OpenHands event-item composition adapted to public Xingwen activity events. */
export function EventMessage({ event }: EventMessageProps) {
  const [expanded, setExpanded] = React.useState(false);
  const detailsId = React.useId();
  const isError = event.status === "error" || event.kind === "error";
  const isRunning = event.status === "pending" || event.status === "running";
  const isSuccess = event.status === "success" || event.kind === "completion";
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
        className={`size-4 shrink-0 ${isRunning ? "animate-spin" : ""}`}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1 truncate">{event.title}</span>
      {hasDetails ? (
        <Chevron className="size-4 shrink-0" aria-hidden="true" />
      ) : null}
    </>
  );

  return (
    <div
      className="my-1 w-full text-sm"
      data-testid="event-message"
      data-event-kind={event.kind}
      data-event-status={event.status ?? "pending"}
      role={isError ? "alert" : undefined}
    >
      {hasDetails ? (
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-[var(--oh-radius-sm)] py-1 text-left text-[var(--oh-muted)] hover:text-[var(--oh-text)]"
          aria-controls={detailsId}
          aria-expanded={expanded}
          onClick={() => setExpanded((current) => !current)}
        >
          {content}
        </button>
      ) : (
        <div className="flex w-full items-center gap-2 py-1 text-[var(--oh-muted)]">
          {content}
        </div>
      )}
      {expanded ? (
        <div
          id={detailsId}
          role="region"
          className="ml-6 mt-1 border-l border-[var(--oh-border)] pl-3 text-[var(--oh-muted)]"
        >
          {event.detail}
        </div>
      ) : null}
    </div>
  );
}
