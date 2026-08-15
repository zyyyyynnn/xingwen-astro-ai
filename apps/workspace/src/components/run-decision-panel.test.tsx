import { asEntityId } from "@xingwen/domain";
import type { ResearchInputRef, RunCheckpoint } from "@xingwen/domain";
import type { ResearchRunViewModel } from "@xingwen/research-adapter";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunDecisionPanel } from "./run-decision-panel";

afterEach(cleanup);

const PROJECT_ID = asEntityId("proj_run_decision");
const RUN_ID = asEntityId("run_run_decision");

function run(status: ResearchRunViewModel["status"]): ResearchRunViewModel {
  return {
    id: RUN_ID,
    projectId: PROJECT_ID,
    contractId: asEntityId("contract_run_decision"),
    executionMode: "live",
    status,
    revision: 3,
    progress: status === "failed" ? 35 : 40,
    latestEventSequence: 4,
    parentRunId: null,
    derivationKind: "original",
    retryFromStep: null,
    cachePolicy: "disabled",
    startedAt: "2026-08-14T00:00:00Z",
    finishedAt: null,
    createdAt: "2026-08-14T00:00:00Z",
    updatedAt: "2026-08-14T00:03:00Z",
    failure:
      status === "failed"
        ? { code: "SCIENTIFIC_INPUT_REPAIRABLE", summary: "输入需要修复" }
        : null,
    isTerminal: status === "failed",
    isFailed: status === "failed",
    isCancelled: false,
  };
}

const checkpoint: RunCheckpoint = {
  code: "INPUT_REQUIRED",
  id: asEntityId("checkpoint_run_decision"),
  openedAt: "2026-08-14T00:02:00Z",
  publicMessage: "请上传宿主星来源。",
  requiredInputTypes: ["pdf", "text"],
  resolutionRunId: null,
  resolvedAt: null,
  runId: RUN_ID,
  status: "open",
  stepKey: "source_validation",
};

const input: ResearchInputRef = {
  contentHash:
    "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  createdAt: "2026-08-14T00:01:00Z",
  filename: "notes.txt",
  id: asEntityId("input_run_decision"),
  mimeType: "text/plain",
  sizeBytes: 20,
  sourceSnapshotId: null,
  sourceType: "upload",
  status: "accepted",
  type: "text",
};

function defaults() {
  return {
    checkpointLoading: false,
    inputs: [input],
    inputsLoading: false,
    pending: false,
    inputPending: false,
    retryStepKey: null,
    errorMessage: null,
    onDecision: vi.fn(async () => undefined),
    onUpload: vi.fn(async () => input),
    onBind: vi.fn(async () => undefined),
  };
}

describe("RunDecisionPanel", () => {
  it("keeps resume disabled until an accepted current-project input is selected", async () => {
    const props = defaults();
    render(
      <RunDecisionPanel
        {...props}
        run={run("waiting_for_input")}
        checkpoint={checkpoint}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "需要你的输入" }),
    ).toBeInTheDocument();
    expect(screen.getByText("PDF / 文本")).toBeInTheDocument();
    const resume = screen.getByRole("button", { name: "继续运行" });
    expect(resume).toBeDisabled();
    fireEvent.click(screen.getByRole("combobox", { name: "选择已接受输入" }));
    fireEvent.click(
      await screen.findByRole("option", { name: "notes.txt · 文本" }),
    );
    expect(resume).not.toBeDisabled();
    fireEvent.click(resume);
    await vi.waitFor(() =>
      expect(props.onDecision).toHaveBeenCalledWith({
        decision: "resume",
        inputIds: [input.id],
      }),
    );
    expect(props.onBind).toHaveBeenCalledWith(input.id);
  });

  it("offers a repairable failed-step retry with a replay-safe disabled state", async () => {
    const props = defaults();
    render(
      <RunDecisionPanel
        {...props}
        run={run("failed")}
        checkpoint={null}
        retryStepKey="source_validation"
      />,
    );
    const retry = screen.getByRole("button", { name: "重试失败步骤" });
    expect(retry).toBeEnabled();
    fireEvent.click(retry);
    await vi.waitFor(() =>
      expect(props.onDecision).toHaveBeenCalledWith({
        decision: "retry",
        stepKey: "source_validation",
      }),
    );
  });
});
