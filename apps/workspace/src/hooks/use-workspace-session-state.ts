import { useSyncExternalStore } from "react";
import type {
  WorkspaceController,
  WorkspaceSessionState,
} from "@xingwen/workspace-core";

/**
 * Subscribe to {@link WorkspaceController.getSessionState} so components re-render
 * when session-local state (context history, rail width) changes.
 *
 * Distinct from {@link useControllerState}, which subscribes to the persisted
 * {@link WorkspaceState}. Both states share the same listener channel, but
 * React only re-renders when the snapshot returned by `getSnapshot` changes.
 */
export function useWorkspaceSessionState(
  controller: WorkspaceController,
): WorkspaceSessionState {
  return useSyncExternalStore(
    (notify) => controller.subscribe(() => notify()),
    () => controller.getSessionState(),
    () => controller.getSessionState(),
  );
}
