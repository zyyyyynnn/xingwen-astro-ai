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
 * Mirrors ADR-029 raw tokens — same oklch values as base.css.
 */
const INK_COLOR = "oklch(0.57 0.018 235)";
const PAPER_COLOR = "oklch(0.995 0.002 230)";

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
  const { seed, quality, freezeTime, canvas } = config;
  let currentWidth = Math.max(100, config.width);
  let currentHeight = Math.max(100, config.height);
  const cellSize = getCellSize(quality);

  let cols = Math.max(1, Math.floor(currentWidth / cellSize));
  let rows = Math.max(1, Math.floor(currentHeight / cellSize));
  const rng = createDeterministicRandom(seed ^ 0x9e3779b9);

  let noiseOffsets: Float32Array = new Float32Array(cols * rows);
  function reinitNoise(): void {
    noiseOffsets = new Float32Array(cols * rows);
    for (let i = 0; i < cols * rows; i++) {
      noiseOffsets[i] = rng.next();
    }
  }
  reinitNoise();

  let disposed = false;

  /**
   * Compute normalized brightness [0, 1] for a cell.
   * Models an off-axis exoplanet transit field: 3D rotating organic mesh,
   * subtle fluid density wave & Bayer 4x4 dithering.
   */
  function computeBrightness(row: number, col: number, time: number): number {
    const cx = cols * 0.52;
    const cy = rows * 0.46;
    const t = freezeTime ?? time;

    // Slow organic 3D rotation & transit phase (16-22s period)
    const angle = t * 0.0003;
    const cosA = Math.cos(angle);
    const sinA = Math.sin(angle);

    const rawDx = (col - cx) / (cols * 0.38);
    const rawDy = (row - cy) / (rows * 0.44);

    // Rotated 3D projection coordinates
    const rx = rawDx * cosA - rawDy * sinA;
    const ry = rawDx * sinA + rawDy * cosA;
    const dist = Math.sqrt(rx * rx + ry * ry);

    // Planet transit shadow body
    let brightness = 0.84;
    if (dist < 1) {
      brightness = 0.14 + dist * 0.32;
    } else if (dist < 1.35) {
      brightness = 0.46 + (dist - 1) * 1.08;
    }

    // Dual harmonic 3D fluid wave
    const wave1 = Math.sin(t * 0.0006 + rx * 2.4 + ry * 1.8) * 0.05;
    const wave2 = Math.cos(t * 0.0004 - rx * 1.5 + ry * 2.2) * 0.04;
    brightness += wave1 + wave2;

    // Bayer ordered dithering
    const bayerValue = (BAYER_4X4[(row % 4) * 4 + (col % 4)] ?? 0) / 16;
    brightness += (bayerValue - 0.5) * 0.07;

    // Stable per-cell noise
    const noiseIdx = Math.min(noiseOffsets.length - 1, row * cols + col);
    brightness += ((noiseOffsets[noiseIdx] ?? 0) - 0.5) * 0.04;

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
    ctx.fillRect(0, 0, currentWidth, currentHeight);

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

  function resize(newWidth: number, newHeight: number): void {
    if (disposed) return;
    if (newWidth <= 0 || newHeight <= 0) return;
    if (newWidth === currentWidth && newHeight === currentHeight) return;

    currentWidth = newWidth;
    currentHeight = newHeight;
    cols = Math.max(1, Math.floor(currentWidth / cellSize));
    rows = Math.max(1, Math.floor(currentHeight / cellSize));
    reinitNoise();
  }

  function dispose(): void {
    disposed = true;
  }

  return { render, resize, dispose, getFrameData };
}
