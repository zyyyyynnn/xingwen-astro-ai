import { asEntityId } from "@xingwen/domain";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { PaperSummaryFullscreenRenderer } from "./paper-summary-renderer";

afterEach(cleanup);

describe("PaperSummary renderer", () => {
  it("renders the governed report sections and expands evidence gaps", async () => {
    const runtime = createTestRuntime();
    const versionId = asEntityId("artv_papsum_01");
    const artifactId = asEntityId("art_papsum_01");
    const [artifact, version, sourceReview] = await Promise.all([
      runtime.repositories.artifacts.getArtifact(artifactId),
      runtime.repositories.artifacts.getVersion(versionId),
      runtime.repositories.paperSummary.getSummary(versionId),
    ]);
    if (!artifact || !version) throw new Error("Fixture Artifact is missing.");
    const review = {
      ...sourceReview,
      findings: sourceReview.findings.map((finding, index) =>
        index === 0
          ? { ...finding, status: "unsupported" as const, evidenceIds: [] }
          : finding,
      ),
    };

    render(
      <PaperSummaryFullscreenRenderer
        artifact={runtime.researchAdapter.toArtifactViewModel(artifact)}
        version={runtime.researchAdapter.toArtifactVersionViewModel(version)}
        review={review}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "研究目标" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "研究方法" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "数据集" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "核心发现" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "局限性" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "后续研究" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("证据不足").length).toBeGreaterThan(0);
    expect(screen.getAllByText("证据链不完整").length).toBeGreaterThan(0);
    expect(screen.getAllByText("该陈述没有绑定证据。").length).toBeGreaterThan(
      0,
    );
  });
});
