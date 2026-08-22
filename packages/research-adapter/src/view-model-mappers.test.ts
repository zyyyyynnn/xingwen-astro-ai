import {
  asEntityId,
  type ArtifactVersionMetadata,
  type Evidence,
  type ResearchArtifact,
  type ResearchContract,
  type ResearchContractDraft,
  type ResearchProject,
  type ResearchRun,
} from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import {
  toArtifactVersionViewModel,
  toArtifactViewModel,
  toContractDraftViewModel,
  toContractViewModel,
  toEvidenceViewModel,
  toProjectViewModel,
  toRunViewModel,
} from "./view-model-mappers";

const projectId = asEntityId("proj_test");
const runId = asEntityId("run_test");
const artifactId = asEntityId("artifact_test");
const versionId = asEntityId("version_test");

const contractInput = {
  researchGoal: "Compare exoplanet candidates with host-star parameters",
  targetObjects: [asEntityId("exoplanet_candidate")],
  dataRequirements: {
    unitPolicy: "canonical" as const,
    documentSourcePolicy: "disabled" as const,
  },
  requestedFields: [asEntityId("planet.toi_id")],
  sourceScope: { allowedSources: [asEntityId("nasa_exoplanet_archive")] },
  paperSearchScope: {
    keywords: ["exoplanet"],
    yearFrom: 2015,
    yearTo: null,
    sourceIds: [asEntityId("nasa_ads")],
    maxCandidates: 10,
  },
  scientificTasks: [],
  outputRequirements: ["dataset" as const],
  evidenceRequirements: {
    requireLocator: true,
    requireSourceSnapshot: true,
    minimumCoverage: 1,
  },
  qualityConstraints: {
    sourceCompletenessMin: 1,
    unitConsistencyMin: 1,
  },
};

const project: ResearchProject = {
  id: projectId,
  sessionId: asEntityId("private_session"),
  name: "Fixture project",
  description: "A deterministic project",
  caseKey: "exoplanet_host_star",
  activeContractId: asEntityId("contract_test"),
  latestRunId: runId,
  threadSummary: {
    hasThreadEntries: true,
    latestThreadActor: "assistant",
    hasUnansweredClarification: true,
  },
  createdAt: "2026-08-11T00:00:00Z",
  updatedAt: "2026-08-11T00:01:00Z",
  revision: 3,
};

const draft: ResearchContractDraft = {
  id: asEntityId("draft_test"),
  sessionId: asEntityId("private_session"),
  version: 4,
  intent: "Compare candidates",
  status: "draft",
  contract: contractInput,
  warnings: ["Source scope is narrow"],
  createdAt: "2026-08-11T00:00:00Z",
  updatedAt: "2026-08-11T00:01:00Z",
  expiresAt: "2026-08-12T00:00:00Z",
};

const contract: ResearchContract = {
  ...contractInput,
  id: asEntityId("contract_test"),
  projectId,
  version: 2,
  createdFromDraftId: draft.id,
  createdAt: "2026-08-11T00:02:00Z",
  contentHash: "sha256:contract",
};

function createRun(
  status: ResearchRun["status"],
  executionMode: ResearchRun["executionMode"],
): ResearchRun {
  return {
    id: runId,
    projectId,
    contractId: contract.id,
    executionMode,
    status,
    progress: status === "completed" ? 100 : 60,
    parentRunId: null,
    derivationKind: "original",
    retryFromStep: null,
    cachePolicy: "disabled",
    startedAt: "2026-08-11T00:03:00Z",
    finishedAt:
      status === "completed" || status === "failed" || status === "cancelled"
        ? "2026-08-11T00:04:00Z"
        : null,
    createdAt: "2026-08-11T00:03:00Z",
    updatedAt: "2026-08-11T00:04:00Z",
    latestEventSequence: 5,
    failureCode: status === "failed" ? "UPSTREAM" : null,
    failureSummary: status === "failed" ? "Public failure summary" : null,
  };
}

const artifact: ResearchArtifact = {
  id: artifactId,
  projectId,
  kind: "dataset",
  title: "Candidate dataset",
  logicalKey: asEntityId("dataset.primary"),
  createdAt: "2026-08-11T00:05:00Z",
  latestVersionId: versionId,
};

const version: ArtifactVersionMetadata = {
  id: versionId,
  artifactId,
  projectId,
  createdByRunId: runId,
  versionNumber: 2,
  schemaVersion: "2.0.0",
  contentHash: "sha256:content",
  inputHash: "sha256:input",
  sourceMode: "fixture",
  producer: {
    type: "pipeline",
    name: "data",
    version: "1.0.0",
    modelName: null,
    promptName: null,
    promptVersion: null,
    parametersHash: null,
  },
  sourceSnapshotIds: [asEntityId("snapshot_test")],
  evidenceIds: [asEntityId("evidence_test")],
  supersedesVersionId: asEntityId("version_previous"),
  createdAt: "2026-08-11T00:06:00Z",
};

