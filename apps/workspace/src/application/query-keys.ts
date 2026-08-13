import type { DomainEntityId } from "@xingwen/domain";

const PRIVATE_QUERY_ROOT = "workspace" as const;

export const workspaceQueryKeys = Object.freeze({
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
  runEvents: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "events"] as const,
  runSteps: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "steps"] as const,
  runArtifacts: (projectId: DomainEntityId, runId: DomainEntityId) =>
    [...workspaceQueryKeys.run(projectId, runId), "artifacts"] as const,
  scientificArtifact: (
    projectId: DomainEntityId,
    artifactVersionId: DomainEntityId,
  ) =>
    [
      ...workspaceQueryKeys.projectScope(projectId),
      "scientific-artifact",
      artifactVersionId,
    ] as const,
});

export function isPrivateWorkspaceQuery(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === PRIVATE_QUERY_ROOT;
}
