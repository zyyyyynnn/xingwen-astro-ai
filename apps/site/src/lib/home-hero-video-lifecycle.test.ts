import { describe, expect, it, vi } from "vitest";

import {
  bindHomeHeroVideoLifecycle,
  computePlayPolicy,
  type HomeHeroVideoLifecycleEnvironment,
} from "./home-hero-video-lifecycle";

function createVideoStub() {
  const pause = vi.fn();
  const play = vi.fn(() => Promise.resolve());
  return { pause, play };
}

function createEnvironment(
  overrides: Partial<HomeHeroVideoLifecycleEnvironment> = {},
): HomeHeroVideoLifecycleEnvironment & {
  setVisibility: (state: DocumentVisibilityState) => void;
  setReducedMotion: (matches: boolean) => void;
} {
  let visibilityState =
    overrides.visibilityState ?? ("visible" as DocumentVisibilityState);
  let reducedMotion = overrides.prefersReducedMotion ?? false;
  const visibilityHandlers = new Set<() => void>();
  const reducedMotionHandlers = new Set<(matches: boolean) => void>();

  return {
    get visibilityState() {
      return visibilityState;
    },
    get prefersReducedMotion() {
      return reducedMotion;
    },
    onVisibilityChange(handler) {
      visibilityHandlers.add(handler);
      return () => visibilityHandlers.delete(handler);
    },
    onReducedMotionChange(handler) {
      reducedMotionHandlers.add(handler);
      return () => reducedMotionHandlers.delete(handler);
    },
    setVisibility(state) {
      visibilityState = state;
      for (const handler of visibilityHandlers) handler();
    },
    setReducedMotion(matches) {
      reducedMotion = matches;
      for (const handler of reducedMotionHandlers) handler(matches);
    },
  };
}

describe("computePlayPolicy", () => {
  it("plays when visible and reduced motion is not preferred", () => {
    expect(
      computePlayPolicy({
        visibilityState: "visible",
        prefersReducedMotion: false,
      }),
    ).toBe("play");
  });

  it("pauses when the page is hidden even without reduced motion", () => {
    expect(
      computePlayPolicy({
        visibilityState: "hidden",
        prefersReducedMotion: false,
      }),
    ).toBe("pause");
  });

  it("pauses when reduced motion is preferred even while visible", () => {
    expect(
      computePlayPolicy({
        visibilityState: "visible",
        prefersReducedMotion: true,
      }),
    ).toBe("pause");
  });

  it("pauses when both signals apply", () => {
    expect(
      computePlayPolicy({
        visibilityState: "hidden",
        prefersReducedMotion: true,
      }),
    ).toBe("pause");
  });
});

describe("bindHomeHeroVideoLifecycle", () => {
  it("applies the initial policy on bind", () => {
    const video = createVideoStub();
    const environment = createEnvironment();

    bindHomeHeroVideoLifecycle(video, environment);

    expect(video.play).toHaveBeenCalledTimes(1);
    expect(video.pause).not.toHaveBeenCalled();
  });

  it("pauses when the page becomes hidden and resumes when visible again", () => {
    const video = createVideoStub();
    const environment = createEnvironment();
    bindHomeHeroVideoLifecycle(video, environment);

    environment.setVisibility("hidden");
    expect(video.pause).toHaveBeenCalledTimes(1);

    environment.setVisibility("visible");
    expect(video.play).toHaveBeenCalledTimes(2);
  });

  it("pauses on reduced motion change and only resumes while visible", () => {
    const video = createVideoStub();
    const environment = createEnvironment();
    bindHomeHeroVideoLifecycle(video, environment);

    environment.setReducedMotion(true);
    expect(video.pause).toHaveBeenCalledTimes(1);

    environment.setVisibility("hidden");
    environment.setReducedMotion(false);
    expect(video.play).toHaveBeenCalledTimes(1);

    environment.setVisibility("visible");
    expect(video.play).toHaveBeenCalledTimes(2);
  });

  it("pauses immediately when bound under reduced motion", () => {
    const video = createVideoStub();
    const environment = createEnvironment({ prefersReducedMotion: true });

    bindHomeHeroVideoLifecycle(video, environment);

    expect(video.pause).toHaveBeenCalledTimes(1);
    expect(video.play).not.toHaveBeenCalled();
  });

  it("swallows play() rejections without affecting the page", async () => {
    const video = createVideoStub();
    video.play.mockReturnValue(
      Promise.reject(new Error("NotAllowedError: play() failed")),
    );
    const environment = createEnvironment();
    bindHomeHeroVideoLifecycle(video, environment);

    environment.setVisibility("hidden");
    environment.setVisibility("visible");

    await vi.waitFor(() => {
      expect(video.play).toHaveBeenCalledTimes(2);
    });
  });

  it("dispose unbinds listeners and stops further policy application", () => {
    const video = createVideoStub();
    const environment = createEnvironment();
    const handle = bindHomeHeroVideoLifecycle(video, environment);

    handle.dispose();

    environment.setVisibility("hidden");
    environment.setReducedMotion(true);
    expect(video.pause).not.toHaveBeenCalled();
    expect(video.play).toHaveBeenCalledTimes(1);
  });

  it("binds exactly once and does not double-play on repeated events", () => {
    const video = createVideoStub();
    const environment = createEnvironment();
    bindHomeHeroVideoLifecycle(video, environment);

    environment.setVisibility("hidden");
    environment.setVisibility("visible");
    environment.setVisibility("visible");

    expect(video.play).toHaveBeenCalledTimes(2);
    expect(video.pause).toHaveBeenCalledTimes(1);
  });
});
