/**
 * Domain-neutral presentation events consumed by the OpenHands-derived
 * activity surface. Runtime adapters map domain events into this contract;
 * the presentation never receives private content.
 */
export type ActivityEventKind =
  | "message"
  | "action"
  | "tool"
  | "progress"
  | "result"
  | "error"
  | "completion";

export type ActivityEventStatus = "pending" | "running" | "success" | "error";

export interface ActivityPresentationEvent {
  readonly id: string;
  readonly kind: ActivityEventKind;
  readonly title: string;
  readonly detail?: string;
  readonly status: ActivityEventStatus;
  readonly groupId?: string;
  readonly timestamp?: string;
}

export const EVENT_GROUP_MIN_SIZE = 2;

/** Public tool/progress events retain the upstream consecutive-run grouping. */
export const isGroupableEvent = (event: ActivityPresentationEvent): boolean =>
  event.kind === "tool" || event.kind === "progress";

export type RenderedItem =
  | {
      readonly kind: "single";
      readonly event: ActivityPresentationEvent;
      readonly index: number;
    }
  | {
      readonly kind: "group";
      readonly events: ActivityPresentationEvent[];
      readonly startIndex: number;
    };

/**
 * Walk a public event stream and bucket consecutive tool/progress events into
 * collapsible groups. Non-tool events stay as individual activity items.
 */
export const groupEvents = (
  events: readonly ActivityPresentationEvent[],
  minSize: number = EVENT_GROUP_MIN_SIZE,
): RenderedItem[] => {
  if (minSize < 1) {
    throw new Error("minSize must be at least 1");
  }

  const items: RenderedItem[] = [];
  let run: {
    events: ActivityPresentationEvent[];
    startIndex: number;
  } | null = null;

  const flushRun = () => {
    if (!run) return;
    if (run.events.length >= minSize) {
      items.push({
        kind: "group",
        events: run.events,
        startIndex: run.startIndex,
      });
    } else {
      run.events.forEach((event, offset) => {
        items.push({
          kind: "single",
          event,
          index: run!.startIndex + offset,
        });
      });
    }
    run = null;
  };

  events.forEach((event, index) => {
    if (!isGroupableEvent(event)) {
      flushRun();
      items.push({ kind: "single", event, index });
      return;
    }

    const previousGroupId = run?.events[0]?.groupId;
    if (
      run &&
      previousGroupId &&
      event.groupId &&
      previousGroupId !== event.groupId
    ) {
      flushRun();
    }
    if (!run) run = { events: [], startIndex: index };
    run.events.push(event);
  });

  flushRun();
  return items;
};
