import { createAsciiDitherRenderer } from "./renderer";
import type { Quality, VisualEngine, VisualEngineConfig } from "./types";

/**
 * Create a Visual Engine runtime.
 *
 * Lifecycle:
 * - start(): begin rAF loop (or render single static frame if reduced motion)
 * - pause() / resume(): stop / restart rAF without disposing resources
 * - dispose(): cancel rAF, remove listeners, release renderer, remove DOM anchor
 *
 * Events:
 * - visibilitychange → pause on hidden, resume on visible
 * - webglcontextlost → trigger onContextLoss handler (caller shows Poster)
 *
 * Deterministic: same seed + freezeTime + viewport produces stable output.
 */
export function createVisualEngine(config: VisualEngineConfig): VisualEngine {
  const { seed, quality, reducedMotion, canvas, domAnchorLabel } = config;

  let disposed = false;
  let running = false;
  let rafId: number | null = null;
  let currentQuality: Quality = quality;
  let contextLossHandler: (() => void) | null = null;
  let domAnchor: HTMLElement | null = null;
  let renderer = createAsciiDitherRenderer({
    seed,
    width: canvas.width,
    height: canvas.height,
    quality: currentQuality,
    freezeTime: config.freezeTime,
    canvas,
  });

  // --- DOM anchor: accessible text describing the visual (AGENTS §9) ---
  function ensureDomAnchor(): void {
    if (domAnchor) return;
    domAnchor = document.createElement("div");
    domAnchor.setAttribute("role", "img");
    domAnchor.setAttribute(
      "aria-label",
      domAnchorLabel ?? "系外行星 ASCII 视觉",
    );
    // Visually hidden but accessible to screen readers
    domAnchor.style.position = "absolute";
    domAnchor.style.width = "1px";
    domAnchor.style.height = "1px";
    domAnchor.style.padding = "0";
    domAnchor.style.margin = "-1px";
    domAnchor.style.overflow = "hidden";
    domAnchor.style.clip = "rect(0 0 0 0)";
    domAnchor.style.whiteSpace = "nowrap";
    domAnchor.style.border = "0";
    if (canvas.parentNode) {
      canvas.parentNode.appendChild(domAnchor);
    }
  }

  // --- rAF loop ---
  function loop(timestamp: number): void {
    if (disposed || !running) return;
    const time = config.freezeTime ?? timestamp;
    renderer.render(time);
    rafId = requestAnimationFrame(loop);
  }

  // --- Event handlers ---
  function handleVisibilityChange(): void {
    if (disposed) return;
    if (document.hidden) {
      pause();
    } else if (!reducedMotion) {
      resume();
    }
  }

  function handleContextLoss(event: Event): void {
    event.preventDefault();
    pause();
    contextLossHandler?.();
  }

  document.addEventListener("visibilitychange", handleVisibilityChange);
  canvas.addEventListener("webglcontextlost", handleContextLoss);

  // --- Public API ---
  function start(): void {
    if (disposed || running) return;
    ensureDomAnchor();
    if (reducedMotion) {
      // Static frame only — no continuous animation
      renderer.render(config.freezeTime ?? 0);
      return;
    }
    running = true;
    rafId = requestAnimationFrame(loop);
  }

  function pause(): void {
    if (!running) return;
    running = false;
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function resume(): void {
    if (disposed || running || reducedMotion) return;
    running = true;
    rafId = requestAnimationFrame(loop);
  }

  function resize(width: number, height: number): void {
    if (disposed) return;
    renderer.resize(width, height);
    if (!running && reducedMotion) {
      renderer.render(config.freezeTime ?? 0);
    }
  }

  function dispose(): void {
    if (disposed) return;
    disposed = true;
    running = false;
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    renderer.dispose();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    canvas.removeEventListener("webglcontextlost", handleContextLoss);
    if (domAnchor?.parentNode) {
      domAnchor.parentNode.removeChild(domAnchor);
    }
    domAnchor = null;
    contextLossHandler = null;
  }

  function setQuality(q: Quality): void {
    if (currentQuality === q) return;
    currentQuality = q;
    renderer.dispose();
    renderer = createAsciiDitherRenderer({
      seed,
      width: canvas.width,
      height: canvas.height,
      quality: currentQuality,
      freezeTime: config.freezeTime,
      canvas,
    });
    if (running) {
      renderer.render(config.freezeTime ?? performance.now());
    } else if (reducedMotion && !disposed) {
      renderer.render(config.freezeTime ?? 0);
    }
  }

  function onContextLoss(handler: () => void): void {
    contextLossHandler = handler;
  }

  function getDomAnchor(): HTMLElement | null {
    return domAnchor;
  }

  function isRunning(): boolean {
    return running;
  }

  function isDisposed(): boolean {
    return disposed;
  }

  return {
    start,
    pause,
    resume,
    resize,
    dispose,
    setQuality,
    onContextLoss,
    getDomAnchor,
    isRunning,
    isDisposed,
  };
}
