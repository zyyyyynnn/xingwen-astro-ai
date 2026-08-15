import type { ResearchThreadEntryViewModel } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import {
  groupThreadProjections,
  threadProjectionInsertionIndex,
} from "./research-thread";

function entry(id: string, createdAt: string): ResearchThreadEntryViewModel {
  return {
    id,
    projectId: "project-1",
    sequence: Number(id.at(-1)),
    kind: "user_message",
    actor: "user",
    publicContent: id,
    structuredPayload: { answerToQuestionId: null },
    modelExecutionId: null,
    createdAt,
  } as ResearchThreadEntryViewModel;
}

describe("Thread projections", () => {
  it("keeps a run projection before later Thread messages", () => {
    const entries = [
      entry("entry-1", "2026-08-12T08:00:00Z"),
      entry("entry-2", "2026-08-12T08:10:00Z"),
      entry("entry-3", "2026-08-12T08:30:00Z"),
    ];

    expect(
      threadProjectionInsertionIndex(entries, "2026-08-12T08:20:00Z"),
    ).toBe(2);
  });

  it("orders process and artifact projections on the same timeline", () => {
    const entries = [
      entry("entry-1", "2026-08-12T08:00:00Z"),
      entry("entry-2", "2026-08-12T08:30:00Z"),
    ];
    const groups = groupThreadProjections(entries, [
      {
        id: "artifact",
        occurredAt: "2026-08-12T08:20:00Z",
        node: "artifact",
      },
      {
        id: "process",
        occurredAt: "2026-08-12T08:10:00Z",
        node: "process",
      },
    ]);

    expect(groups.get(1)?.map((projection) => projection.id)).toEqual([
      "process",
      "artifact",
    ]);
  });
});
