import { asEntityId } from "@xingwen/domain";
import {
  researchAdapter,
  type ActivityPresentationEvent as CanonicalActivityPresentationEvent,
} from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import type { AgentWorkspaceRuntime } from "../upstream/openhands/src/root";
import type { ActivityPresentationEvent as OpenHandsActivityPresentationEvent } from "../upstream/openhands/src/components/conversation-events/chat/group-events";

describe("Research Adapter activity compatibility", () => {
  it("accepts the canonical event in the OpenHands runtime contract", () => {
    const canonicalEvent: CanonicalActivityPresentationEvent =
      researchAdapter.toActivityPresentationEvent({
        runId: asEntityId("run_contract"),
        sequence: 1,
        eventType: asEntityId("run.queued"),
        stepKey: null,
        progress: null,
        publicMessage: "Run queued",
        artifactVersionIds: [],
        occurredAt: "2026-08-11T00:00:00Z",
      });

    const openHandsEvents: readonly OpenHandsActivityPresentationEvent[] = [
      canonicalEvent,
    ];
    const runtime: AgentWorkspaceRuntime = {
      availability: "ready",
      execute: async () => undefined,
      activityEvents: openHandsEvents,
    };

    expect(runtime.activityEvents).toEqual(openHandsEvents);
    expect(runtime.activityEvents?.[0]).toMatchObject({
      id: "run_contract:1",
      kind: "message",
      status: "pending",
      title: "Run queued",
    });
  });
});
