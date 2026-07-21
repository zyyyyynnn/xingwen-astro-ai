import { createDeterministicRandom } from "./random";
import type {
  AsciiDitherRenderer,
  FrameCell,
  FrameData,
  RenderConfig,
} from "./types";

/**
 * Character ramp from light (sparse) to dense.
 * Same ramp as VISUAL_LANGUAGE.md §5. Max 7 chars per frame.
 */
const CHAR_RAMP = ["·", ":", "+", "*", "#", "%", "@"] as const;

/**
 * 4×4 Bayer matrix for ordered dithering (stable, not random per frame).
 */
const BAYER_4X4 = [
  0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5,
] as const;

/**
 * bluegray ink colors inlined (pure TS, no design-tokens dependency).
 * Mirrors ADR-029 raw tokens.
 */
const INK_COLOR = "#6e7981";
const PAPER_COLOR = "#f7f8f9";

function getCellSize(quality: RenderConfig["quality"]): number {
  switch (quality) {
    case "high":
      return 8;
    case "medium":
      return 12;
    case "low":
      return 18;
  }
}

/**
 * ASCII / Dither renderer using Canvas 2D.
 *
 * Deterministic: same seed + time + viewport produces identical output.
 * Quality tier controls cell density (particle count proxy).
 * Uses Bayer ordered dithering + stable per-cell noise — no per-frame randomness.
 */
export function createAsciiDitherRenderer(
  config: RenderConfig,
): AsciiDitherRenderer {
  const { seed, width, height, quality, freezeTime, canvas } = config;
  const cellSize = getCellSize(quality);
  const cols = Math.max(1, Math.floor(width / cellSize));
  const rows = Math.max(1, Math.floor(height / cellSize));
  const rng = createDeterministicRandom(seed ^ 0x9e3779b9);

  // Pre-generate stable per-cell noise offsets (deterministic, not per-frame)
  const noiseOffsets: Float32Array = new Float32Array(cols * rows);
  for (let i = 0; i < cols * rows; i++) {
    noiseOffsets[i] = rng.next();
  }

  let disposed = false;

  /**
   * Compute normalized brightness [0, 1] for a cell.
   * Models an off-axis exoplanet transit: darker inside the planet body,
   * brighter in the surrounding space, with subtle temporal variation.
   */
  function computeBrightness(row: number, col: number, time: number): number {
    const cx = cols * 0.55;
    const cy = rows * 0.48;
    const dx = (col - cx) / (cols * 0.35);
    const dy = (row - cy) / (rows * 0.42);
    const dist = Math.sqrt(dx * dx + dy * dy);

    // Planet body: inside ellipse is darker (transit shadow)
    let brightness = 0.82;
    if (dist < 1) {
      brightness = 0.12 + dist * 0.35;
    } else if (dist < 1.3) {
      brightness = 0.47 + (dist - 1) * 1.17;
    }

    // Slow temporal variation (frozen when freezeTime is set)
    const t = freezeTime ?? time;
    const wave = Math.sin(t * 0.0008 + col * 0.12 + row * 0.07) * 0.06;
    brightness += wave;

    // Bayer ordered dithering
    const bayerValue = (BAYER_4X4[(row % 4) * 4 + (col % 4)] ?? 0) / 16;
    brightness += (bayerValue - 0.5) * 0.08;

    // Stable per-cell noise
    const noiseIdx = row * cols + col;
    brightness += ((noiseOffsets[noiseIdx] ?? 0) - 0.5) * 0.05;

    return Math.max(0, Math.min(1, brightness));
  }

  function getFrameData(time: number): FrameData {
    const cells: FrameCell[] = [];
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const brightness = computeBrightness(row, col, time);
        // Bright area → light char (·), dark area → dense char (@)
        const rampIndex = Math.min(
          CHAR_RAMP.length - 1,
          Math.max(0, Math.floor((1 - brightness) * CHAR_RAMP.length)),
        );
        cells.push({ char: CHAR_RAMP[rampIndex] ?? "·", alpha: brightness });
      }
    }
    return { width: cols, height: rows, cells };
  }

  function render(time: number): void {
    if (disposed) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom or unavailable — graceful degradation

    const frame = getFrameData(time);

    ctx.fillStyle = PAPER_COLOR;
    ctx.fillRect(0, 0, width, height);

    ctx.font = `${Math.floor(cellSize * 0.85)}px ui-monospace, "SF Mono", Menlo, monospace`;
    ctx.textBaseline = "top";
    ctx.fillStyle = INK_COLOR;

    for (let row = 0; row < frame.height; row++) {
      for (let col = 0; col < frame.width; col++) {
        const cell = frame.cells[row * frame.width + col];
        if (!cell) continue;
        ctx.globalAlpha = cell.alpha;
        ctx.fillText(cell.char, col * cellSize, row * cellSize);
      }
    }
    ctx.globalAlpha = 1;
  }

  function dispose(): void {
    disposed = true;
  }

  return { render, dispose, getFrameData };
}
