/**
 * @xingwen/workspace-core — workspace orchestration boundary.
 *
 * Provides the framework-free WorkspaceSnapshot orchestration boundary
 * retained for future Workspace product integration. The snapshot controller
 * manages layout presets, panel slots, evidence pinning, and active run state
 * through the `WorkspaceSnapshotPort`. The port is satisfied structurally by
 * the `WorkspaceSnapshotRepository` in `@xingwen/data-access`.
 */

export { createWorkspaceController } from "./workspace-controller";
export type {
  WorkspaceController,
  WorkspaceSnapshotPort,
  WorkspaceState,
  WorkspaceListener,
} from "./workspace-controller";
