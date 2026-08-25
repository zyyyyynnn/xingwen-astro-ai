import type {
  ContentHash,
  DomainEntityId,
  GraphArtifactReview,
  SourceSnapshotSummary,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import type {
  ContractInputViewModel,
  EvidenceViewModel,
} from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import {
  buildGraphDiffSnapshot,
  buildContractDiffItems,
  buildEvidenceDiffItems,
  buildSourceSetDiffItems,
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

    expect(
      results.find((result) => result.category === "conclusions")?.changes,
    ).toEqual([
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

  it("reports typed immutable Contract changes", () => {
    const contract = (goal: string): ContractInputViewModel => ({
      researchGoal: goal,
      targetObjects: ["toi-700" as DomainEntityId],
      dataRequirements: {
        unitPolicy: "canonical",
        documentSourcePolicy: "disabled",
      },
      requestedFields: ["orbital_period" as DomainEntityId],
      sourceScope: {
        allowedSources: ["nasa_exoplanet_archive" as DomainEntityId],
      },
      paperSearchScope: {
        keywords: ["exoplanet"],
        yearFrom: 2020,
        yearTo: 2026,
        sourceIds: ["crossref" as DomainEntityId],
        maxCandidates: 20,
      },
      scientificTasks: [],
      outputRequirements: ["dataset"],
      evidenceRequirements: {
        requireLocator: true,
        requireSourceSnapshot: true,
        minimumCoverage: 1,
      },
      qualityConstraints: {
        sourceCompletenessMin: 1,
        unitConsistencyMin: 1,
      },
    });
    const results = compareScientificSnapshots(
      { ...empty, contract: buildContractDiffItems(contract("原研究目标")) },
      { ...empty, contract: buildContractDiffItems(contract("修订研究目标")) },
    );

    const contractChanges = results.find(
      (result) => result.category === "contract",
    )?.changes;
    expect(contractChanges).toHaveLength(1);
    expect(contractChanges?.[0]).toMatchObject({
      kind: "changed",
      before: "研究目标：原研究目标",
      after: "研究目标：修订研究目标",
    });
  });

  it("detects equal-count Source Set member replacement without exposing hashes", () => {
    const snapshot = (
      id: string,
      sourceId: string,
      contentHash: string,
    ): SourceSnapshotSummary => ({
      id: id as DomainEntityId,
      sourceId: sourceId as DomainEntityId,
      sourceType: "catalog",
      retrievedAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      queryHash: `query-${contentHash}` as ContentHash,
      contentHash: contentHash as ContentHash,
      sourceVersionOrEtag: null,
      licenseNote: "Open data",
      cacheVersion: null,
      requestMetadata: [],
      cachedOrigin: null,
    });
    const stable = snapshot("snapshot-stable", "gaia", "hash-stable");
    const replaced = snapshot("snapshot-a", "archive-a", "hash-a");
    const replacement = snapshot("snapshot-b", "archive-b", "hash-b");
    const results = compareScientificSnapshots(
      {
        ...empty,
        sources: buildSourceSetDiffItems([stable, replaced]),
      },
      {
        ...empty,
        sources: buildSourceSetDiffItems([stable, replacement]),
      },
    );

    const changes = results.find(
      (result) => result.category === "sources",
    )?.changes;
    expect(changes).toHaveLength(2);
    expect(changes?.map((change) => change.kind).sort()).toEqual([
      "added",
      "removed",
    ]);
    expect(
      changes?.map((change) => `${change.before}${change.after}`).join(" "),
    ).not.toContain("hash-");
  });

  it("does not report Source Set reorder as a change", () => {
    const snapshot = (id: string, sourceId: string): SourceSnapshotSummary => ({
      id: id as DomainEntityId,
      sourceId: sourceId as DomainEntityId,
      sourceType: "catalog",
      retrievedAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      queryHash: `query-${id}` as ContentHash,
      contentHash: `content-${id}` as ContentHash,
      sourceVersionOrEtag: null,
      licenseNote: "Open data",
      cacheVersion: null,
      requestMetadata: [],
      cachedOrigin: null,
    });
    const first = snapshot("snapshot-a", "archive-a");
    const second = snapshot("snapshot-b", "archive-b");
    const results = compareScientificSnapshots(
      { ...empty, sources: buildSourceSetDiffItems([first, second]) },
      { ...empty, sources: buildSourceSetDiffItems([second, first]) },
    );

    expect(
      results.find((result) => result.category === "sources")?.changes,
    ).toEqual([]);
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
