/**
 * Homepage hero video lifecycle.
 *
 * Policy: the hero video plays only while the document is visible and
 * the user has not asked for reduced motion; otherwise it is paused.
 *
 * The policy is a pure function (`computePlayPolicy`) so it can be unit
 * tested without a browser. `bindHomeHeroVideoLifecycle` owns DOM/event
 * binding and takes an injectable environment seam; the browser wiring
 * lives in `createBrowserLifecycleEnvironment` and is loaded by the
 * homepage only (no framework, no third-party media/animation library).
 */

export type VideoPlayPolicy = "play" | "pause";

export interface VideoPlayPolicyInput {
  visibilityState: DocumentVisibilityState;
  prefersReducedMotion: boolean;
}

export function computePlayPolicy(
  input: VideoPlayPolicyInput,
): VideoPlayPolicy {
  if (input.visibilityState !== "visible" || input.prefersReducedMotion) {
    return "pause";
  }
  return "play";
}

export interface HomeHeroVideoLifecycleEnvironment {
  visibilityState: DocumentVisibilityState;
  prefersReducedMotion: boolean;
  onVisibilityChange(handler: () => void): () => void;
  onReducedMotionChange(handler: (matches: boolean) => void): () => void;
}

export interface HomeHeroVideoLifecycleHandle {
  dispose(): void;
}

export function bindHomeHeroVideoLifecycle(
  video: Pick<HTMLVideoElement, "pause" | "play">,
  environment: HomeHeroVideoLifecycleEnvironment,
): HomeHeroVideoLifecycleHandle {
  let reducedMotion = environment.prefersReducedMotion;
  let currentPolicy: VideoPlayPolicy | null = null;

  const applyPolicy = (): void => {
    const policy = computePlayPolicy({
      visibilityState: environment.visibilityState,
      prefersReducedMotion: reducedMotion,
    });
    if (policy === currentPolicy) return;
    currentPolicy = policy;
    if (policy === "pause") {
      video.pause();
      return;
    }
    void video.play().catch(() => {
      // A rejected play() (user-gesture policy, codec or network failure)
      // must never surface as an unhandled rejection or break the page.
    });
  };

  const unsubscribeVisibility = environment.onVisibilityChange(applyPolicy);
  const unsubscribeReducedMotion = environment.onReducedMotionChange(
    (matches) => {
      reducedMotion = matches;
      applyPolicy();
    },
  );

  applyPolicy();

  return {
    dispose(): void {
      unsubscribeVisibility();
      unsubscribeReducedMotion();
    },
  };
}

export function createBrowserLifecycleEnvironment(
  documentRef: Document = window.document,
  matchMedia: (query: string) => MediaQueryList = window.matchMedia.bind(
    window,
  ),
): HomeHeroVideoLifecycleEnvironment {
  const reducedMotionQuery = matchMedia("(prefers-reduced-motion: reduce)");

  return {
    get visibilityState() {
      return documentRef.visibilityState;
    },
    get prefersReducedMotion() {
      return reducedMotionQuery.matches;
    },
    onVisibilityChange(handler) {
      documentRef.addEventListener("visibilitychange", handler);
      return () => documentRef.removeEventListener("visibilitychange", handler);
    },
    onReducedMotionChange(handler) {
      const onChange = (event: MediaQueryListEvent): void =>
        handler(event.matches);
      reducedMotionQuery.addEventListener("change", onChange);
      return () => reducedMotionQuery.removeEventListener("change", onChange);
    },
  };
}
