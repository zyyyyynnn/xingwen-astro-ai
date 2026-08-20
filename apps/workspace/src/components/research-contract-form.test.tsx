import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  asEntityId,
  type ResearchPlanningCatalog,
  type ScientificTask,
} from "@xingwen/domain";
import type { ResearchContractDraftViewModel } from "@xingwen/research-adapter";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ResearchContractForm } from "./research-contract-form";

beforeAll(() => {
  // jsdom does not implement scrollIntoView, which Radix listboxes use.
  Element.prototype.scrollIntoView ??= () => undefined;
});

afterEach(() => {
  cleanup();
});

const scientificTasks: readonly ScientificTask[] = [
  {
    taskId: asEntityId("task-light-curve"),
    skillId: "light_curve_acquisition",
    parameters: { target: "Kepler-186" },
    inputRefs: [asEntityId("input-1")],
  },
  {
    taskId: asEntityId("task-period"),
    skillId: "light_curve_analysis",
    parameters: { method: "bls" },
    inputRefs: [],
  },
];

const catalog: ResearchPlanningCatalog = {
  projectId: asEntityId("proj-1"),
  caseKey: "exoplanet_host_star",
  targetObjects: [
    {
      value: asEntityId("host_star"),
      label: "宿主恒星",
      description: "",
      group: "common",
    },
  ],
  requestedFields: [
    {
      value: asEntityId("teff"),
      label: "有效温度",
      description: "",
      group: "common",
    },
  ],
  allowedSources: [
    {
      value: asEntityId("simbad"),
      label: "SIMBAD",
      description: "",
      group: "common",
    },
  ],
  scientificSkills: [
    {
      value: "light_curve_acquisition",
      label: "获取 TESS 光变",
      description: "从 TESS 档案获取光变曲线",
      group: "common",
    },
    {
      value: "light_curve_analysis",
      label: "光变周期分析",
      description: "提取周期与相位",
      group: "common",
    },
  ],
  outputRequirements: [
    {
      value: "dataset",
      label: "数据集",
      description: "",
      group: "common",
    },
  ],
};

function makeDraft(): ResearchContractDraftViewModel {
  return {
    id: asEntityId("rcd-1"),
    version: 1,
    intent: "宿主星参数比较",
    status: "draft",
    contract: {
      researchGoal: "建立可追溯的宿主恒星参数比较集",
      targetObjects: [asEntityId("host_star")],
      dataRequirements: { unitPolicy: "canonical" },
      requestedFields: [asEntityId("teff")],
      sourceScope: { allowedSources: [asEntityId("simbad")] },
      paperSearchScope: {
        keywords: ["exoplanet"],
        yearFrom: 2020,
        yearTo: 2026,
        sourceIds: [],
        maxCandidates: 10,
      },
      scientificTasks,
      outputRequirements: ["dataset"],
      evidenceRequirements: {
        requireLocator: true,
        requireSourceSnapshot: true,
        minimumCoverage: 1,
      },
      qualityConstraints: {
        sourceCompletenessMin: 1,
        unitConsistencyMin: 1,
      },
    },
    warnings: [],
    createdAt: "2026-08-18T00:00:00Z",
    updatedAt: "2026-08-18T00:00:00Z",
    expiresAt: "2026-08-19T00:00:00Z",
  };
}

describe("ResearchContractForm scientific task closure", () => {
  it("keeps scientificTasks intact when saving after editing a normal field", async () => {
    const onSaveDraft = vi.fn().mockResolvedValue(undefined);
    render(
      <ResearchContractForm
        draft={makeDraft()}
        catalog={catalog}
        pendingAction={null}
        errorMessage={null}
        onSaveDraft={onSaveDraft}
        onConfirmAndRun={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText("预期回答"), {
      target: { value: "建立可追溯且更完整的宿主恒星参数比较集" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));

    await vi.waitFor(() => expect(onSaveDraft).toHaveBeenCalledTimes(1));
    const [intent, submitted] = onSaveDraft.mock.calls[0] ?? [];
    expect(intent).toBe("宿主星参数比较");
    expect(submitted.scientificTasks).toEqual(scientificTasks);
  });

  it("shows catalog human labels for planned scientific tasks in review", () => {
    render(
      <ResearchContractForm
        draft={makeDraft()}
        catalog={catalog}
        pendingAction={null}
        errorMessage={null}
        onSaveDraft={vi.fn()}
        onConfirmAndRun={vi.fn()}
      />,
    );

    // Radix tabs select on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /成果要求/ }));

    expect(screen.getByText("计划执行的科学任务")).toBeInTheDocument();
    expect(screen.getByText("获取 TESS 光变")).toBeInTheDocument();
    expect(screen.getByText("光变周期分析")).toBeInTheDocument();
  });

  it("hides the scientific task section when the draft has none", () => {
    const base = makeDraft();
    const draft = {
      ...base,
      contract: { ...base.contract, scientificTasks: [] },
    };
    render(
      <ResearchContractForm
        draft={draft}
        catalog={catalog}
        pendingAction={null}
        errorMessage={null}
        onSaveDraft={vi.fn()}
        onConfirmAndRun={vi.fn()}
      />,
    );

    // Radix tabs select on mousedown, not click.
    fireEvent.mouseDown(screen.getByRole("tab", { name: /成果要求/ }));

    expect(screen.queryByText("计划执行的科学任务")).toBeNull();
  });
});
