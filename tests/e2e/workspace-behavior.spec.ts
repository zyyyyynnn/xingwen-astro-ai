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

async function openPaperReview(page: Page) {
  await page.goto("http://127.0.0.1:5173/workspace");
  await expect(page.getByRole("heading", { name: "科研工作区" })).toBeVisible();
  await page.getByRole("button", { name: "Retrieved papers" }).click();
  await expect(
    page.getByRole("heading", { name: "论文获取与候选审查" }),
  ).toBeVisible();
  await expect(page.locator(".candidate-item")).toHaveCount(7);
}

test("Fixture paper acquisition review: labels, filtering, candidate and Evidence flow", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await openPaperReview(page);

  // Execution and source modes are displayed separately, never merged.
  await expect(page.getByText("execution: Demo Replay")).toBeVisible();
  await expect(
    page.getByText("source: Fixture", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/确定性演示数据（Fixture/u)).toBeVisible();
  // Real frozen benchmark identity from the pipeline-generated fixture.
  await expect(
    page.getByText(/benchmark: exoplanet_host_star\.paper_reasoning v1\.3\.0/u),
  ).toBeVisible();

  // Filtering hides rows but never renumbers the server ranking.
  await page.getByLabel("入选状态").selectOption("excluded");
  await expect(page.getByText(/显示 4 \/ 7 项/u)).toBeVisible();
  await expect(page.locator(".candidate-rank")).toHaveText([
    "#2",
    "#5",
    "#6",
    "#7",
  ]);
  await page.getByRole("button", { name: "重置筛选" }).click();
  await expect(page.getByText(/显示 7 \/ 7 项/u)).toBeVisible();

  // Keyboard flow: select the top-ranked candidate, then open its Evidence.
  await page
    .getByRole("button", {
      name: "TESS Objects of Interest Catalog from the TESS Prime Mission",
      exact: true,
    })
    .focus();
  await page.keyboard.press("Enter");
  // The Provenance Observatory reflects the selected candidate's snapshot.
  await expect(
    page
      .locator(".provenance-observatory")
      .getByText("snap_paper_crossref_01 / crossref"),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "打开 Evidence evd_paper_01" })
    .focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  // Pinning candidate evidence turns the workspace into an unsaved draft.
  await expect(page.getByText("未保存本地草稿（revision 0）")).toBeVisible();

  // The non-http raw record URL is rendered as plain text, never a link.
  await expect(
    page.getByText(/ftp:\/\/mirror\.example\.org\/flares\.pdf/u),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

for (const width of [1440, 1280]) {
  test.describe(`Paper review at ${String(width)}px`, () => {
    test.use({ viewport: { width, height: 900 } });

    test("renders without horizontal overflow", async ({ page }) => {
      await openPaperReview(page);
      await expect(page.getByLabel("检索详情")).toBeVisible();
      await expectNoHorizontalOverflow(page, width);
    });
  });
}

test.describe("Paper review at 390px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("stays usable on a narrow viewport", async ({ page }) => {
    await openPaperReview(page);
    await expect(page.getByLabel("标题或作者")).toBeVisible();
    await expectNoHorizontalOverflow(page, 390);
  });
});

test.describe("Paper review at 200% font scale", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("keeps the review readable without horizontal overflow", async ({
    page,
  }) => {
    await openPaperReview(page);
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });
    await expect(
      page.getByRole("heading", { name: "论文获取与候选审查" }),
    ).toBeVisible();
    await expectNoHorizontalOverflow(page, 1280);
  });
});

async function openPaperSummary(page: Page) {
  await page.goto("http://127.0.0.1:5173/workspace");
  await expect(page.getByRole("heading", { name: "科研工作区" })).toBeVisible();
  await page.getByRole("button", { name: "Paper summary" }).click();
  await expect(
    page.getByRole("heading", { name: "文献总结阅读" }),
  ).toBeVisible();
}

test("Fixture literature summary: five regions, status badges and statement Evidence flow", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await openPaperSummary(page);

  // The five reading regions render as headings in fixed order.
  for (const title of [
    "研究目标",
    "研究方法",
    "使用数据集",
    "核心发现",
    "局限与未来工作",
  ]) {
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
  }

  // Support statuses are visible and never merged into unmarked facts.
  await expect(page.getByText("有证据支持").first()).toBeVisible();
  await expect(page.getByText("无证据（未证实）").first()).toBeVisible();
  await expect(page.getByText("证据不可核验").first()).toBeVisible();

  // Keyboard flow: focus a supported statement and press Enter — its generic
  // Evidence opens in the Provenance Observatory.
  await page
    .getByRole("button", {
      name: "The paper delivers The Revised TESS Input Catalog and Candidate Target List to prioritize TESS targets.",
    })
    .focus();
  await page.keyboard.press("Enter");
  await expect(
    page
      .locator(".provenance-observatory")
      .getByRole("button", { name: "evd_papsum_03" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evidence" })).toBeVisible();
  expect(errors).toEqual([]);
});
