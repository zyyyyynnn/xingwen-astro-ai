import { useCallback, useEffect, useMemo, useState } from "react";
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

type RenderMode = "poster" | "webgl";

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
 * - SSR / no-JS: the SVG Poster <img> is always in the initial HTML.
 * - On hydration the Poster stays visible until WebGL2 is confirmed and
 *   the palette is read from the semantic CSS tokens; only then is the
 *   R3F Canvas mounted.
 * - Context loss (or an unavailable glyph atlas / renderer failure)
 *   reveals the Poster again; a successful restore remounts the Canvas.
 * - Reduced motion renders a single static phase (frameloop="never").
 * - On unmount the DynamicRenderer and its GPU resources are disposed.
 */
export function HeroVisual({
  poster,
  seed = 42,
  quality = "high",
}: HeroVisualProps) {
  const [initial] = useState(() => {
    if (typeof document === "undefined") {
      return { mode: "poster" as const, palette: null };
    }
    if (!supportsWebGl2()) {
      return { mode: "poster" as const, palette: null };
    }
    return { mode: "webgl" as const, palette: readScenePalette(document) };
  });
  const [mode, setMode] = useState<RenderMode>(initial.mode);
  const [palette] = useState<ScenePalette | null>(initial.palette);
  const [reducedMotion, setReducedMotion] = useState<boolean>(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [attempt, setAttempt] = useState(0);

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
    if (status === "unavailable" || status === "lost") {
      setMode("poster");
      return;
    }
    if (status === "restored") {
      setAttempt((current) => current + 1);
      setMode("webgl");
    }
  }, []);

  const showWebgl = mode === "webgl" && palette !== null;

  return (
    <div className="hero-visual">
      <img
        className="hero-poster"
        src={poster.dataUrl}
        alt="系外行星 Transit 证据系统 ASCII 字符视觉"
        width={480}
        height={330}
        hidden={showWebgl}
      />
      {showWebgl && (
        <Canvas
          key={attempt}
          className="hero-canvas"
          aria-hidden="true"
          frameloop={reducedMotion ? "never" : "always"}
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
