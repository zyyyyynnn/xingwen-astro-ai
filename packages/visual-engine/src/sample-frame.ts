import {
  applyConverge,
  DESIGN_HEIGHT,
  DESIGN_WIDTH,
  GLYPH_RAMP,
  foldAt,
} from "./scene-model";
import type { ResearchSceneModel } from "./scene-model";
import type { FrameData } from "./types";

/**
 * sampleSceneFrame — a pure CPU projection of the ResearchSceneModel
 * onto a character grid. It consumes the exact same model and the exact
 * same deformation math as the WebGL renderer, so composition assertions
 * (coverage, center of gravity, bottom crop, fold ordering) verified here
 * hold for the GPU path too. Intended for offline review images, dev
 * bbox/phase validation and screenshot-style tests — never for the
 * production homepage renderer.
 */

export interface SampleFrameConfig {
  cols?: number;
  rows?: number;
}

export function sampleSceneFrame(
  model: ResearchSceneModel,
  timeSeconds: number,
  config: SampleFrameConfig = {},
): FrameData {
  const { cols = 96, rows = 54 } = config;
  const fold = foldAt(timeSeconds);

  const cells = new Array<{ char: string; alpha: number }>(cols * rows);
  for (let i = 0; i < cells.length; i++) {
    cells[i] = { char: GLYPH_RAMP[0] ?? "·", alpha: 0 };
  }

  const colScale = cols / DESIGN_WIDTH;
  const rowScale = rows / DESIGN_HEIGHT;

  for (const particle of model.particles) {
    const deformed = applyConverge(particle, fold, timeSeconds);
    if (deformed.alpha < 0.05) continue;

    const col = Math.floor((deformed.x + DESIGN_WIDTH / 2) * colScale);
    const row = Math.floor((DESIGN_HEIGHT / 2 - deformed.y) * rowScale);
    if (col < 0 || col >= cols || row < 0 || row >= rows) continue;

    const index = row * cols + col;
    const existing = cells[index];
    if (existing && existing.alpha >= deformed.alpha) continue;
    cells[index] = {
      char:
        particle.glyph === 7
          ? "■"
          : (GLYPH_RAMP[Math.min(6, particle.glyph)] ?? "·"),
      alpha: deformed.alpha,
    };
  }

  return {
    width: cols,
    height: rows,
    cells: cells.map(({ char, alpha }) => ({ char, alpha })),
  };
}
