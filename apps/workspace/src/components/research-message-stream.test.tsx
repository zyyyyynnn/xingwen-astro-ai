import { cleanup, render, screen } from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { ResearchMessageStream } from "./research-message-stream";

const RUN_ID = asEntityId("run_01JEXAMPLE");

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Research thread artifact previews", () => {
  it("shows the summary it was given without reading the artifact again", async () => {
    const runtime = createTestRuntime();
    const artifacts = await runtime.repositories.artifacts.listByRun(RUN_ID);
    const artifact = artifacts.find((item) => item.latestVersionId !== null);
    if (!artifact || artifact.latestVersionId === null) {
      throw new Error("Fixture ResearchArtifact is missing.");
    }
    const getVersion = vi.spyOn(runtime.repositories.artifacts, "getVersion");
    const getSummary = vi.spyOn(
      runtime.repositories.paperSummary,
      "getSummary",
    );
    const getDataset = vi.spyOn(
      runtime.repositories.dataArtifacts,
      "getDataset",
    );
    const getRelations = vi.spyOn(
      runtime.repositories.literatureArtifacts,
      "getRelations",
    );

    render(
      <ResearchMessageStream
        items={[
          {
            id: "stream-artifact-1",
            kind: "artifact_result",
            artifact: runtime.researchAdapter.toArtifactViewModel(artifact),
            versionId: artifact.latestVersionId,
            title: artifact.title,
            summary: "已生成论文结构化摘要",
            timestamp: "2026-09-03T02:47:48.000Z",
          },
        ]}
      />,
    );

    expect(await screen.findByText("已生成论文结构化摘要")).toBeInTheDocument();
    expect(getVersion).not.toHaveBeenCalled();
    expect(getSummary).not.toHaveBeenCalled();
    expect(getDataset).not.toHaveBeenCalled();
    expect(getRelations).not.toHaveBeenCalled();
  });
});
