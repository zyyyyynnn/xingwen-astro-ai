import { queryOptions } from "@tanstack/react-query";
import { EntityNotFoundError } from "@xingwen/data-access/errors";
import type { RepositorySet } from "@xingwen/data-access/ports";
import type { DomainEntityId } from "@xingwen/domain";
import type {
  ActivityPresentationEvent,
  ProjectViewModel,
  ResearchAdapter,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";

interface WorkspaceQueriesDependencies {
  readonly repositories: Pick<RepositorySet, "projects" | "contracts" | "runs">;
  readonly researchAdapter: ResearchAdapter;
}

export interface RunEventFeedCache {
  readonly events: readonly ActivityPresentationEvent[];
  readonly cursor: string | null;
  readonly lastSequence: number;
  readonly latestSequence: number;
}

export const EMPTY_RUN_EVENT_FEED: RunEventFeedCache = Object.freeze({
  events: [],
  cursor: null,
  lastSequence: 0,
  latestSequence: 0,
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
    draft: (draftId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.draft(draftId),
        queryFn: async (): Promise<ResearchContractDraftViewModel> =>
          researchAdapter.toContractDraftViewModel(
            await requireEntity("ResearchContractDraft", draftId, () =>
              repositories.contracts.getDraftById(draftId),
            ),
          ),
      }),
    contract: (contractId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.contract(contractId),
        queryFn: async (): Promise<ResearchContractViewModel> =>
          researchAdapter.toContractViewModel(
            await requireEntity("ResearchContract", contractId, () =>
              repositories.contracts.getContractById(contractId),
            ),
          ),
      }),
    run: (runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.run(runId),
        queryFn: async (): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await requireEntity("ResearchRun", runId, () =>
              repositories.runs.getById(runId),
            ),
          ),
      }),
    runEvents: (runId: DomainEntityId) =>
      queryOptions({
        queryKey: workspaceQueryKeys.runEvents(runId),
        queryFn: async (): Promise<RunEventFeedCache> => EMPTY_RUN_EVENT_FEED,
        initialData: EMPTY_RUN_EVENT_FEED,
        enabled: false,
      }),
  });
}

export type WorkspaceQueries = ReturnType<typeof createWorkspaceQueries>;
