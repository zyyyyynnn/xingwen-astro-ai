import { createDeterministicRandom } from "./random";
import { normalizedBayerThreshold, quantizeGlyphLevel } from "./dither";

/**
 * ResearchSceneModel — the single source of truth consumed by the WebGL
 * dynamic renderer, the reduced-motion static phase, the SVG Poster and
 * offline review frames.
 *
 * The subject is a "Transit Evidence System": a star core (恒星核心),
 * multi-layer orbit bands (多层轨道), a continuous paper-node character
 * field (论文节点/字符层) and a few Evidence anchors (Evidence 锚点).
 * Composition mirrors the reference hero: the subject is extra-large,
 * off-axis (lower-center-right), bleed-cropped on the sides and
 * hard-cropped at the bottom edge.
 *
 * Motion is research-semantic convergence, NOT floral bloom: across the
 * 5.6s loop the outer orbits and character field contract toward the
 * core, sink, thin out, then rebuild — "evidence system focusing and
 * re-organizing", never petals folding.
 *
 * The character field is a stable object-space lattice sampled over a
 * continuous analytic density field; glyph levels come from real Bayer
 * ordered dithering so the surface reads as a continuous half-tone, not
 * random scatter. All randomness is deterministic.
 */

export { GLYPH_RAMP } from "./dither";
export const DESIGN_WIDTH = 3.2;
export const DESIGN_HEIGHT = 2.2;
export const LOOP_SECONDS = 5.6;

/** 恒星核心 anchor in design space: lower-center-right. */
export const HEART = Object.freeze({ x: 0.18, y: -0.5 });

export type SceneUnitType = "star" | "orbit" | "field" | "anchor";

export interface ConvergeParams {
  /** Global convergence phase (0..1) at which this layer starts converging. */
  readonly convergeStart: number;
  /** Phase window over which the layer completes its convergence. */
  readonly convergeWindow: number;
  /** Convergence target — the core the layer contracts toward. */
  readonly coreX: number;
  readonly coreY: number;
  /** Radial contraction toward core at full converge (0..1). */
  readonly contract: number;
  /** Downward sink at full converge (design units). */
  readonly sink: number;
  /** Subtle organizing twist around the core (radians). */
  readonly twist: number;
  /** Lateral drift amplitude while open. */
  readonly drift: number;
}

