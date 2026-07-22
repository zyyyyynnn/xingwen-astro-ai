import type { RepositorySet } from "@xingwen/data-access";
import type { GuidedTourController } from "@xingwen/workspace-core";

export interface WorkspaceRuntimeBoundaries {
  readonly repositories: RepositorySet;
  readonly tour: GuidedTourController;
}
