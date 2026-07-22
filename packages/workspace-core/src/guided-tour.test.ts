import { describe, expect, it } from "vitest";

import { INITIAL_TOUR_STATE, transitionGuidedTour } from "./guided-tour";
import type { GuidedTourState } from "./guided-tour";
import { GuidedTourTransitionError } from "./guided-tour";
import { createGuidedTourController } from "./guided-tour";
import { GUIDED_TOUR_STAGES } from "./guided-tour";

const ALL_STAGES = [...GUIDED_TOUR_STAGES];

function activeTour(): GuidedTourState {
  return transitionGuidedTour(INITIAL_TOUR_STATE, { type: "start" });
}

describe("Guided Tour FSM — start and mode", () => {
  it("starts in idle with no stage or mode", () => {
    expect(INITIAL_TOUR_STATE.status).toBe("idle");
    expect(INITIAL_TOUR_STATE.stage).toBeNull();
    expect(INITIAL_TOUR_STATE.mode).toBeNull();
  });

  it("starts with default demo_replay mode", () => {
    const state = transitionGuidedTour(INITIAL_TOUR_STATE, { type: "start" });
    expect(state.status).toBe("active");
    expect(state.stage).toBe("signal");
    expect(state.mode).toBe("demo_replay");
    expect(state.visited).toEqual(["signal"]);
  });

  it("starts with live mode when explicitly requested", () => {
    const state = transitionGuidedTour(INITIAL_TOUR_STATE, {
      type: "start",
      mode: "live",
    });
    expect(state.mode).toBe("live");
  });

  it("allows selecting mode before starting", () => {
    const withMode = transitionGuidedTour(INITIAL_TOUR_STATE, {
      type: "selectMode",
      mode: "live",
    });
    expect(withMode.mode).toBe("live");
    expect(withMode.status).toBe("idle");

    const started = transitionGuidedTour(withMode, { type: "start" });
    expect(started.mode).toBe("demo_replay");
  });

  it("throws when starting an already-active tour", () => {
    const active = activeTour();
    expect(() => transitionGuidedTour(active, { type: "start" })).toThrow(
      GuidedTourTransitionError,
    );
  });
});

describe("Guided Tour FSM — normal progression", () => {
  it("advances through all eight stages to completion", () => {
    let state = activeTour();

    for (let i = 1; i < ALL_STAGES.length; i++) {
      state = transitionGuidedTour(state, { type: "next" });
      expect(state.stage).toBe(ALL_STAGES[i]);
      expect(state.status).toBe("active");
    }

    // Last "next" at continue → completed
    state = transitionGuidedTour(state, { type: "next" });
    expect(state.status).toBe("completed");
  });

  it("records visited stages without duplicates", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "next" });
    state = transitionGuidedTour(state, { type: "next" });
    state = transitionGuidedTour(state, { type: "back" });
    state = transitionGuidedTour(state, { type: "next" });

    expect(state.visited).toEqual(["signal", "question", "acquire"]);
  });
});

describe("Guided Tour FSM — back navigation", () => {
  it("goes back to the previous stage", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "next" });
    state = transitionGuidedTour(state, { type: "back" });
    expect(state.stage).toBe("signal");
  });

  it("throws when going back from the first stage", () => {
    const state = activeTour();
    expect(() => transitionGuidedTour(state, { type: "back" })).toThrow(
      GuidedTourTransitionError,
    );
  });
});

describe("Guided Tour FSM — skip", () => {
  it("marks the current stage as skipped and advances", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "skip" });
    expect(state.stage).toBe("question");
    expect(state.skipped).toEqual(["signal"]);
  });

  it("completes the tour when skipping the last stage", () => {
    let state = activeTour();
    for (let i = 1; i < ALL_STAGES.length; i++) {
      state = transitionGuidedTour(state, { type: "next" });
    }
    expect(state.stage).toBe("continue");
    state = transitionGuidedTour(state, { type: "skip" });
    expect(state.status).toBe("completed");
  });
});

