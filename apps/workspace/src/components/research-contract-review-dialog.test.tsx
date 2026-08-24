import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import type { ResearchPlanningCatalog } from "@xingwen/domain";
import { describe, expect, it, vi } from "vitest";

import { ResearchContractReviewDialog } from "./research-contract-review-dialog";

const CONTRACT = {
  id: "contract-1",
  projectId: "project-1",
  version: 1,
  researchGoal: "比较太阳型恒星与红矮星宜居带行星的观测偏差。",
  targetObjects: ["host_star", "exoplanet_candidate"],
  dataRequirements: {
    unitPolicy: "canonical",
    documentSourcePolicy: "disabled",
  },
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

const DRAFT = {
  id: "draft-1",
  version: 1,
  intent: "比较宜居带行星的观测偏差",
  status: "draft",
  contract: CONTRACT,
  warnings: [],
  createdAt: "2026-08-12T00:00:00.000Z",
  updatedAt: "2026-08-12T00:00:00.000Z",
  expiresAt: "2026-08-13T00:00:00.000Z",
} as unknown as ResearchContractDraftViewModel;

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

  it("uses the shared confirmation dialog before discarding a dirty draft", async () => {
    const onOpenChange = vi.fn();
    render(
      <ResearchContractReviewDialog
        open
        onOpenChange={onOpenChange}
        draft={DRAFT}
        catalog={CATALOG}
        contract={null}
        runStatusLabel={null}
        pendingAction={null}
        errorMessage={null}
        onSave={vi.fn(async () => undefined)}
        onConfirm={vi.fn(async () => undefined)}
        onCreateRun={vi.fn(async () => undefined)}
        onViewPlan={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("研究问题"), {
      target: { value: "修改后的研究问题" },
    });
    await waitFor(() => {
      fireEvent.click(screen.getByRole("button", { name: "关闭" }));
      expect(
        screen.getByRole("alertdialog", { name: "放弃未保存的修改？" }),
      ).toBeInTheDocument();
    });
    expect(onOpenChange).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "继续编辑" }));
    expect(onOpenChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(screen.getByRole("button", { name: "放弃修改" }));

    expect(onOpenChange).toHaveBeenCalledOnce();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
