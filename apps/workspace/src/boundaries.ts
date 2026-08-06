import type {
  FixtureRepositorySet,
  RepositorySet,
  SessionManager,
} from "@xingwen/data-access";
import type { QueryClient } from "@tanstack/react-query";
import type {
  GuidedTourController,
  WorkspaceController,
} from "@xingwen/workspace-core";

type RepositoryEntityId = Parameters<RepositorySet["projects"]["getById"]>[0];

export interface FixtureBootstrapContext {
  readonly projectId: RepositoryEntityId;
  readonly draftId: RepositoryEntityId;
  readonly contractId: RepositoryEntityId;
  readonly runId: RepositoryEntityId;
}

interface WorkspaceRuntimeBase {
  readonly repositories: RepositorySet;
  readonly tour: GuidedTourController;
  readonly workspaceController: WorkspaceController;
  readonly queryClient: QueryClient;
}

export interface FixtureWorkspaceRuntimeBoundaries extends WorkspaceRuntimeBase {
  readonly adapterKind: "fixture";
  readonly repositories: FixtureRepositorySet;
  readonly bootstrap: FixtureBootstrapContext;
}

export interface HttpWorkspaceRuntimeBoundaries extends WorkspaceRuntimeBase {
  readonly adapterKind: "http";
  readonly session: SessionManager;
}

/**
 * The single runtime boundary consumed by Workspace pages. Adapter selection is
 * performed once at bootstrap; pages only receive Repository Ports and domain
 * controllers.
 */
export type WorkspaceRuntimeBoundaries =
  FixtureWorkspaceRuntimeBoundaries | HttpWorkspaceRuntimeBoundaries;
