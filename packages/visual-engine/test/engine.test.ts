import { createPoster } from "../src/poster";
import { createVisualEngine } from "../src/engine";
import type { VisualEngineConfig } from "../src/types";

function createCanvas(width = 160, height = 100): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  document.body.appendChild(canvas);
  return canvas;
}

function createConfig(
  overrides: Partial<VisualEngineConfig> = {},
): VisualEngineConfig {
  return {
    seed: 42,
    quality: "medium",
    reducedMotion: false,
    canvas: createCanvas(),
    poster: createPoster({ seed: 42 }),
    ...overrides,
  };
}

describe("Visual Engine lifecycle", () => {
  it("starts and stops the rAF loop", () => {
    const engine = createVisualEngine(createConfig());
    expect(engine.isRunning()).toBe(false);

    engine.start();
    expect(engine.isRunning()).toBe(true);

    engine.pause();
    expect(engine.isRunning()).toBe(false);

    engine.resume();
    expect(engine.isRunning()).toBe(true);

    engine.dispose();
    expect(engine.isDisposed()).toBe(true);
    expect(engine.isRunning()).toBe(false);
  });

  it("does not start when already running", () => {
    const engine = createVisualEngine(createConfig());
    engine.start();
    engine.start(); // second call should be a no-op
    expect(engine.isRunning()).toBe(true);
    engine.dispose();
  });

  it("does not resume when reduced motion is enabled", () => {
    const engine = createVisualEngine(createConfig({ reducedMotion: true }));
    engine.start();
    expect(engine.isRunning()).toBe(false); // no rAF loop
    engine.resume();
    expect(engine.isRunning()).toBe(false);
    engine.dispose();
  });

  it("creates DOM anchor on start", () => {
    const canvas = createCanvas();
    const engine = createVisualEngine(
      createConfig({ canvas, domAnchorLabel: "测试视觉" }),
    );

    expect(engine.getDomAnchor()).toBeNull();

    engine.start();
    const anchor = engine.getDomAnchor();
    expect(anchor).not.toBeNull();
    expect(anchor?.getAttribute("role")).toBe("img");
    expect(anchor?.getAttribute("aria-label")).toBe("测试视觉");
    expect(canvas.parentNode?.contains(anchor)).toBe(true);

    engine.dispose();
  });

  it("removes DOM anchor on dispose", () => {
    const canvas = createCanvas();
    const engine = createVisualEngine(createConfig({ canvas }));

    engine.start();
    const anchor = engine.getDomAnchor();
    expect(anchor).not.toBeNull();

    engine.dispose();
    expect(engine.getDomAnchor()).toBeNull();
    expect(canvas.parentNode?.contains(anchor)).toBe(false);
  });

  it("removes event listeners on dispose (no active observers)", () => {
    const engine = createVisualEngine(createConfig());
    engine.start();
    engine.dispose();

    // After dispose, visibilitychange should not cause errors or side effects
    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    expect(engine.isDisposed()).toBe(true);
    expect(engine.isRunning()).toBe(false);
  });
});

describe("Visual Engine visibility handling", () => {
  it("pauses on visibilitychange (hidden)", () => {
    const engine = createVisualEngine(createConfig());
    engine.start();
    expect(engine.isRunning()).toBe(true);

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    expect(engine.isRunning()).toBe(false);
    engine.dispose();
  });

  it("resumes on visibilitychange (visible)", () => {
    const engine = createVisualEngine(createConfig());
    engine.start();

    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(engine.isRunning()).toBe(false);

    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    expect(engine.isRunning()).toBe(true);

    engine.dispose();
  });
});

describe("Visual Engine context loss", () => {
  it("triggers onContextLoss handler on webglcontextlost", () => {
    const canvas = createCanvas();
    const engine = createVisualEngine(createConfig({ canvas }));
    let contextLost = false;
    engine.onContextLoss(() => {
      contextLost = true;
    });

    engine.start();
    expect(engine.isRunning()).toBe(true);

    canvas.dispatchEvent(new Event("webglcontextlost"));

    expect(contextLost).toBe(true);
    expect(engine.isRunning()).toBe(false);
    engine.dispose();
  });
});

describe("Visual Engine quality switch", () => {
  it("setQuality switches renderer quality at runtime", () => {
    const engine = createVisualEngine(createConfig({ quality: "high" }));
    engine.start();

    // Should not throw and engine should still be running
    engine.setQuality("low");
    expect(engine.isRunning()).toBe(true);

    engine.setQuality("medium");
    expect(engine.isRunning()).toBe(true);

    engine.dispose();
  });

  it("setQuality is a no-op when quality is unchanged", () => {
    const engine = createVisualEngine(createConfig({ quality: "high" }));
    engine.start();
    engine.setQuality("high"); // same quality
    expect(engine.isRunning()).toBe(true);
    engine.dispose();
  });
});

describe("Visual Engine reduced motion", () => {
  it("renders single static frame without rAF loop", () => {
    const engine = createVisualEngine(createConfig({ reducedMotion: true }));
    engine.start();
    // Reduced motion: no continuous animation
    expect(engine.isRunning()).toBe(false);
    // But DOM anchor is still created
    expect(engine.getDomAnchor()).not.toBeNull();
    engine.dispose();
  });

  it("does not resume on visibilitychange when reduced motion", () => {
    const engine = createVisualEngine(createConfig({ reducedMotion: true }));
    engine.start();

    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    // Should still not be running (no rAF loop for reduced motion)
    expect(engine.isRunning()).toBe(false);
    engine.dispose();
  });
});
