import type {
  HttpRepositorySet,
  RepositorySet,
  SessionManager,
} from "@xingwen/data-access";
import type {
  GuidedTourController,
  WorkspaceController,
} from "@xingwen/workspace-core";

/**
 * Workspace runtime boundaries.
 *
 * The workspace consumes repositories through the `RepositorySet` port so it
 * is agnostic to whether data comes from the Demo Replay fixture adapter
 * (A-14) or the live HTTP adapter (A-15). The active adapter is chosen at
 * bootstrap based on the runtime mode (tour/demo → fixture; live → HTTP).
 */
export interface WorkspaceRuntimeBoundaries {
  readonly repositories: RepositorySet;
  readonly tour: GuidedTourController;
  readonly workspaceController: WorkspaceController;
}

/**
 * Extended boundaries when the HTTP adapter is active.
 *
 * The session manager is exposed so the workspace can surface session-expired
 * prompts and trigger re-authentication without each component inspecting
 * error types.
 */
export interface HttpWorkspaceRuntimeBoundaries extends WorkspaceRuntimeBoundaries {
  readonly repositories: HttpRepositorySet;
  readonly session: SessionManager;
}
