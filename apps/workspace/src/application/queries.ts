import { queryOptions } from "@tanstack/react-query";
import { EntityNotFoundError } from "@xingwen/data-access/errors";
import type { RepositorySet } from "@xingwen/data-access/ports";
import type {
  DomainEntityId,
  ResearchArtifact,
  ScientificArtifactReview,
} from "@xingwen/domain";
import type {
  ActivityPresentationEvent,
  ProjectViewModel,
  ResearchAdapter,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchPlanningCatalogViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  RunStepViewModel,
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";

interface WorkspaceQueriesDependencies {
  readonly repositories: Pick<
    RepositorySet,
    | "projects"
    | "researchCatalog"
    | "contracts"
    | "runs"
    | "researchThread"
    | "artifacts"
    | "scientificArtifacts"
  >;
  readonly researchAdapter: ResearchAdapter;
}

export interface RunEventFeedCache {
  readonly events: readonly ActivityPresentationEvent[];
  readonly cursor: string | null;
  readonly lastSequence: number;
  readonly latestSequence: number;
  readonly error: unknown | null;
}

export const EMPTY_RUN_EVENT_FEED: RunEventFeedCache = Object.freeze({
  events: [],
  cursor: null,
  lastSequence: 0,
  latestSequence: 0,
  error: null,
});

async function requireEntity<T>(
  kind: string,
  id: DomainEntityId,
  read: () => Promise<T | null>,
): Promise<T> {
  const entity = await read();
  if (entity === null) throw new EntityNotFoundError(kind, id);
  return entity;
}

export function createWorkspaceQueries({
  repositories,
  researchAdapter,
}: WorkspaceQueriesDependencies) {
  return Object.freeze({
    projects: () =>
      queryOptions({
        queryKey: workspaceQueryKeys.projects(),
        queryFn: async (): Promise<readonly ProjectViewModel[]> => {
          const projects: ProjectViewModel[] = [];
          const seenCursors = new Set<string>();
          let cursor: string | null = null;
          do {
            const page = await repositories.projects.list(cursor);
            projects.push(
              ...page.items.map(researchAdapter.toProjectViewModel),
            );
            if (page.nextCursor && seenCursors.has(page.nextCursor)) {
              throw new Error("Project listing returned a repeated cursor.");
            }
            if (page.nextCursor) seenCursors.add(page.nextCursor);
            cursor = page.nextCursor;
          } while (cursor !== null);
          return projects;
        },
      }),
    project: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.project(projectId),
        queryFn: async (): Promise<ProjectViewModel> =>
          researchAdapter.toProjectViewModel(
            await requireEntity("ResearchProject", projectId, () =>
              repositories.projects.getById(projectId),
            ),
          ),
      }),
    researchCatalog: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.researchCatalog(projectId),
        queryFn: async (): Promise<ResearchPlanningCatalogViewModel> =>
          repositories.researchCatalog.getForProject(projectId),
      }),
    thread: (projectId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.thread(projectId),
        queryFn: async (): Promise<readonly ResearchThreadEntryViewModel[]> => {
          const entries: ResearchThreadEntryViewModel[] = [];
          let cursor: string | null = null;
          const seen = new Set<string>();
          do {
            const page = await repositories.researchThread.list(
              projectId,
              cursor,
            );
            entries.push(
              ...page.items.map(researchAdapter.toResearchThreadEntryViewModel),
            );
            if (page.nextCursor !== null && seen.has(page.nextCursor)) {
              throw new Error("Research Thread returned a repeated cursor.");
            }
            if (page.nextCursor !== null) seen.add(page.nextCursor);
            cursor = page.nextCursor;
          } while (cursor !== null);
          return entries;
        },
      }),
    draft: (projectId: DomainEntityId, draftId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.draft(projectId, draftId),
        queryFn: async (): Promise<ResearchContractDraftViewModel> =>
          researchAdapter.toContractDraftViewModel(
            await requireEntity("ResearchContractDraft", draftId, () =>
              repositories.contracts.getDraftById(draftId),
            ),
          ),
      }),
    contract: (projectId: DomainEntityId, contractId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.contract(projectId, contractId),
        queryFn: async (): Promise<ResearchContractViewModel> =>
          researchAdapter.toContractViewModel(
            await requireEntity("ResearchContract", contractId, () =>
              repositories.contracts.getContractById(contractId),
            ),
          ),
      }),
    run: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.run(projectId, runId),
        queryFn: async (): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await requireEntity("ResearchRun", runId, () =>
              repositories.runs.getById(runId),
            ),
          ),
      }),
    runEvents: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runEvents(projectId, runId),
        queryFn: async (): Promise<RunEventFeedCache> => EMPTY_RUN_EVENT_FEED,
        initialData: EMPTY_RUN_EVENT_FEED,
        enabled: false,
      }),
    runSteps: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runSteps(projectId, runId),
        queryFn: async (): Promise<readonly RunStepViewModel[]> =>
          (await repositories.runs.listSteps(runId)).map(
            researchAdapter.toRunStepViewModel,
          ),
      }),
    runArtifacts: (projectId: DomainEntityId, runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runArtifacts(projectId, runId),
        queryFn: async (): Promise<readonly ResearchArtifact[]> =>
          repositories.artifacts.listByRun(runId),
      }),
    scientificArtifact: (
      projectId: DomainEntityId,
      artifactVersionId: DomainEntityId,
    ) =>
      queryOptions({
        queryKey: workspaceQueryKeys.scientificArtifact(
          projectId,
          artifactVersionId,
        ),
        queryFn: async (): Promise<ScientificArtifactReview> =>
          repositories.scientificArtifacts.getReview(artifactVersionId),
      }),
  });
}

export type WorkspaceQueries = ReturnType<typeof createWorkspaceQueries>;
