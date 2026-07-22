/**
 * Guided Tour finite state machine.
 *
 * Implements the eight-stage Guided Tour flow defined in
 * [Workspace UX §11](../../docs/design/WORKSPACE_UX.md):
 *
 *   signal → question → acquire → resolve → reason → map → inspect → continue
 *
 * The FSM supports start, pause, resume, skip, step-jump, Demo Replay / Live
 * mode selection and full state reset. Live API calls are wired by A-15; this
 * module only records the mode choice and does not perform network I/O.
 *
 * The reducer is a pure function; the controller wraps it with subscription
 * support for UI consumers.
 */

import type { ExecutionMode } from "@xingwen/domain";

export const GUIDED_TOUR_STAGES = [
  "signal",
  "question",
  "acquire",
  "resolve",
  "reason",
  "map",
  "inspect",
  "continue",
] as const;
export type GuidedTourStage = (typeof GUIDED_TOUR_STAGES)[number];

export type GuidedTourStatus = "idle" | "active" | "paused" | "completed";

export interface GuidedTourState {
  readonly status: GuidedTourStatus;
  readonly stage: GuidedTourStage | null;
  readonly mode: ExecutionMode | null;
  readonly visited: readonly GuidedTourStage[];
  readonly skipped: readonly GuidedTourStage[];
}

export type GuidedTourEvent =
  | { readonly type: "start"; readonly mode?: ExecutionMode }
  | { readonly type: "selectMode"; readonly mode: ExecutionMode }
  | { readonly type: "next" }
  | { readonly type: "back" }
  | { readonly type: "skip" }
  | { readonly type: "goTo"; readonly stage: GuidedTourStage }
  | { readonly type: "pause" }
  | { readonly type: "resume" }
  | { readonly type: "reset" };

export const INITIAL_TOUR_STATE: GuidedTourState = {
  status: "idle",
  stage: null,
  mode: null,
  visited: [],
  skipped: [],
};

export class GuidedTourTransitionError extends Error {
  readonly eventType: string;
  readonly currentState: GuidedTourStatus;

  constructor(
    eventType: string,
    currentState: GuidedTourStatus,
    reason: string,
  ) {
    super(
      `Invalid tour transition: ${eventType} in ${currentState} state — ${reason}`,
    );
    this.name = "GuidedTourTransitionError";
    this.eventType = eventType;
    this.currentState = currentState;
  }
}

function stageIndex(stage: GuidedTourStage): number {
  return GUIDED_TOUR_STAGES.indexOf(stage);
}

function isFirstStage(stage: GuidedTourStage): boolean {
  return stageIndex(stage) === 0;
}

function isLastStage(stage: GuidedTourStage): boolean {
  return stageIndex(stage) === GUIDED_TOUR_STAGES.length - 1;
}

function nextStage(stage: GuidedTourStage): GuidedTourStage {
  return GUIDED_TOUR_STAGES[stageIndex(stage) + 1]!;
}

function previousStage(stage: GuidedTourStage): GuidedTourStage {
  return GUIDED_TOUR_STAGES[stageIndex(stage) - 1]!;
}

/**
 * Pure transition function. Returns the next state or throws
 * {@link GuidedTourTransitionError} for invalid transitions.
 */
export function transitionGuidedTour(
  state: GuidedTourState,
  event: GuidedTourEvent,
): GuidedTourState {
  switch (event.type) {
    case "start": {
      if (state.status === "active" || state.status === "paused") {
        throw new GuidedTourTransitionError(
          "start",
          state.status,
          "tour is already running; reset first",
        );
      }
      const mode = event.mode ?? "demo_replay";
      return {
        status: "active",
        stage: "signal",
        mode,
        visited: ["signal"],
        skipped: [],
      };
    }

    case "selectMode": {
      // Mode selection is allowed in any state; it never starts or resumes the tour.
      return { ...state, mode: event.mode };
    }

    case "next": {
      if (state.status !== "active") {
        throw new GuidedTourTransitionError(
          "next",
          state.status,
          "tour must be active to advance",
        );
      }
      const current = state.stage!;
      if (isLastStage(current)) {
        return { ...state, status: "completed" };
      }
      const next = nextStage(current);
      return {
        ...state,
        stage: next,
        visited: state.visited.includes(next)
          ? state.visited
          : [...state.visited, next],
      };
    }

    case "back": {
      if (state.status !== "active") {
        throw new GuidedTourTransitionError(
          "back",
          state.status,
          "tour must be active to go back",
        );
      }
      const current = state.stage!;
      if (isFirstStage(current)) {
        throw new GuidedTourTransitionError(
          "back",
          state.status,
          "already at the first stage",
        );
      }
      const prev = previousStage(current);
      return { ...state, stage: prev };
    }

    case "skip": {
      if (state.status !== "active") {
        throw new GuidedTourTransitionError(
          "skip",
          state.status,
          "tour must be active to skip",
        );
      }
      const current = state.stage!;
      if (isLastStage(current)) {
        return { ...state, status: "completed" };
      }
      const next = nextStage(current);
      return {
        ...state,
        stage: next,
        skipped: state.skipped.includes(current)
          ? state.skipped
          : [...state.skipped, current],
        visited: state.visited.includes(next)
          ? state.visited
          : [...state.visited, next],
      };
    }

    case "goTo": {
      if (state.status !== "active") {
        throw new GuidedTourTransitionError(
          "goTo",
          state.status,
          "tour must be active to jump to a stage",
        );
      }
      return {
        ...state,
        stage: event.stage,
        visited: state.visited.includes(event.stage)
          ? state.visited
          : [...state.visited, event.stage],
      };
    }

    case "pause": {
      if (state.status !== "active") {
        throw new GuidedTourTransitionError(
          "pause",
          state.status,
          "tour must be active to pause",
        );
      }
      return { ...state, status: "paused" };
    }

    case "resume": {
      if (state.status !== "paused") {
        throw new GuidedTourTransitionError(
          "resume",
          state.status,
          "tour must be paused to resume",
        );
      }
      return { ...state, status: "active" };
    }

    case "reset": {
      return { ...INITIAL_TOUR_STATE };
    }
  }
}

/** Check whether an event is valid in the given state without applying it. */
export function canTransition(
  state: GuidedTourState,
  eventType: GuidedTourEvent["type"],
): boolean {
  try {
    transitionGuidedTour(state, { type: eventType } as GuidedTourEvent);
    return true;
  } catch {
    return false;
  }
}

export type TourListener = (state: GuidedTourState) => void;

/**
 * Stateful controller wrapping the pure reducer with subscription support.
 * UI consumers call `send(event)` and subscribe to state changes.
 */
export interface GuidedTourController {
  getState(): GuidedTourState;
  send(event: GuidedTourEvent): GuidedTourState;
  subscribe(listener: TourListener): () => void;
}

export function createGuidedTourController(
  initialState: GuidedTourState = INITIAL_TOUR_STATE,
): GuidedTourController {
  let state = initialState;
  const listeners = new Set<TourListener>();

  return {
    getState: () => state,
    send: (event: GuidedTourEvent): GuidedTourState => {
      state = transitionGuidedTour(state, event);
      for (const listener of listeners) {
        listener(state);
      }
      return state;
    },
    subscribe: (listener: TourListener): (() => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
