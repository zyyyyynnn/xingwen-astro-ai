import { createAsciiDitherRenderer } from "../src/renderer";

const CHAR_RAMP = ["·", ":", "+", "*", "#", "%", "@"];

function createTestCanvas(width = 160, height = 100): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

describe("ASCII/Dither renderer", () => {
  it("produces frame data with correct dimensions", () => {
    const renderer = createAsciiDitherRenderer({
      seed: 1,
      width: 160,
      height: 100,
      quality: "high",
      freezeTime: 0,
      canvas: createTestCanvas(),
    });

    const frame = renderer.getFrameData(0);
    expect(frame.width).toBeGreaterThan(0);
    expect(frame.height).toBeGreaterThan(0);
    expect(frame.cells.length).toBe(frame.width * frame.height);
  });

  it("uses only characters from the defined ramp (max 7 per frame)", () => {
    const renderer = createAsciiDitherRenderer({
      seed: 42,
      width: 200,
      height: 150,
      quality: "high",
      freezeTime: 1000,
      canvas: createTestCanvas(200, 150),
    });

    const frame = renderer.getFrameData(1000);
    const usedChars = new Set(frame.cells.map((c) => c.char));

    for (const char of usedChars) {
      expect(CHAR_RAMP).toContain(char);
    }
    expect(usedChars.size).toBeLessThanOrEqual(7);
  });

  it("alpha values are in [0, 1] range", () => {
    const renderer = createAsciiDitherRenderer({
      seed: 7,
      width: 100,
      height: 80,
      quality: "medium",
      freezeTime: 500,
      canvas: createTestCanvas(100, 80),
    });

    const frame = renderer.getFrameData(500);
    for (const cell of frame.cells) {
      expect(cell.alpha).toBeGreaterThanOrEqual(0);
      expect(cell.alpha).toBeLessThanOrEqual(1);
    }
  });

  it("quality tiers affect cell density", () => {
    const width = 160;
    const height = 100;

    const high = createAsciiDitherRenderer({
      seed: 1,
      width,
      height,
      quality: "high",
      freezeTime: 0,
      canvas: createTestCanvas(width, height),
    });
    const low = createAsciiDitherRenderer({
      seed: 1,
      width,
      height,
      quality: "low",
      freezeTime: 0,
      canvas: createTestCanvas(width, height),
    });

    const highFrame = high.getFrameData(0);
    const lowFrame = low.getFrameData(0);

    // High quality has more cells (smaller cellSize) than low quality
    expect(highFrame.cells.length).toBeGreaterThan(lowFrame.cells.length);
  });

  it("render does not throw when canvas 2D context is unavailable (jsdom)", () => {
    const renderer = createAsciiDitherRenderer({
      seed: 1,
      width: 100,
      height: 80,
      quality: "high",
      freezeTime: 0,
      canvas: createTestCanvas(100, 80),
    });

    // jsdom: getContext("2d") returns null — render should be a no-op
    expect(() => renderer.render(0)).not.toThrow();
  });

  it("dispose prevents further rendering", () => {
    const renderer = createAsciiDitherRenderer({
      seed: 1,
      width: 100,
      height: 80,
      quality: "high",
      freezeTime: 0,
      canvas: createTestCanvas(100, 80),
    });

    renderer.dispose();
    // render after dispose should be a no-op (no throw, no draw)
    expect(() => renderer.render(0)).not.toThrow();
  });
});
