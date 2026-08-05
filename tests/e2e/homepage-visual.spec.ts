import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

/**
 * A-17 Homepage Visual — real-browser acceptance for the rebuilt hero.
 *
 * Covers the regressions that unit tests cannot prove:
 *  - Poster is visible first, then hidden only after the WebGL first frame.
 *  - The WebGL canvas is never pure black; the paper background and a
 *    meaningful glyph population are present at the full-open phase.
 *  - The 5.6s fold loop actually moves (full-open density ≫ near-empty).
 *  - No `pageerror`, no unexpected console errors, no duplicate Three.js.
 *  - Degradation paths: no-JS, WebGL2 unavailable, context loss, and
 *    reduced motion all keep a visible, non-black Poster/static frame.
 *
 * Pixel checks read the WebGL drawing buffer directly. To make
 * `readPixels` reliable in the headless browser, an init script forces
 * `preserveDrawingBuffer: true` for the test context only — the
 * production renderer never sets that flag.
 */

const ARTIFACT_DIR = join(tmpdir(), "a17-homepage-visual");
mkdirSync(ARTIFACT_DIR, { recursive: true });

const SITE = "http://127.0.0.1:4321/";

interface FrameStats {
  width: number;
  height: number;
  paperRatio: number;
  glyphRatio: number;
  blackRatio: number;
}

/** Force preserveDrawingBuffer so readPixels is reliable in tests. */
async function forcePreservedDrawingBuffer(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (...args) {
      const kind = String(args[0] ?? "");
      if (kind.startsWith("webgl")) {
        const opts =
          typeof args[1] === "object" && args[1] !== null ? { ...args[1] } : {};
        opts.preserveDrawingBuffer = true;
        args[1] = opts;
      }
      return original.apply(this, args);
    };
  });
}

function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error")
      errors.push(`console.error: ${message.text()}`);
    if (
      message.type() === "warning" &&
      /multiple instances/iu.test(message.text())
    ) {
      errors.push(`console.warn: ${message.text()}`);
    }
  });
  return errors;
}

async function readFrameStats(page: Page): Promise<FrameStats> {
  return page.evaluate(() => {
    const canvas = document.querySelector<HTMLCanvasElement>(
      ".hero-canvas canvas",
    );
    if (!canvas) throw new Error("canvas missing");
    const gl = canvas.getContext("webgl2");
    if (!gl) throw new Error("webgl2 context missing");
    const w = canvas.width;
    const h = canvas.height;
    const px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let paper = 0;
    let glyph = 0;
    let black = 0;
    for (let i = 0; i < px.length; i += 4) {
      const r = px[i] ?? 0;
      const g = px[i + 1] ?? 0;
      const b = px[i + 2] ?? 0;
      const min = Math.min(r, g, b);
      if (r < 12 && g < 12 && b < 12) black++;
      if (r >= 230 && g >= 230 && b >= 230) paper++;
      else if (min < 205) glyph++;
    }
    const total = w * h;
    return {
      width: w,
      height: h,
      paperRatio: paper / total,
      glyphRatio: glyph / total,
      blackRatio: black / total,
    };
  });
}

async function waitForReady(page: Page, timeoutMs = 15_000): Promise<void> {
  await page.goto(SITE);
  await page.waitForSelector(".hero-canvas canvas", { timeout: timeoutMs });
  // Poster is hidden only after the first valid WebGL frame ("ready").
  await page.waitForFunction(
    () =>
      document.querySelector(".hero-poster")?.hasAttribute("hidden") === true,
    { timeout: timeoutMs },
  );
}

