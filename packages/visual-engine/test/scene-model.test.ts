import { describe, expect, it } from "vitest";

import {
  applyConverge,
  createResearchSceneModel,
  foldAt,
  DESIGN_HEIGHT,
  DESIGN_WIDTH,
  LOOP_SECONDS,
} from "../src/scene-model";
import { normalizedBayerThreshold, quantizeGlyphLevel } from "../src/dither";

function mean(values: readonly number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

describe("createResearchSceneModel", () => {
  it("produces an identical model for the same seed", () => {
    expect(createResearchSceneModel(42)).toEqual(createResearchSceneModel(42));
  });

  it("produces different particles for different seeds", () => {
    const a = createResearchSceneModel(42);
    const b = createResearchSceneModel(99);
    expect(a.particles).not.toEqual(b.particles);
  });

  it("keeps a bounded particle count", () => {
    const model = createResearchSceneModel(42);
    expect(model.particles.length).toBeGreaterThan(2000);
    expect(model.particles.length).toBeLessThan(3500);
  });

  it("places the star core lower-center-right", () => {
    const model = createResearchSceneModel(42);
    expect(model.heart.x).toBeGreaterThan(0);
    expect(model.heart.y).toBeLessThan(0);
  });

  it("exposes all semantic unit types", () => {
    const model = createResearchSceneModel(42);
    for (const type of ["star", "orbit", "field", "anchor"]) {
      expect(model.units.some((unit) => unit.type === type)).toBe(true);
    }
  });

  it("converges outer orbits before the star core", () => {
    const model = createResearchSceneModel(42);
    const outerOrbit = model.units.find(
      (unit) => unit.type === "orbit" && unit.label.includes("1.18"),
    );
    const star = model.units.find((unit) => unit.type === "star");
    expect(outerOrbit?.convergeStart).toBe(0);
    expect(star?.convergeStart).toBeGreaterThan(0.3);
    expect(outerOrbit?.convergeStart).toBeLessThan(star?.convergeStart ?? 1);
  });

  it("assigns glyphs inside the ramp range plus the anchor marker", () => {
    for (const particle of createResearchSceneModel(42).particles) {
      expect(particle.glyph).toBeGreaterThanOrEqual(0);
      expect(particle.glyph).toBeLessThanOrEqual(7);
    }
  });

  it("assigns stable lattice coordinates to every particle", () => {
    const model = createResearchSceneModel(42);
    for (const particle of model.particles) {
      expect(Number.isInteger(particle.latticeX)).toBe(true);
      expect(Number.isInteger(particle.latticeY)).toBe(true);
    }
  });

  it("derives non-anchor glyphs from Bayer ordered dithering", () => {
    const model = createResearchSceneModel(42);
    for (const particle of model.particles) {
      if (particle.glyph === 7) continue; // anchor marker
      const threshold = normalizedBayerThreshold(
        particle.latticeX,
        particle.latticeY,
      );
      expect(particle.glyph).toBe(
        quantizeGlyphLevel(particle.density, threshold),
      );
    }
  });
});

describe("foldAt loop curve", () => {
  it("loops every 5.6 seconds", () => {
    expect(foldAt(0)).toBe(0);
    expect(foldAt(LOOP_SECONDS)).toBe(0);
    expect(foldAt(LOOP_SECONDS * 2 + 1.8)).toBe(1);
  });

  it("holds fully open at the start and end of the loop", () => {
    expect(foldAt(0.3)).toBe(0);
    expect(foldAt(4.0)).toBe(0);
    expect(foldAt(5.5)).toBe(0);
  });

  it("holds the near-empty state during the pause", () => {
    expect(foldAt(1.8)).toBe(1);
  });

  it("converges monotonically and rebuilds monotonically", () => {
    const closing = [0.7, 0.9, 1.1, 1.3, 1.5].map(foldAt);
    for (let i = 1; i < closing.length; i++) {
      expect(closing[i] ?? 0).toBeGreaterThan(closing[i - 1] ?? 0);
    }
    const opening = [2.1, 2.3, 2.5, 2.8, 3.0].map(foldAt);
    for (let i = 1; i < opening.length; i++) {
      expect(opening[i] ?? 0).toBeLessThan(opening[i - 1] ?? 0);
    }
  });
});

describe("applyConverge deformation", () => {
  it("is identity at phase 0 and time 0", () => {
    const model = createResearchSceneModel(42);
    const particle = model.particles[0] ?? expect.fail("no particles");
    const out = applyConverge(particle, 0, 0);
    expect(out.x).toBeCloseTo(particle.x, 6);
    expect(out.y).toBeCloseTo(particle.y, 6);
    expect(out.alpha).toBeCloseTo(0.92, 6);
  });

  it("contracts field particles toward the core more than the star core", () => {
    const model = createResearchSceneModel(42);
    const fieldUnit = model.units.find((unit) => unit.type === "field");
    const starUnit = model.units.find((unit) => unit.type === "star");

    function contraction(unitId: number | undefined): number {
      if (unitId === undefined) return 0;
      return mean(
        model.particles
          .filter((particle) => particle.unitId === unitId)
          .map((particle) => {
            const open = Math.hypot(
              particle.x - particle.coreX,
              particle.y - particle.coreY,
            );
            const closed = applyConverge(particle, 1, 0);
            // Add back the sink to isolate pure radial contraction.
            const ry = closed.y - particle.coreY + particle.sink;
            return (
              Math.hypot(closed.x - particle.coreX, ry) / Math.max(open, 1e-6)
            );
          }),
      );
    }

    // Field retains a smaller fraction of its open radius than the core.
    expect(contraction(fieldUnit?.id)).toBeLessThan(contraction(starUnit?.id));
  });

  it("sinks downward (y decreases) as convergence progresses", () => {
    const model = createResearchSceneModel(42);
    const fieldParticles = model.particles.filter(
      (particle) => particle.type === "field",
    );
    const open = fieldParticles.map(
      (particle) => applyConverge(particle, 0, 0).y,
    );
    const converged = fieldParticles.map(
      (particle) => applyConverge(particle, 1, 0).y,
    );
    expect(mean(converged)).toBeLessThan(mean(open));
  });

  it("fades alpha but never blanks particles at full convergence", () => {
    for (const particle of createResearchSceneModel(42).particles) {
      const out = applyConverge(particle, 1, 0);
      expect(out.alpha).toBeLessThan(0.92);
      expect(out.alpha).toBeGreaterThan(0.3);
    }
  });

  it("collapses radial spread toward the core at full convergence", () => {
    const model = createResearchSceneModel(42);
    const fieldParticles = model.particles.filter(
      (particle) => particle.type === "field",
    );
    const openDist = fieldParticles.map((particle) =>
      Math.hypot(
        applyConverge(particle, 0, 0).x - particle.coreX,
        applyConverge(particle, 0, 0).y - particle.coreY,
      ),
    );
    const closedDist = fieldParticles.map((particle) => {
      const closed = applyConverge(particle, 1, 0);
      // Add back the sink to isolate pure radial contraction.
      const ry = closed.y - particle.coreY + particle.sink;
      return Math.hypot(closed.x - particle.coreX, ry);
    });
    expect(mean(closedDist)).toBeLessThan(mean(openDist) * 0.5);
  });
});
