import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";
import type {
  ProjectViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  RunCheckpointViewModel,
} from "./view-model";
import type { ActivityPresentationEvent } from "./activity";
import { buildUnifiedWorkspaceStream } from "./stream-item";

describe("buildUnifiedWorkspaceStream", () => {
  const baseProject: ProjectViewModel = {
    id: asEntityId("proj_1"),
    name: "测试研究",
    description: "描述",
    caseKey: "exoplanet_host_star",
    activeDraftId: asEntityId("draft_1"),
    activeContractId: null,
    latestRunId: null,
    latestRunStatus: null,
    latestRunFailureSummary: null,
    threadSummary: { totalTurns: 1, lastActor: "user" },
    revision: 1,
    createdAt: "2026-08-14T00:00:00Z",
    updatedAt: "2026-08-14T00:01:00Z",
  };

  const userEntry: ResearchThreadEntryViewModel = {
    id: asEntityId("entry_1"),
    projectId: asEntityId("proj_1"),
    sequence: 1,
    kind: "user_message",
    actor: "user",
    publicContent: "分析系外行星宿主星",
    structuredPayload: { answerToQuestionId: null },
    modelExecutionId: null,
    createdAt: "2026-08-14T00:00:05Z",
  };

  const reasoningEntry: ResearchThreadEntryViewModel = {
    id: asEntityId("entry_2"),
    projectId: asEntityId("proj_1"),
    sequence: 2,
    kind: "assistant_reasoning",
    actor: "assistant",
    publicContent: "正在规划系外行星宿主星物理参数分析方案...",
    structuredPayload: {
      outcome: "draft_ready",
      warnings: [],
      draftId: asEntityId("draft_1"),
      missingInformation: [],
      reason: null,
      errorCode: null,
    },
    modelExecutionId: asEntityId("exec_1"),
    createdAt: "2026-08-14T00:00:10Z",
  };

  const assistantEntry: ResearchThreadEntryViewModel = {
    id: asEntityId("entry_3"),
    projectId: asEntityId("proj_1"),
    sequence: 3,
    kind: "assistant_message",
    actor: "assistant",
    publicContent: "已根据您的意图生成研究协议草案。",
    structuredPayload: {
      outcome: "draft_ready",
      warnings: [],
      draftId: asEntityId("draft_1"),
      missingInformation: [],
      reason: null,
      errorCode: null,
    },
    modelExecutionId: asEntityId("exec_1"),
    createdAt: "2026-08-14T00:00:15Z",
  };

  const draft: ResearchContractDraftViewModel = {
    id: asEntityId("draft_1"),
    version: 1,
    intent: "分析系外行星宿主星",
    status: "draft",
    contract: {
      researchGoal: "分析系外行星宿主星物理参数",
      targetObjects: [asEntityId("host_star")],
      dataRequirements: {
        unitPolicy: "canonical",
        documentSourcePolicy: "disabled" as const,
      },
      requestedFields: [asEntityId("teff"), asEntityId("feh")],
      sourceScope: {
        allowedSources: [asEntityId("simbad"), asEntityId("gaia")],
      },
      paperSearchScope: {
        keywords: ["exoplanet"],
        yearFrom: 2020,
        yearTo: 2026,
        sourceIds: [asEntityId("ads")],
        maxCandidates: 10,
      },
      scientificTasks: [],
      outputRequirements: ["paper_summary"],
      evidenceRequirements: {
        requireLocator: true,
        requireSourceSnapshot: true,
        minimumCoverage: 0.8,
      },
      qualityConstraints: {
        sourceCompletenessMin: 0.8,
        unitConsistencyMin: 0.9,
      },
    },
    warnings: [],
    createdAt: "2026-08-14T00:00:15Z",
    updatedAt: "2026-08-14T00:00:15Z",
    expiresAt: "2026-08-15T00:00:15Z",
  };

  it("synthesizes user message, thinking, assistant message and protocol card in order", () => {
    const items = buildUnifiedWorkspaceStream({
      project: baseProject,
      entries: [userEntry, reasoningEntry, assistantEntry],
      draft,
      contract: null,
      run: null,
      steps: [],
      events: [],
      artifacts: [],
    });

    expect(items).toHaveLength(4);
    expect(items[0]?.kind).toBe("user_message");
    expect(items[1]?.kind).toBe("assistant_reasoning");
    expect(items[2]?.kind).toBe("assistant_message");
    expect(items[3]?.kind).toBe("protocol_draft");
    if (items[3]?.kind === "protocol_draft") {
      expect(items[3].draft?.id).toBe("draft_1");
      expect(items[3].isConfirmed).toBe(false);
    }
  });

  it("interleaves activities and published artifacts by deterministic server timestamps", () => {
    const run: ResearchRunViewModel = {
      id: asEntityId("run_1"),
      projectId: asEntityId("proj_1"),
      contractId: asEntityId("contract_1"),
      executionMode: "live",
      status: "running",
      progress: 50,
      revision: 1,
      latestEventSequence: 3,
      parentRunId: null,
      derivationKind: "original",
      retryFromStep: null,
      cachePolicy: "prefer_cache",
      startedAt: "2026-08-14T00:01:00Z",
      finishedAt: null,
      createdAt: "2026-08-14T00:01:00Z",
      updatedAt: "2026-08-14T00:02:00Z",
      failure: null,
      isTerminal: false,
      isFailed: false,
      isCancelled: false,
    };

    const toolEvent: ActivityPresentationEvent = {
      id: "act_1",
      kind: "tool",
      operation: "data_query",
      title: "获取 Gaia 数据",
      summary: "正在查询 Gaia DR3 星表数据",
      status: "running",
      timestamp: "2026-08-14T00:01:10Z",
      runId: asEntityId("run_1"),
      sequence: 1,
      stepKey: asEntityId("step_data"),
      progress: 20,
      artifactVersionIds: [],
      outcome: "running",
      details: {},
      updates: [],
    };

    const publishEvent: ActivityPresentationEvent = {
      id: "act_2",
      kind: "artifact",
      operation: "artifact_generation",
      title: "产出数据表",
      summary: "已生成宿主星参数表",
      status: "success",
      timestamp: "2026-08-14T00:01:30Z",
      runId: asEntityId("run_1"),
      sequence: 2,
      stepKey: asEntityId("step_data"),
      progress: 50,
      artifactVersionIds: [asEntityId("artv_1")],
      outcome: "success",
      details: {},
      updates: [],
    };

    const artifact: ResearchArtifactViewModel = {
      id: asEntityId("art_1"),
      projectId: asEntityId("proj_1"),
      kind: "dataset",
      title: "宿主星物理参数数据集",
      logicalKey: asEntityId("dataset.primary"),
      latestVersionId: asEntityId("artv_1"),
      createdAt: "2026-08-14T00:01:30Z",
    };

    const checkpoint: RunCheckpointViewModel = {
      id: asEntityId("chk_1"),
      runId: asEntityId("run_1"),
      runRevision: 1,
      stepKey: asEntityId("step_data"),
      question: "请确认是否继续交叉证认",
      options: ["继续证认", "跳过证认"],
      kind: "choice",
      repairContext: null,
      createdAt: "2026-08-14T00:01:40Z",
      selectedOption: null,
      freeText: null,
      repairDecisions: [],
      repairOutcome: null,
      decidedAt: null,
      isAnswered: false,
    };

    const items = buildUnifiedWorkspaceStream({
      project: baseProject,
      entries: [userEntry, assistantEntry],
      draft: null,
      contract: null,
      run,
      events: [toolEvent, publishEvent],
      artifacts: [artifact],
      checkpoint,
    });

    const kinds = items.map((i) => i.kind);
    expect(kinds).toContain("tool_execution");
    expect(kinds).toContain("artifact_result");
    expect(kinds).toContain("checkpoint_prompt");

    const toolIndex = items.findIndex((i) => i.kind === "tool_execution");
    const artifactIndex = items.findIndex((i) => i.kind === "artifact_result");
    const checkpointIndex = items.findIndex(
      (i) => i.kind === "checkpoint_prompt",
    );

    expect(toolIndex).toBeLessThan(artifactIndex);
    expect(artifactIndex).toBeLessThan(checkpointIndex);
  });
});
