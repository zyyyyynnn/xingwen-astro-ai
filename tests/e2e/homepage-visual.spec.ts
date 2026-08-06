import { mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

/**
 * A-17 Homepage Visual — real-browser acceptance for the MP4 hero.
 *
 * The homepage uses a single native `<video>` element for brand visual.
 * These tests verify the product contract:
 *  - The video element is present in static HTML (no-JS safe).
 *  - The video has the correct src, attributes (autoplay, muted, loop,
 *    playsinline) and is visible.
 *  - There is exactly one CTA ("进入工作台"); no "开始演示" button.
 *  - No WebGL canvas remains on the page.
 *  - prefers-reduced-motion pauses the video.
 *  - No pageerror, no unexpected console errors.
 *  - 1440×900 and 390×844 viewports have no horizontal scroll.
 */

const ARTIFACT_DIR = join(tmpdir(), "a17-homepage-visual");
mkdirSync(ARTIFACT_DIR, { recursive: true });

const SITE = "http://127.0.0.1:4321/";

function collectErrors(page: import("@playwright/test").Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error")
      errors.push(`console.error: ${message.text()}`);
  });
  return errors;
}

test.describe("A-17 homepage visual (MP4)", () => {
  test("desktop 1440×900: video element is present, visible and correctly attributed", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(SITE);

    const video = page.locator(".hero-video");
    await expect(video).toHaveCount(1);
    await expect(video).toBeVisible();
    await expect(video).toHaveAttribute("autoplay", "");
    await expect(video).toHaveAttribute("muted", "");
    await expect(video).toHaveAttribute("loop", "");
    await expect(video).toHaveAttribute("playsinline", "");
    await expect(video).toHaveAttribute("preload", "metadata");
    await expect(video).toHaveAttribute("aria-hidden", "true");

    const source = video.locator("source");
    await expect(source).toHaveAttribute("src", "/visual/homepage-ascii.mp4");
    await expect(source).toHaveAttribute("type", "video/mp4");

    // No WebGL canvas should remain.
    await expect(page.locator(".hero-canvas canvas")).toHaveCount(0);
    await expect(page.locator(".hero-poster")).toHaveCount(0);

    await page.screenshot({ path: join(ARTIFACT_DIR, "desktop-1440x900.png") });
    expect(errors).toEqual([]);
  });

  test("single CTA: only '进入工作台' exists, no '开始演示'", async ({
    page,
  }) => {
    await page.goto(SITE);

    await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "开始演示" })).toHaveCount(0);
  });

  test("headline is the two-line serif title", async ({ page }) => {
    await page.goto(SITE);
    await expect(
      page.getByRole("heading", {
        name: /让每一颗系外行星候选体/,
      }),
    ).toBeVisible();
    await expect(page.locator("#hero-title")).toContainText("都可溯源");
  });

  test("mobile 390×844: hero video visible, no horizontal scroll", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(SITE);

    await expect(page.locator(".hero-video")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /让每一颗系外行星候选体/ }),
    ).toBeVisible();

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(390);

    await page.screenshot({ path: join(ARTIFACT_DIR, "mobile-390x844.png") });
    expect(errors).toEqual([]);
  });

  test("no-JS: video element is in static HTML, headline and CTA visible", async ({
    browser,
  }) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(SITE);

    // The <video> element is server-rendered in the static HTML.
    const video = page.locator(".hero-video");
    await expect(video).toHaveCount(1);
    const source = video.locator("source");
    await expect(source).toHaveAttribute("src", "/visual/homepage-ascii.mp4");

    // Title, CTA and notes are still visible without JavaScript.
    await expect(
      page.getByRole("heading", { name: /让每一颗系外行星候选体/ }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
    await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();

    await context.close();
  });

  test("reduced motion: video is paused", async ({ browser }) => {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const errors = collectErrors(page);
    await page.goto(SITE);

    await page.locator(".hero-video").waitFor({ state: "attached" });
    // Wait for the inline script to evaluate and pause the video.
    await page.waitForFunction(
      () => {
        const v = document.querySelector<HTMLVideoElement>(".hero-video");
        return v !== null && v.paused;
      },
      { timeout: 5000 },
    );

    const paused = await page.evaluate(() => {
      const v = document.querySelector<HTMLVideoElement>(".hero-video");
      return v?.paused ?? false;
    });
    expect(paused).toBe(true);

    await page.screenshot({ path: join(ARTIFACT_DIR, "reduced-motion.png") });
    expect(errors).toEqual([]);
    await context.close();
  });

  test("1280×800: no horizontal overflow at standard laptop width", async ({
    page,
  }) => {
    const errors = collectErrors(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(SITE);

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);

    await page.screenshot({ path: join(ARTIFACT_DIR, "laptop-1280x800.png") });
    expect(errors).toEqual([]);
  });
});
