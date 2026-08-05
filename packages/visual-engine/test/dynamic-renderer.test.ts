import { describe, expect, it } from "vitest";

import {
  createDynamicRenderer,
  GlyphAtlasUnavailableError,
} from "../src/webgl/dynamic-renderer";
import type { ScenePalette } from "../src/palette";
import { createResearchSceneModel } from "../src/scene-model";

const TEST_PALETTE: ScenePalette = {
  paper: "oklch(0.978 0.004 230)",
  ink: "oklch(0.38 0.022 235)",
  deep: "oklch(0.21 0.026 235)",
  soft: "oklch(0.885 0.011 235)",
  particle: "oklch(0.57 0.018 235)",
  anchor: "oklch(0.38 0.022 235)",
};

describe("createDynamicRenderer", () => {
  it("throws GlyphAtlasUnavailableError where canvas 2D is unavailable", () => {
    const canvas = document.createElement("canvas");
    const gl = { render: () => undefined } as never;
    expect(() =>
      createDynamicRenderer({
        gl,
        canvas,
        model: createResearchSceneModel(1),
        palette: TEST_PALETTE,
        quality: "high",
      }),
    ).toThrow(GlyphAtlasUnavailableError);
  });
});
