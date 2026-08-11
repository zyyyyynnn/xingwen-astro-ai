import type {
  FixtureRepositorySet,
  RepositorySet,
  SessionManager,
} from "@xingwen/data-access";
import type { ResearchAdapter } from "@xingwen/research-adapter";
import type { WorkspaceController } from "@xingwen/workspace-core";

interface WorkspaceRuntimeBase {
  readonly repositories: RepositorySet;
  readonly researchAdapter: ResearchAdapter;
  readonly workspaceController: WorkspaceController;
}

export interface FixtureWorkspaceRuntimeBoundaries extends WorkspaceRuntimeBase {
  readonly adapterKind: "fixture";
  readonly repositories: FixtureRepositorySet;
}

export interface HttpWorkspaceRuntimeBoundaries extends WorkspaceRuntimeBase {
  readonly adapterKind: "http";
  readonly session: SessionManager;
}

/**
 * The single runtime boundary consumed by Workspace routes. Adapter selection
 * is performed once at bootstrap; pages only receive Repository Ports and
 * domain controllers. No private session is created for the public share
 * route.
 */
export type WorkspaceRuntimeBoundaries =
  FixtureWorkspaceRuntimeBoundaries | HttpWorkspaceRuntimeBoundaries;
