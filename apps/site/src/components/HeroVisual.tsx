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
 * - On client hydration: initializes VisualEngine with Canvas
 * - Poster `<img>` sits beneath Canvas in DOM order — context loss or
 *   no-JS naturally reveals it without engine involvement
 * - Reduced motion: engine renders single static frame
 * - On unmount: disposes engine resources
 *
 * DOM anchor provides accessible text (AGENTS §9).
 */
export function HeroVisual({ seed = 42 }: HeroVisualProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const engineRef = useRef<VisualEngine | null>(null);

  const poster = useMemo(
    () => createPoster({ seed, width: 480, height: 300 }),
    [seed],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    const initialWidth = Math.max(300, container.clientWidth || 800);
    const initialHeight = Math.max(200, container.clientHeight || 450);
    canvas.width = initialWidth;
    canvas.height = initialHeight;

    const engine = createVisualEngine({
      seed,
      quality: "medium",
      reducedMotion,
      canvas,
      domAnchorLabel: "系外行星 ASCII 视觉",
    });

    engineRef.current = engine;
    engine.start();

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        const newWidth = Math.max(300, Math.floor(width));
        const newHeight = Math.max(200, Math.floor(height));
        if (canvas.width !== newWidth || canvas.height !== newHeight) {
          canvas.width = newWidth;
          canvas.height = newHeight;
          engine.resize(newWidth, newHeight);
        }
      }
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      engine.dispose();
      engineRef.current = null;
    };
  }, [seed]);

  return (
    <div ref={containerRef} className="hero-visual">
      <img
        className="hero-poster"
        src={poster.dataUrl}
        alt="系外行星 ASCII 视觉"
        width={480}
        height={300}
      />
      <canvas ref={canvasRef} className="hero-canvas" aria-hidden="true" />
    </div>
  );
}
