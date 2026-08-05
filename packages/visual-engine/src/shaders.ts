/**
 * GLSL shader source for the Transit Evidence dynamic renderer — exported
 * as pure data strings so the Site Visual Adapter (which owns Three.js)
 * can build the `ShaderMaterial` without the visual engine importing Three.
 *
 * The vertex shader mirrors the CPU `applyConverge` deformation in
 * `scene-model.ts`: radial contraction toward the core, organizing twist,
 * downward sink, slow internal drift and a supporting alpha fade. This is
 * research-semantic convergence (system focusing), NOT floral petal fold.
 */

export const VERTEX_SHADER = /* glsl */ `
precision highp float;

attribute vec4 aTransform; // x, y, size, glyph
attribute vec4 aFold;      // convergeStart, convergeWindow, coreX, coreY
attribute vec4 aDeform;    // contract, sink, twist, drift
attribute vec4 aShrink;    // latticeX, latticeY, depth, density
attribute vec4 aSeed;      // seedA, seedB, colorClass, driftAmp

uniform float uTime;
uniform float uFold;
uniform float uKeep;
uniform float uSizeScale;
uniform vec2 uScale;
uniform vec2 uOffset;

varying vec2 vUv;
varying float vGlyph;
varying float vDensity;
varying float vColorClass;
varying float vAlpha;

void main() {
  vUv = uv;

  // Per-particle convergence progress (0 open, 1 fully converged).
  float raw = clamp((uFold - aFold.x) / max(aFold.y, 0.0001), 0.0, 1.0);
  float p = raw * raw * (3.0 - 2.0 * raw);

  // Vector from convergence target (core) to the particle.
  vec2 d = aTransform.xy - aFold.zw;

  // Radial contraction toward the core.
  vec2 r = d * (1.0 - p * aDeform.x);

  // Organizing twist — radius-weighted, fades to zero at the core.
  float tw = p * aDeform.z * clamp(length(r) * 0.85, 0.0, 1.0);
  float ct = cos(tw);
  float st = sin(tw);
  r = vec2(r.x * ct - r.y * st, r.x * st + r.y * ct);

  // Position: core + contracted offset + downward sink (−y).
  vec2 pos = aFold.zw + r - vec2(0.0, p * aDeform.y);

  // Slow internal drift (breathing), dampened as the system converges.
  float w1 = sin(uTime * 0.35 + aSeed.x * 40.6) - sin(aSeed.x * 40.6);
  float w2 = cos(uTime * 0.28 + aSeed.y * 31.7) - cos(aSeed.y * 31.7);
  float wob = (w1 * 0.016 + w2 * 0.014) * aSeed.w * (1.0 - 0.4 * p);
  pos += vec2(wob, wob * 0.7);

  // Quality cull: move off-screen.
  if (aSeed.y > uKeep) pos = vec2(4.0, 4.0);

  // Glyph quad corner.
  vec2 corner = (vUv - 0.5) * aTransform.z * uSizeScale;
  pos += corner;

  vGlyph = aTransform.w;
  vDensity = aShrink.w;
  vColorClass = aSeed.z;
  vAlpha = (1.0 - 0.6 * p) * 0.92;

  vec2 ndc = pos * uScale + uOffset;
  gl_Position = vec4(ndc, 0.0, 1.0);
}
`;

export const FRAGMENT_SHADER = /* glsl */ `
precision highp float;

varying vec2 vUv;
varying float vGlyph;
varying float vDensity;
varying float vColorClass;
varying float vAlpha;

uniform sampler2D uAtlas;
uniform float uAtlasCells;
uniform vec3 uInk;
uniform vec3 uDeep;
uniform vec3 uSoft;
uniform vec3 uParticle;
uniform vec3 uAnchor;

void main() {
  if (vColorClass > 1.5) {
    gl_FragColor = vec4(uAnchor, vAlpha);
    return;
  }
  if (vColorClass > 0.5) {
    float a = texture2D(uAtlas, vec2((vGlyph + vUv.x) / uAtlasCells, vUv.y)).a;
    gl_FragColor = vec4(uParticle, a * vAlpha);
    return;
  }
  vec3 col = mix(uSoft, uInk, clamp(vDensity, 0.0, 1.0));
  col = mix(col, uDeep, smoothstep(0.72, 0.95, vDensity) * 0.75);
  float a = texture2D(uAtlas, vec2((vGlyph + vUv.x) / uAtlasCells, vUv.y)).a;
  gl_FragColor = vec4(col, a * vAlpha);
}
`;
