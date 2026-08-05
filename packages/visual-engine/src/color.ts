/**
 * CSS color parsing for the WebGL renderer. Only oklch(...) and hex are
 * supported; anything else yields null and the renderer refuses to start
 * rather than silently mis-render.
 */

export interface SrgbColor {
  readonly r: number;
  readonly g: number;
  readonly b: number;
}

const OKLCH_PATTERN =
  /oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*[\d.]+)?\s*\)/iu;

function toSrgb(c: number): number {
  const clamped = Math.min(1, Math.max(0, c));
  const v =
    clamped <= 0.0031308
      ? 12.92 * clamped
      : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  return Math.min(1, Math.max(0, v));
}

/** oklch(l c h) → sRGB components in 0..1 (D65 reference white). */
export function oklchToSrgb(l: number, c: number, h: number): SrgbColor {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);

  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;

  const l3 = l_ ** 3;
  const m3 = m_ ** 3;
  const s3 = s_ ** 3;

  const r = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
  const g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
  const bl = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3;

  return { r: toSrgb(r), g: toSrgb(g), b: toSrgb(bl) };
}

/** Parse an oklch(...) or hex CSS color into sRGB 0..1, or null. */
export function cssColorToSrgb(css: string): SrgbColor | null {
  const trimmed = css.trim();
  const oklch = OKLCH_PATTERN.exec(trimmed);
  if (oklch) {
    return oklchToSrgb(Number(oklch[1]), Number(oklch[2]), Number(oklch[3]));
  }
  if (/^#[0-9a-f]{6}$/iu.test(trimmed)) {
    const value = Number.parseInt(trimmed.slice(1), 16);
    return {
      r: ((value >> 16) & 0xff) / 255,
      g: ((value >> 8) & 0xff) / 255,
      b: (value & 0xff) / 255,
    };
  }
  if (/^#[0-9a-f]{3}$/iu.test(trimmed)) {
    const r = Number.parseInt(trimmed[1] ?? "0", 16);
    const g = Number.parseInt(trimmed[2] ?? "0", 16);
    const b = Number.parseInt(trimmed[3] ?? "0", 16);
    return { r: (r * 17) / 255, g: (g * 17) / 255, b: (b * 17) / 255 };
  }
  return null;
}
