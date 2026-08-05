import * as THREE from "three";

import {
  cssColorToSrgb,
  createGlyphAtlas,
  foldAt,
  FRAGMENT_SHADER,
  VERTEX_SHADER,
} from "@xingwen/visual-engine";
import type {
  GlyphAtlas,
  Quality,
  ResearchSceneModel,
  ScenePalette,
} from "@xingwen/visual-engine";

/**
 * Site Visual Adapter — the sole owner of Three.js for the hero visual.
 *
 * `@xingwen/visual-engine` exports only framework-agnostic data (scene
 * model, palette contract, glyph atlas, GLSL source); this adapter turns
 * that data into Three.js geometry/material/texture and renders it with
 * the WebGLRenderer instance provided by the R3F Canvas.
 *
 * Render ownership: the R3F Canvas disables its automatic render loop
 * (`useFrame` priority > 0), so `gl.render(scene, camera)` here is the
 * single authoritative draw call. The clear color is always the palette
 * `paper` token — the canvas can never fall back to default black. The
 * first successful frame fires `onReady` so the Poster is only hidden
 * once a real frame is on screen; any initialization failure (glyph
 * atlas, palette parse) throws and the caller keeps the Poster.
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
  /** Fired once after the first successful `gl.render`. */
  onReady?: () => void;
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

interface QualityProfile {
  keep: number;
  sizeScale: number;
}

const QUALITY_PROFILES: Record<Quality, QualityProfile> = {
  high: { keep: 1.0, sizeScale: 2.5 },
  medium: { keep: 0.6, sizeScale: 1.8 },
  low: { keep: 0.42, sizeScale: 1.3 },
};

const DUMMY_CAMERA = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

function toColor(colorName: string, value: string): THREE.Color {
  const parsed = cssColorToSrgb(value);
  if (!parsed) throw new UnparseablePaletteError(colorName, value);
  return new THREE.Color(parsed.r, parsed.g, parsed.b);
}

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
        particle.convergeStart,
        particle.convergeWindow,
        particle.coreX,
        particle.coreY,
      ],
      i * 4,
    );
    deforms.set(
      [particle.contract, particle.sink, particle.twist, particle.drift],
      i * 4,
    );
    shrinks.set(
      [particle.latticeX, particle.latticeY, particle.depth, particle.density],
      i * 4,
    );
    seeds.set(
      [particle.seedA, particle.seedB, particle.colorClass, particle.drift],
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

  const paperColor = toColor("paper", palette.paper);
  // The canvas is opaque (alpha: false); always clear to the paper token so
  // the WebGL surface matches the page/Poster background, never default black.
  gl.setClearColor(paperColor, 1);

  const uniforms = {
    uTime: { value: 0 },
    uFold: { value: 0 },
    uKeep: { value: profile.keep },
    uSizeScale: { value: profile.sizeScale },
    uScale: { value: new THREE.Vector2(1, 1) },
    uOffset: { value: new THREE.Vector2(0, -0.02) },
    uAtlasCells: { value: atlas.cellCount },
    uAtlas: { value: texture },
    uInk: { value: toColor("ink", palette.ink) },
    uDeep: { value: toColor("deep", palette.deep) },
    uSoft: { value: toColor("soft", palette.soft) },
    uParticle: { value: toColor("particle", palette.particle) },
    uAnchor: { value: toColor("anchor", palette.anchor) },
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
  let firstFrameEmitted = false;

  const handleLost = (event: Event): void => {
    event.preventDefault();
    if (disposed) return;
    status = "lost";
    firstFrameEmitted = false;
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
    // Cover projection: scale the design rect so the shorter axis fills the
    // viewport and the longer axis bleed-crops. 1 design unit = s pixels =
    // (2 * s / cssAxis) NDC, mapping the design rect onto [-1, 1] on the
    // fill axis and beyond on the crop axis.
    const s = Math.max(
      cssWidth / model.designWidth,
      cssHeight / model.designHeight,
    );
    const scale = new THREE.Vector2((2 * s) / cssWidth, (2 * s) / cssHeight);
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

  function emitReadyOnce(): void {
    if (firstFrameEmitted) return;
    firstFrameEmitted = true;
    config.onReady?.();
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
      emitReadyOnce();
    },

    renderAt(timeSeconds: number): void {
      if (disposed || status !== "ok") return;
      clock = timeSeconds;
      setFold(foldAt(timeSeconds));
      uniforms.uTime.value = timeSeconds;
      gl.render(scene, DUMMY_CAMERA);
      emitReadyOnce();
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
      gl.setClearColor(toColor("paper", next.paper), 1);
      (uniforms.uInk.value as THREE.Color).copy(toColor("ink", next.ink));
      (uniforms.uDeep.value as THREE.Color).copy(toColor("deep", next.deep));
      (uniforms.uSoft.value as THREE.Color).copy(toColor("soft", next.soft));
      (uniforms.uParticle.value as THREE.Color).copy(
        toColor("particle", next.particle),
      );
      (uniforms.uAnchor.value as THREE.Color).copy(
        toColor("anchor", next.anchor),
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
