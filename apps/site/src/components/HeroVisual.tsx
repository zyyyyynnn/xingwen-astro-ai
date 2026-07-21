import { useEffect, useMemo, useRef } from "react";
import {
  createPoster,
  createVisualEngine,
  type VisualEngine,
} from "@xingwen/visual-engine";

interface HeroVisualProps {
  seed?: number;
}

/**
 * Hero visual: wraps @xingwen/visual-engine for the Brand Site hero.
 *
 * - Renders Poster `<img>` in initial HTML (no-JS fallback)
 * - On client hydration: initializes VisualEngine with Canvas + Poster
 * - Reduced motion: engine renders single static frame
 * - On unmount: disposes engine resources
 *
 * DOM anchor provides accessible text (AGENTS §9).
 */
export function HeroVisual({ seed = 42 }: HeroVisualProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<VisualEngine | null>(null);

  const poster = useMemo(
    () => createPoster({ seed, width: 480, height: 300 }),
    [seed],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const engine = createVisualEngine({
      seed,
      quality: "medium",
      reducedMotion,
      canvas,
      poster,
      domAnchorLabel: "系外行星 ASCII 视觉",
    });

    engineRef.current = engine;
    engine.start();

    return () => {
      engine.dispose();
      engineRef.current = null;
    };
  }, [seed, poster]);

  return (
    <div className="hero-visual">
      <img
        className="hero-poster"
        src={poster.dataUrl}
        alt="系外行星 ASCII 视觉"
        width={480}
        height={300}
      />
      <canvas
        ref={canvasRef}
        className="hero-canvas"
        width={480}
        height={300}
        aria-hidden="true"
      />
    </div>
  );
}
