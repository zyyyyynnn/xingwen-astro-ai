/**
 * Glyph atlas — a canvas-2D rendered alpha texture of the character
 * ramp. Browser-only: returns null where canvas 2D is unavailable
 * (jsdom, no canvas support), which forces the Poster fallback path.
 */

export const GLYPHS = ["·", ":", "+", "*", "#", "%", "@"] as const;

export interface GlyphAtlas {
  readonly image: HTMLCanvasElement;
  readonly cellCount: number;
  readonly cellSize: number;
}

const ATLAS_FONT = `600 45px ui-monospace, "SFMono-Regular", Menlo, Consolas, "Courier New", monospace`;

export function createGlyphAtlas(doc: Document): GlyphAtlas | null {
  const canvas = doc.createElement("canvas");
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  const cellSize = 64;
  const count = GLYPHS.length;
  canvas.width = cellSize * count;
  canvas.height = cellSize;

  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = ATLAS_FONT;

  for (let i = 0; i < count; i++) {
    ctx.fillText(
      GLYPHS[i] ?? "·",
      i * cellSize + cellSize / 2,
      cellSize / 2 + cellSize * 0.07,
    );
  }

  return { image: canvas, cellCount: count, cellSize };
}
