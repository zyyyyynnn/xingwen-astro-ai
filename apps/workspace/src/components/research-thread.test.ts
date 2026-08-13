import type { ResearchThreadEntryViewModel } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { processProjectionInsertionIndex } from "./research-thread";

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

describe("processProjectionInsertionIndex", () => {
  it("keeps a run projection before later Thread messages", () => {
    const entries = [
      entry("entry-1", "2026-08-12T08:00:00Z"),
      entry("entry-2", "2026-08-12T08:10:00Z"),
      entry("entry-3", "2026-08-12T08:30:00Z"),
    ];

    expect(
      processProjectionInsertionIndex(entries, "2026-08-12T08:20:00Z"),
    ).toBe(2);
  });
});
