import { expect, test } from "@playwright/test";

/**
 * A-19 MP4 Brand Site homepage: video element, resilience, reduced motion.
 */

const HERO_TITLE = /让每一颗系外行星候选体\s*都可溯源/;

test("homepage renders the ASCII video element from the public visual dir", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect(video).toBeVisible();
  await expect(video.locator("source")).toHaveAttribute(
    "src",
    "/visual/homepage-ascii.mp4",
  );
  await expect(video.locator("source")).toHaveAttribute("type", "video/mp4");
  await expect(video).toHaveAttribute("autoplay", "");
  await expect(video).toHaveAttribute("muted", "");
  await expect(video).toHaveAttribute("loop", "");
  await expect(video).toHaveAttribute("playsinline", "");
});

test("homepage keeps title, notes and single CTA when video fails to load", async ({
  page,
}) => {
  await page.route("**/visual/homepage-ascii.mp4", (route) =>
    route.abort("failed"),
  );

  await page.goto("http://127.0.0.1:14321/");

  await expect(page.getByRole("heading", { name: HERO_TITLE })).toBeVisible();
  await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
  await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();
  await expect(page.getByText(/每个字段绑定可审查的证据/)).toBeVisible();
});

test("homepage honours reduced motion by hiding the video", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });

  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect(video).toBeHidden();

  await expect(page.getByRole("heading", { name: HERO_TITLE })).toBeVisible();
  await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
});

test("homepage exposes exactly one CTA pointing at the workspace", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:14321/");

  const cta = page.getByRole("link", { name: "进入工作台" });
  await expect(cta).toHaveCount(1);
  await expect(cta).toHaveAttribute("href", "http://localhost:5173/workspace");
  await expect(page.getByRole("link", { name: "开始演示" })).toHaveCount(0);
});

test("homepage title renders as two lines without client-side scripting", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  await page.goto("http://127.0.0.1:14321/");

  const titleHtml = await page
    .locator("#hero-title")
    .evaluate((el) => el.innerHTML);
  expect(titleHtml).toContain("<br>");

  await expect(page.getByRole("heading", { name: HERO_TITLE })).toBeVisible();

  await context.close();
});

test("homepage pauses the hero video under reduced motion via lifecycle", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });

  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect(video).toBeHidden();

  const state = await video.evaluate((el: HTMLVideoElement) => ({
    paused: el.paused,
    dataAttribute: el.hasAttribute("data-home-hero-video"),
  }));
  expect(state.paused).toBe(true);
  expect(state.dataAttribute).toBe(true);
});

test("homepage pauses the hero video while the tab is hidden and resumes on return", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect(video).toBeVisible();

  await expect
    .poll(() => video.evaluate((el: HTMLVideoElement) => el.paused))
    .toBe(false);

  const setVisibility = (state: string) =>
    video.evaluate((el, visibilityState) => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => visibilityState,
      });
      document.dispatchEvent(new Event("visibilitychange"));
      void el;
    }, state);

  await setVisibility("hidden");
  await expect
    .poll(() => video.evaluate((el: HTMLVideoElement) => el.paused))
    .toBe(true);

  await setVisibility("visible");
  await expect
    .poll(() => video.evaluate((el: HTMLVideoElement) => el.paused))
    .toBe(false);
});
