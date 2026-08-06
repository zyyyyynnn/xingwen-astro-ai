/**
 * @xingwen/workspace-core — workspace orchestration boundary.
 *
 * Provides the framework-free workspace snapshot controller that drives the
 * /workspace host (layout presets, panel slots, evidence pinning, active run)
 * through the `WorkspaceSnapshotPort`. The port is satisfied structurally by
 * the `WorkspaceSnapshotRepository` in `@xingwen/data-access`; UI bindings
 * are added by `apps/workspace`.
 */

export { createWorkspaceController } from "./workspace-controller";
export type {
  WorkspaceController,
  WorkspaceSnapshotPort,
  WorkspaceState,
  WorkspaceListener,
} from "./workspace-controller";
