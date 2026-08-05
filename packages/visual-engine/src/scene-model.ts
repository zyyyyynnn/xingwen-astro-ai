import { createDeterministicRandom } from "./random";

/**
 * ResearchSceneModel — the single source of truth consumed by the WebGL
 * dynamic renderer, the reduced-motion static phase, the SVG Poster and
 * offline review frames.
 *
 * The subject is the "Transit Evidence System": a star core (恒星核心,
 * formerly the flower heart), orbit rings (轨道), paper node petals
 * (论文节点瓣状层), Evidence anchors (Evidence 锚点) and sparse signal
 * characters (数据字符). Composition mirrors the reference hero: the
 * subject is extra-large, off-axis, bleed-cropped on top/left/right and
 * hard-cropped at the bottom edge.
 *
 * All randomness is deterministic: the same seed always yields the same
 * model. No DOM dependency — safe for SSR (Poster) and node tests.
 */

export const DESIGN_WIDTH = 3.2;
export const DESIGN_HEIGHT = 2.2;
export const LOOP_SECONDS = 5.6;

export const GLYPH_RAMP = ["·", ":", "+", "*", "#", "%", "@"] as const;

/** 花心/恒星核心 in design space: lower-center-right. */
export const HEART = Object.freeze({ x: 0.16, y: -0.55 });

export type SceneUnitType =
  "star" | "orbit" | "paperNode" | "signal" | "anchor";

export interface FoldParams {
  /** Global fold phase (0..1) at which this layer starts folding. */
  readonly foldStart: number;
  /** Fold phase window over which the layer completes its fold. */
  readonly foldWindow: number;
  /** Independent local pivot (design space). */
  readonly pivotX: number;
  readonly pivotY: number;
  /** Maximum pitch angle around the local pivot (radians). */
  readonly pitch: number;
  /** Maximum bend (arc deflection along the layer direction). */
  readonly bend: number;
  /** Maximum twist around the layer axis (radians). */
  readonly twist: number;
  /** Non-uniform horizontal shrink at full fold (0..1). */
  readonly shrinkX: number;
  /** Non-uniform vertical shrink at full fold (0..1). */
  readonly shrinkY: number;
  /** Extra downward sink at full fold (design units). */
  readonly sink: number;
}

export interface SceneUnit extends FoldParams {
  readonly id: number;
  readonly type: SceneUnitType;
  readonly label: string;
  /** Draw order; lower depth is drawn first (behind). */
  readonly depth: number;
  /** Amplitude of the slow internal drift while fully open. */
  readonly driftAmp: number;
  /** 0 = character (soft→ink), 1 = orbit/signal (particle), 2 = anchor. */
  readonly colorClass: number;
  readonly geometry: {
    readonly kind: "ellipse" | "ring" | "point";
    readonly cx: number;
    readonly cy: number;
    readonly rx: number;
    readonly ry: number;
    readonly angle: number;
  };
}

export interface SceneParticle extends FoldParams {
  readonly unitId: number;
  readonly type: SceneUnitType;
  readonly colorClass: number;
  readonly depth: number;
  readonly driftAmp: number;
  /** Design-space position at full open (fold = 0). */
  readonly x: number;
  readonly y: number;
  /** Character size in design units. */
  readonly size: number;
  /** Glyph ramp index 0..6 (7 = anchor square, colorClass 2 only). */
  readonly glyph: number;
  /** 0..1 — shading density; drives glyph and ink mix. */
  readonly density: number;
  readonly seedA: number;
  readonly seedB: number;
}

export interface ResearchSceneModel {
  readonly seed: number;
  readonly designWidth: number;
  readonly designHeight: number;
  readonly heart: Readonly<{ x: number; y: number }>;
  readonly units: readonly SceneUnit[];
  readonly particles: readonly SceneParticle[];
}

/**
 * Global fold phase curve over one 5.6s loop, matching the reference
 * rhythm: long full hold → accelerating close → brief near-empty pause →
 * fast re-open → long full hold.
 */
export function foldAt(timeSeconds: number): number {
  const t = ((timeSeconds % LOOP_SECONDS) + LOOP_SECONDS) % LOOP_SECONDS;
  if (t < 0.6) return 0;
  if (t < 1.6) return smoothstep01((t - 0.6) / 1.0);
  if (t < 2.0) return 1;
  if (t < 3.1) return 1 - smoothstep01((t - 2.0) / 1.1);
  return 0;
}

