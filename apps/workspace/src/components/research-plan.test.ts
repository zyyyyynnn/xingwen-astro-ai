import type { RunStepViewModel } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { createResearchPlanItems } from "./research-plan";

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

describe("createResearchPlanItems", () => {
  it("omits redundant secondary copy for steps that have not started", () => {
    const items = createResearchPlanItems({
      draft: null,
      contract: null,
      run: null,
      steps: [step("pending", "等待规划研究路径。")],
    });

    expect(items.at(-1)?.detail).toBeUndefined();
  });

  it("keeps actionable execution detail", () => {
    const items = createResearchPlanItems({
      draft: null,
      contract: null,
      run: null,
      steps: [step("failed", "目录服务暂时不可用。")],
    });

    expect(items.at(-1)?.detail).toBe("目录服务暂时不可用。");
  });
});
