import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  LoaderCircle,
} from "@xingwen/ui/icons";

import type { ActivityPresentationEvent } from "./group-events";

/** OpenHands GenericEventMessage interaction over a public research event. */
export function EventMessage({
  event,
}: {
  readonly event: ActivityPresentationEvent;
}) {
  const hasDetails = Boolean(event.detail?.trim());
  const isRunning = event.status === "pending" || event.status === "running";
  const StatusIcon =
    event.status === "error"
      ? AlertCircle
      : isRunning
        ? LoaderCircle
        : CheckCircle2;
  const content = (
    <>
      {hasDetails ? (
        <ChevronDown className="oh-narrative-chevron" aria-hidden="true" />
      ) : (
        <span className="oh-narrative-disclosure-slot" aria-hidden="true" />
      )}
      <StatusIcon
        className={`oh-narrative-icon ${isRunning ? "animate-spin motion-reduce:animate-none" : ""}`}
        aria-hidden="true"
      />
      <span className="oh-narrative-title truncate">{event.title}</span>
    </>
  );
  if (!hasDetails) {
    return (
      <div
        className="oh-narrative-node oh-narrative-row"
        data-testid="event-message"
        data-event-kind={event.kind}
        data-event-status={event.status}
        role={event.status === "error" ? "alert" : undefined}
      >
        {content}
      </div>
    );
  }
  return (
    <Collapsible
      className="oh-narrative-node"
      data-testid="event-message"
      data-event-kind={event.kind}
      data-event-status={event.status}
      role={event.status === "error" ? "alert" : undefined}
    >
      <CollapsibleTrigger asChild>
        <button type="button" className="oh-narrative-row oh-narrative-trigger">
          {content}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="oh-narrative-content">
        <div role="region">{event.detail}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}
