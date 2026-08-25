import type { ArtifactVersionSummary, DomainEntityId } from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { describeArtifactLineage } from "./artifact-fullscreen-workspace";

describe("Artifact result lineage", () => {
  it("uses formal supersedes and Run derivation fields to locate history", () => {
    const predecessor = {
      id: "version-before" as DomainEntityId,
      artifactId: "artifact" as DomainEntityId,
      versionNumber: 1,
      schemaVersion: "2.0.0",
      contentHash: "before",
      sourceMode: "live",
      supersedesVersionId: null,
      createdAt: "2026-08-24T08:00:00Z",
    } as ArtifactVersionSummary;
    const version = {
      provenance: { supersedesVersionId: predecessor.id },
    } as ArtifactVersionMetadataViewModel;
    const run = {
      parentRunId: "run-before" as DomainEntityId,
      derivationKind: "revision",
    } as ResearchRunViewModel;

    const result = describeArtifactLineage(version, run, [predecessor]);

    expect(result.predecessor).toBe(predecessor);
    expect(result.description).toContain("直接前序结果");
    expect(result.description).toContain("修订");
    expect(result.description).not.toContain("version-before");
    expect(result.description).not.toContain("run-before");
  });
});
