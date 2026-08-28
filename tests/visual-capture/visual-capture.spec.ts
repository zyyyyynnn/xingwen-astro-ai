import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

const SHOT_DIR =
  process.env.VISUAL_SHOT_DIR || resolve(".artifacts/visual-acceptance/shots");
mkdirSync(SHOT_DIR, { recursive: true });

const PROJECT_A = "/workspace/proj_01JEXAMPLE";
const PROJECT_B = "/workspace/proj_02JTRANSIT";
const PROJECT_C = "/workspace/proj_03JSPECTRO";

async function settle(page: Page, ms = 800): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(ms);
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${SHOT_DIR}/${name}.png` });
  // eslint-disable-next-line no-console
  console.log(`[shot] ${name}.png`);
}

async function openProject(page: Page, projectUrl = PROJECT_A, wait = 1200): Promise<void> {
  await page.goto(projectUrl);
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

    await page.getByRole("button", { name: /模型服务/ }).click();
    await expect(page.getByRole("dialog", { name: "模型服务" })).toBeVisible();
    await settle(page, 400);
    await shot(page, "04_model-provider-dialog");
    await page.keyboard.press("Escape");
    await settle(page, 300);
  });
});

test.describe("project workspace overview and message stream", () => {
  test("overview, inspector tabs, protocol dialog", async ({ page }) => {
    await openProject(page);
    await shot(page, "10_project-overview");

    const resultsTab = page.getByRole("tab", { name: "研究结果" });
    await expect(resultsTab).toBeVisible();
    await resultsTab.click();
    await settle(page, 700);
    await shot(page, "12_inspector-results");
    await page.getByRole("tab", { name: "研究概览" }).click();
    await settle(page, 500);

    const protocolButton = page.getByRole("button", { name: /研究协议/ }).first();
    await expect(protocolButton).toBeVisible();
    await protocolButton.click();
    await settle(page, 600);
    await shot(page, "13_protocol-review-dialog");
    await page.keyboard.press("Escape");
    await settle(page, 300);
  });

  test("message stream scroll anchors", async ({ page }) => {
    await openProject(page);
    const stream = page.getByTestId("agent-message-stream");
    await expect(stream).toBeVisible();

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
  });
});

const FORMAL_ARTIFACTS: ReadonlyArray<readonly [string, string, string]> = [
  ["20_artifact-dataset", "artv_dataset_01", PROJECT_A],
  ["21_artifact-field-dictionary", "artv_fdict_01", PROJECT_A],
  ["22_artifact-source-collection", "artv_srccol_01", PROJECT_A],
  [
    "23_artifact-paper-collection",
    "11111111-1111-4111-8111-111111111111",
    PROJECT_A,
  ],
  ["24_artifact-paper-summary", "artv_papsum_01", PROJECT_A],
  ["25_artifact-literature-claims", "artv_claims_01", PROJECT_A],
  ["26_artifact-literature-relations", "artv_rels_01", PROJECT_A],
  ["27_artifact-graph", "artv_graph_01", PROJECT_A],
];

const SCIENTIFIC_ARTIFACTS: ReadonlyArray<readonly [string, string, string]> = [
  ["50_analysis-report", "artv_analysis_01", PROJECT_A],
  ["51_scientific-chart", "artv_vis_chart_01", PROJECT_A],
  ["52_spectrum", "artv_spec_01", PROJECT_A],
  ["53_light-curve", "artv_lc_01", PROJECT_A],
  ["54_model-evaluation", "artv_modeval_01", PROJECT_A],
  ["55_model-artifact", "artv_model_01", PROJECT_A],
  ["56_fits", "artv_vis_fits_01", PROJECT_A],
  ["57_wwt-scene", "artv_vis_wwt_01", PROJECT_A],
];

test.describe("fullscreen formal artifact workspaces", () => {
  for (const [name, versionId, project] of FORMAL_ARTIFACTS) {
    test(name, async ({ page }) => {
      await page.goto(`${project}?artifactVersionId=${versionId}`);
      await expect(page.getByTestId("root-layout")).toBeVisible();
      await expect(page.getByTestId("artifact-fullscreen-workspace")).toBeVisible();
      await settle(page, name.includes("graph") ? 2500 : 1500);
      await shot(page, name);
    });
  }
});

test.describe("fullscreen scientific artifact workspaces", () => {
  for (const [name, versionId, project] of SCIENTIFIC_ARTIFACTS) {
    test(name, async ({ page }) => {
      await page.goto(`${project}?artifactVersionId=${versionId}`);
      await expect(page.getByTestId("root-layout")).toBeVisible();
      await expect(page.getByTestId("artifact-fullscreen-workspace")).toBeVisible();
      await settle(page, name.includes("wwt") ? 3000 : 1500);
      await shot(page, name);
    });
  }
});

test.describe("share flow and public pages", () => {
  test("share dialog, link creation, and public share pages", async ({ page }) => {
    await page.goto(`${PROJECT_A}?artifactVersionId=artv_dataset_01`);
    await expect(page.getByTestId("artifact-fullscreen-workspace")).toBeVisible();
    await settle(page, 1000);

    const shareButton = page.getByRole("button", { name: "分享", exact: true }).first();
    await expect(shareButton).toBeVisible();
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

    // Test seeded valid public share
    await page.goto("/share/token_fixture_dataset");
    await expect(page.locator(".public-share-page")).toBeVisible();
    await settle(page, 1500);
    await shot(page, "42_valid-public-share");

    // Test invalid / revoked public share
    await page.goto("/share/token_invalid_revoked");
    await expect(page.getByText("共享结果当前不可用")).toBeVisible();
    await settle(page, 1000);
    await shot(page, "43_invalid-public-share");
  });
});

test.describe("responsive viewports", () => {
  test("1440, 1280, and 1024 widths", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openProject(page, PROJECT_A, 1000);
    await shot(page, "60_viewport-1440x900");

    await page.setViewportSize({ width: 1280, height: 800 });
    await settle(page, 600);
    await shot(page, "61_viewport-1280x800");

    await page.setViewportSize({ width: 1024, height: 768 });
    await settle(page, 600);
    await shot(page, "62_viewport-1024x768");
  });
});
