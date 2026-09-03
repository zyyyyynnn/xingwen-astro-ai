import { expect, test } from "@playwright/test";

/**
 * Homepage video playback, resilience and reduced-motion preferences.
 */

const HERO_TITLE = /让每一颗系外行星候选体\s*都可溯源/;

test("homepage starts decorative video playback without media controls", async ({
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
  await expect(video).not.toHaveAttribute("autoplay", "");
  await expect
    .poll(() => video.evaluate((element: HTMLVideoElement) => element.paused))
    .toBe(false);
  await expect(video).toHaveAttribute("muted", "");
  await expect(video).toHaveAttribute("loop", "");
  await expect(video).toHaveAttribute("playsinline", "");
  await expect(video).toHaveAttribute("preload", "metadata");
  await expect(video).toHaveAttribute("disablepictureinpicture", "");
  await expect(video).toHaveAttribute("disableremoteplayback", "");
  await expect(video).toHaveAttribute(
    "controlslist",
    "nodownload nofullscreen noremoteplayback noplaybackrate",
  );
  await expect(video).toHaveAttribute("tabindex", "-1");
  await expect(video).toHaveAttribute("aria-hidden", "true");
  await expect(video).not.toHaveAttribute("controls", "");
  expect(
    await video.evaluate((element: HTMLVideoElement) => ({
      controls: element.controls,
      disablePictureInPicture: element.disablePictureInPicture,
      disableRemotePlayback: element.disableRemotePlayback,
      tabIndex: element.tabIndex,
    })),
  ).toEqual({
    controls: false,
    disablePictureInPicture: true,
    disableRemotePlayback: true,
    tabIndex: -1,
  });
  await expect(page.getByRole("button")).toHaveCount(0);
  await expect(
    page.locator("astro-dev-toolbar, vite-error-overlay"),
  ).toHaveCount(0);
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

test("homepage retains a static hero frame under reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });

  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect(video).toBeVisible();
  await expect
    .poll(() =>
      video.evaluate((element: HTMLVideoElement) => element.readyState),
    )
    .toBeGreaterThanOrEqual(2);
  expect(
    await video.evaluate((element: HTMLVideoElement) => ({
      paused: element.paused,
      currentTime: element.currentTime,
    })),
  ).toEqual({ paused: true, currentTime: 0 });

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

test("homepage responds when reduced-motion preference changes", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("http://127.0.0.1:14321/");

  const video = page.locator("video.hero-video");
  await expect
    .poll(() => video.evaluate((element: HTMLVideoElement) => element.paused))
    .toBe(false);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(video).toBeVisible();
  await expect
    .poll(() => video.evaluate((element: HTMLVideoElement) => element.paused))
    .toBe(true);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await expect
    .poll(() => video.evaluate((element: HTMLVideoElement) => element.paused))
    .toBe(false);
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
