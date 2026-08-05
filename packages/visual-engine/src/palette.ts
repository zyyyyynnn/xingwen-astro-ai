/**
 * ScenePalette — the explicit Shader/Material palette for the visual
 * engine. Colors are always injected by the Site Adapter (SSR fallback
 * constants or live CSS custom property reads); the engine itself never
 * hardcodes color values.
 */
export interface ScenePalette {
  /** Cold paper canvas background (--color-canvas). */
  readonly paper: string;
  /** Celestial ink — main character color (--color-visual-celestial-ink). */
  readonly ink: string;
  /** Deep core color (--color-visual-celestial-deep). */
  readonly deep: string;
  /** Soft edge color (--color-visual-celestial-soft). */
  readonly soft: string;
  /** Particle/orbit color (--color-visual-particle). */
  readonly particle: string;
  /** Evidence anchor color. */
  readonly anchor: string;
}