export interface SceneUnit extends ConvergeParams {
  readonly id: number;
  readonly type: SceneUnitType;
  readonly label: string;
  /** Draw order; lower depth is drawn first (behind). */
  readonly depth: number;
  /** 0 = character (soft→ink), 1 = orbit (particle), 2 = anchor. */
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

export interface SceneParticle extends ConvergeParams {
  readonly id: number;
  readonly unitId: number;
  readonly type: SceneUnitType;
  readonly colorClass: number;
  readonly depth: number;
  /** Design-space position at full open (converge phase = 0). */
  readonly x: number;
  readonly y: number;
  /** Character size in design units. */
  readonly size: number;
  /** Glyph ramp index 0..6 (Bayer-dithered); 7 = anchor square. */
  readonly glyph: number;
  /** Continuous density 0..1 driving the dither and ink mix. */
  readonly density: number;
  /** Object-space lattice coordinates — stable, drive Bayer threshold. */
  readonly latticeX: number;
  readonly latticeY: number;
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
 * Global convergence phase curve over one 5.6s loop, matching the
 * reference rhythm: long full hold → accelerating convergence → brief
 * near-empty pause → fast rebuild → long full hold.
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

/** Per-particle convergence progress 0..1 for a given global phase. */
export function particleConverge(
  particle: ConvergeParams,
  phase: number,
): number {
  const raw =
    (phase - particle.convergeStart) / Math.max(particle.convergeWindow, 1e-4);
  return smoothstep01(raw);
}

export interface DeformedParticle {
  readonly x: number;
  readonly y: number;
  readonly alpha: number;
  readonly size: number;
}

/**
 * Research-semantic convergence deformation — the CPU mirror of the GLSL
 * vertex deformation (kept in lockstep by tests): radial contraction
 * toward the core, organizing twist, downward sink, slow internal drift
 * and a supporting (non-primary) alpha fade. No petal pitch/bend, no
 * floral fold — the system contracts, sinks and thins.
 */
export function applyConverge(
  particle: SceneParticle,
  phase: number,
  timeSeconds: number,
): DeformedParticle {
  const p = particleConverge(particle, phase);

  const dx = particle.x - particle.coreX;
  const dy = particle.y - particle.coreY;

  // Radial contraction toward core.
  const rx = dx * (1 - p * particle.contract);
  const ry = dy * (1 - p * particle.contract);

  // Subtle organizing twist (stronger at radius, fades to zero at core).
  const tw = p * particle.twist * Math.min(1, Math.hypot(rx, ry) * 0.85);
  const ct = Math.cos(tw);
  const st = Math.sin(tw);
  const qx = rx * ct - ry * st;
  const qy = rx * st + ry * ct;

  // Downward sink (design space +y is up, so subtract to sink).
  let x = particle.coreX + qx;
  let y = particle.coreY + qy - p * particle.sink;

  // Slow internal drift (breathing) — dampens as the system converges.
  const wob =
    (Math.sin(timeSeconds * 0.35 + particle.seedA * 40.6) -
      Math.sin(particle.seedA * 40.6)) *
      0.016 +
    (Math.cos(timeSeconds * 0.28 + particle.seedB * 31.7) -
      Math.cos(particle.seedB * 31.7)) *
      0.014;
  const drift = wob * particle.drift * (1 - 0.4 * p);
  x += drift;
  y += drift * 0.7;

  return {
    x,
    y,
    alpha: (1 - 0.6 * p) * 0.92,
    size: particle.size * (1 - 0.18 * p),
  };
}

// ── Subject body definition ──────────────────────────────────────────
// The subject is a union of overlapping ellipses forming one continuous
// asymmetric body, bleed-cropped. Each ellipse contributes a local
// density field; the composite density is the max over all ellipses,
// giving a continuous half-tone surface (no gaps between "petals").

interface BodyEllipse {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  angle: number;
  base: number; // peak density contribution
}

const BODY_ELLIPSES: readonly BodyEllipse[] = [
  // Core — highest density, the visual anchor.
  { cx: HEART.x, cy: HEART.y, rx: 0.52, ry: 0.44, angle: 0, base: 0.95 },
  // Right dominant mass — extends the body rightward (bleed-crop).
  {
    cx: HEART.x + 0.5,
    cy: HEART.y - 0.04,
    rx: 0.46,
    ry: 0.34,
    angle: -0.12,
    base: 0.72,
  },
  // Upper-left shoulder.
  {
    cx: HEART.x - 0.34,
    cy: HEART.y + 0.38,
    rx: 0.34,
    ry: 0.3,
    angle: 0.55,
    base: 0.6,
  },
  // Lower apron — extends toward bottom crop.
  {
    cx: HEART.x + 0.12,
    cy: HEART.y - 0.42,
    rx: 0.32,
    ry: 0.26,
    angle: 0.1,
    base: 0.55,
  },
];

/** Continuous density at a design-space point — max over body ellipses. */
function densityAt(x: number, y: number): number {
  let best = 0;
  for (const e of BODY_ELLIPSES) {
    const dx = x - e.cx;
    const dy = y - e.cy;
    const ca = Math.cos(-e.angle);
    const sa = Math.sin(-e.angle);
    const lx = dx * ca - dy * sa;
    const ly = dx * sa + dy * ca;
    const nd = Math.hypot(lx / e.rx, ly / e.ry);
    if (nd >= 1) continue;
    const local = e.base * (1 - nd * 0.92);
    if (local > best) best = local;
  }
  return best;
}

interface OrbitDef {
  r: number;
  tilt: number;
  yc: number;
  convergeStart: number;
  depth: number;
}

const ORBIT_DEFS: readonly OrbitDef[] = [
  { r: 0.62, tilt: -0.16, yc: 0.62, convergeStart: 0.18, depth: 0.9 },
  { r: 0.92, tilt: -0.16, yc: 0.62, convergeStart: 0.0, depth: 0.8 },
  { r: 1.18, tilt: -0.14, yc: 0.6, convergeStart: 0.0, depth: 0.7 },
];

const LATTICE_STEP = 0.026;
const LATTICE_JITTER = 0.011;

export function createResearchSceneModel(seed: number): ResearchSceneModel {
  const rng = createDeterministicRandom(seed);
  const units: SceneUnit[] = [];
  const particles: SceneParticle[] = [];
  let unitId = 0;
  let particleId = 0;

  function pushUnit(unit: Omit<SceneUnit, "id">): SceneUnit {
    const full = { ...unit, id: unitId++ };
    units.push(full);
    return full;
  }

  function pushParticle(
    particle: Omit<SceneParticle, "id" | "seedA" | "seedB">,
  ): void {
    particles.push({
      ...particle,
      id: particleId++,
      seedA: rng.next(),
      seedB: rng.next(),
    });
  }

  // ── Star core unit (恒星核心) ──────────────────────────────────────
  // Converges last and mildly — it survives the near-empty pause as the
  // residual core. High density, dense cluster.
  const starUnit = pushUnit({
    type: "star",
    label: "star",
    convergeStart: 0.42,
    convergeWindow: 0.58,
    coreX: HEART.x,
    coreY: HEART.y,
    contract: 0.32,
    sink: 0.14,
    twist: 0.18,
    drift: 0.4,
    depth: 2.0,
    colorClass: 0,
    geometry: {
      kind: "ellipse",
      cx: HEART.x,
      cy: HEART.y,
      rx: 0.5,
      ry: 0.44,
      angle: 0,
    },
  });

  // ── Character field (论文节点/字符层) ──────────────────────────────
  // The continuous subject surface: a stable lattice sampled over the
  // body density field, glyphs assigned by real Bayer ordered dithering.
  // This replaces the old discrete petals — no gaps, one continuous body.
  const fieldUnit = pushUnit({
    type: "field",
    label: "field",
    convergeStart: 0.08,
    convergeWindow: 0.92,
    coreX: HEART.x,
    coreY: HEART.y,
    contract: 0.78,
    sink: 0.3,
    twist: 0.32,
    drift: 0.85,
    depth: 1.4,
    colorClass: 0,
    geometry: {
      kind: "ellipse",
      cx: HEART.x,
      cy: HEART.y,
      rx: 1.0,
      ry: 0.8,
      angle: 0,
    },
  });

  const xMin = -DESIGN_WIDTH / 2 - 0.1;
  const xMax = DESIGN_WIDTH / 2 + 0.1;
  const yMin = -DESIGN_HEIGHT / 2 - 0.1;
  const yMax = DESIGN_HEIGHT / 2 + 0.1;
  let latY = 0;
  for (let gy = yMin; gy <= yMax; gy += LATTICE_STEP) {
    let latX = 0;
    for (let gx = xMin; gx <= xMax; gx += LATTICE_STEP) {
      const jx = (rng.next() * 2 - 1) * LATTICE_JITTER;
      const jy = (rng.next() * 2 - 1) * LATTICE_JITTER;
      const x = gx + jx;
      const y = gy + jy;
      const density = densityAt(x, y);
      if (density < 0.1) {
        latX++;
        continue;
      }
      const threshold = normalizedBayerThreshold(latX, latY);
      const glyph = quantizeGlyphLevel(density, threshold);
      // Density ramp for ink color mix in the shader.
      const inkMix = Math.min(1, density);
      pushParticle({
        unitId: fieldUnit.id,
        type: "field",
        colorClass: 0,
        depth: fieldUnit.depth + (1 - density) * 0.3,
        x,
        y,
        size: 0.02 + density * 0.012 + rng.next() * 0.002,
        glyph,
        density: inkMix,
        latticeX: latX,
        latticeY: latY,
        convergeStart: fieldUnit.convergeStart,
        convergeWindow: fieldUnit.convergeWindow,
        coreX: fieldUnit.coreX,
        coreY: fieldUnit.coreY,
        contract: fieldUnit.contract,
        sink: fieldUnit.sink,
        twist: fieldUnit.twist,
        drift: fieldUnit.drift,
      });
      latX++;
    }
    latY++;
  }

  // ── Star core cluster ─────────────────────────────────────────────
  // Extra dense particles at the core for a stable, recognizable anchor.
  const STAR_EXTRA = 360;
  for (let i = 0; i < STAR_EXTRA; i++) {
    const r = Math.sqrt(rng.next()) * 0.34;
    const a = rng.next() * Math.PI * 2;
    const x = HEART.x + Math.cos(a) * r;
    const y = HEART.y + Math.sin(a) * r * 0.85;
    const density = 1 - r / 0.34;
    const latX = Math.floor((x - xMin) / LATTICE_STEP);
    const latY = Math.floor((y - yMin) / LATTICE_STEP);
    const threshold = normalizedBayerThreshold(latX, latY);
    const glyph = quantizeGlyphLevel(density, threshold);
    pushParticle({
      unitId: starUnit.id,
      type: "star",
      colorClass: 0,
      depth: starUnit.depth,
      x,
      y,
      size: 0.022 + density * 0.01 + rng.next() * 0.002,
      glyph,
      density,
      latticeX: latX,
      latticeY: latY,
      convergeStart: starUnit.convergeStart,
      convergeWindow: starUnit.convergeWindow,
      coreX: starUnit.coreX,
      coreY: starUnit.coreY,
      contract: starUnit.contract,
      sink: starUnit.sink,
      twist: starUnit.twist,
      drift: starUnit.drift,
    });
  }

  // ── Orbit bands (多层轨道) ─────────────────────────────────────────
  // Off-axis, asymmetric, with local density variation. Converge before
  // the core — outer rings contract first.
  for (const def of ORBIT_DEFS) {
    const orbitUnit = pushUnit({
      type: "orbit",
      label: `orbit-${def.r.toFixed(2)}`,
      convergeStart: def.convergeStart,
      convergeWindow: 1 - def.convergeStart,
      coreX: HEART.x,
      coreY: HEART.y,
      contract: 0.7,
      sink: 0.22,
      twist: 0.22,
      drift: 0.6,
      depth: def.depth,
      colorClass: 1,
      geometry: {
        kind: "ring",
        cx: HEART.x,
        cy: HEART.y,
        rx: def.r,
        ry: def.r * def.yc,
        angle: def.tilt,
      },
    });

    const RING_COUNT = 150;
    for (let i = 0; i < RING_COUNT; i++) {
      const a = (i / RING_COUNT) * Math.PI * 2;
      // Local density variation along the band — denser on the leading arc.
      const arcDensity = 0.45 + 0.3 * (0.5 + 0.5 * Math.cos(a + 0.6));
      const rr = def.r * (1 + (rng.next() * 2 - 1) * 0.018);
      const x = HEART.x + Math.cos(a + def.tilt) * rr;
      const y = HEART.y + Math.sin(a + def.tilt) * rr * def.yc;
      const latX = Math.floor((x - xMin) / LATTICE_STEP);
      const latY = Math.floor((y - yMin) / LATTICE_STEP);
      const threshold = normalizedBayerThreshold(latX, latY);
      const glyph = quantizeGlyphLevel(arcDensity, threshold);
      pushParticle({
        unitId: orbitUnit.id,
        type: "orbit",
        colorClass: 1,
        depth: orbitUnit.depth,
        x,
        y,
        size: 0.018,
        glyph,
        density: arcDensity,
        latticeX: latX,
        latticeY: latY,
        convergeStart: orbitUnit.convergeStart,
        convergeWindow: orbitUnit.convergeWindow,
        coreX: orbitUnit.coreX,
        coreY: orbitUnit.coreY,
        contract: orbitUnit.contract,
        sink: orbitUnit.sink,
        twist: orbitUnit.twist,
        drift: orbitUnit.drift,
      });
    }
  }

  // ── Evidence anchors (Evidence 锚点) ───────────────────────────────
  // Few stable structural points at orbit intersections / lobe tips.
  const ANCHOR_POINTS = [
    { x: HEART.x + 0.92, y: HEART.y - 0.04, label: "right" },
    { x: HEART.x - 0.34, y: HEART.y + 0.62, label: "upperLeft" },
    { x: HEART.x + 0.12, y: HEART.y - 0.66, label: "lower" },
    { x: HEART.x - 0.78, y: HEART.y + 0.1, label: "left" },
  ];
  for (const ap of ANCHOR_POINTS) {
    const anchorUnit = pushUnit({
      type: "anchor",
      label: `anchor-${ap.label}`,
      convergeStart: 0.12,
      convergeWindow: 0.88,
      coreX: HEART.x,
      coreY: HEART.y,
      contract: 0.55,
      sink: 0.18,
      twist: 0.2,
      drift: 0.5,
      depth: 3.0,
      colorClass: 2,
      geometry: { kind: "point", cx: ap.x, cy: ap.y, rx: 0, ry: 0, angle: 0 },
    });
    pushParticle({
      unitId: anchorUnit.id,
      type: "anchor",
      colorClass: 2,
      depth: anchorUnit.depth,
      x: ap.x,
      y: ap.y,
      size: 0.032,
      glyph: 7,
      density: 1,
      latticeX: Math.floor((ap.x - xMin) / LATTICE_STEP),
      latticeY: Math.floor((ap.y - yMin) / LATTICE_STEP),
      convergeStart: anchorUnit.convergeStart,
      convergeWindow: anchorUnit.convergeWindow,
      coreX: anchorUnit.coreX,
      coreY: anchorUnit.coreY,
      contract: anchorUnit.contract,
      sink: anchorUnit.sink,
      twist: anchorUnit.twist,
      drift: anchorUnit.drift,
    });
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
