import type { DomainEntityId, RunEvent } from "@xingwen/domain";

export type ActivityEventKind =
  | "message"
  | "action"
  | "tool"
  | "progress"
  | "result"
  | "error"
  | "completion";

export type ActivityEventStatus = "pending" | "running" | "success" | "error";

export type ActivityOutcome =
  "pending" | "running" | "success" | "failed" | "cancelled" | "unsupported";

/** Public, domain-neutral activity data with immutable run traceability. */
export interface ActivityPresentationEvent {
  readonly id: string;
  readonly kind: ActivityEventKind;
  readonly title: string;
  readonly detail?: string;
  readonly status: ActivityEventStatus;
  readonly groupId?: string;
  readonly timestamp?: string;
  readonly runId: DomainEntityId;
  readonly sequence: number;
  readonly stepKey: DomainEntityId | null;
  readonly progress: number | null;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly outcome: ActivityOutcome;
}

type ActivityGroupScope = "none" | "run" | "step";

interface ActivityDefinition {
  readonly kind: ActivityEventKind;
  readonly title: string;
  readonly status: ActivityEventStatus;
  readonly outcome: ActivityOutcome;
  readonly groupScope: ActivityGroupScope;
}

function groupIdFor(
  event: RunEvent,
  scope: ActivityGroupScope,
): string | undefined {
  switch (scope) {
    case "none":
      return undefined;
    case "run":
      return `${event.runId}:run`;
    case "step":
      return `${event.runId}:${event.stepKey ?? "run"}`;
  }
}

function buildActivityEvent(
  event: RunEvent,
  definition: ActivityDefinition,
): ActivityPresentationEvent {
  const groupId = groupIdFor(event, definition.groupScope);
  const base = {
    id: `${event.runId}:${event.sequence}`,
    kind: definition.kind,
    title: definition.title,
    detail: event.publicMessage,
    status: definition.status,
    timestamp: event.occurredAt,
    runId: event.runId,
    sequence: event.sequence,
    stepKey: event.stepKey,
    progress: event.progress,
    artifactVersionIds: [...event.artifactVersionIds],
    outcome: definition.outcome,
  };

  return groupId === undefined ? base : { ...base, groupId };
}

/** Map the current exact RunEvent taxonomy; unknown types fail visibly. */
export function toActivityPresentationEvent(
  event: RunEvent,
): ActivityPresentationEvent {
  switch (event.eventType) {
    case "run.queued":
      return buildActivityEvent(event, {
        kind: "message",
        title: "Run queued",
        status: "pending",
        outcome: "pending",
        groupScope: "none",
      });
    case "run.planning":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Planning",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.fetching_data":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Fetching data",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.cleaning_data":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Cleaning data",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.searching_papers":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Searching papers",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.summarizing_papers":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Summarizing papers",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.reasoning_literature":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Reasoning over literature",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.building_graph":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "Building evidence graph",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "step.started":
      return buildActivityEvent(event, {
        kind: "action",
        title: "Step started",
        status: "running",
        outcome: "running",
        groupScope: "step",
      });
    case "step.retry_scheduled":
      return buildActivityEvent(event, {
        kind: "action",
        title: "Step retry scheduled",
        status: "pending",
        outcome: "pending",
        groupScope: "step",
      });
    case "step.completed":
      return buildActivityEvent(event, {
        kind: "result",
        title: "Step completed",
        status: "success",
        outcome: "success",
        groupScope: "step",
      });
    case "run.completed":
      return buildActivityEvent(event, {
        kind: "completion",
        title: "Run completed",
        status: "success",
        outcome: "success",
        groupScope: "none",
      });
    case "run.failed":
      return buildActivityEvent(event, {
        kind: "error",
        title: "Run failed",
        status: "error",
        outcome: "failed",
        groupScope: "none",
      });
    case "run.cancelled":
      return buildActivityEvent(event, {
        kind: "error",
        title: "Run cancelled",
        status: "error",
        outcome: "cancelled",
        groupScope: "none",
      });
    default:
      return buildActivityEvent(event, {
        kind: "error",
        title: "Unsupported activity event",
        status: "error",
        outcome: "unsupported",
        groupScope: "none",
      });
  }
}
