/* eslint-disable @typescript-eslint/no-explicit-any */
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
    id: "proj_1" as any,
    name: "测试研究",
    description: "描述",
    caseKey: "exoplanet_host_star",
    activeDraftId: "draft_1" as any,
    activeContractId: null,
    latestRunId: null,
    latestRunStatus: null,
    latestRunFailureSummary: null,
    threadSummary: { totalTurns: 1, lastActor: "user" } as any,
    revision: 1,
    createdAt: "2026-08-14T00:00:00Z" as any,
    updatedAt: "2026-08-14T00:01:00Z" as any,
  };

  const userEntry: ResearchThreadEntryViewModel = {
    id: "entry_1" as any,
    projectId: "proj_1" as any,
    sequence: 1,
    kind: "user_message",
    actor: "user",
    publicContent: "分析系外行星宿主星",
    structuredPayload: { intent: "分析系外行星宿主星" },
    modelExecutionId: null,
    createdAt: "2026-08-14T00:00:05Z" as any,
  };

  const reasoningEntry: ResearchThreadEntryViewModel = {
    id: "entry_2" as any,
    projectId: "proj_1" as any,
    sequence: 2,
    kind: "assistant_reasoning",
    actor: "assistant",
    publicContent: "正在规划系外行星宿主星物理参数分析方案...",
    structuredPayload: { outcome: "draft_ready" } as any,
    modelExecutionId: "exec_1" as any,
    createdAt: "2026-08-14T00:00:10Z" as any,
  };

  const assistantEntry: ResearchThreadEntryViewModel = {
    id: "entry_3" as any,
    projectId: "proj_1" as any,
    sequence: 3,
    kind: "assistant_message",
    actor: "assistant",
    publicContent: "已根据您的意图生成研究协议草案。",
    structuredPayload: { outcome: "draft_ready", draftId: "draft_1" } as any,
    modelExecutionId: "exec_1" as any,
    createdAt: "2026-08-14T00:00:15Z" as any,
  };

  const draft: ResearchContractDraftViewModel = {
    id: "draft_1" as any,
    version: 1,
    intent: "分析系外行星宿主星",
    status: "draft",
    contract: {
      researchGoal: "分析系外行星宿主星物理参数" as any,
      targetObjects: ["host_star" as any],
      dataRequirements: { unitPolicy: "canonical" },
      requestedFields: ["teff" as any, "feh" as any],
      sourceScope: { allowedSources: ["simbad" as any, "gaia" as any] },
      paperSearchScope: {
        keywords: ["exoplanet"],
        yearFrom: 2020,
        yearTo: 2026,
        sourceIds: ["ads" as any],
        maxCandidates: 10,
      },
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
    createdAt: "2026-08-14T00:00:15Z" as any,
    updatedAt: "2026-08-14T00:00:15Z" as any,
    expiresAt: "2026-08-15T00:00:15Z" as any,
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
      id: "run_1" as any,
      projectId: "proj_1" as any,
      contractId: "contract_1" as any,
      executionMode: "live",
      status: "running",
      progress: 50,
      latestEventSequence: 3,
      parentRunId: null,
      derivationKind: "original",
      retryFromStep: null,
      cachePolicy: "prefer_cache",
      startedAt: "2026-08-14T00:01:00Z" as any,
      finishedAt: null,
      createdAt: "2026-08-14T00:01:00Z" as any,
      updatedAt: "2026-08-14T00:02:00Z" as any,
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
      runId: "run_1" as any,
      sequence: 1,
      stepKey: "step_data" as any,
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
      runId: "run_1" as any,
      sequence: 2,
      stepKey: "step_data" as any,
      progress: 50,
      artifactVersionIds: ["artv_1" as any],
      outcome: "success",
      details: {},
      updates: [],
    };

    const artifact: ResearchArtifactViewModel = {
      id: "art_1" as any,
      projectId: "proj_1" as any,
      kind: "dataset",
      title: "宿主星物理参数数据集",
      logicalKey: "dataset.primary" as any,
      latestVersionId: "artv_1" as any,
      createdAt: "2026-08-14T00:01:30Z" as any,
    };

    const checkpoint: RunCheckpointViewModel = {
      id: "chk_1" as any,
      runId: "run_1" as any,
      stepKey: "step_data" as any,
      question: "请确认是否继续交叉证认",
      options: ["继续证认", "跳过证认"],
      kind: "choice",
      repairContext: null,
      createdAt: "2026-08-14T00:01:40Z" as any,
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
