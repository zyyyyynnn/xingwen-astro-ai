/**
 * @xingwen/workspace-core — workspace orchestration boundary.
 *
 * Currently provides the Guided Tour finite state machine that drives the
 * Demo Replay / Live Run guided experience. The FSM is framework-free (depends
 * only on `@xingwen/domain`); UI bindings are added by `apps/workspace`.
 */

export {
  GUIDED_TOUR_STAGES,
  INITIAL_TOUR_STATE,
  canTransition,
  createGuidedTourController,
  transitionGuidedTour,
} from "./guided-tour";
export type {
  GuidedTourController,
  GuidedTourEvent,
  GuidedTourStage,
  GuidedTourState,
  GuidedTourStatus,
  GuidedTourTransitionError,
  TourListener,
} from "./guided-tour";
export { createWorkspaceController } from "./workspace-controller";
export type {
  WorkspaceController,
  WorkspaceState,
  WorkspaceListener,
} from "./workspace-controller";
