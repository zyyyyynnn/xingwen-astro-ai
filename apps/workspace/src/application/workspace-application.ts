import type { QueryClient } from "@tanstack/react-query";
import type { RepositorySet, SessionManager } from "@xingwen/data-access";
import type { DomainEntityId } from "@xingwen/domain";
import type { ResearchAdapter } from "@xingwen/research-adapter";

import { createWorkspaceMutations } from "./mutations";
import { createWorkspaceQueries } from "./queries";
import { createRunEventFeed } from "./run-event-feed";
import { createSessionGate } from "./session-gate";

interface WorkspaceApplicationDependencies {
  readonly repositories: RepositorySet;
  readonly researchAdapter: ResearchAdapter;
  readonly session: SessionManager;
  readonly queryClient: QueryClient;
  readonly createIdempotencyKey?: () => string;
}

function createBrowserIdempotencyKey(): string {
  return globalThis.crypto.randomUUID();
}

export function createWorkspaceApplication({
  repositories,
  researchAdapter,
  session,
  queryClient,
  createIdempotencyKey = createBrowserIdempotencyKey,
}: WorkspaceApplicationDependencies) {
  const queries = createWorkspaceQueries({ repositories, researchAdapter });
  const mutations = createWorkspaceMutations({
    repositories,
    researchAdapter,
    queryClient,
    createIdempotencyKey,
  });
  const sessionGate = createSessionGate({
    session,
    queryClient,
    toPublicError: researchAdapter.toPublicApplicationError,
  });

  return Object.freeze({
    queries,
    mutations,
    sessionGate,
    createRunEventFeed(runId: DomainEntityId) {
      return createRunEventFeed({
        runId,
        runs: repositories.runs,
        researchAdapter,
        queryClient,
        runQuery: queries.run,
        visibilitySource:
          typeof document === "undefined" ? undefined : document,
      });
    },
    dispose() {
      sessionGate.dispose();
    },
  });
}

export type WorkspaceApplication = ReturnType<
  typeof createWorkspaceApplication
>;
