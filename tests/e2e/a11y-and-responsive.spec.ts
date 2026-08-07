import { expect, test } from "@playwright/test";

/**
 * A-02 Epic 退出条件验证：键盘、200% 字体缩放、移动端与降级。
 * 覆盖 frontend-entrypoints.spec.ts 未涉及的 a11y 与响应式证据。
 * A-20 后工作台为退役宿主：键盘/缩放/窄屏断言指向新的固定边界。
 */

test("brand site keyboard navigation reaches the single CTA", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:4321/");

  // Tab from body: skip-link is not present on brand site (only workspace has it),
  // so first focusable should be the only CTA "进入工作台"
  await page.keyboard.press("Tab");

  const cta = page.getByRole("link", { name: "进入工作台" });
  await expect(cta).toBeFocused();
});

test("brand site focus outline is visible on CTAs", async ({ page }) => {
  await page.goto("http://127.0.0.1:4321/");
  const cta = page.getByRole("link", { name: "进入工作台" });
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

test("workspace skip link appears on focus and targets main content", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const skipLink = page.getByRole("link", { name: "跳到主要内容" });
  // Initially transformed off-screen
  await expect(skipLink).not.toBeInViewport();

  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();

  // Activate skip link
  await page.keyboard.press("Enter");
  const mainContent = page.locator("main#main-content");
  await expect(mainContent).toBeFocused();
});

test.describe("mobile viewport @ 375px", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("brand site hero and content fit without horizontal overflow", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:4321/");

    await expect(
      page.getByRole("heading", {
        name: /让每一颗系外行星候选体\s*都可溯源/,
      }),
    ).toBeVisible();

    // No horizontal scroll
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(375);
  });

  test("workspace shows the desktop-required notice without overflow", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:5173/workspace");

    await expect(
      page.getByRole("heading", { name: "研究工作台" }),
    ).toBeVisible();
    await expect(page.getByText("请使用桌面设备")).toBeVisible();
    await expect(
      page.getByText("研究工作台需要更宽的浏览器窗口。"),
    ).toBeVisible();

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
        name: /让每一颗系外行星候选体\s*都可溯源/,
      }),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "进入工作台" })).toBeVisible();
    await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();

    // No horizontal overflow caused by enlarged text
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });

  test("workspace host remains functional at 200% font size", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:5173/workspace");
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });

    await expect(
      page.getByRole("heading", { name: "研究工作台" }),
    ).toBeVisible();

    // No horizontal overflow
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });
});
