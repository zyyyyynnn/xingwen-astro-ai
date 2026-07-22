import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

async function expectNoHorizontalOverflow(page: Page, width: number) {
  const scrollWidth = await page.evaluate(
    () => document.documentElement.scrollWidth,
  );
  expect(scrollWidth).toBeLessThanOrEqual(width);
}

test("Fixture Guided Tour supports keyboard FSM and Demo Replay Run actions", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/tour");

  await expect(page.getByRole("heading", { name: "研究引导" })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "已确认 Contract" }),
  ).toBeVisible();
  await expect(page.getByRole("radio", { name: "Live" })).toBeDisabled();

  const draftIntent = page.getByLabel("研究意图");
  await draftIntent.fill("Keyboard-confirmed exoplanet research intent");
  await page.getByRole("button", { name: "确认 Contract" }).focus();
  await page.keyboard.press("Enter");
  await expect(draftIntent).toBeDisabled();

  await page.getByRole("button", { name: "开始引导" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("阶段：SIGNAL")).toBeVisible();

  await page.getByRole("button", { name: "暂停" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/已暂停/u)).toBeVisible();

  await page.getByRole("button", { name: "继续" }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "跳过本步" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("阶段：QUESTION")).toBeVisible();

  await page.getByRole("button", { name: "启动运行" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("demo_replay / queued / 0%")).toBeVisible();
  expect(errors).toEqual([]);
});

test("Fixture Workspace saves selection state and opens a frozen public Share", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/workspace");

  await expect(page.getByRole("heading", { name: "科研工作区" })).toBeVisible();
  await expect(page.getByText("Run queued for Demo Replay")).toBeVisible();
  await page.getByLabel("布局").selectOption("focus");
  await page.getByRole("button", { name: "保存工作区" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("已保存 revision 1")).toBeVisible();

  await page.getByRole("button", { name: "恢复运行事件" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Demo Replay run completed")).toBeVisible();

  await page
    .getByRole("button", { name: "Exoplanet host-star dataset" })
    .click();
  await expect(page.getByText("本地更改尚未保存")).toBeVisible();
  await page.getByRole("button", { name: "evd_01" }).click();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();

  await page.getByRole("button", { name: "创建只读分享" }).click();
  const shareLink = page.getByRole("link", { name: "打开只读分享" });
  await expect(shareLink).toBeVisible();
  const sharePath = await shareLink.getAttribute("href");
  expect(sharePath).toMatch(/^\/share\//u);
  const shareToken = sharePath?.split("/").at(-1);
  await shareLink.click();

  await expect(
    page.getByRole("heading", { name: "Exoplanet host-star dataset v1" }),
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "主要导航" })).toHaveCount(
    0,
  );
  await expect(page.getByRole("button", { name: "保存工作区" })).toHaveCount(0);
  if (shareToken) {
    await expect(page.locator("body")).not.toContainText(shareToken);
  }
  expect(errors).toEqual([]);
});

test.describe("Workspace at 375px", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("keeps both side regions available through native disclosure controls", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:5173/workspace");

    await expect(
      page.getByRole("heading", { name: "科研工作区" }),
    ).toBeVisible();
    const atlas = page.locator(".research-atlas .region-details");
    const observatory = page.locator(".provenance-observatory .region-details");
    await expect(atlas.locator("summary")).toBeVisible();
    await expect(observatory.locator("summary")).toBeVisible();
    await atlas.locator("summary").click();
    await expect(atlas).not.toHaveAttribute("open", "");
    await atlas.locator("summary").click();
    await expect(atlas).toHaveAttribute("open", "");
    await expect(
      page.getByRole("button", { name: "保存工作区" }),
    ).toBeVisible();
    await expectNoHorizontalOverflow(page, 375);
  });
});

test.describe("Workspace at 200% font scale", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("keeps primary Workspace actions visible", async ({ page }) => {
    await page.goto("http://127.0.0.1:5173/workspace");
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });

    await expect(
      page.getByRole("heading", { name: "科研工作区" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "保存工作区" }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "创建只读分享" }),
    ).toBeVisible();
    await expect(page.locator(".research-atlas summary")).toBeVisible();
    await expectNoHorizontalOverflow(page, 1280);
  });
});
