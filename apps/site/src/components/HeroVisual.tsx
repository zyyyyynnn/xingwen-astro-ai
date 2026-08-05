import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { Canvas } from "@react-three/fiber";
import {
  createResearchSceneModel,
  type PosterSource,
  type Quality,
  type ScenePalette,
} from "@xingwen/visual-engine";

import { readScenePalette } from "../lib/scene-palette";
import { TransitScene } from "./transit-scene";
import type { TransitStatus } from "./transit-scene";

interface HeroVisualProps {
  poster: PosterSource;
  seed?: number;
  quality?: Quality;
}

const QUALITY_DPR: Record<Quality, [number, number]> = {
  high: [1, 2],
  medium: [1, 1.5],
  low: [1, 1],
};

function supportsWebGl2(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}

/**
 * Brand Site hero visual.
 *
 * - SSR / no-JS: the SVG Poster `<img>` is always in the initial HTML.
 * - On hydration the Poster stays visible (and on top of the Canvas)
 *   until WebGL2 is confirmed AND the DynamicRenderer has submitted its
 *   first valid frame (`ready`). The Canvas mounts behind the Poster so
 *   no partially-initialized (black) surface is ever shown.
 * - Glyph atlas / palette parse failure, context loss, or WebGL2
 *   unavailable keeps the Poster; a successful restore remounts the
 *   Canvas and re-runs the first-frame readiness gate.
 * - Reduced motion renders a single static phase (frameloop="never").
 * - On unmount the DynamicRenderer and its GPU resources are disposed.
 */
export function HeroVisual({
  poster,
  seed = 42,
  quality = "high",
}: HeroVisualProps) {
  const [palette] = useState<ScenePalette | null>(() => {
    if (typeof document === "undefined") return null;
    if (!supportsWebGl2()) return null;
    return readScenePalette(document);
  });
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [reducedMotion, setReducedMotion] = useState<boolean>(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  // Canvas mounts only after client-side hydration — R3F's Canvas renders
  // a container <div> via useLayoutEffect which cannot run during SSR, so
  // rendering it in the initial tree causes a hydration mismatch. The
  // Poster covers the area until the first WebGL frame is ready.
  const hydrated = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );

  const model = useMemo(() => createResearchSceneModel(seed), [seed]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (event: MediaQueryListEvent): void => {
      setReducedMotion(event.matches);
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const handleStatus = useCallback((status: TransitStatus) => {
    if (status === "ready") {
      setReady(true);
      return;
    }
    if (status === "unavailable") {
      // Permanent failure (no WebGL2 / atlas / palette) — unmount canvas.
      setReady(false);
      setFailed(true);
      return;
    }
    if (status === "lost") {
      // Transient failure — keep canvas mounted so the context can be
      // restored; just reveal the Poster while the surface is gone.
      setReady(false);
      return;
    }
    if (status === "restored") {
      setReady(false);
      setAttempt((current) => current + 1);
    }
  }, []);

  const mountCanvas = hydrated && palette !== null && !failed;
  const showPoster = !ready || !mountCanvas;

  return (
    <div className="hero-visual">
      <img
        className="hero-poster"
        src={poster.dataUrl}
        alt="系外行星 Transit 证据系统 ASCII 字符视觉"
        width={480}
        height={330}
        hidden={!showPoster}
      />
      {mountCanvas && palette && (
        <Canvas
          key={attempt}
          className="hero-canvas"
          aria-hidden="true"
          frameloop="always"
          dpr={QUALITY_DPR[quality]}
          gl={{
            antialias: false,
            alpha: false,
            powerPreference: "high-performance",
          }}
        >
          <TransitScene
            model={model}
            palette={palette}
            quality={quality}
            reducedMotion={reducedMotion}
            freezeTime={0}
            onStatus={handleStatus}
          />
        </Canvas>
      )}
    </div>
  );
}
