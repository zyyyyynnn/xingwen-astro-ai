import { asEntityId, type RunEvent } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { toActivityPresentationEvent } from "./activity";

const runId = asEntityId("run_activity");
const artifactVersionIds = [
  asEntityId("version_a"),
  asEntityId("version_b"),
] as const;

function event(eventType: string, sequence = 7): RunEvent {
  return {
    runId,
    sequence,
    eventType: asEntityId(eventType),
    stepKey: asEntityId("step_data"),
    progress: 42,
    publicMessage: "Public activity message",
    artifactVersionIds,
    occurredAt: "2026-08-11T00:08:00Z",
  };
}

describe("RunEvent to public ActivityPresentationEvent", () => {
  it("maps every current producer taxonomy entry explicitly", () => {
    const expected = new Map([
      ["run.queued", ["message", "pending", "pending"]],
      ["run.planning", ["progress", "running", "running"]],
      ["run.fetching_data", ["progress", "running", "running"]],
      ["run.cleaning_data", ["progress", "running", "running"]],
      ["run.searching_papers", ["progress", "running", "running"]],
      ["run.summarizing_papers", ["progress", "running", "running"]],
      ["run.reasoning_literature", ["progress", "running", "running"]],
      ["run.building_graph", ["progress", "running", "running"]],
      ["step.started", ["action", "running", "running"]],
      ["step.retry_scheduled", ["action", "pending", "pending"]],
      ["step.completed", ["result", "success", "success"]],
      ["run.completed", ["completion", "success", "success"]],
      ["run.failed", ["error", "error", "failed"]],
      ["run.cancelled", ["error", "error", "cancelled"]],
    ] as const);

    for (const [eventType, [kind, status, outcome]] of expected) {
      const result = toActivityPresentationEvent(event(eventType));

      expect(result.kind).toBe(kind);
      expect(result.status).toBe(status);
      expect(result.outcome).toBe(outcome);
      expect(result.runId).toBe(runId);
      expect(result.sequence).toBe(7);
      expect(result.id).toBe("run_activity:7");
      expect(result.timestamp).toBe("2026-08-11T00:08:00Z");
      expect(result.stepKey).toBe(asEntityId("step_data"));
      expect(result.progress).toBe(42);
      expect(result.artifactVersionIds).toEqual(artifactVersionIds);
      expect(result.detail).toBe("Public activity message");
    }
  });

  it("keeps failed and cancelled distinct from success", () => {
    expect(toActivityPresentationEvent(event("run.failed")).outcome).toBe(
      "failed",
    );
    expect(toActivityPresentationEvent(event("run.cancelled")).outcome).toBe(
      "cancelled",
    );
    expect(toActivityPresentationEvent(event("run.failed")).status).toBe(
      "error",
    );
  });

  it("fails visibly for an unknown event without exposing raw payload", () => {
    const result = toActivityPresentationEvent(
      event("run.future_private_event"),
    );

    expect(result.outcome).toBe("unsupported");
    expect(result.status).toBe("error");
    expect(result.kind).toBe("error");
    expect(result.title).toBe("暂无法显示此运行事件");
    expect(result.detail).toBe("Public activity message");
    expect(JSON.stringify(result)).not.toContain("future_private_event");
  });

  it("uses deterministic identity and preserves event ordering context", () => {
    const input = event("step.completed", 11);
    const first = toActivityPresentationEvent(input);
    const second = toActivityPresentationEvent(input);

    expect(first).toEqual(second);
    expect(first.id).toBe("run_activity:11");
    expect(first.artifactVersionIds).toEqual(["version_a", "version_b"]);
    expect(first.groupId).toBe("run_activity:step_data");
  });

  it("uses deterministic run and step grouping scopes", () => {
    expect(toActivityPresentationEvent(event("run.planning")).groupId).toBe(
      "run_activity:run",
    );
    expect(toActivityPresentationEvent(event("run.completed")).groupId).toBe(
      undefined,
    );
  });
});
