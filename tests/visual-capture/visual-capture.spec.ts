import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const SHOT_DIR = resolve("E:/xingwen-visual-acceptance/shots");
mkdirSync(SHOT_DIR, { recursive: true });

const PROJECT = "/workspace/proj_01JEXAMPLE";

async function settle(page: Page, ms = 800): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(ms);
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${SHOT_DIR}/${name}.png` });
  // eslint-disable-next-line no-console
  console.log(`[shot] ${name}.png`);
}

async function openProject(page: Page, wait = 1200): Promise<void> {
  await page.goto(PROJECT);
  await expect(page.getByTestId("root-layout")).toBeVisible();
  await settle(page, wait);
}

test.describe("workspace shell & navigation", () => {
  test("index entry, sidebar states, command menu, model provider", async ({
    page,
  }) => {
    await page.goto("/workspace");
    await expect(page.getByTestId("root-layout")).toBeVisible();
    await settle(page, 1000);
    await shot(page, "01_workspace-index");

    await page.getByRole("button", { name: "收起侧栏" }).click();
    await settle(page, 500);
    await shot(page, "02_sidebar-collapsed");
    await page.getByRole("button", { name: "展开侧栏" }).click();
    await settle(page, 500);

    await page.getByTestId("command-menu-trigger").click();
    await settle(page, 400);
    await shot(page, "03_command-menu");
    await page.keyboard.press("Escape");
    await settle(page, 300);

    await page.getByRole("button", { name: "配置模型服务" }).click();
    await expect(page.getByRole("dialog", { name: "模型服务" })).toBeVisible();
    await settle(page, 400);
    await shot(page, "04_model-provider-dialog");
    await page.keyboard.press("Escape");
    await settle(page, 300);
  });
});

test.describe("project workspace", () => {
  test("overview, inspector tabs, protocol dialog", async ({ page }) => {
    await openProject(page);
    await shot(page, "10_project-overview");

    const resultsTab = page.getByRole("tab", { name: "研究结果" });
    if (await resultsTab.isVisible().catch(() => false)) {
      await resultsTab.click();
      await settle(page, 700);
      await shot(page, "12_inspector-results");
      await page.getByRole("tab", { name: "研究概览" }).click();
      await settle(page, 500);
    }

    const protocolButton = page.getByRole("button", { name: /研究协议/ }).first();
    if (await protocolButton.isVisible().catch(() => false)) {
      await protocolButton.click();
      await settle(page, 600);
      await shot(page, "13_protocol-review-dialog");
      await page.keyboard.press("Escape");
      await settle(page, 300);
    }
  });

  test("message stream scroll positions", async ({ page }) => {
    await openProject(page);
    const stream = page.getByTestId("agent-message-stream");
    if (await stream.isVisible().catch(() => false)) {
      await stream.evaluate((el) => {
        let scroller: HTMLElement | null = el;
        while (scroller && scroller !== document.body) {
          const overflow = window.getComputedStyle(scroller).overflowY;
          if (overflow === "auto" || overflow === "scroll") {
            scroller.scrollTop = 0;
            break;
          }
          scroller = scroller.parentElement;
        }
      });
      await settle(page, 400);
      await shot(page, "11_message-stream-top");
      await stream.evaluate((el) => {
        let scroller: HTMLElement | null = el;
        while (scroller && scroller !== document.body) {
          const overflow = window.getComputedStyle(scroller).overflowY;
          if (overflow === "auto" || overflow === "scroll") {
            scroller.scrollTop = Math.floor(scroller.scrollHeight / 2);
            break;
          }
          scroller = scroller.parentElement;
        }
      });
      await settle(page, 400);
      await shot(page, "11b_message-stream-mid");
      await stream.evaluate((el) => {
        let scroller: HTMLElement | null = el;
        while (scroller && scroller !== document.body) {
          const overflow = window.getComputedStyle(scroller).overflowY;
          if (overflow === "auto" || overflow === "scroll") {
            scroller.scrollTop = scroller.scrollHeight;
            break;
          }
          scroller = scroller.parentElement;
        }
      });
      await settle(page, 400);
      await shot(page, "11c_message-stream-bottom");
    }
  });
});

const ARTIFACTS: ReadonlyArray<readonly [string, string]> = [
  ["20_artifact-dataset", "artv_dataset_01"],
  ["21_artifact-field-dictionary", "artv_fdict_01"],
  ["22_artifact-source-collection", "artv_srccol_01"],
  [
    "23_artifact-paper-collection",
    "11111111-1111-4111-8111-111111111111",
  ],
  ["24_artifact-paper-summary", "artv_papsum_01"],
  ["25_artifact-literature-claims", "artv_claims_01"],
  ["26_artifact-literature-relations", "artv_rels_01"],
  ["27_artifact-graph", "artv_graph_01"],
];

test.describe("fullscreen artifact workspaces", () => {
  for (const [name, versionId] of ARTIFACTS) {
    test(name, async ({ page }) => {
      await page.goto(`${PROJECT}?artifactVersionId=${versionId}`);
      await expect(page.getByTestId("root-layout")).toBeVisible();
      await page
        .getByTestId("artifact-fullscreen-workspace")
        .waitFor({ state: "visible", timeout: 30_000 })
        .catch(() => undefined);
      await settle(page, name.includes("graph") ? 2500 : 1500);
      await shot(page, name);
    });
  }
});

test.describe("share flow", () => {
  test("share dialog and public share page", async ({ page }) => {
    await page.goto(`${PROJECT}?artifactVersionId=artv_dataset_01`);
    await page
      .getByTestId("artifact-fullscreen-workspace")
      .waitFor({ state: "visible", timeout: 30_000 })
      .catch(() => undefined);
    await settle(page, 1000);

    const shareButton = page
      .getByRole("button", { name: "分享", exact: true })
      .first();
    if (!(await shareButton.isVisible().catch(() => false))) return;
    await shareButton.click();
    const dialog = page.getByRole("dialog", { name: "分享研究结果" });
    await expect(dialog).toBeVisible();
    await settle(page, 400);
    await shot(page, "40_share-dialog");

    await page.getByRole("button", { name: "创建链接" }).click();
    const shareLink = page.getByLabel("分享链接");
    await expect(shareLink).toHaveValue(/\/share\/[^/]+$/);
    await settle(page, 400);
    await shot(page, "41_share-dialog-with-link");

    const shareUrl = await shareLink.inputValue();
    const shareToken = new URL(shareUrl).pathname.split("/").filter(Boolean).pop();
    await page.goto(`/share/${shareToken}`);
    await settle(page, 1500);
    await shot(page, "42_share-public-page");
  });
});

test.describe("responsive viewports", () => {
  test("1280 and 1024 widths", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await openProject(page, 1000);
    await shot(page, "30_viewport-1280x800");

    await page.setViewportSize({ width: 1024, height: 768 });
    await settle(page, 600);
    await shot(page, "31_viewport-1024x768");

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/workspace");
    await settle(page, 800);
    await shot(page, "32_index-1440x900");
  });
});
