import type { ResearchThreadEntry as ResearchThreadEntryDto } from "@xingwen/contracts";
import { describe, expect, it } from "vitest";

import { mapResearchThreadEntry } from "../src/mapping";

const BASE = {
  id: "entry-1",
  project_id: "project-1",
  sequence: 1,
  actor: "assistant",
  public_content: "需要确认研究范围。",
  model_execution_id: "execution-1",
  created_at: "2026-08-12T08:00:00Z",
} as const;

describe("Research Thread transport mapping", () => {
  it("maps a clarification payload into the typed camelCase domain shape", () => {
    const entry = mapResearchThreadEntry({
      ...BASE,
      kind: "clarification_question",
      structured_payload: {
        outcome: "clarification_required",
        question_id: "question-1",
        options: ["仅公开数据"],
        warnings: [],
      },
    } as ResearchThreadEntryDto);

    expect(entry.kind).toBe("clarification_question");
    if (entry.kind !== "clarification_question") throw new Error("wrong kind");
    expect(entry.structuredPayload.questionId).toBe("question-1");
    expect(entry.structuredPayload.options).toEqual(["仅公开数据"]);
  });

  it("rejects a kind and actor mismatch instead of reinterpreting it", () => {
    expect(() =>
      mapResearchThreadEntry({
        ...BASE,
        kind: "user_message",
        structured_payload: { answer_to_question_id: null },
      } as ResearchThreadEntryDto),
    ).toThrow(/invalid actor/u);
  });
});
