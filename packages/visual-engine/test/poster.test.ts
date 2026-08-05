import { describe, expect, it } from "vitest";

import type { ScenePalette } from "../src/palette";
import { createPoster } from "../src/poster";
import { createResearchSceneModel } from "../src/scene-model";

const TEST_PALETTE: ScenePalette = {
  paper: "oklch(0.978 0.004 230)",
  ink: "oklch(0.38 0.022 235)",
  deep: "oklch(0.21 0.026 235)",
  soft: "oklch(0.885 0.011 235)",
  particle: "oklch(0.57 0.018 235)",
  anchor: "oklch(0.38 0.022 235)",
};

describe("createPoster", () => {
  const model = createResearchSceneModel(42);

  it("produces SVG and dataUrl", () => {
    const poster = createPoster(model, TEST_PALETTE);
    expect(poster.svg).toContain("<svg");
    expect(poster.svg).toContain("</svg>");
    expect(poster.dataUrl).toMatch(/^data:image\/svg\+xml/);
  });

  it("is deterministic for the same model and palette", () => {
    const a = createPoster(model, TEST_PALETTE);
    const b = createPoster(model, TEST_PALETTE);
    expect(a.svg).toBe(b.svg);
    expect(a.dataUrl).toBe(b.dataUrl);
  });

  it("differs for a different model seed", () => {
    const a = createPoster(model, TEST_PALETTE);
    const b = createPoster(createResearchSceneModel(99), TEST_PALETTE);
    expect(a.svg).not.toBe(b.svg);
  });

  it("contains orbit ellipses and character textures", () => {
    const poster = createPoster(model, TEST_PALETTE);
    expect(poster.svg).toContain("<ellipse");
    expect(poster.svg).toContain("<text");
  });

  it("contains Evidence anchor squares", () => {
    const poster = createPoster(model, TEST_PALETTE);
    const anchorSquares = poster.svg.match(/<rect/g);
    expect(anchorSquares?.length).toBeGreaterThan(0);
  });

  it("uses only the injected palette colors", () => {
    const poster = createPoster(model, TEST_PALETTE);
    for (const color of Object.values(TEST_PALETTE)) {
      expect(poster.svg).toContain(color);
    }
  });

  it("includes an accessible label", () => {
    const poster = createPoster(model, TEST_PALETTE);
    expect(poster.svg).toContain('role="img"');
    expect(poster.svg).toContain("aria-label");
  });

  it("respects custom dimensions", () => {
    const poster = createPoster(model, TEST_PALETTE, {
      width: 640,
      height: 400,
    });
    expect(poster.svg).toContain('width="640"');
    expect(poster.svg).toContain('height="400"');
  });

  it("dataUrl is the URL-encoded SVG", () => {
    const poster = createPoster(model, TEST_PALETTE);
    const decoded = decodeURIComponent(
      poster.dataUrl.replace(/^data:image\/svg\+xml;charset=utf-8,/, ""),
    );
    expect(decoded).toBe(poster.svg);
  });
});
