import type {
  ArtifactVersionSummary,
  DomainEntityId,
  PublicArtifactPresentation,
  PublicPresentationEntry,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import {
  describeArtifactLineage,
  selectGlobalRevisionMode,
  toCandidateRelationOptions,
} from "./artifact-fullscreen-workspace";

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

describe("Object revision candidate gating", () => {
  function relationsPresentation(
    entries: readonly Partial<PublicPresentationEntry>[],
  ): PublicArtifactPresentation {
    return {
      kind: "literature_relations",
      summary: null,
      facts: [],
      sections: [],
      entries: entries.map(
        (entry) =>
          ({
            key: "relation",
            title: "候选关系",
            externalUrl: null,
            status: null,
            assessment: null,
            paragraphs: [],
            facts: [],
            evidenceIds: [],
            reasoningTrace: null,
            canAdjudicate: null,
            ...entry,
          }) as unknown as PublicPresentationEntry,
      ),
      tables: [],
      graphNodes: [],
      graphEdges: [],
    } as unknown as PublicArtifactPresentation;
  }

  it("only surfaces adjudicable candidate relations as revision options", () => {
    const options = toCandidateRelationOptions(
      relationsPresentation([
        { key: "adjudicable", title: "可审定关系", canAdjudicate: true },
        { key: "not-evaluated", title: "未评估关系", canAdjudicate: null },
        {
          key: "not-adjudicable",
          title: "不可审定关系",
          canAdjudicate: false,
        },
      ]),
    );
    expect(options).toEqual([
      { relationId: "adjudicable", title: "可审定关系" },
    ]);
  });

  it("offers no candidate options outside literature relations", () => {
    expect(toCandidateRelationOptions(relationsPresentation([]))).toEqual([]);
    expect(
      toCandidateRelationOptions({
        ...relationsPresentation([]),
        kind: "dataset",
      } as unknown as PublicArtifactPresentation),
    ).toEqual([]);
    expect(toCandidateRelationOptions(null)).toEqual([]);
    expect(toCandidateRelationOptions(undefined)).toEqual([]);
  });

  it("keeps the fullscreen global revision action as artifact correction", () => {
    expect(selectGlobalRevisionMode()).toEqual({
      kind: "artifact_correction",
    });
  });
});
