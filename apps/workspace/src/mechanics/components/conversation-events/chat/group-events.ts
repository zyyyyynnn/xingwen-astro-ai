export type {
  ActivityOperation,
  ActivityPresentationEvent,
  ActivityPresentationUpdate,
  ActivityUpdatePhase,
} from "@xingwen/research-adapter";

import type { ActivityPresentationEvent } from "@xingwen/research-adapter";

export const EVENT_GROUP_MIN_SIZE = 2;

export const isGroupableEvent = (event: ActivityPresentationEvent): boolean =>
  event.kind === "tool";

export type RenderedItem =
  | {
      readonly kind: "single";
      readonly event: ActivityPresentationEvent;
      readonly index: number;
    }
  | {
      readonly kind: "group";
      readonly events: readonly ActivityPresentationEvent[];
      readonly startIndex: number;
    };

/** OpenHands consecutive Action/Observation grouping over research Activities. */
export function groupEvents(
  events: readonly ActivityPresentationEvent[],
  minSize: number = EVENT_GROUP_MIN_SIZE,
): RenderedItem[] {
  if (minSize < 1) throw new Error("minSize must be at least 1");
  const items: RenderedItem[] = [];
  let run: { events: ActivityPresentationEvent[]; startIndex: number } | null =
    null;

  const flushRun = () => {
    const current = run;
    if (!current) return;
    if (current.events.length >= minSize) {
      items.push({
        kind: "group",
        events: current.events,
        startIndex: current.startIndex,
      });
    } else {
      current.events.forEach((event, offset) =>
        items.push({
          kind: "single",
          event,
          index: current.startIndex + offset,
        }),
      );
    }
    run = null;
  };

  events.forEach((event, index) => {
    if (!isGroupableEvent(event)) {
      flushRun();
      items.push({ kind: "single", event, index });
      return;
    }
    if (!run) run = { events: [], startIndex: index };
    run.events.push(event);
  });
  flushRun();
  return items;
}
