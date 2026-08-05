/**
 * Deterministic Bayer ordered dithering for the ASCII / glyph field.
 *
 * The subject surface is a continuous density field sampled on a stable
 * object-space lattice. Ordered dithering converts the continuous density
 * into discrete glyph levels (blank / · / : / + / * / # / % / @) with the
 * characteristic Bayer crosshatch at level boundaries — so the surface
 * reads as a continuous half-tone from far away and as organized glyph
 * density up close, never as random scatter.
 *
 * Pure algorithm, no DOM / WebGL dependency — shared by the dynamic
 * renderer, the SVG Poster and the reduced-motion path so all three are
 * the same composition.
 */

export const BAYER_8X8 = [
  0, 48, 12, 60, 3, 51, 15, 63, 32, 16, 44, 28, 35, 19, 47, 31, 8, 56, 4, 52,
  11, 59, 7, 55, 40, 24, 36, 20, 43, 27, 39, 23, 2, 50, 14, 62, 1, 49, 13, 61,
  34, 18, 46, 30, 33, 17, 45, 29, 10, 58, 6, 54, 9, 57, 5, 53, 42, 26, 38, 22,
  41, 25, 37, 21,
] as const;

const BAYER_SIZE = 8;
const BAYER_COUNT = BAYER_SIZE * BAYER_SIZE;

/**
 * Threshold in [0, 1) for a lattice cell. The lattice coordinates are
 * object-space grid indices (stable across frames), so the same cell always
 * maps to the same threshold — the dither pattern is fixed to the subject,
 * not flickering per frame.
 */
export function normalizedBayerThreshold(
  latticeX: number,
  latticeY: number,
): number {
  const x = ((Math.floor(latticeX) % BAYER_SIZE) + BAYER_SIZE) % BAYER_SIZE;
  const y = ((Math.floor(latticeY) % BAYER_SIZE) + BAYER_SIZE) % BAYER_SIZE;
  const value = BAYER_8X8[y * BAYER_SIZE + x] ?? 0;
  return value / BAYER_COUNT;
}

export const GLYPH_LEVELS = 7;

/**
 * Map a continuous density [0,1] plus a Bayer threshold [0,1) to a discrete
 * glyph level 0..6 (blank..@). The threshold shifts the quantization boundary
 * by up to one level step, producing the ordered-dither crosshatch instead
 * of hard bands.
 */
export function quantizeGlyphLevel(density: number, threshold: number): number {
  const d = Math.min(1, Math.max(0, density));
  const step = 1 / GLYPH_LEVELS;
  // Center the dither around the boundary: ±half a step.
  const dithered = d + (threshold - 0.5) * step;
  return Math.min(
    GLYPH_LEVELS - 1,
    Math.max(0, Math.floor(dithered * GLYPH_LEVELS)),
  );
}

/** Glyph character for a level 0..6. Level 0 is the faintest dot. */
export function glyphForLevel(level: number): string {
  const clamped = Math.min(GLYPH_LEVELS - 1, Math.max(0, Math.floor(level)));
  return GLYPH_RAMP[clamped] ?? "·";
}

export const GLYPH_RAMP = ["·", ":", "+", "*", "#", "%", "@"] as const;
