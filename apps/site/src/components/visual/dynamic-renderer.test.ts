import { describe, expect, it } from "vitest";

import {
  createDynamicRenderer,
  GlyphAtlasUnavailableError,
} from "./dynamic-renderer";
import type { ScenePalette } from "@xingwen/visual-engine";
import { createResearchSceneModel } from "@xingwen/visual-engine";

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

  it("throws UnparseablePaletteError when the paper token cannot be parsed", () => {
    // createGlyphAtlas builds its own canvas internally, so the 2D stub must
    // be installed on the prototype to reach palette parsing.
    const stub = {
      fillStyle: "",
      textAlign: "",
      textBaseline: "",
      font: "",
      fillText: () => undefined,
    } as unknown as CanvasRenderingContext2D;
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = ((contextId: string): unknown => {
      if (contextId === "2d") return stub;
      return original.call(this, contextId);
    }) as typeof original;
    try {
      const canvas = document.createElement("canvas");
      const gl = {
        render: () => undefined,
        setClearColor: () => undefined,
      } as never;
      expect(() =>
        createDynamicRenderer({
          gl,
          canvas,
          model: createResearchSceneModel(1),
          palette: { ...TEST_PALETTE, paper: "not-a-color" },
          quality: "high",
        }),
      ).toThrow(/paper/);
    } finally {
      HTMLCanvasElement.prototype.getContext = original;
    }
  });
});
