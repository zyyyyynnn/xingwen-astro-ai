import { test, expect } from "@playwright/test";

test.describe("Gate 1: Completed Mission Vertical Chain (Shadow UI)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/__a17-research-canvas-preview");
    // Wait for initial render
    await page.waitForSelector("text=A-17 CANVAS");
  });

  test("Completed Run defaults to Completion Summary and lacks technical IDs", async ({
    page,
  }) => {
    // 1. Completed Run 默认进入 Completion Summary
    await expect(page.getByText("The paper delivers The Revised TESS Input Catalog", { exact: false }).first()).toBeVisible();
    await expect(page.getByText("Final Artifact").first()).toBeVisible();

    // 2. 不存在主舞台视图手动选择器 (should not find any select/dropdown for view)
    const select = page.locator("select");
    await expect(select).toHaveCount(0);

    // 3. 默认界面不出现技术字段
    const bodyText = await page.textContent("body");
    expect(bodyText).not.toContain("fixture");
    expect(bodyText).not.toContain("adapter");
    expect(bodyText).not.toContain("demo_replay");
    expect(bodyText).not.toContain("execution mode");
    expect(bodyText).not.toContain("sha256");
  });

  test("Vertical chain: Summary -> Artifact -> Statement -> Evidence -> Source -> Back", async ({
    page,
  }) => {
    // 4. 点击 Final Artifact 进入 Artifact Review
    await page.getByText("Final Artifact").first().click();
    await expect(page.getByText("Paper Summary").first()).toBeVisible();
    await expect(
      page.getByText("The Revised TESS Input Catalog").first(),
    ).toBeVisible();

    // 11. 支持的 Artifact 不走 Hash fallback (It shows human readable content)
    await expect(page.getByText("Goal:")).toBeVisible();

    // 5. 点击 Statement 打开 Evidence Lens
    await page
      .getByText("The paper delivers The Revised TESS Input Catalog")
      .click();
    await expect(page.getByText("Evidence Lens")).toBeVisible();

    // 6. Evidence 展示来源摘录和位置
    await expect(page.getByText("Extracted Quote")).toBeVisible();

    // 7. Source Peek 可打开
    await page.getByText("View Full Source").click();
    await expect(page.getByText("Source Extract")).toBeVisible();

    // 8. Back 链正确
    await page.getByText("← Back to Artifact").click();
    await expect(page.getByText("Paper Summary")).toBeVisible();
  });

  test("Context Dock state", async ({ page }) => {
    // 9. Context Dock 由 selected object 驱动
    await expect(page.getByText("Context")).toBeVisible();
    await expect(page.getByText("Evidence Set")).toBeVisible();

    // Reproducibility incomplete
    await expect(page.getByText("Reproducibility Capsule")).toBeVisible();
    await expect(page.getByText("Incomplete")).toBeVisible();
  });

  test("Composer is unavailable for completed mission", async ({ page }) => {
    // 10. Composer
    const input = page.getByPlaceholder("Message Research Agent...");
    await expect(input).toBeDisabled();
    await expect(page.getByText("Agent is not available")).toBeVisible();
  });

  test("No page errors or console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    await page.goto("/__a17-research-canvas-preview");
    await page.waitForSelector("text=A-17 CANVAS");
    expect(errors).toHaveLength(0);
  });
});