function smoothstep01(x: number): number {
  const v = Math.min(1, Math.max(0, x));
  return v * v * (3 - 2 * v);
}

/** Per-particle fold progress 0..1 for a given global fold phase. */
export function particleFold(particle: FoldParams, fold: number): number {
  const raw = (fold - particle.foldStart) / Math.max(particle.foldWindow, 1e-4);
  return smoothstep01(raw);
}

export interface DeformedParticle {
  readonly x: number;
  readonly y: number;
  readonly alpha: number;
  readonly size: number;
}

/**
 * Layered parameterized deformation — the exact CPU mirror of the GLSL
 * vertex deformation used by the WebGL renderer (kept in lockstep by
 * tests): local pivot pitch, non-uniform shrink, radius-gradient twist,
 * directional bend, downward sink, slow internal drift and a supporting
 * (non-primary) alpha fade. No uniform scale, no global opacity.
 */
export function applyFold(
  particle: SceneParticle,
  fold: number,
  timeSeconds: number,
): DeformedParticle {
  const p = particleFold(particle, fold);

  const dx = particle.x - particle.pivotX;
  const dy = particle.y - particle.pivotY;

  const ang = p * particle.pitch;
  const ca = Math.cos(ang);
  const sa = Math.sin(ang);
  let rx = dx * ca - dy * sa;
  let ry = dx * sa + dy * ca;

  rx *= 1 - p * particle.shrinkX * 0.55;
  ry *= 1 - p * particle.shrinkY;

  const tw = p * particle.twist * Math.min(1, Math.hypot(rx, ry) * 0.9);
  const ct = Math.cos(tw);
  const st = Math.sin(tw);
  const qx = rx * ct - ry * st;
  const qy = rx * st + ry * ct;

  const bend = p * particle.bend * Math.min(1, Math.abs(qy) * 0.7);
  let x = particle.pivotX + qx + bend * Math.sign(dx || 1e-4);
  let y = particle.pivotY + qy + p * particle.sink;

  const wobble =
    (Math.sin(timeSeconds * 0.35 + particle.seedA * 40.6) -
      Math.sin(particle.seedA * 40.6)) *
      0.016 +
    (Math.cos(timeSeconds * 0.28 + particle.seedB * 31.7) -
      Math.cos(particle.seedB * 31.7)) *
      0.014;
  const drift = wobble * particle.driftAmp * (1 - 0.4 * p);
  x += drift;
  y += drift * 0.7;

  return {
    x,
    y,
    alpha: (1 - 0.55 * p) * 0.92,
    size: particle.size * (1 - 0.22 * p),
  };
}

function densityToGlyph(density: number): number {
  const d = Math.min(1, Math.max(0, density));
  if (d > 0.72) return 6;
  if (d > 0.58) return 5;
  if (d > 0.45) return 4;
  if (d > 0.32) return 3;
  if (d > 0.2) return 2;
  if (d > 0.08) return 1;
  return 0;
}

interface PaperNodePreset {
  label: string;
  angle: number;
  len: number;
  width: number;
  foldStart: number;
  pitch: number;
  bend: number;
  twist: number;
  shrinkX: number;
  shrinkY: number;
  sink: number;
  depth: number;
}

/**
 * 论文节点瓣状层 — petal layers around the star core. foldStart drives
 * the fold order: the right long petal folds first, then upper-right and
 * left, then the vertical center, then the star core itself last.
 */
