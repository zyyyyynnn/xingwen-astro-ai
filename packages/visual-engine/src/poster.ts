import type { ScenePalette } from "./palette";
import { createDeterministicRandom } from "./random";
import {
  applyFold,
  DESIGN_HEIGHT,
  DESIGN_WIDTH,
  GLYPH_RAMP,
} from "./scene-model";
import type { ResearchSceneModel } from "./scene-model";
import type { PosterSource } from "./types";

/**
 * Deterministic SVG Poster — the no-JS / reduced-motion / WebGL-loss
 * fallback. It consumes the exact same ResearchSceneModel and ScenePalette
 * as the WebGL dynamic renderer (static phase fold = 0), so the Poster is
 * a still of the same subject, never a second composition.
 *
 * Sample fraction keeps the SVG lean while preserving the composition.
 */

export interface PosterConfig {
  readonly width?: number;
  readonly height?: number;
}

const SAMPLE_KEEP = 0.45;

function formatColor(
  particleColorClass: number,
  density: number,
  palette: ScenePalette,
): {
  fill: string;
  opacity: number;
} {
  if (particleColorClass === 2) {
    return { fill: palette.anchor, opacity: 0.95 };
  }
  if (particleColorClass === 1) {
    return { fill: palette.particle, opacity: 0.6 };
  }
  return {
    fill: density > 0.55 ? palette.ink : palette.soft,
    opacity: 0.5 + density * 0.45,
  };
}

export function createPoster(
  model: ResearchSceneModel,
  palette: ScenePalette,
  config: PosterConfig = {},
): PosterSource {
  const { width = 480, height = 330 } = config;
  const scale = Math.max(width / DESIGN_WIDTH, height / DESIGN_HEIGHT);
  const toX = (x: number): number => width / 2 + x * scale;
  const toY = (y: number): number => height / 2 - y * scale;

  const rng = createDeterministicRandom((model.seed + 1013) >>> 0);

  const orbitElements: string[] = [];
  const charElements: string[] = [];

  for (const unit of model.units) {
    if (unit.type === "orbit") {
      const { cx, cy, rx, ry, angle } = unit.geometry;
      orbitElements.push(
        `    <ellipse cx="${toX(cx).toFixed(1)}" cy="${toY(cy).toFixed(1)}" rx="${(rx * scale).toFixed(1)}" ry="${(ry * scale).toFixed(1)}" transform="rotate(${((-angle * 180) / Math.PI).toFixed(1)} ${toX(cx).toFixed(1)} ${toY(cy).toFixed(1)})" fill="none" stroke="${palette.particle}" stroke-width="1.2" opacity="0.45"/>`,
      );
    }
  }

  for (const particle of model.particles) {
    if (particle.type === "anchor") {
      const x = toX(particle.x);
      const y = toY(particle.y);
      const s = particle.size * scale;
      charElements.push(
        `    <rect x="${(x - s / 2).toFixed(1)}" y="${(y - s / 2).toFixed(1)}" width="${s.toFixed(1)}" height="${s.toFixed(1)}" fill="${palette.anchor}" opacity="0.95"/>`,
      );
      continue;
    }
    if (rng.next() > SAMPLE_KEEP) continue;

    const deformed = applyFold(particle, 0, 0);
    const x = toX(deformed.x);
    const y = toY(deformed.y);
    if (x < -4 || x > width + 4 || y < -4 || y > height + 4) continue;

    const { fill, opacity } = formatColor(
      particle.colorClass,
      particle.density,
      palette,
    );
    const fontSize = Math.max(3, particle.size * scale * 1.6);
    const glyph = GLYPH_RAMP[Math.min(6, particle.glyph)] ?? "·";
    charElements.push(
      `    <text x="${x.toFixed(1)}" y="${y.toFixed(1)}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, 'Courier New', monospace" font-size="${fontSize.toFixed(1)}" text-anchor="middle" dominant-baseline="central" fill="${fill}" opacity="${opacity.toFixed(2)}">${glyph}</text>`,
    );
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="系外行星 Transit 证据系统 ASCII 字符视觉">
  <rect width="${width}" height="${height}" fill="${palette.paper}"/>
  <ellipse cx="${toX(model.heart.x).toFixed(1)}" cy="${toY(model.heart.y).toFixed(1)}" rx="${(0.5 * scale).toFixed(1)}" ry="${(0.5 * scale).toFixed(1)}" fill="${palette.deep}" opacity="0.05"/>
${orbitElements.join("\n")}
${charElements.join("\n")}
</svg>`;

  return {
    svg,
    dataUrl: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
  };
}
