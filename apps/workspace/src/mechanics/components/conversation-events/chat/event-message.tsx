import type { DomainEntityId } from "@xingwen/domain";
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

/** Public research-event projection. */
export function EventMessage({
  event,
}: {
  readonly event: ActivityPresentationEvent;
  readonly onOpenArtifactVersion?: (artifactVersionId: DomainEntityId) => void;
}) {
  const hasDetails =
    Boolean(event.summary.trim()) || event.updates.length > 1 || event.details;
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
        <ChevronDown
          className="workspace-narrative-chevron xw-disclosure-chevron"
          aria-hidden="true"
        />
      ) : (
        <span
          className="workspace-narrative-disclosure-slot"
          aria-hidden="true"
        />
      )}
      <StatusIcon
        className={`workspace-narrative-icon ${isRunning ? "animate-spin motion-reduce:animate-none" : ""}`}
        aria-hidden="true"
      />
      <span className="workspace-narrative-title truncate">{event.title}</span>
    </>
  );
  if (!hasDetails) {
    return (
      <div
        className="workspace-narrative-node workspace-narrative-row"
        data-testid="event-message"
        data-event-kind={event.kind}
        data-event-status={event.status}
        role={event.status === "error" ? "alert" : undefined}
      >
        {content}
      </div>
    );
  }
  const distinctUpdates = event.updates.reduce<
    (typeof event.updates)[number][]
  >((acc, update) => {
    const last = acc.at(-1);
    if (!last || last.message.trim() !== update.message.trim()) {
      acc.push(update);
    }
    return acc;
  }, []);

  return (
    <Collapsible
      className="workspace-narrative-node"
      data-testid="event-message"
      data-event-kind={event.kind}
      data-event-status={event.status}
      role={event.status === "error" ? "alert" : undefined}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="workspace-narrative-row workspace-narrative-trigger"
        >
          {content}
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="workspace-narrative-content">
        <div role="region">
          {distinctUpdates.length <= 1 ? (
            <p>{distinctUpdates[0]?.message || event.summary}</p>
          ) : (
            <ol className="space-y-1.5 text-xs text-[var(--color-ink-secondary)]">
              {distinctUpdates.map((update, idx) => {
                const isLatest = idx === distinctUpdates.length - 1;
                return (
                  <li
                    key={update.sequence}
                    className={
                      isLatest
                        ? "font-medium leading-relaxed text-[var(--color-ink-primary)]"
                        : "leading-relaxed"
                    }
                  >
                    {update.message}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