test.describe("A-17 homepage visual", () => {
  test.describe.configure({ mode: "serial" });

  test("desktop 1440×900: WebGL first frame hides Poster, canvas is not black", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await forcePreservedDrawingBuffer(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SITE);

    // Poster is present and visible before WebGL is ready.
    const poster = page.locator(".hero-poster");
    await expect(poster).toBeVisible();

    await waitForReady(page);
    await expect(poster).not.toBeVisible();

    const stats = await readFrameStats(page);
    expect(stats.blackRatio).toBeLessThan(0.02);
    expect(stats.paperRatio).toBeGreaterThan(0.3);
    expect(stats.glyphRatio).toBeGreaterThan(0.05);

    await page.screenshot({ path: join(ARTIFACT_DIR, "desktop-1440x900.png") });
    expect(errors).toEqual([]);
  });

  test("motion loop: full-open frame is dense, near-empty frame is sparse, no black", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await forcePreservedDrawingBuffer(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await waitForReady(page);

    // Sample a full 5.6s+ loop and capture representative frames.
    const frames: { t: number; stats: FrameStats }[] = [];
    const started = Date.now();
    for (let i = 0; i <= 30; i++) {
      const stats = await readFrameStats(page);
      frames.push({ t: Date.now() - started, stats });
      if (i === 30) break;
      await page.waitForTimeout(200);
    }

    const ratios = frames.map((f) => f.stats.glyphRatio);
    const maxIndex = ratios.indexOf(Math.max(...ratios));
    const minIndex = ratios.indexOf(Math.min(...ratios));
    const fullOpen = frames[maxIndex]?.stats;
    const nearEmpty = frames[minIndex]?.stats;
    if (!fullOpen || !nearEmpty) throw new Error("frame capture failed");

    // Full-open phase must fill the visual area with glyphs.
    expect(fullOpen.glyphRatio).toBeGreaterThan(0.06);
    expect(fullOpen.blackRatio).toBeLessThan(0.02);
    // Motion must occur: density swings across the loop.
    expect(fullOpen.glyphRatio - nearEmpty.glyphRatio).toBeGreaterThan(0.025);
    // Near-empty may be sparse but never all-black.
    expect(nearEmpty.blackRatio).toBeLessThan(0.05);
    expect(nearEmpty.paperRatio).toBeGreaterThan(0.4);

    // Capture representative frames as evidence.
    await page.screenshot({ path: join(ARTIFACT_DIR, "motion-full-open.png") });
    expect(errors).toEqual([]);
  });

  test("mobile 390×844: hero is visible and not black", async ({ page }) => {
    const errors = collectErrors(page);
    await forcePreservedDrawingBuffer(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(SITE);
    await page.waitForSelector(".hero-canvas canvas", { timeout: 15_000 });
    await page.waitForFunction(
      () =>
        document.querySelector(".hero-poster")?.hasAttribute("hidden") === true,
      { timeout: 15_000 },
    );

    const stats = await readFrameStats(page);
    expect(stats.blackRatio).toBeLessThan(0.05);
    expect(stats.glyphRatio).toBeGreaterThan(0.03);

    await page.screenshot({ path: join(ARTIFACT_DIR, "mobile-390x844.png") });
    expect(errors).toEqual([]);
  });

  test("no-JS: Poster is shown, no canvas is mounted", async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(SITE);
    await expect(page.locator(".hero-poster")).toBeVisible();
    await expect(page.locator(".hero-canvas canvas")).toHaveCount(0);
    await context.close();
  });

  test("WebGL2 unavailable: Poster stays, no canvas", async ({ page }) => {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (...args) {
        if (String(args[0] ?? "").startsWith("webgl")) return null;
        return original.apply(this, args);
      };
    });
    await page.goto(SITE);
    await expect(page.locator(".hero-poster")).toBeVisible();
    await expect(page.locator(".hero-canvas canvas")).toHaveCount(0);
  });

  test("context loss reveals Poster; restore remounts a visible canvas", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await forcePreservedDrawingBuffer(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await waitForReady(page);

    const canvas = page.locator(".hero-canvas canvas");
    await canvas.evaluate((el) =>
      el.dispatchEvent(new Event("webglcontextlost", { cancelable: true })),
    );
    await expect(page.locator(".hero-poster")).toBeVisible();

    await canvas.evaluate((el) =>
      el.dispatchEvent(new Event("webglcontextrestored")),
    );
    // Restore remounts the Canvas (key bump) and re-runs readiness.
    await page.waitForFunction(
      () =>
        document.querySelector(".hero-poster")?.hasAttribute("hidden") === true,
      { timeout: 15_000 },
    );
    const stats = await readFrameStats(page);
    expect(stats.blackRatio).toBeLessThan(0.05);
    expect(errors).toEqual([]);
  });

  test("reduced motion: static frame, no continuous animation, not black", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = collectErrors(page);
    await forcePreservedDrawingBuffer(page);
    await page.goto(SITE);
    await page.waitForSelector(".hero-canvas canvas", { timeout: 15_000 });
    await page.waitForFunction(
      () =>
        document.querySelector(".hero-poster")?.hasAttribute("hidden") === true,
      { timeout: 15_000 },
    );

    const first = await readFrameStats(page);
    await page.waitForTimeout(800);
    const second = await readFrameStats(page);
    // Same static phase across two samples (no continuous animation).
    expect(Math.abs(first.glyphRatio - second.glyphRatio)).toBeLessThan(0.005);
    expect(first.blackRatio).toBeLessThan(0.05);
    expect(first.glyphRatio).toBeGreaterThan(0.03);

    await page.screenshot({ path: join(ARTIFACT_DIR, "reduced-motion.png") });
    expect(errors).toEqual([]);
    await context.close();
  });
});
