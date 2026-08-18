import type { DomainEntityId, RunEvent } from "@xingwen/domain";

export type ActivityEventKind = RunEvent["activityKind"];
export type ActivityEventStatus = "pending" | "running" | "success" | "error";
export type ActivityOutcome = "pending" | "running" | "success" | "failed";
export type ActivityOperation =
  | "analysis"
  | "search"
  | "data_query"
  | "document_read"
  | "evidence_validation"
  | "artifact_generation"
  | "retry"
  | "status"
  | "completion"
  | "error"
  | "tool";
export type ActivityUpdatePhase = RunEvent["activityPhase"];

export interface ActivityPresentationUpdate {
  readonly sequence: number;
  readonly phase: ActivityUpdatePhase;
  readonly message: string;
  readonly timestamp: string;
  readonly details: Readonly<Record<string, unknown>>;
}

/** Project-private Agent activity projected from the persisted Run event stream. */
export interface ActivityPresentationEvent {
  /** Stable identity across reasoning deltas and tool Action → Observation updates. */
  readonly id: string;
  readonly kind: ActivityEventKind;
  readonly operation: ActivityOperation;
  readonly title: string;
  readonly summary: string;
  readonly status: ActivityEventStatus;
  readonly groupId?: string;
  readonly timestamp: string;
  readonly runId: DomainEntityId;
  readonly sequence: number;
  readonly stepKey: DomainEntityId | null;
  readonly progress: number | null;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly outcome: ActivityOutcome;
  readonly details: Readonly<Record<string, unknown>>;
  readonly updates: readonly ActivityPresentationUpdate[];
}

const OPERATIONS = new Set<ActivityOperation>([
  "analysis",
  "search",
  "data_query",
  "document_read",
  "evidence_validation",
  "artifact_generation",
  "retry",
  "status",
  "completion",
  "error",
  "tool",
]);

function operationOf(event: RunEvent): ActivityOperation {
  const value = event.details.tool_kind;
  if (typeof value === "string" && OPERATIONS.has(value as ActivityOperation)) {
    return value as ActivityOperation;
  }
  if (event.activityKind === "reasoning") return "analysis";
  if (event.activityKind === "retry") return "retry";
  if (event.activityKind === "completion") return "completion";
  if (event.activityKind === "error") return "error";
  if (event.activityKind === "status") return "status";
  if (event.activityKind === "artifact") return "artifact_generation";
  return "tool";
}

function statusOf(phase: RunEvent["activityPhase"]): ActivityEventStatus {
  if (phase === "failed") return "error";
  if (phase === "completed") return "success";
  if (phase === "queued") return "pending";
  return "running";
}

function outcomeOf(phase: RunEvent["activityPhase"]): ActivityOutcome {
  if (phase === "failed") return "failed";
  if (phase === "completed") return "success";
  if (phase === "queued") return "pending";
  return "running";
}

export function toActivityPresentationEvent(
  event: RunEvent,
): ActivityPresentationEvent {
  const update: ActivityPresentationUpdate = {
    sequence: event.sequence,
    phase: event.activityPhase,
    message: event.content,
    timestamp: event.occurredAt,
    details: event.details,
  };
  return Object.freeze({
    id: event.activityId,
    kind: event.activityKind,
    operation: operationOf(event),
    title: event.activityName,
    summary: event.content,
    status: statusOf(event.activityPhase),
    groupId: event.stepKey ?? undefined,
    timestamp: event.occurredAt,
    runId: event.runId,
    sequence: event.sequence,
    stepKey: event.stepKey,
    progress: event.progress,
    artifactVersionIds: [...event.artifactVersionIds],
    outcome: outcomeOf(event.activityPhase),
    details: event.details,
    updates: [update],
  });
}

function mergeOne(
  previous: ActivityPresentationEvent,
  next: ActivityPresentationEvent,
): ActivityPresentationEvent {
  const updates = new Map<number, ActivityPresentationUpdate>();
  for (const update of [...previous.updates, ...next.updates]) {
    updates.set(update.sequence, update);
  }
  const latest = previous.sequence > next.sequence ? previous : next;
  const first = previous.sequence <= next.sequence ? previous : next;
  const artifactVersionIds = new Set([
    ...previous.artifactVersionIds,
    ...next.artifactVersionIds,
  ]);
  return Object.freeze({
    ...latest,
    kind:
      first.kind === "tool" &&
      (latest.kind === "observation" || latest.kind === "artifact")
        ? "tool"
        : latest.kind,
    operation:
      first.kind === "tool" &&
      (latest.kind === "observation" || latest.kind === "artifact")
        ? first.operation
        : latest.operation === "tool"
          ? first.operation
          : latest.operation,
    timestamp: first.timestamp,
    details: Object.freeze({ ...previous.details, ...next.details }),
    artifactVersionIds: [...artifactVersionIds],
    updates: [...updates.values()].sort(
      (left, right) => left.sequence - right.sequence,
    ),
  });
}

/** Fold streaming deltas and Action → Observation updates in place by identity. */
export function mergeActivityPresentationEvents(
  previous: readonly ActivityPresentationEvent[],
  incoming: readonly ActivityPresentationEvent[],
): readonly ActivityPresentationEvent[] {
  const byId = new Map(previous.map((event) => [event.id, event]));
  for (const event of incoming) {
    const existing = byId.get(event.id);
    byId.set(event.id, existing ? mergeOne(existing, event) : event);
  }
  return [...byId.values()].sort(
    (left, right) =>
      left.updates[0]!.sequence - right.updates[0]!.sequence ||
      left.id.localeCompare(right.id),
  );
}
