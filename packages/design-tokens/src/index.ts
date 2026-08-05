/**
 * Visual token fallbacks — the single source of truth for visual colors
 * outside the browser (SSR Poster generation, node contexts). Values are
 * mirrored by design-tokens/base.css; test/base-tokens.test.ts asserts
 * they stay in lockstep with the raw token declarations.
 */

export const VISUAL_TOKEN_FALLBACK = {
  /** --color-canvas → --raw-paper-50 */
  canvas: "oklch(0.978 0.004 230)",
  /** --color-visual-celestial-ink → --raw-bluegray-700 */
  celestialInk: "oklch(0.38 0.022 235)",
  /** --color-visual-celestial-deep → --raw-bluegray-900 */
  celestialDeep: "oklch(0.21 0.026 235)",
  /** --color-visual-celestial-soft → --raw-bluegray-200 */
  celestialSoft: "oklch(0.885 0.011 235)",
  /** --color-visual-particle → --raw-bluegray-500 */
  particle: "oklch(0.57 0.018 235)",
} as const;

export type VisualTokenFallback = typeof VISUAL_TOKEN_FALLBACK;

export const DESIGN_TOKEN_BASELINE = "A-01-foundation" as const;
