import { VISUAL_TOKEN_FALLBACK } from "@xingwen/design-tokens";
import type { ScenePalette } from "@xingwen/visual-engine";

/**
 * Scene palette for the Brand Site hero. In the browser the palette is
 * read from the semantic design tokens (CSS custom properties resolved by
 * getComputedStyle); anything unavailable falls back to
 * VISUAL_TOKEN_FALLBACK. The anchor color intentionally reuses the
 * celestial ink — no new color is introduced.
 */
export function readScenePalette(
  doc: Document,
  computed: typeof getComputedStyle = getComputedStyle,
): ScenePalette {
  const styles = computed(doc.documentElement);
  const read = (name: string): string => styles.getPropertyValue(name).trim();

  const canvas = read("--color-canvas") || VISUAL_TOKEN_FALLBACK.canvas;
  const ink =
    read("--color-visual-celestial-ink") || VISUAL_TOKEN_FALLBACK.celestialInk;
  const deep =
    read("--color-visual-celestial-deep") ||
    VISUAL_TOKEN_FALLBACK.celestialDeep;
  const soft =
    read("--color-visual-celestial-soft") ||
    VISUAL_TOKEN_FALLBACK.celestialSoft;
  const particle =
    read("--color-visual-particle") || VISUAL_TOKEN_FALLBACK.particle;

  return {
    paper: canvas,
    ink,
    deep,
    soft,
    particle,
    anchor: ink,
  };
}