describe("Domain to ViewModel projections", () => {
  it("projects a project without leaking session ownership", () => {
    const before = JSON.stringify(project);
    const result = toProjectViewModel(project);

    expect(result).toEqual({
      id: project.id,
      name: project.name,
      description: project.description,
      caseKey: project.caseKey,
      activeDraftId: project.activeDraftId,
      activeContractId: project.activeContractId,
      latestRunId: project.latestRunId,
      latestRunStatus: null,
      latestRunFailureSummary: null,
      threadSummary: project.threadSummary,
      revision: project.revision,
      createdAt: project.createdAt,
      updatedAt: project.updatedAt,
    });
    expect("sessionId" in result).toBe(false);
    expect(JSON.stringify(project)).toBe(before);
  });

  it("keeps draft warnings and version while omitting sessionId", () => {
    const result = toContractDraftViewModel(draft);

    expect(result).toMatchObject({
      id: draft.id,
      version: draft.version,
      intent: draft.intent,
      status: draft.status,
      warnings: draft.warnings,
    });
    expect(result.contract.researchGoal).toBe(contractInput.researchGoal);
    expect("sessionId" in result).toBe(false);
  });

  it("keeps confirmed contract semantics and explicit provenance", () => {
    const result = toContractViewModel(contract);

    expect(result.researchGoal).toBe(contract.researchGoal);
    expect(result.targetObjects).toEqual(contract.targetObjects);
    expect(result.createdFromDraftId).toBe(contract.createdFromDraftId);
    expect(result.provenance).toEqual({ contentHash: contract.contentHash });
  });

  it("derives terminal flags only from the domain status", () => {
    const statuses: ResearchRun["status"][] = [
      "queued",
      "planning",
      "fetching_data",
      "cleaning_data",
      "searching_papers",
      "summarizing_papers",
      "reasoning_literature",
      "building_graph",
      "waiting_for_input",
      "completed",
      "failed",
      "cancelled",
    ];

    for (const status of statuses) {
      const result = toRunViewModel(createRun(status, "demo_replay"));
      expect(result.isTerminal).toBe(
        status === "completed" || status === "failed" || status === "cancelled",
      );
      expect(result.isFailed).toBe(status === "failed");
      expect(result.isCancelled).toBe(status === "cancelled");
      expect(result.executionMode).toBe("demo_replay");
    }

    expect(toRunViewModel(createRun("completed", "live")).executionMode).toBe(
      "live",
    );
  });

  it("projects artifact identity without interpreting rich content", () => {
    const result = toArtifactViewModel(artifact);

    expect(result).toEqual(artifact);
  });

  it("preserves immutable version provenance as a dedicated context", () => {
    const result = toArtifactVersionViewModel(version);

    expect(result).toMatchObject({
      id: version.id,
      artifactId: version.artifactId,
      projectId: version.projectId,
      createdByRunId: version.createdByRunId,
      versionNumber: version.versionNumber,
      schemaVersion: version.schemaVersion,
      sourceMode: version.sourceMode,
      createdAt: version.createdAt,
    });
    expect(result.provenance).toEqual({
      contentHash: version.contentHash,
      inputHash: version.inputHash,
      producer: version.producer,
      sourceSnapshotIds: version.sourceSnapshotIds,
      evidenceIds: version.evidenceIds,
      supersedesVersionId: version.supersedesVersionId,
    });
    expect("content" in result).toBe(false);
  });
});

describe("Evidence locator projections", () => {
  const baseEvidence: Omit<Evidence, "locator"> = {
    id: asEntityId("evidence_test"),
    artifactVersionId: versionId,
    targetType: "field",
    targetId: asEntityId("planet.toi_id"),
    evidenceType: "database_query",
    sourceSnapshotId: asEntityId("snapshot_test"),
    paperId: null,
    quoteOrValue: "TOI-1",
    extractionMethod: "query",
    confidence: 1,
    createdAt: "2026-08-11T00:07:00Z",
  };

  it.each([
    {
      kind: "database_cell" as const,
      queryHash: "sha256:query",
      rowKey: "row-1",
      field: asEntityId("planet.toi_id"),
    },
    {
      kind: "paper_text" as const,
      section: "Results",
      page: 2,
      paragraph: 3,
      range: "12-18",
    },
    {
      kind: "model_extraction" as const,
      inputEvidenceId: asEntityId("evidence_input"),
      promptName: "extract-field",
      modelVersion: "model-1",
    },
    {
      kind: "reasoning_trace" as const,
      relationId: asEntityId("relation_test"),
      stepKey: asEntityId("reasoning_step"),
    },
  ])("maps $kind exhaustively", (locator) => {
    const result = toEvidenceViewModel({ ...baseEvidence, locator });

    expect(result.locator).toEqual(locator);
    expect(result.quoteOrValue).toBe(baseEvidence.quoteOrValue);
  });

  it("keeps a missing locator explicit", () => {
    expect(
      toEvidenceViewModel({ ...baseEvidence, locator: null }).locator,
    ).toBe(null);
  });
});
