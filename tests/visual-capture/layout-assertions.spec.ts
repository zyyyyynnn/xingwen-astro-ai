import { expect, test, type Page } from "@playwright/test";

/**
 * Post-repair layout assertions that complement the screenshot pack:
 * verifies the structural facts behind the visual acceptance items
 * (no default card chrome on thread results, single-line table headers,
 * and 1024 sidebar auto-collapse).
 */

const PROJECT_A = "/workspace/proj_01JEXAMPLE";
const PROJECT_B = "/workspace/proj_toi_transit";
const PROJECT_C = "/workspace/proj_l9859_spectroscopy";

async function settle(page: Page, ms = 800): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(ms);
}

test.describe("thread result rows left the card wall", () => {
  for (const [name, project] of [
    ["project A", PROJECT_A],
    ["project B", PROJECT_B],
    ["project C", PROJECT_C],
  ] as const) {
    test(`${name}: result previews carry no card chrome`, async ({ page }) => {
      await page.goto(project);
      await expect(page.getByTestId("root-layout")).toBeVisible();
      await settle(page);
      const previews = page.getByTestId(/artifact-result-/);
      const count = await previews.count();
      expect(count).toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        const chrome = await previews.nth(i).evaluate((element) => {
          const style = window.getComputedStyle(element);
          const parent = element.parentElement
            ? window.getComputedStyle(element.parentElement)
            : null;
          return {
            borderRadius: Number.parseFloat(style.borderRadius),
            boxShadow: style.boxShadow,
            background: style.backgroundColor,
            parentBackground: parent?.backgroundColor ?? "",
          };
        });
        expect(chrome.borderRadius).toBeLessThanOrEqual(1);
        expect(chrome.boxShadow).toBe("none");
        expect(
          chrome.background === "rgba(0, 0, 0, 0)" ||
            chrome.background === chrome.parentBackground,
        ).toBe(true);
      }
    });
  }
});

test.describe("dataset table headers stay single-line", () => {
  test("chinese headers render horizontally with column min widths", async ({
    page,
  }) => {
    await page.goto(`${PROJECT_A}?artifactVersionId=artv_dataset_01`);
    await expect(
      page.getByTestId("artifact-fullscreen-workspace"),
    ).toBeVisible();
    await settle(page, 1200);
    const headers = page.locator(
      "[data-testid='artifact-fullscreen-workspace'] thead th",
    );
    const headerCount = await headers.count();
    expect(headerCount).toBeGreaterThan(4);
    for (let i = 0; i < headerCount; i++) {
      const box = await headers.nth(i).boundingBox();
      if (box) {
        // A vertically-compressed CJK header cell would be far taller than wide.
        expect(
          box.height,
          `header ${i} looks vertically wrapped (h=${box.height}, w=${box.width})`,
        ).toBeLessThan(box.width * 1.5);
      }
    }
    const table = page.locator(
      "[data-testid='artifact-fullscreen-workspace'] table",
    );
    const overflow = await table.evaluate((element) => {
      const scroller = element.closest(".scientific-table");
      return scroller ? scroller.scrollWidth > scroller.clientWidth : false;
    });
    expect(overflow).toBe(true);
    for (let i = 0; i < headerCount; i++) {
      expect(
        await headers
          .nth(i)
          .evaluate((element) => window.getComputedStyle(element).whiteSpace),
      ).toBe("nowrap");
    }
  });
});

test.describe("1024 viewport shell", () => {
  test("sidebar collapses to icon rail and main thread stays readable", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(PROJECT_A);
    await expect(page.getByTestId("root-layout")).toBeVisible();
    await settle(page, 1000);
    const sidebar = page.getByLabel("工作台侧栏");
    const width = (await sidebar.boundingBox())?.width ?? 0;
    expect(width).toBeLessThanOrEqual(3.5 * 16 + 2);
    const main = page.getByTestId("workspace-main-column");
    const mainBox = await main.boundingBox();
    expect(mainBox?.width ?? 0).toBeGreaterThan(480);
  });

  test("1440 keeps expanded sidebar", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(PROJECT_A);
    await expect(page.getByTestId("root-layout")).toBeVisible();
    await settle(page, 1000);
    const sidebar = page.getByLabel("工作台侧栏");
    const width = (await sidebar.boundingBox())?.width ?? 0;
    expect(width).toBeGreaterThanOrEqual(14 * 16);
  });
});
