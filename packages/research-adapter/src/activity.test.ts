import { asEntityId, type RunEvent } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import {
  mergeActivityPresentationEvents,
  toActivityPresentationEvent,
} from "./activity";

const runId = asEntityId("run_activity");

function event(sequence: number, overrides: Partial<RunEvent> = {}): RunEvent {
  return {
    runId,
    sequence,
    activityId: "tool:paper-search",
    activityKind: "tool",
    activityPhase: "running",
    activityName: "检索研究论文",
    stepKey: asEntityId("searching_papers"),
    progress: 40,
    content: "正在检索研究论文。",
    details: { tool_name: "search_research_papers", tool_kind: "search" },
    artifactVersionIds: [],
    occurredAt: `2026-08-11T00:08:0${String(sequence)}Z`,
    ...overrides,
  };
}

describe("RunEvent Activity projection", () => {
  it("projects server-owned Agent semantics without rewriting content", () => {
    expect(toActivityPresentationEvent(event(1))).toMatchObject({
      id: "tool:paper-search",
      kind: "tool",
      operation: "search",
      title: "检索研究论文",
      summary: "正在检索研究论文。",
      status: "running",
      outcome: "running",
    });
  });

  it("folds Action, Observation and artifact commit into one row", () => {
    const projected = [
      event(1),
      event(2, {
        activityKind: "observation",
        content: "已检索 10 篇候选论文。",
        details: {
          tool_name: "search_research_papers",
          tool_kind: "search",
          result: { candidate_count: 10 },
        },
      }),
      event(3, {
        activityKind: "artifact",
        activityPhase: "completed",
        content: "论文集合已生成。",
        artifactVersionIds: [asEntityId("version-paper-collection")],
      }),
    ].map(toActivityPresentationEvent);

    const [activity] = mergeActivityPresentationEvents([], projected);

    expect(activity).toMatchObject({
      id: "tool:paper-search",
      kind: "tool",
      operation: "search",
      status: "success",
      sequence: 3,
      timestamp: "2026-08-11T00:08:01Z",
    });
    expect(activity?.updates.map((update) => update.phase)).toEqual([
      "running",
      "running",
      "completed",
    ]);
    expect(activity?.artifactVersionIds).toEqual(["version-paper-collection"]);
  });

  it("replaces streaming reasoning in place while retaining update order", () => {
    const result = mergeActivityPresentationEvents(
      [],
      [
        event(1, {
          activityId: "reasoning:1",
          activityKind: "reasoning",
          activityPhase: "streaming",
          activityName: "分析",
          content: "先核对来源",
          details: {},
        }),
        event(2, {
          activityId: "reasoning:1",
          activityKind: "reasoning",
          activityPhase: "completed",
          activityName: "分析",
          content: "先核对来源，再确定检索范围。",
          details: {},
        }),
      ].map(toActivityPresentationEvent),
    );

    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      operation: "analysis",
      summary: "先核对来源，再确定检索范围。",
      status: "success",
    });
  });

  it("keeps distinct activities in first-seen sequence order", () => {
    const result = mergeActivityPresentationEvents(
      [],
      [
        event(2),
        event(1, {
          activityId: "data-query",
          activityName: "查询天文数据",
          details: { tool_kind: "data_query" },
        }),
      ].map(toActivityPresentationEvent),
    );
    expect(result.map((activity) => activity.operation)).toEqual([
      "data_query",
      "search",
    ]);
  });
});
