import type { DomainEntityId } from "@xingwen/domain";

const PRIVATE_QUERY_ROOT = "workspace" as const;

export const workspaceQueryKeys = Object.freeze({
  modelProviderConfiguration: () =>
    [PRIVATE_QUERY_ROOT, "model-provider", "configuration"] as const,
  projects: () => [PRIVATE_QUERY_ROOT, "projects"] as const,
  projectScope: (projectId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "project", projectId] as const,
  project: (projectId: DomainEntityId) =>
    [...workspaceQueryKeys.projectScope(projectId), "detail"] as const,
  researchCatalog: (projectId: DomainEntityId) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "research-catalog",
    ] as const,
  researchInputs: (projectId: DomainEntityId) =>
    [...workspaceQueryKeys.projectScope(projectId), "research-inputs"] as const,
  thread: (projectId: DomainEntityId) =>
    [...workspaceQueryKeys.projectScope(projectId), "research-thread"] as const,
  draft: (projectId: DomainEntityId, draftId: DomainEntityId) =>
    [...workspaceQueryKeys.projectScope(projectId), "draft", draftId] as const,
  contract: (projectId: DomainEntityId, contractId: DomainEntityId) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "contract",
      contractId,
    ] as const,
  run: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.projectScope(projectId), "run", runId] as const,
  runCheckpoint: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "checkpoint"] as const,
  runEvents: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "events"] as const,
  runSteps: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "steps"] as const,
  artifactsByRun: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "artifacts"] as const,
  artifact: (projectId: DomainEntityId, artifactId: DomainEntityId) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "artifact",
      artifactId,
    ] as const,
  artifactVersions: (projectId: DomainEntityId, artifactId: DomainEntityId) =>
    [
      ...workspaceQueryKeys.artifact(projectId, artifactId),
      "versions",
    ] as const,
  artifactVersion: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "artifact-version",
      artifactVersionId,
    ] as const,
  evidence: (
    projectId: DomainEntityId,
    expectedArtifactVersionId: DomainEntityId,
    evidenceId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "evidence",
      expectedArtifactVersionId,
      evidenceId,
    ] as const,
  sourceSnapshot: (
    projectId: DomainEntityId,
    sourceSnapshotId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "source-snapshot",
      sourceSnapshotId,
    ] as const,
  paperSummary: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.artifactVersion(projectId, artifactVersionId),
      "paper-summary",
    ] as const,
  paperSummaryDocumentSource: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.paperSummary(projectId, artifactVersionId),
      "document-source",
    ] as const,
  dataArtifact: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
    kind: string,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "data-artifact",
      kind,
      artifactVersionId,
    ] as const,
  paperAcquisition: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "paper-acquisition",
      artifactVersionId,
    ] as const,
  literatureArtifact: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
    kind: string,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "literature-artifact",
      kind,
      artifactVersionId,
    ] as const,
  graphArtifact: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "graph-artifact",
      artifactVersionId,
    ] as const,
  scientificArtifact: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
    kind: string,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "scientific-artifact",
      kind,
      artifactVersionId,
    ] as const,
});

export function isPrivateWorkspaceQuery(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === PRIVATE_QUERY_ROOT;
}
