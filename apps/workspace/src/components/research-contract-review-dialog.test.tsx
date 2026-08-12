import { fireEvent, render, screen } from "@testing-library/react";
import type { ResearchContractViewModel } from "@xingwen/research-adapter";
import type { ResearchPlanningCatalog } from "@xingwen/domain";
import { describe, expect, it, vi } from "vitest";

import { ResearchContractReviewDialog } from "./research-contract-review-dialog";

const CONTRACT = {
  id: "contract-1",
  projectId: "project-1",
  version: 1,
  researchGoal: "比较太阳型恒星与红矮星宜居带行星的观测偏差。",
  targetObjects: ["host_star", "exoplanet_candidate"],
  dataRequirements: { unitPolicy: "canonical" },
  requestedFields: ["planet.toi_id", "star.gaia_dr3_id"],
  sourceScope: { allowedSources: ["nasa_exoplanet_archive"] },
  paperSearchScope: {
    keywords: [],
    yearFrom: null,
    yearTo: null,
    sourceIds: [],
    maxCandidates: 10,
  },
  outputRequirements: ["dataset", "graph"],
  evidenceRequirements: {
    requireLocator: true,
    requireSourceSnapshot: true,
    minimumCoverage: 0.8,
  },
  qualityConstraints: {
    sourceCompletenessMin: 0.8,
    unitConsistencyMin: 1,
  },
  createdAt: "2026-08-12T00:00:00.000Z",
  createdFromDraftId: "draft-1",
  provenance: { contentHash: "hash" },
} as unknown as ResearchContractViewModel;

const CATALOG = {
  projectId: "project-1",
  caseKey: "exoplanet_host_star",
  targetObjects: [
    { value: "host_star", label: "宿主恒星", description: "", group: null },
    {
      value: "exoplanet_candidate",
      label: "系外行星候选体",
      description: "",
      group: null,
    },
  ],
  requestedFields: [
    { value: "planet.toi_id", label: "TOI 编号", description: "", group: null },
    {
      value: "star.gaia_dr3_id",
      label: "Gaia DR3 编号",
      description: "",
      group: null,
    },
  ],
  allowedSources: [
    {
      value: "nasa_exoplanet_archive",
      label: "NASA 系外行星档案",
      description: "",
      group: null,
    },
  ],
  outputRequirements: [
    { value: "dataset", label: "结构化数据", description: "", group: "common" },
    { value: "graph", label: "证据图谱", description: "", group: "common" },
  ],
} as unknown as ResearchPlanningCatalog;

function renderDialog({
  runStatusLabel,
  onViewPlan = vi.fn(),
  onCreateRun = vi.fn(async () => undefined),
}: {
  runStatusLabel: string | null;
  onViewPlan?: () => void;
  onCreateRun?: () => Promise<void>;
}) {
  render(
    <ResearchContractReviewDialog
      open
      onOpenChange={vi.fn()}
      draft={null}
      catalog={CATALOG}
      contract={CONTRACT}
      runStatusLabel={runStatusLabel}
      pendingAction={null}
      errorMessage={null}
      onSave={vi.fn(async () => undefined)}
      onConfirm={vi.fn(async () => undefined)}
      onCreateRun={onCreateRun}
      onViewPlan={onViewPlan}
    />,
  );
}

describe("ResearchContractReviewDialog", () => {
  it("shows a confirmed run as a readable result with a plan action", () => {
    const onViewPlan = vi.fn();
    renderDialog({ runStatusLabel: "已排队", onViewPlan });

    expect(screen.getByText("已确认")).toBeInTheDocument();
    expect(screen.getByText("已排队")).toBeInTheDocument();
    expect(screen.getByText("≥ 80%")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "开始真实研究" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "查看研究计划" }));
    expect(onViewPlan).toHaveBeenCalledOnce();
  });

  it("keeps the long research data list collapsed until requested", () => {
    renderDialog({ runStatusLabel: null });

    const trigger = screen.getByRole("button", { name: /研究数据\s*2 项/u });
    expect(trigger).toHaveAttribute("data-state", "closed");
    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute("data-state", "open");
    expect(screen.getByText("TOI 编号")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "开始真实研究" }),
    ).toBeInTheDocument();
  });
});
