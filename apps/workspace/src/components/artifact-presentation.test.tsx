import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";
import { useArtifactPresentation } from "./artifact-presentation";

const PROJECT_ID = asEntityId("proj_01JEXAMPLE");
const RUN_ID = asEntityId("run_01JEXAMPLE");

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function ResultPanel(props: {
  readonly runtime: ReturnType<typeof createTestRuntime>;
}) {
  const { resultPanel } = useArtifactPresentation({
    runtime: props.runtime,
    projectId: PROJECT_ID,
    runId: RUN_ID,
    artifactVersionId: null,
    onOpenArtifactVersion: () => undefined,
    onReturnToOverview: () => undefined,
  });
  return <>{resultPanel}</>;
}

function renderIndex(runtime: ReturnType<typeof createTestRuntime>) {
  return render(
    <QueryClientProvider client={runtime.queryClient}>
      <ResultPanel runtime={runtime} />
    </QueryClientProvider>,
  );
}

/** Every read that hydrates a whole artifact behind an index row. */
function spyOnRichReads(runtime: ReturnType<typeof createTestRuntime>) {
  const { repositories } = runtime;
  return [
    vi.spyOn(repositories.artifacts, "getVersion"),
    vi.spyOn(repositories.dataArtifacts, "getDataset"),
    vi.spyOn(repositories.dataArtifacts, "getFieldDictionary"),
    vi.spyOn(repositories.dataArtifacts, "getSourceCollection"),
    vi.spyOn(repositories.paperSummary, "getSummary"),
    vi.spyOn(repositories.paperAcquisition, "getReview"),
    vi.spyOn(repositories.literatureArtifacts, "getClaims"),
    vi.spyOn(repositories.graphArtifacts, "getReview"),
    vi.spyOn(repositories.scientificArtifacts, "getReview"),
  ];
}

async function relationVersionId(
  runtime: ReturnType<typeof createTestRuntime>,
) {
  const artifacts = await runtime.repositories.artifacts.listByRun(RUN_ID);
  const relations = artifacts.find(
    (artifact) => artifact.kind === "literature_relations",
  );
  if (!relations || relations.latestVersionId === null) {
    throw new Error("Fixture literature_relations artifact is missing.");
  }
  return relations.latestVersionId;
}

describe("Research result index reads", () => {
  it("lists results without reading any ArtifactVersion detail", async () => {
    const runtime = createTestRuntime();
    const richReads = spyOnRichReads(runtime);
    // The artifact list itself is the index's only synchronous source.
    const listByRun = vi.spyOn(runtime.repositories.artifacts, "listByRun");

    renderIndex(runtime);

    expect(await screen.findByText(/研究结果 · /)).toBeInTheDocument();
    expect(listByRun).toHaveBeenCalled();
    for (const richRead of richReads) {
      expect(richRead).not.toHaveBeenCalled();
    }
  });

  it("reads only the relation contract to flag results needing review", async () => {
    const runtime = createTestRuntime();
    const versionId = await relationVersionId(runtime);
    const review =
      await runtime.repositories.literatureArtifacts.getRelations(versionId);
    const getRelations = vi.spyOn(
      runtime.repositories.literatureArtifacts,
      "getRelations",
    );
    getRelations.mockResolvedValue({
      ...review,
      relations: review.relations.map((relation) => ({
        ...relation,
        status: "candidate" as const,
      })),
    });
    const getVersion = vi.spyOn(runtime.repositories.artifacts, "getVersion");

    renderIndex(runtime);

    expect(await screen.findByText(/需要处理 · /)).toBeInTheDocument();
    expect(
      await screen.findByText(`${review.relations.length} 待审`),
    ).toBeInTheDocument();
    expect(getRelations).toHaveBeenCalledWith(versionId);
    expect(getVersion).not.toHaveBeenCalled();
  });

  it("keeps accepted relations in the ordinary result group", async () => {
    const runtime = createTestRuntime();
    const versionId = await relationVersionId(runtime);
    const review =
      await runtime.repositories.literatureArtifacts.getRelations(versionId);
    vi.spyOn(
      runtime.repositories.literatureArtifacts,
      "getRelations",
    ).mockResolvedValue({
      ...review,
      relations: review.relations.map((relation) => ({
        ...relation,
        status: "accepted" as const,
      })),
    });

    renderIndex(runtime);

    expect(await screen.findByText(/研究结果 · /)).toBeInTheDocument();
    expect(screen.queryByText(/需要处理 · /)).not.toBeInTheDocument();
    expect(screen.queryByText(/^\d+ 待审$/)).not.toBeInTheDocument();
  });
});
