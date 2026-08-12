import type { DomainEntityId } from "@xingwen/domain";

const PRIVATE_QUERY_ROOT = "workspace" as const;

export const workspaceQueryKeys = Object.freeze({
  projects: () => [PRIVATE_QUERY_ROOT, "projects"] as const,
  project: (projectId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "project", projectId] as const,
  researchCatalog: (projectId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "research-catalog", projectId] as const,
  thread: (projectId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "research-thread", projectId] as const,
  draft: (draftId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "draft", draftId] as const,
  contract: (contractId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "contract", contractId] as const,
  run: (runId: DomainEntityId) => [PRIVATE_QUERY_ROOT, "run", runId] as const,
  runEvents: (runId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "run-events", runId] as const,
  runSteps: (runId: DomainEntityId) =>
    [PRIVATE_QUERY_ROOT, "run-steps", runId] as const,
});

export function isPrivateWorkspaceQuery(queryKey: readonly unknown[]): boolean {
  return queryKey[0] === PRIVATE_QUERY_ROOT;
}