const PAPER_NODE_PRESETS: readonly PaperNodePreset[] = [
  {
    label: "rightLong",
    angle: -0.12,
    len: 1.02,
    width: 0.2,
    foldStart: 0.0,
    pitch: 1.75,
    bend: 0.42,
    twist: 0.5,
    shrinkX: 0.55,
    shrinkY: 0.82,
    sink: 0.34,
    depth: 1.4,
  },
  {
    label: "upRight",
    angle: 0.85,
    len: 0.78,
    width: 0.18,
    foldStart: 0.08,
    pitch: 1.6,
    bend: 0.38,
    twist: 0.4,
    shrinkX: 0.5,
    shrinkY: 0.8,
    sink: 0.28,
    depth: 1.5,
  },
  {
    label: "leftUp",
    angle: 1.95,
    len: 0.58,
    width: 0.14,
    foldStart: 0.12,
    pitch: 1.7,
    bend: 0.4,
    twist: 0.35,
    shrinkX: 0.5,
    shrinkY: 0.78,
    sink: 0.26,
    depth: 1.3,
  },
  {
    label: "leftBig",
    angle: 2.55,
    len: 0.88,
    width: 0.28,
    foldStart: 0.15,
    pitch: 1.65,
    bend: 0.45,
    twist: 0.55,
    shrinkX: 0.55,
    shrinkY: 0.8,
    sink: 0.3,
    depth: 1.6,
  },
  {
    label: "upVertical",
    angle: 1.45,
    len: 0.72,
    width: 0.13,
    foldStart: 0.22,
    pitch: 1.5,
    bend: 0.35,
    twist: 0.3,
    shrinkX: 0.45,
    shrinkY: 0.78,
    sink: 0.24,
    depth: 1.7,
  },
  {
    label: "lowerCenter",
    angle: 3.35,
    len: 0.5,
    width: 0.16,
    foldStart: 0.28,
    pitch: 1.4,
    bend: 0.3,
    twist: 0.25,
    shrinkX: 0.4,
    shrinkY: 0.7,
    sink: 0.2,
    depth: 1.2,
  },
];

const ORBIT_DEFS: readonly {
  r: number;
  foldStart: number;
  sink: number;
  depth: number;
}[] = [
  { r: 0.85, foldStart: 0.32, sink: 0.2, depth: 0.8 },
  { r: 1.05, foldStart: 0.38, sink: 0.22, depth: 0.9 },
];

const ORBIT_TILT = -0.18;
const ORBIT_YC = 0.55;

