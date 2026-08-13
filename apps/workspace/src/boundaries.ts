import type { QueryClient } from "@tanstack/react-query";
import type { RepositorySet, SessionManager } from "@xingwen/data-access";
import type { ResearchAdapter } from "@xingwen/research-adapter";
import type { WorkspaceController } from "@xingwen/workspace-core";

import type { WorkspaceApplication } from "./application/workspace-application";

/** The single production boundary shared by private Workspace routes. */
export interface WorkspaceRuntimeBoundaries {
  readonly siteUrl: string;
  readonly repositories: RepositorySet;
  readonly researchAdapter: ResearchAdapter;
  readonly session: SessionManager;
  readonly queryClient: QueryClient;
  readonly application: WorkspaceApplication;
  readonly workspaceController: WorkspaceController;
}
