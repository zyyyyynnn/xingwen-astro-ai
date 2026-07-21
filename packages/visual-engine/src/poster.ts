import { createDeterministicRandom } from "./random";
import type { PosterConfig, PosterSource } from "./types";

/**
 * bluegray anchor from ADR-029.
 * Visual Engine is pure TS (no design-tokens dependency), so raw
 * oklch strings are inlined. These mirror packages/design-tokens/base.css.
 */
const BLUEGRAY_300 = "oklch(0.72 0.014 235)";
const BLUEGRAY_500 = "oklch(0.57 0.018 235)";
const BLUEGRAY_700 = "oklch(0.43 0.022 235)";
const BLUEGRAY_900 = "oklch(0.21 0.026 235)";
const PAPER_0 = "oklch(0.985 0.004 230)";

const CHAR_RAMP = ["·", ":", "+", "*", "#", "%", "@"] as const;
const CHAR_COUNT = 48;

/**
 * Deterministic SVG Poster: off-axis exoplanet outline + character texture.
 * Same seed always produces the same Poster.
 */
export function createPoster(config: PosterConfig): PosterSource {
  const { seed, width = 320, height = 200 } = config;
  const rng = createDeterministicRandom(seed);

  // Off-axis exoplanet: ellipse offset from center (偏轴构图)
  const cx = width * (0.52 + rng.next() * 0.08);
  const cy = height * (0.46 + rng.next() * 0.08);
  const rx = width * (0.28 + rng.next() * 0.06);
  const ry = height * (0.34 + rng.next() * 0.06);

  // Scatter character texture inside and around the planet
  const chars: { x: number; y: number; char: string; opacity: number }[] = [];
  for (let i = 0; i < CHAR_COUNT; i++) {
    const angle = rng.next() * Math.PI * 2;
    const dist = rng.next() * 1.15;
    const x = cx + Math.cos(angle) * rx * dist;
    const y = cy + Math.sin(angle) * ry * dist;
    const char = CHAR_RAMP[Math.floor(rng.next() * CHAR_RAMP.length)] ?? "·";
    const opacity = 0.15 + rng.next() * 0.55;
    chars.push({ x, y, char, opacity });
  }

  const charElements = chars
    .map(
      (c) =>
        `    <text x="${c.x.toFixed(1)}" y="${c.y.toFixed(1)}" font-family="ui-monospace, monospace" font-size="8" fill="${BLUEGRAY_700}" opacity="${c.opacity.toFixed(2)}">${c.char}</text>`,
    )
    .join("\n");

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="系外行星 ASCII 视觉">
  <rect width="${width}" height="${height}" fill="${PAPER_0}"/>
  <ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${rx.toFixed(1)}" ry="${ry.toFixed(1)}" fill="${BLUEGRAY_900}" opacity="0.06"/>
  <ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${rx.toFixed(1)}" ry="${ry.toFixed(1)}" fill="none" stroke="${BLUEGRAY_500}" stroke-width="1.2" opacity="0.55"/>
  <ellipse cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" rx="${(rx * 0.82).toFixed(1)}" ry="${(ry * 0.82).toFixed(1)}" fill="none" stroke="${BLUEGRAY_300}" stroke-width="0.6" opacity="0.35"/>
${charElements}
</svg>`;

  const dataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;

  return { svg, dataUrl };
}
