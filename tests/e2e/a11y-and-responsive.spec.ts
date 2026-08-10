import { expect, test } from "@playwright/test";

import { requireBoundingBox, setDocumentFontScale } from "./test-helpers";

/** 覆盖入口测试未涉及的键盘、焦点、200% 字体与窄屏边界证据。 */

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

test("shared controls remove non-essential transitions under reduced motion", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:4321/");

  await expect(page.getByRole("link", { name: "进入工作台" })).toHaveCSS(
    "transition-property",
    "none",
  );
});

test("workspace skip link appears on focus and targets main content", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const skipLink = page.getByRole("link", { name: "跳到主要内容" });
  await expect(skipLink).toHaveCSS("opacity", "0");

  for (let tabCount = 0; tabCount < 8; tabCount += 1) {
    if (
      await skipLink.evaluate((element) => element === document.activeElement)
    ) {
      break;
    }
    await page.keyboard.press("Tab");
  }
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toHaveCSS("opacity", "1");

  // Activate skip link
  await page.keyboard.press("Enter");
  const mainContent = page.locator("main#main-content");
  await expect(mainContent).toBeFocused();
});

test.describe("narrow viewport @ 375px", () => {
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
      page.getByRole("heading", { name: "请使用桌面设备" }),
    ).toBeVisible();
    await expect(
      page.getByText("研究工作台需要至少 1024 像素宽的浏览器窗口。"),
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
    await setDocumentFontScale(page, "200%");

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
    await setDocumentFontScale(page, "200%");

    await expect(
      page.getByRole("heading", { name: "研究工作台" }),
    ).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "工作台导航" }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "向 Agent 发送指令" }),
    ).toBeVisible();

    const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
    const expandedSidebarWidth = (
      await requireBoundingBox(sidebar, "expanded sidebar")
    ).width;
    await page.getByRole("button", { name: "收起侧栏" }).click();
    await expect(page.getByRole("button", { name: "展开侧栏" })).toBeVisible();
    await expect
      .poll(async () => (await sidebar.boundingBox())?.width ?? Infinity)
      .toBeLessThan(expandedSidebarWidth);
    const collapsedSidebarWidth = (
      await requireBoundingBox(sidebar, "collapsed sidebar")
    ).width;
    expect(collapsedSidebarWidth).toBeLessThan(expandedSidebarWidth);
    await page.getByRole("button", { name: "展开侧栏" }).click();

    const activityTab = page.getByRole("tab", { name: "活动" });
    await activityTab.focus();
    await page.keyboard.press("ArrowRight");
    await expect(page.getByRole("tab", { name: "上下文" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const panelSeparator = page.getByRole("separator", {
      name: "调整任务与活动面板宽度",
    });
    await panelSeparator.focus();
    const initialPanelRatio = Number(
      await panelSeparator.getAttribute("aria-valuenow"),
    );
    await page.keyboard.press("ArrowRight");
    await expect
      .poll(async () =>
        Number(await panelSeparator.getAttribute("aria-valuenow")),
      )
      .toBeGreaterThan(initialPanelRatio);

    const commandTrigger = page.getByRole("button", {
      name: "打开命令菜单",
    });
    await commandTrigger.focus();
    await page.keyboard.press("Control+k");
    await expect(
      page.getByRole("combobox", { name: "搜索命令" }),
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(commandTrigger).toBeFocused();

    const composerSeparator = page.getByRole("separator", {
      name: "调整指令输入区高度",
    });
    const composer = page.getByTestId("chat-input-container");
    const actions = page.getByTestId("chat-input-actions");
    const input = page.getByRole("textbox", { name: "向 Agent 发送指令" });
    const initialComposerBox = await requireBoundingBox(
      composer,
      "initial composer",
    );
    const initialComposerHeight = Number(
      await composerSeparator.getAttribute("aria-valuenow"),
    );
    expect(initialComposerHeight).toBeGreaterThan(0);
    await composerSeparator.focus();
    await page.keyboard.press("ArrowUp");
    await expect
      .poll(async () =>
        Number(await composerSeparator.getAttribute("aria-valuenow")),
      )
      .toBeGreaterThan(initialComposerHeight);
    await page.keyboard.press("Home");
    await expect
      .poll(async () =>
        Number(await composerSeparator.getAttribute("aria-valuenow")),
      )
      .toBeLessThanOrEqual(initialComposerHeight);

    await page.reload();
    await setDocumentFontScale(page, "200%");

    await input.evaluate((element) => {
      element.contentEditable = "true";
      element.removeAttribute("aria-disabled");
      element.textContent = Array.from(
        { length: 20 },
        (_, index) => `第${index + 1}行`,
      ).join("\n");
      element.dispatchEvent(
        new InputEvent("input", { bubbles: true, inputType: "insertText" }),
      );
    });
    await expect
      .poll(async () => (await composer.boundingBox())?.height ?? 0)
      .toBeGreaterThan(initialComposerBox.height);
    const expandedComposerBox = await requireBoundingBox(
      composer,
      "expanded composer",
    );
    const actionsBox = await requireBoundingBox(actions, "composer actions");
    expect(expandedComposerBox.height).toBeGreaterThan(
      initialComposerBox.height,
    );
    expect(actionsBox.y + actionsBox.height).toBeLessThanOrEqual(
      expandedComposerBox.y + expandedComposerBox.height + 1,
    );
    await input.evaluate((element) => {
      element.textContent = "";
      element.dispatchEvent(new InputEvent("input", { bubbles: true }));
    });

    // No horizontal overflow
    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);
  });

  test("shared share-route controls remain operable at 200% font size", async ({
    page,
  }) => {
    let shareRequests = 0;
    let initialRequestsReleased = false;
    let releaseInitialRequest = () => {};
    const initialRequestPending = new Promise<void>((resolve) => {
      releaseInitialRequest = resolve;
    });
    await page.route("**/api/public/shares/test-token", async (route) => {
      shareRequests += 1;
      if (!initialRequestsReleased) await initialRequestPending;
      await route.fulfill({ status: 404, body: "{}" });
    });

    await page.goto("http://127.0.0.1:5173/share/test-token");
    const spinner = page.getByRole("status", {
      name: "正在重新载入共享结果",
    });
    await expect(spinner).toBeVisible();
    const normalSpinnerFontSize = Number.parseFloat(
      await spinner.evaluate((element) => getComputedStyle(element).fontSize),
    );

    await setDocumentFontScale(page, "200%");
    await expect(spinner).toBeVisible();
    expect(
      Number.parseFloat(
        await spinner.evaluate((element) => getComputedStyle(element).fontSize),
      ),
    ).toBeGreaterThanOrEqual(normalSpinnerFontSize * 2);

    initialRequestsReleased = true;
    releaseInitialRequest();
    const retry = page.getByRole("button", { name: "重试" });
    await expect(retry).toBeVisible();
    await expect(retry).toBeEnabled();
    const initialRequestCount = shareRequests;
    await page.keyboard.press("Tab");
    await expect(retry).toBeFocused();

    await page.keyboard.press("Enter");
    await expect.poll(() => shareRequests).toBe(initialRequestCount + 1);
    await expect(retry).toBeEnabled();
    for (let tabCount = 0; tabCount < 3; tabCount += 1) {
      if (await retry.evaluate((element) => element === document.activeElement))
        break;
      await page.keyboard.press("Tab");
    }
    await expect(retry).toBeFocused();
    await page.keyboard.press("Space");
    await expect.poll(() => shareRequests).toBe(initialRequestCount + 2);
    await expect(retry).toBeEnabled();

    const scrollWidth = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(scrollWidth).toBeLessThanOrEqual(1280);

    const returnHome = page.getByRole("link", { name: "返回首页" });
    for (let tabCount = 0; tabCount < 3; tabCount += 1) {
      if (
        await returnHome.evaluate(
          (element) => element === document.activeElement,
        )
      )
        break;
      await page.keyboard.press("Tab");
    }
    await expect(returnHome).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/workspace$/u);
  });
});

test("workspace honors reduced motion for shell transitions", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:5173/workspace");

  await expect(
    page.getByRole("complementary", { name: "工作台侧栏" }),
  ).toHaveCSS("transition-property", "none");
  await expect(
    page.locator('[aria-labelledby="agent-task-heading"]'),
  ).toHaveCSS("transition-property", "none");
  await expect(page.locator("#workspace-activity-panel")).toHaveCSS(
    "transition-property",
    "none",
  );
});
