import type {
  ContentHash,
  DomainEntityId,
  GraphArtifactReview,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import type { EvidenceViewModel } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import {
  buildGraphDiffSnapshot,
  buildEvidenceDiffItems,
  compareScientificSnapshots,
  type ScientificDiffSnapshot,
} from "./scientific-diff";

const empty: ScientificDiffSnapshot = {
  conclusions: [],
  evidence: [],
  relations: [],
  limitations: [],
};

describe("scientific result comparison", () => {
  it("reports an equal-count Evidence source, locator, or quote replacement", () => {
    const evidence = (
      id: string,
      sourceId: string,
      page: number,
      quoteOrValue: string,
    ): EvidenceViewModel => ({
      id: id as DomainEntityId,
      artifactVersionId: "version" as DomainEntityId,
      targetType: "claim",
      targetId: "claim-stable" as DomainEntityId,
      evidenceType: "paper_text",
      sourceSnapshotId: `${sourceId}-snapshot` as DomainEntityId,
      paperId: null,
      locator: {
        kind: "paper_text",
        section: "Results",
        page,
        paragraph: 2,
        range: null,
      },
      quoteOrValue,
      extractionMethod: "manual",
      confidence: 1,
      createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      source: {
        sourceId,
        sourceType: "paper",
        retrievedAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
        licenseNote: "Open access",
        sourceVersionOrEtag: null,
        requestMetadata: {},
      },
    });
    const baseline = {
      ...empty,
      evidence: buildEvidenceDiffItems([
        evidence(
          "evidence-stable-baseline",
          "paper-stable",
          2,
          "Stable finding",
        ),
        evidence(
          "evidence-replaced-baseline",
          "paper-a",
          3,
          "Original finding",
        ),
      ]),
    };
    const current = {
      ...empty,
      evidence: buildEvidenceDiffItems([
        evidence(
          "evidence-stable-current",
          "paper-stable",
          2,
          "Stable finding",
        ),
        evidence("evidence-replaced-current", "paper-b", 4, "Revised finding"),
      ]),
    };

    const evidenceResult = compareScientificSnapshots(baseline, current).find(
      (result) => result.category === "evidence",
    );

    expect(evidenceResult?.changes).toHaveLength(1);
    expect(evidenceResult?.changes[0]).toMatchObject({ kind: "changed" });
    expect(evidenceResult?.changes[0]?.before).toContain("Original finding");
    expect(evidenceResult?.changes[0]?.after).toContain("Revised finding");
  });

  it("keeps stable Evidence identities unchanged across reorder and prepend", () => {
    const evidence = (id: string, value: string): EvidenceViewModel => ({
      id: id as DomainEntityId,
      artifactVersionId: "version" as DomainEntityId,
      targetType: "claim",
      targetId: "claim-stable" as DomainEntityId,
      evidenceType: "paper_text",
      sourceSnapshotId: `${value}-snapshot` as DomainEntityId,
      paperId: null,
      locator: null,
      quoteOrValue: value,
      extractionMethod: "manual",
      confidence: 1,
      createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      source: null,
    });
    const baseline = {
      ...empty,
      evidence: buildEvidenceDiffItems([
        evidence("evidence-a-baseline", "a"),
        evidence("evidence-b-baseline", "b"),
      ]),
    };
    const reordered = {
      ...empty,
      evidence: buildEvidenceDiffItems([
        evidence("evidence-new-current", "new"),
        evidence("evidence-b-current", "b"),
        evidence("evidence-a-current", "a"),
      ]),
    };

    const evidenceResult = compareScientificSnapshots(baseline, reordered).find(
      (result) => result.category === "evidence",
    );

    expect(evidenceResult?.changes).toHaveLength(1);
    expect(evidenceResult?.changes[0]).toMatchObject({
      kind: "added",
      before: null,
    });
  });

  it("classifies semantic additions, removals and changes", () => {
    const results = compareScientificSnapshots(
      {
        ...empty,
        conclusions: [
          { key: "stable", value: "原结论" },
          { key: "removed", value: "被移除结论" },
        ],
      },
      {
        ...empty,
        conclusions: [
          { key: "stable", value: "修订结论" },
          { key: "added", value: "新增结论" },
        ],
      },
    );

    expect(results[0]?.changes).toEqual([
      {
        key: "stable",
        kind: "changed",
        before: "原结论",
        after: "修订结论",
      },
      {
        key: "removed",
        kind: "removed",
        before: "被移除结论",
        after: null,
      },
      {
        key: "added",
        kind: "added",
        before: null,
        after: "新增结论",
      },
    ]);
  });

  it("builds graph changes from readable scientific identities", () => {
    const id = (value: string) => value as DomainEntityId;
    const review: GraphArtifactReview = {
      kind: "graph",
      graphId: null,
      artifactId: id("artifact"),
      artifactVersionId: id("version"),
      projectId: id("project"),
      versionNumber: 1,
      schemaVersion: "2.0.0",
      sourceMode: "live",
      contentHash: "content" as ContentHash,
      inputHash: "input" as ContentHash,
      createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      nodeCount: 2,
      edgeCount: 1,
      evidenceUseCount: 1,
      inputVersions: [],
      integrity: {
        status: "pass",
        counts: {
          edgeCount: 1,
          evidenceUseCount: 1,
          inputVersionCount: 1,
          nodeCount: 2,
          relationEdgeCount: 1,
          sourceSnapshotCount: 1,
        },
        findings: [],
      },
      layoutStrategy: "dagre",
      scopeSummary: [],
      taxonomyNodeTypes: ["claim"],
      taxonomyEdgeTypes: ["supports"],
      progressive: { chunkCount: 1, complete: true },
      nodes: [
        {
          nodeId: id("node-a"),
          nodeType: "claim",
          label: "液态水可能存在",
          logicalReference: [],
          versionBindings: [],
        },
        {
          nodeId: id("node-b"),
          nodeType: "claim",
          label: "目标位于宜居带",
          logicalReference: [],
          versionBindings: [],
        },
      ],
      edges: [
        {
          edgeId: id("edge"),
          edgeType: "supports",
          sourceNodeId: id("node-a"),
          targetNodeId: id("node-b"),
          evidenceIds: [id("evidence")],
          evidenceUseIds: [],
          dataAggregation: null,
          relationTrace: null,
          relation: null,
        },
      ],
    };

    const snapshot = buildGraphDiffSnapshot(review);

    expect(snapshot.relations[0]?.value).toContain("液态水可能存在");
    expect(snapshot.relations[0]?.value).toContain("目标位于宜居带");
    expect(snapshot.evidence[0]?.value).toContain("1 条直接证据");
  });
});
