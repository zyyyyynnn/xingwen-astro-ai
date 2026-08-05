export { createDeterministicRandom } from "./random";
export {
  createResearchSceneModel,
  applyConverge,
  particleConverge,
  foldAt,
  DESIGN_WIDTH,
  DESIGN_HEIGHT,
  LOOP_SECONDS,
  GLYPH_RAMP,
  HEART,
} from "./scene-model";
export type {
  ResearchSceneModel,
  SceneUnit,
  SceneUnitType,
  SceneParticle,
  ConvergeParams,
  DeformedParticle,
} from "./scene-model";
export {
  BAYER_8X8,
  GLYPH_LEVELS,
  normalizedBayerThreshold,
  quantizeGlyphLevel,
  glyphForLevel,
} from "./dither";
export type { ScenePalette } from "./palette";
export { GLYPHS, createGlyphAtlas } from "./glyph-atlas";
export type { GlyphAtlas } from "./glyph-atlas";
export { cssColorToSrgb, oklchToSrgb } from "./color";
export type { SrgbColor } from "./color";
export { sampleSceneFrame } from "./sample-frame";
export type { SampleFrameConfig } from "./sample-frame";
export { VERTEX_SHADER, FRAGMENT_SHADER } from "./shaders";
export { createPoster } from "./poster";
export type { PosterConfig } from "./poster";
export type {
  Quality,
  PosterSource,
  DeterministicRandom,
  FrameCell,
  FrameData,
} from "./types";
