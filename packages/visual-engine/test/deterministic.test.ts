import { describe, expect, it } from "vitest";

import { createDeterministicRandom } from "../src/random";
import { createPoster } from "../src/poster";
import { createResearchSceneModel } from "../src/scene-model";
import { sampleSceneFrame } from "../src/sample-frame";
import type { ScenePalette } from "../src/palette";

const TEST_PALETTE: ScenePalette = {
  paper: "oklch(0.978 0.004 230)",
  ink: "oklch(0.38 0.022 235)",
  deep: "oklch(0.21 0.026 235)",
  soft: "oklch(0.885 0.011 235)",
  particle: "oklch(0.57 0.018 235)",
  anchor: "oklch(0.38 0.022 235)",
};

describe("deterministic output", () => {
  it("createDeterministicRandom produces the same sequence for the same seed", () => {
    const a = createDeterministicRandom(42);
    const b = createDeterministicRandom(42);
    expect([a.next(), a.next(), a.next()]).toEqual([
      b.next(),
      b.next(),
      b.next(),
    ]);
  });

  it("different seeds produce different sequences", () => {
    const a = createDeterministicRandom(42);
    const b = createDeterministicRandom(99);
    expect([a.next(), a.next(), a.next()]).not.toEqual([
      b.next(),
      b.next(),
      b.next(),
    ]);
  });

  it("poster is deterministic for the same model", () => {
    const model = createResearchSceneModel(42);
    expect(createPoster(model, TEST_PALETTE).svg).toBe(
      createPoster(model, TEST_PALETTE).svg,
    );
  });

  it("sample frames are deterministic for the same time", () => {
    const model = createResearchSceneModel(12345);
    const a = sampleSceneFrame(model, 1.9, { cols: 64, rows: 36 });
    const b = sampleSceneFrame(model, 1.9, { cols: 64, rows: 36 });
    expect(a).toEqual(b);
  });

  it("different seeds produce different posters", () => {
    const a = createPoster(createResearchSceneModel(42), TEST_PALETTE);
    const b = createPoster(createResearchSceneModel(99), TEST_PALETTE);
    expect(a.svg).not.toBe(b.svg);
  });
});
