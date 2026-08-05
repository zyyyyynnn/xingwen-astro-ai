import * as THREE from "three";

import { cssColorToSrgb } from "../color";
import { createGlyphAtlas } from "../glyph-atlas";
import type { GlyphAtlas } from "../glyph-atlas";
import type { ScenePalette } from "../palette";
import { foldAt } from "../scene-model";
import type { ResearchSceneModel } from "../scene-model";
import type { Quality } from "../types";

/**
 * DynamicRenderer — the WebGL2 renderer for the ResearchSceneModel.
 *
 * One instanced draw call renders every glyph particle; the layered
 * parameterized deformation (pivot pitch, non-uniform shrink, twist,
 * bend, sink, drift) runs entirely in the vertex shader, mirroring the
 * CPU `applyFold` math. The renderer reuses the WebGLRenderer instance
 * owned by the caller (the R3F Canvas adapter) and manages only its own
 * scene/geometry/material/texture.
 *
 * Creation fails (throws) when glyph atlas rendering or palette color
 * parsing is impossible — callers fall back to the SVG Poster.
 */

export type DynamicRendererStatus = "ok" | "lost" | "disposed";

export interface DynamicRenderer {
  readonly status: DynamicRendererStatus;
  /** Advance the internal clock and render one frame. */
  update(deltaSeconds: number): void;
  /** Render the phase at an absolute time without advancing the clock. */
  renderAt(timeSeconds: number): void;
  /** Re-fit the cover projection to a CSS pixel viewport size. */
  resize(cssWidth: number, cssHeight: number): void;
  setQuality(quality: Quality): void;
  setPalette(palette: ScenePalette): void;
  dispose(): void;
}

export interface DynamicRendererConfig {
  gl: THREE.WebGLRenderer;
  canvas: HTMLCanvasElement;
  model: ResearchSceneModel;
  palette: ScenePalette;
  quality: Quality;
  onContextLost?: () => void;
  onContextRestored?: () => void;
}

export class GlyphAtlasUnavailableError extends Error {
  readonly code = "GLYPH_ATLAS_UNAVAILABLE";

  constructor() {
    super("Glyph atlas unavailable: canvas 2D context could not be created.");
    this.name = "GlyphAtlasUnavailableError";
  }
}

export class UnparseablePaletteError extends Error {
  readonly code = "UNPARSEABLE_PALETTE";

  constructor(colorName: string, value: string) {
    super(`Palette color ${colorName} could not be parsed: "${value}".`);
    this.name = "UnparseablePaletteError";
  }
}

const VERTEX_SHADER = /* glsl */ `
precision highp float;

attribute vec4 aTransform; // x, y, size, glyph
attribute vec4 aFold;      // foldStart, foldWindow, pivotX, pivotY
attribute vec4 aDeform;    // pitch, bend, twist, sink
attribute vec4 aShrink;    // shrinkX, shrinkY, depth, density
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

  float raw = clamp((uFold - aFold.x) / max(aFold.y, 0.0001), 0.0, 1.0);
  float p = raw * raw * (3.0 - 2.0 * raw);

  vec2 d = aTransform.xy - aFold.zw;

  float ang = p * aDeform.x;
  float ca = cos(ang);
  float sa = sin(ang);
  vec2 r = vec2(d.x * ca - d.y * sa, d.x * sa + d.y * ca);

  r *= vec2(1.0 - p * aShrink.x * 0.55, 1.0 - p * aShrink.y);

  float tw = p * aDeform.z * clamp(length(r) * 0.9, 0.0, 1.0);
  float ct = cos(tw);
  float st = sin(tw);
  r = vec2(r.x * ct - r.y * st, r.x * st + r.y * ct);

  float bend = p * aDeform.y * clamp(abs(r.y) * 0.7, 0.0, 1.0);
  r.x += bend * sign(d.x + 0.0001);

  vec2 pos = aFold.zw + r + vec2(0.0, p * aDeform.w);

  float w1 = sin(uTime * 0.35 + aSeed.x * 40.6) - sin(aSeed.x * 40.6);
  float w2 = cos(uTime * 0.28 + aSeed.y * 31.7) - cos(aSeed.y * 31.7);
  float wob = (w1 * 0.016 + w2 * 0.014) * aSeed.w * (1.0 - 0.4 * p);
  pos += vec2(wob, wob * 0.7);

  if (aSeed.y > uKeep) pos = vec2(4.0, 4.0);

  vec2 corner = (vUv - 0.5) * aTransform.z * uSizeScale;
  pos += corner;

  vGlyph = aTransform.w;
  vDensity = aShrink.w;
  vColorClass = aSeed.z;
  vAlpha = (1.0 - 0.55 * p) * 0.92;

  vec2 ndc = pos * uScale + uOffset;
  gl_Position = vec4(ndc, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = /* glsl */ `
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

