import { createPoster } from "../src/poster";

describe("Poster generation", () => {
  it("produces SVG and dataUrl", () => {
    const poster = createPoster({ seed: 42 });
    expect(poster.svg).toContain("<svg");
    expect(poster.svg).toContain("</svg>");
    expect(poster.dataUrl).toMatch(/^data:image\/svg\+xml/);
  });

  it("SVG contains off-axis exoplanet outline (ellipse)", () => {
    const poster = createPoster({ seed: 42 });
    expect(poster.svg).toContain("<ellipse");
  });

  it("SVG contains character texture from the ramp", () => {
    const poster = createPoster({ seed: 42 });
    // At least some chars from the ramp should appear as <text> elements
    expect(poster.svg).toContain("<text");
  });

  it("SVG includes accessible label", () => {
    const poster = createPoster({ seed: 42 });
    expect(poster.svg).toContain('role="img"');
    expect(poster.svg).toContain("aria-label");
  });

  it("respects custom dimensions", () => {
    const poster = createPoster({ seed: 42, width: 640, height: 400 });
    expect(poster.svg).toContain('width="640"');
    expect(poster.svg).toContain('height="400"');
  });

  it("dataUrl is URL-encoded SVG", () => {
    const poster = createPoster({ seed: 42 });
    // Decode and verify it matches the SVG
    const decoded = decodeURIComponent(
      poster.dataUrl.replace(/^data:image\/svg\+xml;charset=utf-8,/, ""),
    );
    expect(decoded).toBe(poster.svg);
  });
});
