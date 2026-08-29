import { expect, test, type Page } from "@playwright/test";
import { resolve } from "node:path";

const SHOT_DIR =
  process.env.VISUAL_SHOT_DIR || resolve(".artifacts/visual-acceptance/shots");

const PROJECT_A = "/workspace/proj_01JEXAMPLE";
const PROJECT_B = "/workspace/proj_toi_transit";
const PROJECT_C = "/workspace/proj_l9859_spectroscopy";

async function settle(page: Page, ms = 800): Promise<void> {
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(ms);
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: `${SHOT_DIR}/${name}.png` });
  console.log(`[shot] ${name}.png`);
}

async function openProject(
  page: Page,
  projectUrl = PROJECT_A,
  wait = 1200,
): Promise<void> {
  await page.goto(projectUrl);
  await expect(page.getByTestId("root-layout")).toBeVisible();
  await settle(page, wait);
}

async function openArtifactFromThread(
  page: Page,
  versionId: string,
): Promise<void> {
  const result = page.getByTestId(`artifact-result-${versionId}`);
  await expect(result).toBeVisible();
  await result.getByRole("button", { name: /查看完整结果|审查结果/ }).click();
  await expect(page.getByTestId("artifact-fullscreen-workspace")).toBeVisible();
}

async function returnToResearch(page: Page): Promise<void> {
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  await fullscreen.getByRole("button", { name: /返回研究/ }).click();
  await expect(fullscreen).toBeHidden();
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

    const protocolButton = page
      .getByRole("button", { name: /研究协议/ })
      .first();
    await expect(protocolButton).toBeVisible();
    await protocolButton.click();
    await settle(page, 600);
    await shot(page, "13_protocol-review-dialog");
    await page.keyboard.press("Escape");
    await settle(page, 300);
  });

  test("project B overview lists AutoAstro-derived results", async ({
    page,
  }) => {
    await openProject(page, PROJECT_B);
    await shot(page, "11_project-b-overview");

    const resultsTab = page.getByRole("tab", { name: "研究结果" });
    await expect(resultsTab).toBeVisible();
    await resultsTab.click();
    await settle(page, 700);
    await expect(page.getByText("TOI-1233 凌星分析报告").first()).toBeVisible();
    await expect(
      page.getByText("TOI-1233 TESS 光变曲线").first(),
    ).toBeVisible();
    await shot(page, "11b_project-b-results");
  });

  test("project C overview lists MAVIS-derived results", async ({ page }) => {
    await openProject(page, PROJECT_C);
    await shot(page, "12_project-c-overview");

    const resultsTab = page.getByRole("tab", { name: "研究结果" });
    await expect(resultsTab).toBeVisible();
    await resultsTab.click();
    await settle(page, 700);
    await expect(
      page.getByText("L 98-59 高分辨率光谱", { exact: true }).first(),
    ).toBeVisible();
    await expect(
      page.getByText("L 98-59 WWT 天球视口场景", { exact: true }).first(),
    ).toBeVisible();
    await shot(page, "12b_project-c-results");
  });

  test("message stream scroll anchors", async ({ page }) => {
    await openProject(page);
    const stream = page.getByTestId("agent-message-stream");
    await expect(stream).toBeVisible();
    await expect(
      stream.getByText("整合系外行星候选体与宿主星参数", { exact: false }),
    ).toBeVisible();
    await expect(
      stream.getByText("我已整理研究目标与来源范围", { exact: false }),
    ).toBeVisible();

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

const FORMAL_ARTIFACTS: ReadonlyArray<readonly [string, string]> = [
  ["20_artifact-dataset", "artv_dataset_01"],
  ["22_artifact-field-dictionary", "artv_fdict_01"],
  ["23_artifact-source-collection", "artv_srccol_01"],
  ["24_artifact-paper-collection", "11111111-1111-4111-8111-111111111111"],
  ["30_artifact-literature-claims", "artv_claims_01"],
  ["31_artifact-literature-relations", "artv_rels_01"],
  ["36_artifact-graph", "artv_graph_01"],
];

test.describe("fullscreen formal artifact workspaces", () => {
  test("Scenario A traverses every formal result through the research thread", async ({
    page,
  }) => {
    await openProject(page, PROJECT_A);
    for (const [name, versionId] of FORMAL_ARTIFACTS) {
      await openArtifactFromThread(page, versionId);
      await settle(page, name.includes("graph") ? 2500 : 900);
      await assertNoFatalError(page);
      await shot(page, name);

      if (versionId === "artv_dataset_01") {
        const scroller = page.locator(".scientific-table").first();
        await scroller.evaluate((element) => {
          element.scrollLeft = element.scrollWidth;
        });
        expect(
          await scroller.evaluate(
            (element) =>
              element.scrollLeft + element.clientWidth >=
              element.scrollWidth - 2,
          ),
        ).toBe(true);
        await shot(page, "21_artifact-dataset-horizontal-scroll");
      }

      if (versionId === "artv_rels_01") {
        const candidate = page.getByTestId("dossier-entry-rel_03");
        await candidate.scrollIntoViewIfNeeded();
        await expect(
          candidate.getByRole("button", { name: "接受并进入图谱" }),
        ).toBeVisible();
        await candidate
          .getByRole("button", { name: "接受并进入图谱" })
          .click();
        const adjudicationSheet = page.getByRole("dialog", {
          name: "审定候选关系",
        });
        await expect(adjudicationSheet).toBeVisible();
        await expect(
          adjudicationSheet.getByRole("combobox", {
            name: "选择关系审定结论",
          }),
        ).toHaveText("接受并进入图谱");
        await shot(page, "32_relation-candidate-actions");
        await page.keyboard.press("Escape");
        await expect(adjudicationSheet).toBeHidden();

        const accepted = page.getByTestId("dossier-entry-rel_01");
        await accepted.scrollIntoViewIfNeeded();
        await expect(
          accepted.getByText("已纳入结论", { exact: false }).first(),
        ).toBeVisible();
        await expect(
          accepted.getByRole("button", { name: "接受并进入图谱" }),
        ).toHaveCount(0);
        await shot(page, "33_relation-accepted");
        await accepted.getByRole("button", { name: /相同的 TIC 标识/ }).click();
        await expect(
          accepted.getByText("比对行星母星标识", { exact: false }),
        ).toBeVisible();
        await shot(page, "34_relation-reasoning-trace");
      }

      await returnToResearch(page);
    }
  });
});

test.describe("paper summary reading workspace", () => {
  test("normal path: report, real PDF, evidence jump", async ({ page }) => {
    await openProject(page, PROJECT_A);
    await page
      .getByTestId("artifact-result-artv_papsum_01")
      .getByRole("button", { name: "查看完整结果" })
      .click();
    const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
    await expect(fullscreen).toBeVisible();

    await expect(
      page.getByRole("heading", {
        name: "The TESS Faint Star Search: 1,617 TOIs from the TESS Primary Mission",
      }),
    ).toBeVisible();
    // 24a captures the reading report immediately, before the PDF pane
    // has necessarily painted its first canvas (spec: report-first view).
    await settle(page, 200);
    await shot(page, "24a_paper-summary-report");

    const viewer = page.getByTestId("paper-pdf-viewer").first();
    await expect(viewer).toBeVisible();
    await expect
      .poll(async () => Number(await viewer.getAttribute("data-num-pages")), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
    await expect(
      page.getByTestId("paper-pdf-page").first().locator("canvas"),
    ).toBeVisible();
    await shot(page, "24b_paper-summary-with-pdf");

    await fullscreen
      .getByRole("button", { name: /查看证据/ })
      .nth(1)
      .click();
    await page.getByRole("button", { name: "在论文中查看" }).click();
    await expect(viewer).toContainText("2 /");
    await settle(page, 600);
    await shot(page, "24c_paper-evidence-jump");
  });
});

/**
 * Per-capability assertions each required screenshot must pass before capture
 * (spec §60/§61/§78: a visible fullscreen shell is never enough).
 */
const FATAL_ERROR_MARKERS = [
  "操作暂时不可用",
  "载入失败",
  "暂时无法显示",
  "当前结果类型暂时无法显示",
] as const;

async function assertNoFatalError(page: Page) {
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  for (const marker of FATAL_ERROR_MARKERS) {
    const count = await fullscreen.getByText(marker, { exact: false }).count();
    if (count > 0) {
      throw new Error(
        `Scientific screenshot would capture an error page: "${marker}" found`,
      );
    }
  }
}

test.describe("graph selected-object inspector", () => {
  test("37_graph-selected-node and 38_graph-selected-relation", async ({
    page,
  }) => {
    await openProject(page, PROJECT_A);
    await openArtifactFromThread(page, "artv_graph_01");
    const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
    await settle(page, 2500);

    // Selected node → side inspector shows the node's scientific identity.
    const firstNode = fullscreen.locator(".react-flow__node").first();
    await expect(firstNode).toBeVisible();
    await firstNode.click();
    await expect(
      fullscreen.locator(".graph-workspace__side-inspector"),
    ).toBeVisible();
    await expect(
      fullscreen
        .locator(".graph-workspace__side-inspector")
        .getByRole("heading"),
    ).toContainText(/研究对象|研究目标|指标|行星|宿主/);
    await shot(page, "37_graph-selected-node");

    // Selected edge → inspector shows relation details (spec §43).
    const firstEdge = fullscreen.locator(".react-flow__edge").first();
    const edgeBox = await firstEdge.boundingBox();
    expect(edgeBox, "关系边必须具有可点击几何区域").not.toBeNull();
    await page.mouse.click(
      edgeBox!.x + edgeBox!.width / 2,
      edgeBox!.y + edgeBox!.height / 2,
    );
    await settle(page, 600);
    await expect(
      fullscreen.locator(".graph-workspace__side-inspector"),
    ).toContainText(/关系|可比性|公开推导/);
    await shot(page, "38_graph-selected-relation");
  });
});

test.describe("fullscreen scientific artifact workspaces", () => {
  test("Scenario B traverses analysis, chart, light curve, evaluation and model", async ({
    page,
  }) => {
    await openProject(page, PROJECT_B);

    await openArtifactFromThread(page, "artv_b_analysis_01");
    await assertNoFatalError(page);
    await expect(
      page.getByText("TOI-1233", { exact: false }).first(),
    ).toBeVisible();
    await shot(page, "50_analysis-report");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_b_chart_01");
    await assertNoFatalError(page);
    const chart = page.locator('.scientific-chart__canvas[data-state="ready"]');
    await expect(chart).toBeVisible();
    const chartSvg = chart.locator("svg");
    await expect(chartSvg).toBeVisible();
    expect((await chartSvg.boundingBox())?.width ?? 0).toBeGreaterThan(240);
    await shot(page, "51_scientific-chart");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_b_lc_01");
    await assertNoFatalError(page);
    await expect(page.getByRole("tab", { name: /连续光变序列/ })).toBeVisible();
    await shot(page, "53_light-curve-time-series");
    await page.getByRole("tab", { name: /相位折叠曲线/ }).click();
    await expect(page.getByText("轨道相位 Orbital Phase")).toBeVisible();
    await shot(page, "54_light-curve-phase-folded");
    await page.getByRole("tab", { name: /周期图谱/ }).click();
    await expect(
      page.getByText("周期图谱峰值", { exact: false }).first(),
    ).toBeVisible();
    await shot(page, "55_light-curve-periodogram");
    await page.getByRole("button", { name: /周期图谱峰值候选/ }).click();
    await expect(
      page.getByRole("columnheader", { name: /周期/ }),
    ).toBeVisible();
    await shot(page, "55b_light-curve-peaks-expanded");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_b_modeval_01");
    await assertNoFatalError(page);
    await expect(
      page.getByText("基线", { exact: false }).first(),
    ).toBeVisible();
    await shot(page, "56_model-evaluation");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_b_model_01");
    await assertNoFatalError(page);
    await expect(
      page.getByText("ONNX", { exact: false }).first(),
    ).toBeVisible();
    await expect(page.getByText(/sha256:/i)).toHaveCount(0);
    await shot(page, "57_model-artifact");
  });

  test("Scenario C traverses spectrum, FITS and WWT ready/interaction states", async ({
    page,
  }) => {
    await openProject(page, PROJECT_C);

    await openArtifactFromThread(page, "artv_c_analysis_01");
    await assertNoFatalError(page);
    await shot(page, "49_l9859-analysis-report");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_c_spec_01");
    await assertNoFatalError(page);
    await expect(
      page.getByText("L 98-59", { exact: false }).first(),
    ).toBeVisible();
    await shot(page, "52_spectrum");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_c_fits_01");
    await assertNoFatalError(page);
    await expect(page.getByTestId("wwt-viewport")).toHaveAttribute(
      "data-state",
      "ready",
      { timeout: 30_000 },
    );
    await shot(page, "58_fits-ready");
    await returnToResearch(page);

    await openArtifactFromThread(page, "artv_c_wwt_01");
    await assertNoFatalError(page);
    const viewport = page.getByTestId("wwt-viewport");
    await expect(viewport).toHaveAttribute("data-state", "ready", {
      timeout: 30_000,
    });
    await shot(page, "59_wwt-ready");
    await page.getByRole("button", { name: "坐标网格" }).click();
    const gridToggle = page.getByRole("menuitemcheckbox", { name: /银道网格/ });
    await expect(gridToggle).toBeVisible();
    await gridToggle.click();
    await expect(viewport).toHaveAttribute("data-state", "ready", {
      timeout: 30_000,
    });
    await page.getByRole("button", { name: "坐标网格" }).click();
    await expect(
      page.getByRole("menuitemcheckbox", { name: /银道网格/ }),
    ).toHaveAttribute("aria-checked", "true");
    await settle(page, 600);
    await shot(page, "60_wwt-grid-interaction");
  });
});

test.describe("share flow and public pages", () => {
  test("share dialog, link creation, and public share pages", async ({
    page,
  }) => {
    await page.goto(`${PROJECT_A}?artifactVersionId=artv_dataset_01`);
    await expect(
      page.getByTestId("artifact-fullscreen-workspace"),
    ).toBeVisible();
    await settle(page, 1000);

    const shareButton = page
      .getByRole("button", { name: "分享", exact: true })
      .first();
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

    const createdShareUrl = await shareLink.inputValue();
    await page.evaluate((pathname) => {
      window.history.pushState({}, "", pathname);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, new URL(createdShareUrl).pathname);
    await expect(page.locator(".public-share-page")).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: "系外行星宿主星数据集 (40 颗)",
        level: 1,
      }),
    ).toBeVisible();
    await expect(page.getByText(/创建分享时冻结的公开副本/)).toBeVisible();
    await expect(page.getByText("共享结果当前不可用")).toHaveCount(0);
    await settle(page, 1500);
    await shot(page, "42_created-public-share");

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
    await shot(page, "80_viewport-1440x900");

    await page.setViewportSize({ width: 1280, height: 800 });
    await settle(page, 600);
    await shot(page, "81_viewport-1280x800");

    await page.setViewportSize({ width: 1024, height: 768 });
    await settle(page, 600);
    await shot(page, "82_viewport-1024x768");
  });
});

test.describe("desktop accessibility NFR", () => {
  test("long fullscreen dossier content is scroll-reachable", async ({
    page,
  }) => {
    await page.goto(`${PROJECT_A}?artifactVersionId=artv_claims_01`);
    await expect(
      page.getByTestId("artifact-fullscreen-workspace"),
    ).toBeVisible();
    await settle(page, 1500);

    const scrollState = await page.evaluate(() => {
      const dialog = document.querySelector(
        '[data-testid="artifact-fullscreen-workspace"]',
      );
      if (!dialog) return { hasScroller: false, reachedBottom: false };
      let scroller: HTMLElement | null = null;
      dialog.querySelectorAll<HTMLElement>("*").forEach((el) => {
        if (scroller) return;
        const overflowY = window.getComputedStyle(el).overflowY;
        if (
          (overflowY === "auto" || overflowY === "scroll") &&
          el.scrollHeight > el.clientHeight + 1
        ) {
          scroller = el;
        }
      });
      if (!scroller) return { hasScroller: false, reachedBottom: false };
      scroller.scrollTop = scroller.scrollHeight;
      return {
        hasScroller: true,
        reachedBottom:
          scroller.scrollTop + scroller.clientHeight >=
          scroller.scrollHeight - 2,
      };
    });
    expect(scrollState.hasScroller).toBe(true);
    expect(scrollState.reachedBottom).toBe(true);
    await settle(page, 400);
    await shot(page, "71_long-content-scrolled-bottom");
  });
});
