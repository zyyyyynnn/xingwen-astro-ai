import { test, expect } from "@playwright/test";
import path from "path";
import os from "os";

const outDir = path.join(os.tmpdir(), "xingwen-a17-research-canvas", "gate1-review");

test("take screenshots", async ({ browser }) => {
  const url = "http://127.0.0.1:5174/__a17-research-canvas-preview";

  async function setupEvidenceLens(page: any) {
    await page.goto(url);
    await page.locator("text=星文智析").first().waitFor({ state: "attached" });
    await page.getByText("查看来源").first().evaluate((node: HTMLElement) => node.click());
    await page.locator("text=当前结论").first().waitFor({ state: "attached" });
  }

  // 1440x900 Completed Mission
  let page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url);
  await page.waitForSelector("text=星文智析");
  await page.screenshot({ path: path.join(outDir, "1440x900-completed-mission.png") });
  await page.close();

  // 1440x900 Artifact Review
  page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url);
  await page.waitForSelector("text=星文智析");
  await page.getByText("查看产物 →").first().click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, "1440x900-artifact-review.png") });
  await page.close();

  // 1440x900 Evidence Lens / Source Peek
  page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await setupEvidenceLens(page);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, "1440x900-evidence-lens.png") });
  await page.close();

  // 1280x800 Completed Mission
  page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto(url);
  await page.waitForSelector("text=星文智析");
  await page.screenshot({ path: path.join(outDir, "1280x800-completed-mission.png") });
  await page.close();

  // 390x844 Completed Mission
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await page.goto(url);
  await page.waitForSelector("text=星文智析");
  await page.screenshot({ path: path.join(outDir, "390x844-completed-mission.png") });
  await page.close();

  // 390x844 Evidence Sheet
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await setupEvidenceLens(page);
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(outDir, "390x844-evidence-sheet.png") });
  await page.close();

  // 200% font Completed Mission
  page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url);
  await page.evaluate(() => { document.body.style.zoom = '2'; });
  await page.waitForSelector("text=星文智析");
  await page.screenshot({ path: path.join(outDir, "200percent-font-completed-mission.png") });
  await page.close();
});
