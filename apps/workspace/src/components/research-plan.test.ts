import type {
  ProjectViewModel,
  ResearchThreadEntryViewModel,
  RunStepViewModel,
} from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { deriveResearchPresentation } from "../presentation/research-presentation";

const project = {
  id: "project-1",
  activeDraftId: null,
  activeContractId: null,
  latestRunId: null,
  latestRunStatus: null,
  threadSummary: {
    hasThreadEntries: false,
    latestThreadActor: null,
    hasUnansweredClarification: false,
  },
} as unknown as ProjectViewModel;

function step(
  status: RunStepViewModel["status"],
  publicMessage: string,
): RunStepViewModel {
  return {
    id: `step-${status}`,
    runId: "run-1",
    position: 1,
    key: "plan_path",
    label: "规划研究路径",
    status,
    progress: 0,
    publicMessage,
    startedAt: null,
    finishedAt: null,
    failureCode: null,
  } as unknown as RunStepViewModel;
}

describe("deriveResearchPresentation", () => {
  it("omits redundant secondary copy for steps that have not started", () => {
    const items = deriveResearchPresentation({
      project,
      steps: [step("pending", "等待规划研究路径。")],
    }).planItems;

    expect(items.at(-1)?.detail).toBeUndefined();
  });

  it("keeps actionable execution detail", () => {
    const items = deriveResearchPresentation({
      project,
      steps: [step("failed", "目录服务暂时不可用。")],
    }).planItems;

    expect(items.at(-1)?.detail).toBe("目录服务暂时不可用。");
  });

  it("drives the shared waiting state from an unanswered clarification", () => {
    const question = {
      id: "question-entry",
      actor: "assistant",
      kind: "clarification_question",
      structuredPayload: { questionId: "question-1" },
    } as unknown as ResearchThreadEntryViewModel;

    const presentation = deriveResearchPresentation({
      project,
      entries: [question],
    });

    expect(presentation.state).toBe("awaiting_clarification");
    expect(presentation.statusLabel).toBe("等待你的回答");
    expect(presentation.planItems[0]?.status).toBe("waiting");
  });

  it("does not let an older Contract or Run hide a new clarification", () => {
    const question = {
      id: "question-after-run",
      actor: "assistant",
      kind: "clarification_question",
      structuredPayload: { questionId: "question-2" },
    } as unknown as ResearchThreadEntryViewModel;
    const projectWithRun = {
      ...project,
      activeContractId: "contract-1",
      latestRunId: "run-1",
      latestRunStatus: "completed",
    } as unknown as ProjectViewModel;

    const presentation = deriveResearchPresentation({
      project: projectWithRun,
      entries: [question],
    });

    expect(presentation.state).toBe("awaiting_clarification");
    expect(presentation.statusLabel).toBe("等待你的回答");
    expect(presentation.planItems[0]?.status).toBe("waiting");
  });

  it("leaves the waiting state after the matching answer is recorded", () => {
    const entries = [
      {
        id: "question-entry",
        actor: "assistant",
        kind: "clarification_question",
        structuredPayload: { questionId: "question-1" },
      },
      {
        id: "answer-entry",
        actor: "user",
        kind: "clarification_answer",
        structuredPayload: { answerToQuestionId: "question-1" },
      },
    ] as unknown as readonly ResearchThreadEntryViewModel[];

    const presentation = deriveResearchPresentation({ project, entries });

    expect(presentation.state).toBe("assistant_processing");
    expect(presentation.statusLabel).toBe("研究助手处理中");
    expect(presentation.planItems[0]?.status).toBe("running");
  });

  it("projects a provider failure as a failed preparation step", () => {
    const unavailable = {
      id: "assistant-unavailable",
      actor: "assistant",
      kind: "assistant_message",
      structuredPayload: { outcome: "unavailable" },
    } as unknown as ResearchThreadEntryViewModel;

    const presentation = deriveResearchPresentation({
      project,
      entries: [unavailable],
    });

    expect(presentation.state).toBe("assistant_unavailable");
    expect(presentation.statusLabel).toBe("研究助手暂不可用");
    expect(presentation.planItems[0]?.status).toBe("failed");
  });

  it("preserves a non-current Project clarification state from its server summary", () => {
    const projectA = {
      ...project,
      id: "project-a",
      threadSummary: {
        hasThreadEntries: true,
        latestThreadActor: "assistant",
        hasUnansweredClarification: true,
      },
    } as unknown as ProjectViewModel;
    const question = {
      id: "question-a",
      actor: "assistant",
      kind: "clarification_question",
      structuredPayload: { questionId: "question-a" },
    } as unknown as ResearchThreadEntryViewModel;

    const nonCurrent = deriveResearchPresentation({ project: projectA });
    const current = deriveResearchPresentation({
      project: projectA,
      entries: [question],
    });

    expect(nonCurrent.statusLabel).toBe("等待你的回答");
    expect(nonCurrent.state).toBe(current.state);
    expect(nonCurrent.statusLabel).toBe(current.statusLabel);
  });
});
