/**
 * Query layer for the A-17 research workbench.
 *
 * Every hook wraps a {@link RepositorySet} call so page components never
 * call repositories directly. Query keys follow a hierarchical scheme so
 * invalidation is scoped to the right entity.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RepositorySet } from "@xingwen/data-access";

type EntityId = Parameters<RepositorySet["projects"]["getById"]>[0];
type Project = NonNullable<
  Awaited<ReturnType<RepositorySet["projects"]["getById"]>>
>;
type ResearchRun = NonNullable<
  Awaited<ReturnType<RepositorySet["runs"]["getById"]>>
>;
type Contract = NonNullable<
  Awaited<ReturnType<RepositorySet["contracts"]["getContractById"]>>
>;
type Artifact = Awaited<
  ReturnType<RepositorySet["artifacts"]["listByRun"]>
>[number];
type ArtifactVersion = NonNullable<
  Awaited<ReturnType<RepositorySet["artifacts"]["getVersion"]>>
>;
type Evidence = NonNullable<
  Awaited<ReturnType<RepositorySet["artifacts"]["getEvidence"]>>
>;
type Share = Awaited<ReturnType<RepositorySet["shares"]["list"]>>[number];
type RunEventRecovery = Awaited<
  ReturnType<RepositorySet["runs"]["recoverEvents"]>
>;
type CreateShareRequest = Parameters<RepositorySet["shares"]["create"]>[1];

export const queryKeys = {
  projects: () => ["projects"] as const,
  project: (projectId: EntityId | string) => ["projects", projectId] as const,
  contract: (contractId: EntityId | string) =>
    ["contracts", contractId] as const,
  run: (runId: EntityId | string) => ["runs", runId] as const,
  runEvents: (runId: EntityId | string) => ["runs", runId, "events"] as const,
  artifacts: (runId: EntityId | string) =>
    ["runs", runId, "artifacts"] as const,
  artifactVersion: (versionId: EntityId | string) =>
    ["artifactVersions", versionId] as const,
  evidence: (evidenceId: EntityId | string) =>
    ["evidence", evidenceId] as const,
  shares: (projectId: EntityId | string) =>
    ["projects", projectId, "shares"] as const,
} as const;

export function useProjectsQuery(repositories: RepositorySet) {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: () => repositories.projects.list().then((page) => page.items),
  });
}

export function useProjectQuery(
  repositories: RepositorySet,
  projectId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.project(projectId ?? ""),
    queryFn: () => repositories.projects.getById(projectId!),
    enabled: projectId !== null,
  });
}

export function useContractQuery(
  repositories: RepositorySet,
  contractId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.contract(contractId ?? ""),
    queryFn: () => repositories.contracts.getContractById(contractId!),
    enabled: contractId !== null,
  });
}

export function useRunQuery(
  repositories: RepositorySet,
  runId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.run(runId ?? ""),
    queryFn: () => repositories.runs.getById(runId!),
    enabled: runId !== null,
  });
}

export function useRunEventsQuery(
  repositories: RepositorySet,
  runId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.runEvents(runId ?? ""),
    queryFn: () => repositories.runs.recoverEvents(runId!),
    enabled: runId !== null,
  });
}

export function useArtifactsQuery(
  repositories: RepositorySet,
  runId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.artifacts(runId ?? ""),
    queryFn: () => repositories.artifacts.listByRun(runId!),
    enabled: runId !== null,
  });
}

export function useArtifactVersionQuery(
  repositories: RepositorySet,
  versionId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.artifactVersion(versionId ?? ""),
    queryFn: () => repositories.artifacts.getVersion(versionId!),
    enabled: versionId !== null,
  });
}

export function useEvidenceQuery(
  repositories: RepositorySet,
  evidenceId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.evidence(evidenceId ?? ""),
    queryFn: () => repositories.artifacts.getEvidence(evidenceId!),
    enabled: evidenceId !== null,
  });
}

export function useSharesQuery(
  repositories: RepositorySet,
  projectId: EntityId | null,
) {
  return useQuery({
    queryKey: queryKeys.shares(projectId ?? ""),
    queryFn: () => repositories.shares.list(projectId!),
    enabled: projectId !== null,
  });
}

export function useCreateShareMutation(
  repositories: RepositorySet,
  projectId: EntityId,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateShareRequest) =>
      repositories.shares.create(projectId, request),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.shares(projectId),
      });
    },
  });
}

export function useRevokeShareMutation(
  repositories: RepositorySet,
  projectId: EntityId,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (shareId: EntityId) =>
      repositories.shares.revoke(projectId, shareId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.shares(projectId),
      });
    },
  });
}

export type {
  Artifact,
  ArtifactVersion,
  Contract,
  CreateShareRequest,
  EntityId,
  Evidence,
  Project,
  ResearchRun,
  RunEventRecovery,
  Share,
};
