import { describe, expect, it } from "vitest";

import {
  applyFold,
  createResearchSceneModel,
  foldAt,
  DESIGN_HEIGHT,
  DESIGN_WIDTH,
  LOOP_SECONDS,
} from "../src/scene-model";

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
    expect(model.particles.length).toBeLessThan(3000);
  });

  it("places the star core lower-center-right", () => {
    const model = createResearchSceneModel(42);
    expect(model.heart.x).toBeGreaterThan(0);
    expect(model.heart.y).toBeLessThan(0);
  });

  it("keeps every non-orbit particle inside the design space", () => {
    const model = createResearchSceneModel(42);
    for (const particle of model.particles) {
      if (particle.type === "orbit") continue;
      expect(Math.abs(particle.x)).toBeLessThanOrEqual(DESIGN_WIDTH / 2 + 1e-6);
      expect(Math.abs(particle.y)).toBeLessThanOrEqual(
        DESIGN_HEIGHT / 2 + 1e-6,
      );
    }
  });

  it("lets the orbit rings bleed past the bottom crop line", () => {
    const model = createResearchSceneModel(42);
    const orbits = model.particles.filter(
      (particle) => particle.type === "orbit",
    );
    expect(Math.min(...orbits.map((particle) => particle.y))).toBeLessThan(
      -DESIGN_HEIGHT / 2,
    );
  });

  it("exposes all semantic unit types", () => {
    const model = createResearchSceneModel(42);
    for (const type of ["star", "orbit", "paperNode", "anchor", "signal"]) {
      expect(model.units.some((unit) => unit.type === type)).toBe(true);
    }
  });

  it("folds the right long petal first and the star core last", () => {
    const model = createResearchSceneModel(42);
    const rightLong = model.units.find((unit) => unit.label === "rightLong");
    const star = model.units.find((unit) => unit.type === "star");
    expect(rightLong?.foldStart).toBe(0);
    expect(star?.foldStart).toBeGreaterThan(0.4);
    expect(rightLong?.foldStart).toBeLessThan(star?.foldStart ?? 1);
  });

  it("assigns glyphs inside the ramp range plus the anchor marker", () => {
    for (const particle of createResearchSceneModel(42).particles) {
      expect(particle.glyph).toBeGreaterThanOrEqual(0);
      expect(particle.glyph).toBeLessThanOrEqual(7);
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

  it("closes monotonically and re-opens monotonically", () => {
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

describe("applyFold deformation", () => {
  it("is identity at fold 0 and time 0", () => {
    const model = createResearchSceneModel(42);
    const particle = model.particles[0] ?? expect.fail("no particles");
    const out = applyFold(particle, 0, 0);
    expect(out.x).toBeCloseTo(particle.x, 6);
    expect(out.y).toBeCloseTo(particle.y, 6);
    expect(out.alpha).toBeCloseTo(0.92, 6);
  });

  it("displaces the right long petal more than the star core at partial fold", () => {
    const model = createResearchSceneModel(42);
    const rightUnit = model.units.find((unit) => unit.label === "rightLong");
    const starUnit = model.units.find((unit) => unit.type === "star");

    function displacement(unitId: number | undefined): number[] {
      if (unitId === undefined) return [0];
      return model.particles
        .filter((particle) => particle.unitId === unitId)
        .map((particle) => {
          const out = applyFold(particle, 0.45, 0);
          return Math.hypot(out.x - particle.x, out.y - particle.y);
        });
    }

    expect(mean(displacement(rightUnit?.id))).toBeGreaterThan(
      mean(displacement(starUnit?.id)),
    );
  });

  it("sinks downward (y increases) as the fold progresses", () => {
    const model = createResearchSceneModel(42);
    const starParticles = model.particles.filter(
      (particle) => particle.type === "star",
    );
    const closed = starParticles.map((particle) => applyFold(particle, 1, 0).y);
    const open = starParticles.map((particle) => applyFold(particle, 0, 0).y);
    expect(mean(closed)).toBeGreaterThan(mean(open));
  });

  it("fades alpha but never blanks particles at full fold", () => {
    for (const particle of createResearchSceneModel(42).particles) {
      const out = applyFold(particle, 1, 0);
      expect(out.alpha).toBeLessThan(0.92);
      expect(out.alpha).toBeGreaterThan(0.3);
    }
  });

  it("collapses particle radial spread toward each layer pivot at full fold", () => {
    const model = createResearchSceneModel(42);
    const openDist = model.particles.map((particle) =>
      Math.hypot(
        applyFold(particle, 0, 0).x - particle.pivotX,
        applyFold(particle, 0, 0).y - particle.pivotY,
      ),
    );
    const closedDist = model.particles.map((particle) =>
      Math.hypot(
        applyFold(particle, 1, 0).x - particle.pivotX,
        applyFold(particle, 1, 0).y - particle.pivotY,
      ),
    );
    expect(mean(closedDist)).toBeLessThan(mean(openDist) * 0.8);
  });

  it("defines non-uniform shrink on every folding unit (shrinkY > shrinkX)", () => {
    for (const unit of createResearchSceneModel(42).units) {
      expect(unit.shrinkY).toBeGreaterThan(unit.shrinkX);
    }
  });
});
