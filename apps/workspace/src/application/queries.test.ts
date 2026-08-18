import { asEntityId } from "@xingwen/domain";
import { describe, expect, it, vi } from "vitest";

import { createTestRuntime } from "../test/runtime";

const PROJECT_ID = asEntityId("proj_01JEXAMPLE");
const VERSION_ID = asEntityId("artv_papsum_01");

describe("Workspace ArtifactVersion queries", () => {
  it("returns the exact requested PaperSummary version", async () => {
    const runtime = createTestRuntime();
    const summary = await runtime.queryClient.fetchQuery(
      runtime.application.queries.paperSummary(PROJECT_ID, VERSION_ID),
    );

    expect(summary.artifactVersionId).toBe(VERSION_ID);
    expect(summary.projectId).toBe(PROJECT_ID);
  });

  it("fails closed when a version belongs to another project", async () => {
    const runtime = createTestRuntime();
    const version = await runtime.repositories.artifacts.getVersion(VERSION_ID);
    if (!version) throw new Error("Fixture ArtifactVersion is missing.");
    vi.spyOn(runtime.repositories.artifacts, "getVersion").mockResolvedValue({
      ...version,
      projectId: asEntityId("different-project"),
    });

    await expect(
      runtime.queryClient.fetchQuery(
        runtime.application.queries.artifactVersion(PROJECT_ID, VERSION_ID),
      ),
    ).rejects.toMatchObject({ name: "EntityNotFoundError" });
  });

  it("rejects a repository response for a different requested version", async () => {
    const runtime = createTestRuntime();
    const summary =
      await runtime.repositories.paperSummary.getSummary(VERSION_ID);
    vi.spyOn(runtime.repositories.paperSummary, "getSummary").mockResolvedValue(
      {
        ...summary,
        artifactVersionId: asEntityId("different-version"),
      },
    );

    await expect(
      runtime.queryClient.fetchQuery(
        runtime.application.queries.paperSummary(PROJECT_ID, VERSION_ID),
      ),
    ).rejects.toMatchObject({ name: "EntityNotFoundError" });
  });
});
