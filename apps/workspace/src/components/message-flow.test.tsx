/* eslint-disable @typescript-eslint/no-explicit-any */
import { asEntityId } from "@xingwen/domain";
import type {
  ActivityPresentationEvent,
  WorkspaceStreamItem,
} from "@xingwen/research-adapter";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProtocolDraftCard } from "./protocol-draft-card";
import { ResearchMessageStream } from "./research-message-stream";

function activity(
  overrides: Partial<ActivityPresentationEvent> = {},
): ActivityPresentationEvent {
  return {
    id: "activity-1",
    kind: "tool",
    operation: "search",
    title: "检索研究论文",
    summary: "正在检索与研究目标相关的真实论文。",
    status: "running",
    timestamp: "2026-08-14T08:00:00Z",
    runId: asEntityId("run-1"),
    sequence: 1,
    stepKey: asEntityId("searching_papers"),
    progress: 40,
    artifactVersionIds: [],
    outcome: "running",
    details: { tool_kind: "search" },
    updates: [
      {
        sequence: 1,
        phase: "running",
        message: "正在检索与研究目标相关的真实论文。",
        timestamp: "2026-08-14T08:00:00Z",
        details: { tool_kind: "search" },
      },
    ],
    ...overrides,
  };
}

describe("OpenHands-derived research message flow", () => {
  it("renders user messages and thinking stream items cleanly", () => {
    const items: WorkspaceStreamItem[] = [
      {
        id: "msg-1",
        kind: "user_message",
        message: "比较 TESS 与 Gaia 的观测选择偏差",
        timestamp: "2026-08-14T08:00:00Z",
      },
      {
        id: "think-1",
        kind: "assistant_reasoning",
        content: "正在规划系外行星宿主星物理参数分析方案...",
        isStreaming: false,
        timestamp: "2026-08-14T08:00:05Z",
      },
      {
        id: "msg-2",
        kind: "assistant_message",
        message: "已为您制定了研究协议草案。",
        outcome: "draft_ready",
        timestamp: "2026-08-14T08:00:10Z",
      },
    ];

    render(<ResearchMessageStream items={items} />);

    expect(
      screen.getByText("比较 TESS 与 Gaia 的观测选择偏差"),
    ).toBeInTheDocument();
    expect(screen.getByText("已为您制定了研究协议草案。")).toBeInTheDocument();
  });

  it("keeps one OpenHands event row when a tool changes from running to completed", () => {
    const items1: WorkspaceStreamItem[] = [
      {
        id: "act-1",
        kind: "tool_execution",
        event: activity(),
        timestamp: "2026-08-14T08:00:00Z",
      },
    ];

    const { container, rerender } = render(
      <ResearchMessageStream items={items1} />,
    );

    expect(
      container.querySelector('[data-testid="event-message"]'),
    ).toHaveAttribute("data-event-kind", "tool");
    expect(within(container).getByText("检索研究论文")).toBeInTheDocument();

    const items2: WorkspaceStreamItem[] = [
      {
        id: "act-1",
        kind: "tool_execution",
        event: activity({
          status: "success",
          outcome: "success",
          summary: "已检索 10 篇候选论文。",
          sequence: 2,
        }),
        timestamp: "2026-08-14T08:00:00Z",
      },
    ];

    rerender(<ResearchMessageStream items={items2} />);

    expect(within(container).getByText("检索研究论文")).toBeInTheDocument();
    expect(
      container.querySelectorAll('[data-testid="event-message"]'),
    ).toHaveLength(1);
  });

  it("keeps public analysis separate from the OpenHands tool activity rows", () => {
    const { container } = render(
      <ResearchMessageStream
        items={[
          {
            id: "analysis-1",
            kind: "tool_execution",
            event: activity({
              id: "analysis-1",
              kind: "reasoning",
              operation: "analysis",
              title: "分析",
              summary: "先核对研究协议与数据边界。",
              details: {},
            }),
            timestamp: "2026-08-14T08:00:00Z",
          },
        ]}
      />,
    );

    expect(
      container.querySelector('[data-testid="collapsible-thinking"]'),
    ).toBeInTheDocument();
    expect(
      container.querySelector('[data-testid="event-message"]'),
    ).not.toBeInTheDocument();
  });

  it("renders in-stream protocol draft cards with one-click confirm and edit actions", () => {
    const draft = {
      id: "draft-1" as any,
      version: 1,
      intent: "宿主星物理参数分析",
      status: "draft" as any,
      contract: {
        researchGoal: "分析 Kepler 宿主星物理参数" as any,
        targetObjects: ["host_star" as any],
        dataRequirements: { unitPolicy: "canonical" as any },
        requestedFields: ["teff" as any, "feh" as any],
        sourceScope: { allowedSources: ["simbad" as any, "gaia" as any] },
        paperSearchScope: {
          keywords: ["exoplanet"],
          yearFrom: 2020,
          yearTo: 2026,
          sourceIds: ["ads" as any],
          maxCandidates: 10,
        },
        outputRequirements: ["paper_summary" as any],
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
      createdAt: "2026-08-14T08:00:00Z" as any,
      updatedAt: "2026-08-14T08:00:00Z" as any,
      expiresAt: "2026-08-15T08:00:00Z" as any,
    };

    const items: WorkspaceStreamItem[] = [
      {
        id: "draft-item-1",
        kind: "protocol_draft",
        draft,
        contract: null,
        isConfirmed: false,
        runStatusLabel: null,
        timestamp: "2026-08-14T08:00:00Z",
      },
    ];

    const onConfirm = vi.fn();
    const onOpenEditor = vi.fn();

    render(
      <ResearchMessageStream
        items={items}
        onConfirmProtocol={onConfirm}
        onOpenProtocolEditor={onOpenEditor}
        renderProtocolDraft={(props) => <ProtocolDraftCard {...props} />}
      />,
    );

    expect(screen.getByText("研究协议")).toBeInTheDocument();
    expect(screen.getByText("分析 Kepler 宿主星物理参数")).toBeInTheDocument();

    const confirmButton = screen.getByText("确认协议并开始研究");
    fireEvent.click(confirmButton);
    expect(onConfirm).toHaveBeenCalled();

    const editButton = screen.getByText("调整");
    fireEvent.click(editButton);
    expect(onOpenEditor).toHaveBeenCalled();
  });
});
