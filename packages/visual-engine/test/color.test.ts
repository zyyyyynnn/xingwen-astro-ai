import { describe, expect, it } from "vitest";

import { cssColorToSrgb, oklchToSrgb } from "../src/color";

describe("oklchToSrgb", () => {
  it("maps white to near-white", () => {
    const { r, g, b } = oklchToSrgb(1, 0, 0);
    expect(r).toBeGreaterThan(0.98);
    expect(g).toBeGreaterThan(0.98);
    expect(b).toBeGreaterThan(0.98);
  });

  it("maps black to near-black", () => {
    const { r, g, b } = oklchToSrgb(0, 0, 0);
    expect(r).toBeLessThan(0.02);
    expect(g).toBeLessThan(0.02);
    expect(b).toBeLessThan(0.02);
  });

  it("is monotonically lighter with lightness", () => {
    const dark = oklchToSrgb(0.2, 0.02, 235);
    const light = oklchToSrgb(0.8, 0.02, 235);
    const luminance = (c: { r: number; g: number; b: number }): number =>
      0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b;
    expect(luminance(light)).toBeGreaterThan(luminance(dark));
  });

  it("keeps results inside the sRGB gamut", () => {
    for (const l of [0.05, 0.2, 0.5, 0.8, 0.95]) {
      const { r, g, b } = oklchToSrgb(l, 0.03, 235);
      expect(r).toBeGreaterThanOrEqual(0);
      expect(r).toBeLessThanOrEqual(1);
      expect(g).toBeGreaterThanOrEqual(0);
      expect(g).toBeLessThanOrEqual(1);
      expect(b).toBeGreaterThanOrEqual(0);
      expect(b).toBeLessThanOrEqual(1);
    }
  });
});

describe("cssColorToSrgb", () => {
  it("parses oklch strings", () => {
    const color = cssColorToSrgb("oklch(0.21 0.026 235)");
    expect(color).not.toBeNull();
  });

  it("parses 6-digit hex", () => {
    expect(cssColorToSrgb("#000000")).toEqual({ r: 0, g: 0, b: 0 });
    expect(cssColorToSrgb("#ffffff")).toEqual({ r: 1, g: 1, b: 1 });
    expect(cssColorToSrgb("#ff0000")).toEqual({ r: 1, g: 0, b: 0 });
  });

  it("parses 3-digit hex", () => {
    expect(cssColorToSrgb("#fff")).toEqual({ r: 1, g: 1, b: 1 });
    expect(cssColorToSrgb("#000")).toEqual({ r: 0, g: 0, b: 0 });
  });

  it("returns null for unsupported formats", () => {
    expect(cssColorToSrgb("rgb(1, 2, 3)")).toBeNull();
    expect(cssColorToSrgb("not-a-color")).toBeNull();
    expect(cssColorToSrgb("")).toBeNull();
  });
});
