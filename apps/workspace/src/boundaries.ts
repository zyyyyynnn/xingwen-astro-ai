import type { DataAccessBoundary } from "@xingwen/data-access";
import type { WorkspaceCoreBoundary } from "@xingwen/workspace-core";

export interface WorkspaceRuntimeBoundaries {
  readonly core: WorkspaceCoreBoundary;
  readonly data: DataAccessBoundary;
}
