import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { resolveArtifactRenderer } from "./artifact-renderer-registry";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Artifact Scientific Diff loading", () => {
  it("uses ArtifactVersion embedded Evidence without per-item reads", async () => {
    const runtime = createTestRuntime();
    const artifact = await runtime.repositories.artifacts.getArtifact(
      asEntityId("art_dataset_01"),
    );
    const version = await runtime.repositories.artifacts.getVersion(
      asEntityId("artv_dataset_01"),
    );
    const evidenceId = version?.evidenceIds[0];
    const evidence = evidenceId
      ? await runtime.repositories.artifacts.getEvidence(evidenceId)
      : null;
    const descriptor = resolveArtifactRenderer("dataset");
    if (!artifact || !version || !evidence || !descriptor) {
      throw new Error("Dataset Diff fixture is incomplete");
    }
    const getEvidence = vi.spyOn(runtime.repositories.artifacts, "getEvidence");
    const versionWithEvidence = { ...version, evidence: [evidence] };
    const viewModel =
      runtime.researchAdapter.toArtifactVersionViewModel(versionWithEvidence);
    const DiffRenderer = descriptor.DiffRenderer;

    render(
      <QueryClientProvider client={runtime.queryClient}>
        <DiffRenderer
          runtime={runtime}
          projectId={asEntityId("proj_01JEXAMPLE")}
          artifact={runtime.researchAdapter.toArtifactViewModel(artifact)}
          baselineVersion={viewModel}
          currentVersion={viewModel}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("没有发现科学内容变化")).toBeInTheDocument();
    expect(getEvidence).not.toHaveBeenCalled();
  });

  it("falls back to version-pinned Evidence reads when inline Evidence is absent", async () => {
    const runtime = createTestRuntime();
    const artifact = await runtime.repositories.artifacts.getArtifact(
      asEntityId("art_dataset_01"),
    );
    const version = await runtime.repositories.artifacts.getVersion(
      asEntityId("artv_dataset_01"),
    );
    const evidenceId = version?.evidenceIds[0];
    const descriptor = resolveArtifactRenderer("dataset");
    if (!artifact || !version || !evidenceId || !descriptor) {
      throw new Error("Dataset Diff fixture is incomplete");
    }
    expect(version.evidence).toBeUndefined();

    const getEvidence = vi.spyOn(runtime.repositories.artifacts, "getEvidence");
    const getVersion = vi.spyOn(runtime.repositories.artifacts, "getVersion");
    getVersion.mockClear();
    const viewModel =
      runtime.researchAdapter.toArtifactVersionViewModel(version);
    const DiffRenderer = descriptor.DiffRenderer;

    render(
      <QueryClientProvider client={runtime.queryClient}>
        <DiffRenderer
          runtime={runtime}
          projectId={asEntityId("proj_01JEXAMPLE")}
          artifact={runtime.researchAdapter.toArtifactViewModel(artifact)}
          baselineVersion={viewModel}
          currentVersion={viewModel}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("没有发现科学内容变化")).toBeInTheDocument();
    expect(getEvidence).toHaveBeenCalledWith(evidenceId);
    expect(getVersion).not.toHaveBeenCalled();
  });

  it("fails safely when a version-bound SourceSnapshot cannot be read", async () => {
    const runtime = createTestRuntime();
    const artifact = await runtime.repositories.artifacts.getArtifact(
      asEntityId("art_dataset_01"),
    );
    const version = await runtime.repositories.artifacts.getVersion(
      asEntityId("artv_dataset_01"),
    );
    const descriptor = resolveArtifactRenderer("dataset");
    if (!artifact || !version || !descriptor) {
      throw new Error("Dataset Diff fixture is incomplete");
    }
    vi.spyOn(
      runtime.repositories.artifacts,
      "getSourceSnapshot",
    ).mockRejectedValue(new Error("SourceSnapshot unavailable"));
    const DiffRenderer = descriptor.DiffRenderer;

    render(
      <QueryClientProvider client={runtime.queryClient}>
        <DiffRenderer
          runtime={runtime}
          projectId={asEntityId("proj_01JEXAMPLE")}
          artifact={runtime.researchAdapter.toArtifactViewModel(artifact)}
          baselineVersion={runtime.researchAdapter.toArtifactVersionViewModel(
            version,
          )}
          currentVersion={runtime.researchAdapter.toArtifactVersionViewModel(
            version,
          )}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "操作暂时不可用，请稍后重试",
    );
    expect(screen.queryByText("没有发现科学内容变化")).not.toBeInTheDocument();
  });
});