export function createResearchSceneModel(seed: number): ResearchSceneModel {
  const rng = createDeterministicRandom(seed);
  const units: SceneUnit[] = [];
  const particles: SceneParticle[] = [];
  let unitId = 0;

  function pushUnit(unit: Omit<SceneUnit, "id">): SceneUnit {
    const full = { ...unit, id: unitId++ };
    units.push(full);
    return full;
  }

  function pushParticle(
    particle: Omit<SceneParticle, "seedA" | "seedB">,
  ): void {
    particles.push({
      ...particle,
      seedA: rng.next(),
      seedB: rng.next(),
    });
  }

  // --- star core (花心) --------------------------------------------
  const starUnit = pushUnit({
    type: "star",
    label: "star",
    foldStart: 0.45,
    foldWindow: 0.55,
    pivotX: HEART.x,
    pivotY: HEART.y,
    pitch: 1.2,
    bend: 0.25,
    twist: 0.2,
    shrinkX: 0.35,
    shrinkY: 0.6,
    sink: 0.16,
    depth: 2.0,
    driftAmp: 0.4,
    colorClass: 0,
    geometry: {
      kind: "ellipse",
      cx: HEART.x,
      cy: HEART.y,
      rx: 0.5,
      ry: 0.5,
      angle: 0,
    },
  });

  const STAR_COUNT = 900;
  for (let i = 0; i < STAR_COUNT; i++) {
    const r = Math.sqrt(rng.next()) * 0.5;
    const a = rng.next() * Math.PI * 2;
    const density = 1 - r / 0.5;
    pushParticle({
      unitId: starUnit.id,
      type: "star",
      colorClass: 0,
      depth: starUnit.depth,
      driftAmp: starUnit.driftAmp,
      foldStart: starUnit.foldStart,
      foldWindow: starUnit.foldWindow,
      pivotX: starUnit.pivotX,
      pivotY: starUnit.pivotY,
      pitch: starUnit.pitch,
      bend: starUnit.bend,
      twist: starUnit.twist,
      shrinkX: starUnit.shrinkX,
      shrinkY: starUnit.shrinkY,
      sink: starUnit.sink,
      x: HEART.x + Math.cos(a) * r,
      y: HEART.y + Math.sin(a) * r,
      size: 0.014 + density * 0.007 + rng.next() * 0.002,
      glyph: densityToGlyph(density),
      density,
    });
  }

  // --- orbit rings (轨道) -------------------------------------------
  for (const def of ORBIT_DEFS) {
    const orbitUnit = pushUnit({
      type: "orbit",
      label: `orbit-${def.r.toFixed(2)}`,
      foldStart: def.foldStart,
      foldWindow: 1 - def.foldStart,
      pivotX: HEART.x,
      pivotY: HEART.y,
      pitch: 1.1,
      bend: 0.15,
      twist: 0.15,
      shrinkX: 0.4,
      shrinkY: 0.6,
      sink: def.sink,
      depth: def.depth,
      driftAmp: 0.6,
      colorClass: 1,
      geometry: {
        kind: "ring",
        cx: HEART.x,
        cy: HEART.y,
        rx: def.r,
        ry: def.r * ORBIT_YC,
        angle: ORBIT_TILT,
      },
    });

    const RING_COUNT = 130;
    for (let i = 0; i < RING_COUNT; i++) {
      const a = (i / RING_COUNT) * Math.PI * 2;
      const rr = def.r * (1 + (rng.next() * 2 - 1) * 0.015);
      const x = HEART.x + Math.cos(a + ORBIT_TILT) * rr;
      const y = HEART.y + Math.sin(a + ORBIT_TILT) * rr * ORBIT_YC;
      const density = 0.5 + (rng.next() - 0.5) * 0.24;
      pushParticle({
        unitId: orbitUnit.id,
        type: "orbit",
        colorClass: 1,
        depth: orbitUnit.depth,
        driftAmp: orbitUnit.driftAmp,
        foldStart: orbitUnit.foldStart,
        foldWindow: orbitUnit.foldWindow,
        pivotX: orbitUnit.pivotX,
        pivotY: orbitUnit.pivotY,
        pitch: orbitUnit.pitch,
        bend: orbitUnit.bend,
        twist: orbitUnit.twist,
        shrinkX: orbitUnit.shrinkX,
        shrinkY: orbitUnit.shrinkY,
        sink: orbitUnit.sink,
        x,
        y,
        size: 0.013,
        glyph: densityToGlyph(density),
        density,
      });
    }
  }

  // --- paper node petals (论文节点瓣状层) ----------------------------
  for (const preset of PAPER_NODE_PRESETS) {
    const dirX = Math.cos(preset.angle);
    const dirY = Math.sin(preset.angle);
    const perpX = -dirY;
    const perpY = dirX;
    const pivotX = HEART.x + dirX * preset.len * 0.12;
    const pivotY = HEART.y + dirY * preset.len * 0.12;

    const nodeUnit = pushUnit({
      type: "paperNode",
      label: preset.label,
      foldStart: preset.foldStart,
      foldWindow: 1 - preset.foldStart,
      pivotX,
      pivotY,
      pitch: preset.pitch,
      bend: preset.bend,
      twist: preset.twist,
      shrinkX: preset.shrinkX,
      shrinkY: preset.shrinkY,
      sink: preset.sink,
      depth: preset.depth,
      driftAmp: 0.85 + rng.next() * 0.15,
      colorClass: 0,
      geometry: {
        kind: "ellipse",
        cx: HEART.x + dirX * preset.len * 0.5,
        cy: HEART.y + dirY * preset.len * 0.5,
        rx: preset.len * 0.55,
        ry: preset.width,
        angle: preset.angle,
      },
    });

    const count = Math.round(preset.len * preset.width * 1500);
    for (let i = 0; i < count; i++) {
      const t = 0.12 + 0.88 * Math.sqrt(rng.next());
      const spread = (rng.next() * 2 - 1) * preset.width * (0.75 + 0.25 * t);
      const x = HEART.x + dirX * t * preset.len + perpX * spread;
      const y = HEART.y + dirY * t * preset.len + perpY * spread;
      const density =
        Math.min(
          1,
          Math.max(0.08, 1 - Math.abs(spread) / (preset.width * 1.1)),
        ) *
        (0.55 + 0.45 * t);
      pushParticle({
        unitId: nodeUnit.id,
        type: "paperNode",
        colorClass: 0,
        depth: nodeUnit.depth,
        driftAmp: nodeUnit.driftAmp,
        foldStart: nodeUnit.foldStart,
        foldWindow: nodeUnit.foldWindow,
        pivotX: nodeUnit.pivotX,
        pivotY: nodeUnit.pivotY,
        pitch: nodeUnit.pitch,
        bend: nodeUnit.bend,
        twist: nodeUnit.twist,
        shrinkX: nodeUnit.shrinkX,
        shrinkY: nodeUnit.shrinkY,
        sink: nodeUnit.sink,
        x,
        y,
        size: 0.014 + density * 0.006 + rng.next() * 0.002,
        glyph: densityToGlyph(density),
        density,
      });
    }
  }

  // --- Evidence anchors (Evidence 锚点) ------------------------------
  const anchorFoldSource = [
    ...PAPER_NODE_PRESETS,
    { label: "star-top", angle: -Math.PI / 2, len: 0.52 },
  ];
  for (const preset of anchorFoldSource) {
    const dirX = Math.cos(preset.angle);
    const dirY = Math.sin(preset.angle);
    const ax = HEART.x + dirX * preset.len;
    const ay = HEART.y + dirY * preset.len;
    const matchingNode =
      preset.label === "star-top"
        ? starUnit
        : units.find((u) => u.label === preset.label);
    const anchorUnit = pushUnit({
      type: "anchor",
      label: `anchor-${preset.label}`,
      foldStart: (matchingNode?.foldStart ?? 0.2) + 0.02,
      foldWindow: (matchingNode?.foldWindow ?? 0.8) + 0.02,
      pivotX: matchingNode?.pivotX ?? HEART.x,
      pivotY: matchingNode?.pivotY ?? HEART.y,
      pitch: matchingNode?.pitch ?? 1.2,
      bend: matchingNode?.bend ?? 0.25,
      twist: matchingNode?.twist ?? 0.2,
      shrinkX: matchingNode?.shrinkX ?? 0.4,
      shrinkY: matchingNode?.shrinkY ?? 0.6,
      sink: (matchingNode?.sink ?? 0.2) + 0.05,
      depth: 3.0,
      driftAmp: 0.5,
      colorClass: 2,
      geometry: { kind: "point", cx: ax, cy: ay, rx: 0, ry: 0, angle: 0 },
    });
    pushParticle({
      unitId: anchorUnit.id,
      type: "anchor",
      colorClass: 2,
      depth: anchorUnit.depth,
      driftAmp: anchorUnit.driftAmp,
      foldStart: anchorUnit.foldStart,
      foldWindow: anchorUnit.foldWindow,
      pivotX: anchorUnit.pivotX,
      pivotY: anchorUnit.pivotY,
      pitch: anchorUnit.pitch,
      bend: anchorUnit.bend,
      twist: anchorUnit.twist,
      shrinkX: anchorUnit.shrinkX,
      shrinkY: anchorUnit.shrinkY,
      sink: anchorUnit.sink,
      x: ax,
      y: ay,
      size: 0.024,
      glyph: 7,
      density: 1,
    });
  }

  // --- sparse signal characters (数据字符) ---------------------------
  const signalUnit = pushUnit({
    type: "signal",
    label: "signal",
    foldStart: 0.2,
    foldWindow: 0.8,
    pivotX: HEART.x,
    pivotY: HEART.y,
    pitch: 1.1,
    bend: 0.2,
    twist: 0.2,
    shrinkX: 0.35,
    shrinkY: 0.55,
    sink: 0.22,
    depth: 0.5,
    driftAmp: 0.9,
    colorClass: 1,
    geometry: { kind: "point", cx: 0, cy: 0, rx: 0, ry: 0, angle: 0 },
  });

  let signals = 0;
  let tries = 0;
  while (signals < 36 && tries < 4000) {
    tries++;
    const x = rng.next() * 2.9 - 1.45;
    const y = rng.next() * 1.9 - 0.95;
    const distToHeart = Math.hypot(x - HEART.x, y - HEART.y);
    if (distToHeart < 0.62 || Math.abs(y) > 0.85) continue;
    const density = 0.12 + rng.next() * 0.18;
    pushParticle({
      unitId: signalUnit.id,
      type: "signal",
      colorClass: 1,
      depth: signalUnit.depth,
      driftAmp: signalUnit.driftAmp,
      foldStart: signalUnit.foldStart,
      foldWindow: signalUnit.foldWindow,
      pivotX: signalUnit.pivotX,
      pivotY: signalUnit.pivotY,
      pitch: signalUnit.pitch,
      bend: signalUnit.bend,
      twist: signalUnit.twist,
      shrinkX: signalUnit.shrinkX,
      shrinkY: signalUnit.shrinkY,
      sink: signalUnit.sink,
      x,
      y,
      size: 0.011,
      glyph: densityToGlyph(density),
      density,
    });
    signals++;
  }

  // Draw order: lower depth first (behind). Stable sort keeps generation
  // order within the same depth.
  const sorted = particles
    .map((particle, index) => ({ particle, index }))
    .sort((a, b) => a.particle.depth - b.particle.depth || a.index - b.index)
    .map(({ particle }) => particle);

  return {
    seed,
    designWidth: DESIGN_WIDTH,
    designHeight: DESIGN_HEIGHT,
    heart: HEART,
    units,
    particles: sorted,
  };
}