function toVec3(colorName: string, color: string): THREE.Color {
  const parsed = cssColorToSrgb(color);
  if (!parsed) throw new UnparseablePaletteError(colorName, color);
  return new THREE.Color(parsed.r, parsed.g, parsed.b);
}

interface QualityProfile {
  keep: number;
  sizeScale: number;
}

const QUALITY_PROFILES: Record<Quality, QualityProfile> = {
  high: { keep: 1.0, sizeScale: 1.0 },
  medium: { keep: 0.6, sizeScale: 0.92 },
  low: { keep: 0.42, sizeScale: 0.78 },
};

const DUMMY_CAMERA = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

export function createDynamicRenderer(
  config: DynamicRendererConfig,
): DynamicRenderer {
  const { gl, canvas, model, palette, quality } = config;

  const atlas: GlyphAtlas | null = createGlyphAtlas(
    canvas.ownerDocument ?? globalThis.document,
  );
  if (!atlas) throw new GlyphAtlasUnavailableError();

  const texture = new THREE.CanvasTexture(atlas.image);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.NearestFilter;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;

  const positions = new Float32Array([
    -0.5, 0.5, 0, -0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0,
  ]);
  const uvs = new Float32Array([0, 1, 0, 0, 1, 0, 1, 1]);
  const indices = new Uint16Array([0, 1, 2, 0, 2, 3]);

  const count = model.particles.length;
  const transforms = new Float32Array(count * 4);
  const folds = new Float32Array(count * 4);
  const deforms = new Float32Array(count * 4);
  const shrinks = new Float32Array(count * 4);
  const seeds = new Float32Array(count * 4);

  model.particles.forEach((particle, i) => {
    transforms.set(
      [particle.x, particle.y, particle.size, particle.glyph],
      i * 4,
    );
    folds.set(
      [
        particle.foldStart,
        particle.foldWindow,
        particle.pivotX,
        particle.pivotY,
      ],
      i * 4,
    );
    deforms.set(
      [particle.pitch, particle.bend, particle.twist, particle.sink],
      i * 4,
    );
    shrinks.set(
      [particle.shrinkX, particle.shrinkY, particle.depth, particle.density],
      i * 4,
    );
    seeds.set(
      [particle.seedA, particle.seedB, particle.colorClass, particle.driftAmp],
      i * 4,
    );
  });

  const geometry = new THREE.InstancedBufferGeometry();
  geometry.instanceCount = count;
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  geometry.setAttribute(
    "aTransform",
    new THREE.InstancedBufferAttribute(transforms, 4),
  );
  geometry.setAttribute("aFold", new THREE.InstancedBufferAttribute(folds, 4));
  geometry.setAttribute(
    "aDeform",
    new THREE.InstancedBufferAttribute(deforms, 4),
  );
  geometry.setAttribute(
    "aShrink",
    new THREE.InstancedBufferAttribute(shrinks, 4),
  );
  geometry.setAttribute("aSeed", new THREE.InstancedBufferAttribute(seeds, 4));

  const profile = QUALITY_PROFILES[quality];

  const uniforms = {
    uTime: { value: 0 },
    uFold: { value: 0 },
    uKeep: { value: profile.keep },
    uSizeScale: { value: profile.sizeScale },
    uScale: { value: new THREE.Vector2(1, 1) },
    uOffset: { value: new THREE.Vector2(0, -0.02) },
    uAtlasCells: { value: atlas.cellCount },
    uAtlas: { value: texture },
    uInk: { value: toVec3("ink", palette.ink) },
    uDeep: { value: toVec3("deep", palette.deep) },
    uSoft: { value: toVec3("soft", palette.soft) },
    uParticle: { value: toVec3("particle", palette.particle) },
    uAnchor: { value: toVec3("anchor", palette.anchor) },
  } satisfies Record<string, THREE.IUniform>;

  const material = new THREE.ShaderMaterial({
    vertexShader: VERTEX_SHADER,
    fragmentShader: FRAGMENT_SHADER,
    uniforms,
    transparent: true,
    depthTest: false,
    depthWrite: false,
  });

  const scene = new THREE.Scene();
  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  let status: DynamicRendererStatus = "ok";
  let clock = 0;
  let cssWidth = 0;
  let cssHeight = 0;
  let disposed = false;
  let currentQuality = quality;

  const handleLost = (event: Event): void => {
    event.preventDefault();
    if (disposed) return;
    status = "lost";
    config.onContextLost?.();
  };

  const handleRestored = (): void => {
    if (disposed) return;
    config.onContextRestored?.();
  };

  canvas.addEventListener("webglcontextlost", handleLost, false);
  canvas.addEventListener("webglcontextrestored", handleRestored, false);

  function fitViewport(): void {
    if (cssWidth <= 0 || cssHeight <= 0) return;
    const s = Math.max(
      cssWidth / model.designWidth,
      cssHeight / model.designHeight,
    );
    const scale = new THREE.Vector2(
      (2 * s) / (cssWidth * (model.designWidth / 2)),
      (2 * s) / (cssHeight * (model.designHeight / 2)),
    );
    (uniforms.uScale.value as THREE.Vector2).copy(scale);
  }

  function setFold(fold: number): void {
    uniforms.uFold.value = fold;
  }

  function applyQuality(): void {
    const next = QUALITY_PROFILES[currentQuality];
    uniforms.uKeep.value = next.keep;
    uniforms.uSizeScale.value = next.sizeScale;
  }

  return {
    get status() {
      return status;
    },

    update(deltaSeconds: number): void {
      if (disposed || status !== "ok") return;
      clock += Math.max(0, deltaSeconds);
      setFold(foldAt(clock));
      uniforms.uTime.value = clock;
      gl.render(scene, DUMMY_CAMERA);
    },

    renderAt(timeSeconds: number): void {
      if (disposed || status !== "ok") return;
      clock = timeSeconds;
      setFold(foldAt(timeSeconds));
      uniforms.uTime.value = timeSeconds;
      gl.render(scene, DUMMY_CAMERA);
    },

    resize(width: number, height: number): void {
      if (disposed) return;
      cssWidth = Math.max(1, Math.floor(width));
      cssHeight = Math.max(1, Math.floor(height));
      fitViewport();
    },

    setQuality(quality: Quality): void {
      currentQuality = quality;
      applyQuality();
    },

    setPalette(next: ScenePalette): void {
      if (disposed) return;
      (uniforms.uInk.value as THREE.Color).copy(toVec3("ink", next.ink));
      (uniforms.uDeep.value as THREE.Color).copy(toVec3("deep", next.deep));
      (uniforms.uSoft.value as THREE.Color).copy(toVec3("soft", next.soft));
      (uniforms.uParticle.value as THREE.Color).copy(
        toVec3("particle", next.particle),
      );
      (uniforms.uAnchor.value as THREE.Color).copy(
        toVec3("anchor", next.anchor),
      );
    },

    dispose(): void {
      if (disposed) return;
      disposed = true;
      status = "disposed";
      canvas.removeEventListener("webglcontextlost", handleLost, false);
      canvas.removeEventListener("webglcontextrestored", handleRestored, false);
      geometry.dispose();
      material.dispose();
      texture.dispose();
      scene.clear();
    },
  };
}
