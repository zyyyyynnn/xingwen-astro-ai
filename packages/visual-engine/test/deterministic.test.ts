import { createAsciiDitherRenderer } from "../src/renderer";
import { createDeterministicRandom } from "../src/random";
import { createPoster } from "../src/poster";

/**
 * Hash frame data into a stable string for deterministic comparison.
 */
function hashFrame(frame: {
  width: number;
  height: number;
  cells: readonly { char: string; alpha: number }[];
}): string {
  const cellHash = frame.cells
    .map((c) => `${c.char}${c.alpha.toFixed(4)}`)
    .join("|");
  return `${frame.width}x${frame.height}:${cellHash}`;
}

describe("deterministic output", () => {
  it("createDeterministicRandom produces same sequence for same seed", () => {
    const a = createDeterministicRandom(42);
    const b = createDeterministicRandom(42);
    const seqA = [a.next(), a.next(), a.next(), a.next(), a.next()];
    const seqB = [b.next(), b.next(), b.next(), b.next(), b.next()];
    expect(seqA).toEqual(seqB);
  });

  it("different seeds produce different sequences", () => {
    const a = createDeterministicRandom(42);
    const b = createDeterministicRandom(99);
    const seqA = [a.next(), a.next(), a.next()];
    const seqB = [b.next(), b.next(), b.next()];
    expect(seqA).not.toEqual(seqB);
  });

  it("renderer produces identical frame data for same seed + time + viewport", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 100;

    const config = {
      seed: 12345,
      width: 160,
      height: 100,
      quality: "medium" as const,
      freezeTime: 5000,
      canvas,
    };

    const rendererA = createAsciiDitherRenderer(config);
    const rendererB = createAsciiDitherRenderer(config);

    const frameA = rendererA.getFrameData(5000);
    const frameB = rendererB.getFrameData(5000);

    expect(hashFrame(frameA)).toBe(hashFrame(frameB));
  });

  it("renderer produces identical frame data across two calls (stability)", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 100;

    const renderer = createAsciiDitherRenderer({
      seed: 777,
      width: 160,
      height: 100,
      quality: "high" as const,
      freezeTime: 3000,
      canvas,
    });

    const frame1 = renderer.getFrameData(3000);
    const frame2 = renderer.getFrameData(3000);

    expect(hashFrame(frame1)).toBe(hashFrame(frame2));
  });

  it("freezeTime fixes temporal variation", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 160;
    canvas.height = 100;

    const renderer = createAsciiDitherRenderer({
      seed: 42,
      width: 160,
      height: 100,
      quality: "medium" as const,
      freezeTime: 10000,
      canvas,
    });

    // Different "time" arguments should produce same output when frozen
    const frame1 = renderer.getFrameData(10000);
    const frame2 = renderer.getFrameData(99999);

    expect(hashFrame(frame1)).toBe(hashFrame(frame2));
  });

  it("poster is deterministic for same seed", () => {
    const posterA = createPoster({ seed: 42 });
    const posterB = createPoster({ seed: 42 });
    expect(posterA.svg).toBe(posterB.svg);
    expect(posterA.dataUrl).toBe(posterB.dataUrl);
  });

  it("poster differs for different seeds", () => {
    const posterA = createPoster({ seed: 42 });
    const posterB = createPoster({ seed: 99 });
    expect(posterA.svg).not.toBe(posterB.svg);
  });
});