describe("Guided Tour FSM — goTo", () => {
  it("jumps to any stage while active", () => {
    const state = activeTour();
    const jumped = transitionGuidedTour(state, { type: "goTo", stage: "map" });
    expect(jumped.stage).toBe("map");
    expect(jumped.visited).toContain("map");
  });

  it("throws when goTo is attempted while paused", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "pause" });
    expect(() =>
      transitionGuidedTour(state, { type: "goTo", stage: "map" }),
    ).toThrow(GuidedTourTransitionError);
  });
});

describe("Guided Tour FSM — pause and resume", () => {
  it("pauses and resumes at the same stage", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "next" });
    state = transitionGuidedTour(state, { type: "pause" });
    expect(state.status).toBe("paused");
    expect(state.stage).toBe("question");

    state = transitionGuidedTour(state, { type: "resume" });
    expect(state.status).toBe("active");
    expect(state.stage).toBe("question");
  });

  it("rejects navigation events while paused", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "pause" });

    for (const event of [
      { type: "next" as const },
      { type: "back" as const },
      { type: "skip" as const },
      { type: "goTo" as const, stage: "map" as const },
    ]) {
      expect(() => transitionGuidedTour(state, event)).toThrow(
        GuidedTourTransitionError,
      );
    }
  });

  it("throws when pausing an idle tour", () => {
    expect(() =>
      transitionGuidedTour(INITIAL_TOUR_STATE, { type: "pause" }),
    ).toThrow(GuidedTourTransitionError);
  });

  it("throws when resuming an active tour", () => {
    const state = activeTour();
    expect(() => transitionGuidedTour(state, { type: "resume" })).toThrow(
      GuidedTourTransitionError,
    );
  });
});

describe("Guided Tour FSM — reset", () => {
  it("resets from active to idle and clears all state", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "next" });
    state = transitionGuidedTour(state, { type: "skip" });
    state = transitionGuidedTour(state, { type: "reset" });

    expect(state).toEqual(INITIAL_TOUR_STATE);
  });

  it("resets from paused", () => {
    let state = activeTour();
    state = transitionGuidedTour(state, { type: "pause" });
    state = transitionGuidedTour(state, { type: "reset" });
    expect(state.status).toBe("idle");
    expect(state.stage).toBeNull();
  });

  it("resets from completed", () => {
    let state = activeTour();
    for (let i = 0; i < ALL_STAGES.length; i++) {
      state = transitionGuidedTour(state, { type: "next" });
    }
    expect(state.status).toBe("completed");
    state = transitionGuidedTour(state, { type: "reset" });
    expect(state).toEqual(INITIAL_TOUR_STATE);
  });
});

describe("Guided Tour FSM — restart from completed", () => {
  it("can restart after completing and resetting", () => {
    let state = activeTour();
    for (let i = 0; i < ALL_STAGES.length; i++) {
      state = transitionGuidedTour(state, { type: "next" });
    }
    expect(state.status).toBe("completed");

    state = transitionGuidedTour(state, { type: "reset" });
    state = transitionGuidedTour(state, { type: "start", mode: "live" });
    expect(state.status).toBe("active");
    expect(state.stage).toBe("signal");
    expect(state.mode).toBe("live");
    expect(state.visited).toEqual(["signal"]);
  });
});

describe("Guided Tour controller — subscription", () => {
  it("notifies subscribers on accepted events", () => {
    const controller = createGuidedTourController();
    const states: GuidedTourState[] = [];
    controller.subscribe((s) => states.push(s));

    controller.send({ type: "start" });
    controller.send({ type: "next" });

    expect(states).toHaveLength(2);
    expect(states[0]!.stage).toBe("signal");
    expect(states[1]!.stage).toBe("question");
  });

  it("does not notify subscribers on rejected events", () => {
    const controller = createGuidedTourController();
    const states: GuidedTourState[] = [];
    controller.subscribe((s) => states.push(s));

    expect(() => controller.send({ type: "next" })).toThrow(
      GuidedTourTransitionError,
    );
    expect(states).toHaveLength(0);
  });

  it("unsubscribes correctly", () => {
    const controller = createGuidedTourController();
    const states: GuidedTourState[] = [];
    const unsubscribe = controller.subscribe((s) => states.push(s));

    controller.send({ type: "start" });
    unsubscribe();
    controller.send({ type: "next" });

    expect(states).toHaveLength(1);
  });
});
