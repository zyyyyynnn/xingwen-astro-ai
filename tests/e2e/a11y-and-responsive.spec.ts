import { expect, test } from "@playwright/test";

/**
 * A-02 Epic 退出条件验证：键盘、200% 字体缩放、移动端与降级。
 * 覆盖 frontend-entrypoints.spec.ts 未涉及的 a11y 与响应式证据。
 */

test("brand site keyboard navigation reaches CTAs in sequence", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:4321/");

  // Tab from body: skip-link is not present on brand site (only workspace has it),
  // so first focusable should be the first CTA "开始演示"
  await page.keyboard.press("Tab");

  const primaryCta = page.getByRole("link", { name: "开始演示" });
  await expect(primaryCta).toBeFocused();

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "进入工作台" })).toBeFocused();
});

test("brand site focus outline is visible on CTAs", async ({ page }) => {
  await page.goto("http://127.0.0.1:4321/");
  const cta = page.getByRole("link", { name: "开始演示" });
  await cta.focus();
  // focus-visible outline must be non-empty
  const outlineStyle = await cta.evaluate(
    (el) => window.getComputedStyle(el).outlineStyle,
  );
  const outlineWidth = await cta.evaluate(
    (el) => window.getComputedStyle(el).outlineWidth,
  );
  expect(outlineStyle).not.toBe("none");
  expect(parseFloat(outlineWidth)).toBeGreaterThan(0);
});

test("workspace skip link appears on focus and targets research canvas", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const skipLink = page.getByRole("link", { name: "跳到研究画布" });
  // Initially transformed off-screen
  await expect(skipLink).not.toBeInViewport();

  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();

  // Activate skip link
  await page.keyboard.press("Enter");
  const canvas = page.locator("#research-canvas");
  await expect(canvas).toBeFocused();
});

test("workspace keyboard tab sequence: rail nav links are reachable", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/");

  // Tab past skip link to first nav link
  await page.keyboard.press("Tab"); // skip-link
  await page.keyboard.press("Tab"); // first nav link

  // Should be on one of the nav links
  const focusedText = await page.evaluate(
    () => document.activeElement?.textContent ?? "",
  );
  expect(["入口", "引导", "工作区"]).toContain(focusedText.trim());
});

test.describe("mobile viewport @ 375px", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("brand site hero and content fit without horizontal overflow", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:4321/");

    await expect(
      page.getByRole("heading", {
        name: "让每一颗系外行星候选体都可溯源",
      }),
    ).toBeVisible();

    // No horizontal scroll
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });

  test("workspace collapses panels and stays usable", async ({ page }) => {
    await page.goto("http://127.0.0.1:5173/workspace");

    await expect(
      page.getByRole("heading", { name: "科研工作区" }),
    ).toBeVisible();

    // Side panels hidden on mobile (≤60rem), main canvas visible
    await expect(page.locator("#research-canvas")).toBeVisible();

    // No horizontal scroll
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });
});

test.describe("200% font scale", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("brand site content remains visible and readable at 200% font size", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:4321/");
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });

    await expect(
      page.getByRole("heading", {
        name: "让每一颗系外行星候选体都可溯源",
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "开始演示" })).toBeVisible();
    await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();

    // No horizontal overflow caused by enlarged text
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });

  test("workspace shell remains functional at 200% font size", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:5173/workspace");
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });

    await expect(
      page.getByRole("heading", { name: "科研工作区" }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "主要导航" }),
    ).toBeVisible();

    // No horizontal overflow
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });
});
