import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import {
  requireBoundingBox,
  requireValue,
  requireViewport,
  setDocumentFontScale,
} from "./test-helpers";

/** 验证源码采用后的 /workspace 壳层与 /share 安全边界。 */

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

async function assertDesktopWorkspacePath(page: Page) {
  const header = page
    .getByRole("heading", { name: "研究工作台" })
    .locator("xpath=ancestor::header");
  const rightHeader = page
    .getByRole("tablist", { name: "工作区面板" })
    .locator("..");
  const [headerBox, rightHeaderBox] = await Promise.all([
    requireBoundingBox(header, "workspace header"),
    requireBoundingBox(rightHeader, "activity header"),
  ]);
  expect(headerBox.y).toBe(0);
  expect(rightHeaderBox.y).toBe(0);
  expect(headerBox.height).toBeGreaterThan(0);
  expect(rightHeaderBox.height).toBe(headerBox.height);

  const activityTab = page.getByRole("tab", { name: "活动" });
  await activityTab.focus();
  await page.keyboard.press("ArrowRight");
  const contextTab = page.getByRole("tab", { name: "上下文" });
  await expect(contextTab).toHaveAttribute("aria-selected", "true");
  await expect(contextTab).toBeFocused();

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
  await expect(page.getByRole("combobox", { name: "搜索命令" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(commandTrigger).toBeFocused();

  const composer = page.getByRole("textbox", {
    name: "向 Agent 发送指令",
  });
  await expect(composer).toBeVisible();
  const composerContainer = page.getByTestId("chat-input-container");
  const composerBox = await requireBoundingBox(
    composerContainer,
    "composer container",
  );
  const actionBox = await requireBoundingBox(
    page.getByTestId("chat-input-actions"),
    "composer actions",
  );
  const viewport = requireViewport(page);
  const composerOuter = composerContainer.locator("xpath=../..");
  const reservedBottomPadding = Number(
    await composerOuter.evaluate((element) =>
      Number.parseFloat(getComputedStyle(element).paddingBottom),
    ),
  );
  expect(
    viewport.height - composerBox.y - composerBox.height,
  ).toBeLessThanOrEqual(reservedBottomPadding + 1);
  expect(actionBox.y + actionBox.height).toBeLessThanOrEqual(
    composerBox.y + composerBox.height,
  );
}

test("root entry redirects to the Workspace host", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:15173/");
  await expect(page).toHaveURL(/\/workspace$/u);
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Workspace host renders the desktop shell", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:15173/workspace");

  const heading = page.getByRole("heading", { name: "研究工作台" });
  const runtimeStatus = page.getByText("运行服务未连接", { exact: true });
  await expect(heading).toBeVisible();
  await expect(runtimeStatus).toHaveCount(1);
  const headingBox = await requireBoundingBox(heading, "workspace title");
  const runtimeStatusBox = await requireBoundingBox(
    runtimeStatus,
    "runtime status",
  );
  expect(
    Math.abs(
      headingBox.y +
        headingBox.height / 2 -
        (runtimeStatusBox.y + runtimeStatusBox.height / 2),
    ),
  ).toBeLessThanOrEqual(2);
  await expect(page.getByText("星文智析")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "工作台导航" }),
  ).toBeVisible();
  await expect(page.getByRole("tablist", { name: "工作区面板" })).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "向 Agent 发送指令" }),
  ).toHaveAttribute("aria-disabled", "true");
  await expect(page.getByRole("button", { name: "新建任务" })).toBeDisabled();
  await expect(
    page.getByRole("link", { name: "跳到主要内容" }),
  ).toHaveAttribute("href", "#main-content");
  await expect(page.getByText("请使用桌面设备")).toBeHidden();
  expect(errors).toEqual([]);
});

test("Workspace top bars share one height, divider, and type scale", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const sidebarBar = sidebar.locator("header");
  const workspaceBar = page
    .getByRole("heading", { name: "研究工作台" })
    .locator("xpath=ancestor::header");
  const activityBar = page
    .getByRole("tablist", { name: "工作区面板" })
    .locator("..");

  const barBoxes = await Promise.all(
    [sidebarBar, workspaceBar, activityBar].map((bar, index) =>
      requireBoundingBox(bar, `top bar ${index}`),
    ),
  );
  for (const box of barBoxes) {
    expect(box.y).toBe(0);
    expect(box.height).toBe(barBoxes[0].height);
  }
  const dividerWidths = await Promise.all(
    [sidebarBar, workspaceBar, activityBar].map((bar) =>
      bar.evaluate((element) => getComputedStyle(element).borderBottomWidth),
    ),
  );
  expect(new Set(dividerWidths).size).toBe(1);
  expect(Number.parseFloat(dividerWidths[0] ?? "0")).toBeGreaterThan(0);

  const brandFontSize = await page
    .getByText("星文智析", { exact: true })
    .evaluate((element) => getComputedStyle(element).fontSize);
  const titleFontSize = await page
    .getByRole("heading", { name: "研究工作台" })
    .evaluate((element) => getComputedStyle(element).fontSize);
  const tabFontSize = await page
    .getByRole("tab", { name: "活动" })
    .evaluate((element) => getComputedStyle(element).fontSize);
  const statusFontSize = await page
    .getByText("运行服务未连接", { exact: true })
    .evaluate((element) => getComputedStyle(element).fontSize);
  expect(brandFontSize).toBe(titleFontSize);
  expect(titleFontSize).toBe(tabFontSize);
  expect(Number.parseFloat(statusFontSize)).toBeLessThan(
    Number.parseFloat(tabFontSize),
  );
});

test.describe("Workspace desktop shell at 1440×900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("keeps the desktop mechanics aligned", async ({ page }) => {
    await page.goto("http://127.0.0.1:15173/workspace");
    await assertDesktopWorkspacePath(page);
  });
});

test.describe("Workspace desktop shell at 1280×800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("keeps the desktop mechanics aligned at normal scale", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:15173/workspace");
    await assertDesktopWorkspacePath(page);
  });
});

test("Workspace right-panel toggle stays anchored while the panel collapses", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const leftSidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const rightPanel = page.locator("#workspace-activity-panel");
  const readMotion = (element: Element) => {
    const style = getComputedStyle(element);
    return {
      duration: style.transitionDuration,
      timing: style.transitionTimingFunction,
    };
  };
  const [leftMotion, rightMotion] = await Promise.all([
    leftSidebar.evaluate(readMotion),
    rightPanel.evaluate(readMotion),
  ]);
  expect(rightMotion).toEqual(leftMotion);

  const collapse = page.getByRole("button", { name: "收起活动面板" });
  const before = await requireBoundingBox(collapse, "collapse toggle");
  const activityHeading = rightPanel.getByText("尚无 Agent 活动", {
    exact: true,
  });
  const initialHeadingBox = await requireBoundingBox(
    activityHeading,
    "activity empty state",
  );
  await expect(rightPanel).toHaveAttribute("aria-hidden", "false");
  expect(await rightPanel.evaluate((element) => element.inert)).toBe(false);

  await collapse.click();
  const expand = page.getByRole("button", { name: "展开活动面板" });
  await expect(expand).toBeVisible();
  await expect(expand).toBeFocused();
  await expect(rightPanel).toHaveAttribute("aria-hidden", "true");
  expect(await rightPanel.evaluate((element) => element.inert)).toBe(true);
  const collapsedSurface = page.getByTestId("workspace-main-surface");
  const collapsedSurfaceMetrics = await collapsedSurface.evaluate((surface) => {
    const taskPanel = surface.closest<HTMLElement>(
      '[aria-labelledby="agent-task-heading"]',
    );
    if (!taskPanel) return null;
    return {
      taskPanelWidth: taskPanel.getBoundingClientRect().width,
      surfaceWidth: surface.getBoundingClientRect().width,
    };
  });
  const collapsedMetrics = requireValue(
    collapsedSurfaceMetrics,
    "collapsed workspace surface",
  );
  expect(
    Math.abs(collapsedMetrics.surfaceWidth - collapsedMetrics.taskPanelWidth),
  ).toBeLessThanOrEqual(1);
  const collapsedAnchor = await requireBoundingBox(expand, "expanded toggle");
  expect(Math.abs(collapsedAnchor.x - before.x)).toBeLessThanOrEqual(2);

  await expand.click();
  await expect(collapse).toBeFocused();
  await expect(rightPanel).toBeVisible();
  await expect(rightPanel).toHaveAttribute("aria-hidden", "false");
  expect(await rightPanel.evaluate((element) => element.inert)).toBe(false);
  const expandedHeadingBox = await requireBoundingBox(
    activityHeading,
    "restored activity empty state",
  );
  expect(
    Math.abs(expandedHeadingBox.height - initialHeadingBox.height),
  ).toBeLessThanOrEqual(1);
  const expandedAnchor = await requireBoundingBox(collapse, "collapse toggle");
  expect(Math.abs(expandedAnchor.x - before.x)).toBeLessThanOrEqual(2);
  await expect(activityHeading).toBeVisible();
});

test("Sidebar toggle tracks the rail edge throughout collapse and expansion", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const geometry = await sidebar.evaluate((sidebarElement) => {
    const toggle = sidebarElement.querySelector<HTMLButtonElement>(
      'button[aria-label="收起侧栏"]',
    );
    const initialNewTaskIcon = sidebarElement.querySelector<SVGElement>(
      'button[aria-label="新建任务"] svg',
    );
    if (!toggle || !initialNewTaskIcon) return null;

    const readGeometry = () => {
      const sidebarBox = sidebarElement.getBoundingClientRect();
      const toggleBox = toggle.getBoundingClientRect();
      const newTaskIcon = sidebarElement.querySelector<SVGElement>(
        'button[aria-label="新建任务"] svg',
      );
      if (!newTaskIcon) throw new Error("New task icon is missing");
      const newTaskIconBox = newTaskIcon.getBoundingClientRect();
      return {
        toggleRightGap: sidebarBox.right - toggleBox.right,
        newTaskIconCenter:
          newTaskIconBox.left + newTaskIconBox.width / 2 - sidebarBox.left,
      };
    };
    const expanded = readGeometry();
    toggle.click();
    const collapsed = readGeometry();
    toggle.click();
    const restored = readGeometry();
    return { expanded, collapsed, restored };
  });

  const sidebarGeometry = requireValue(geometry, "sidebar geometry");
  expect(
    Math.abs(
      sidebarGeometry.expanded.toggleRightGap -
        sidebarGeometry.restored.toggleRightGap,
    ),
  ).toBeLessThanOrEqual(2);
  expect(
    Math.abs(
      sidebarGeometry.expanded.newTaskIconCenter -
        sidebarGeometry.restored.newTaskIconCenter,
    ),
  ).toBeLessThanOrEqual(2);
});

test("Sidebar text stays horizontal after expansion", async ({ page }) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  await page.getByRole("button", { name: "收起侧栏" }).click();
  await expect(page.getByText("星文智析", { exact: true })).toBeHidden();

  await expect(page.getByRole("button", { name: "展开侧栏" })).toBeVisible();
  await page.getByRole("button", { name: "展开侧栏" }).click();
  const brandTitle = page.getByText("星文智析", { exact: true });
  const emptyTask = sidebar
    .getByRole("region", { name: "任务列表" })
    .getByText("没有任务记录", { exact: true });
  await expect(brandTitle).toBeVisible();
  await expect(emptyTask).toBeVisible();
  const textHeights = await Promise.all(
    [brandTitle, emptyTask].map((locator) =>
      locator.evaluate((element) => ({
        height: element.getBoundingClientRect().height,
        whiteSpace: getComputedStyle(element).whiteSpace,
        writingMode: getComputedStyle(element).writingMode,
      })),
    ),
  );
  const [brandMetrics, emptyTaskMetrics] = textHeights;
  const expandedText = requireValue(
    brandMetrics && emptyTaskMetrics
      ? { brand: brandMetrics, emptyTask: emptyTaskMetrics }
      : null,
    "expanded sidebar text",
  );
  expect(expandedText.brand.height).toBeGreaterThan(0);
  expect(expandedText.emptyTask.height).toBeGreaterThan(0);
  expect(expandedText.brand.whiteSpace).toBe("nowrap");
  expect(expandedText.emptyTask.whiteSpace).toBe("nowrap");
  expect(expandedText.brand.writingMode).toBe("horizontal-tb");
  expect(expandedText.emptyTask.writingMode).toBe("horizontal-tb");
});

test("Composer stays transparent without a full-width hover line", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const composer = page.getByTestId("chat-input-container");
  await expect(composer).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(composer.locator("..")).toHaveCSS("border-top-width", "0px");
  const composerBox = await composer.boundingBox();
  const conversationBox = await page
    .getByTestId("conversation-main")
    .boundingBox();
  const composerBounds = requireValue(composerBox, "composer bounds");
  const conversationBounds = requireValue(
    conversationBox,
    "conversation bounds",
  );
  expect(composerBounds.height).toBeGreaterThan(0);
  expect(composerBounds.y + composerBounds.height).toBeLessThanOrEqual(
    conversationBounds.y + conversationBounds.height + 1,
  );

  const gripIndicator = page
    .getByRole("separator", { name: "调整指令输入区高度" })
    .locator("span");
  await page.getByRole("separator", { name: "调整指令输入区高度" }).hover();
  await expect(gripIndicator).toHaveCSS("opacity", "0");
  await page.getByRole("separator", { name: "调整指令输入区高度" }).focus();
  await expect(gripIndicator).toHaveCSS("opacity", "1");
});

test("Workspace command menu preserves keyboard focus", async ({ page }) => {
  await page.goto("http://127.0.0.1:15173/workspace");
  const trigger = page.getByRole("button", { name: "打开命令菜单" });
  await trigger.focus();

  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", { name: "搜索命令" });
  await expect(search).toBeVisible();
  await expect(search).toBeFocused();
  await expect(search).toHaveCSS("outline-style", "none");
  const searchDividerWidth = Number.parseFloat(
    await search
      .locator("..")
      .evaluate((element) => getComputedStyle(element).borderBottomWidth),
  );
  expect(searchDividerWidth).toBeGreaterThan(0);

  await page.keyboard.press("Tab");
  await expect(search).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "命令菜单" })).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Workspace tabs and split panel support keyboard control", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const activityTab = page.getByRole("tab", { name: "活动" });
  await activityTab.focus();
  await page.keyboard.press("ArrowRight");
  const contextTab = page.getByRole("tab", { name: "上下文" });
  await expect(contextTab).toHaveAttribute("aria-selected", "true");
  await expect(contextTab).toBeFocused();

  const separator = page.getByRole("separator", {
    name: "调整任务与活动面板宽度",
  });
  await separator.focus();
  const initialPanelRatio = Number(
    await separator.getAttribute("aria-valuenow"),
  );
  await page.keyboard.press("ArrowRight");
  await expect
    .poll(async () => Number(await separator.getAttribute("aria-valuenow")))
    .toBeGreaterThan(initialPanelRatio);

  await page.getByRole("button", { name: "收起活动面板" }).click();
  await expect(
    page.getByRole("complementary", { name: "活动面板" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "展开活动面板" }).click();
  await expect(
    page.getByRole("complementary", { name: "活动面板" }),
  ).toBeVisible();

  const composerSeparator = page.getByRole("separator", {
    name: "调整指令输入区高度",
  });
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
});

test("Composer natural layout grows without clipping at 100%", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const input = page.getByRole("textbox", { name: "向 Agent 发送指令" });
  const composer = page.getByTestId("chat-input-container");
  const actions = page.getByTestId("chat-input-actions");
  const before = await requireBoundingBox(composer, "initial composer");
  const rhythm = await composer.evaluate((container) => {
    const input = container.querySelector<HTMLElement>('[role="textbox"]');
    const actions = container.querySelector<HTMLElement>(
      '[data-testid="chat-input-actions"]',
    );
    if (!input || !actions) {
      throw new Error("Composer rhythm elements are missing");
    }
    const containerBox = container.getBoundingClientRect();
    const inputBox = input.getBoundingClientRect();
    const actionsBox = actions.getBoundingClientRect();
    return {
      edgePadding: inputBox.top - containerBox.top,
      rowGap: actionsBox.top - inputBox.bottom,
    };
  });
  expect(rhythm.edgePadding).toBeGreaterThan(0);
  expect(rhythm.rowGap).toBeGreaterThanOrEqual(12);
  expect(rhythm.rowGap).toBeGreaterThan(rhythm.edgePadding);

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
    .toBeGreaterThan(before.height);
  const after = await requireBoundingBox(composer, "expanded composer");
  const actionsBox = await requireBoundingBox(actions, "composer actions");
  expect(after.height).toBeGreaterThan(before.height);
  expect(actionsBox.y + actionsBox.height).toBeLessThanOrEqual(
    after.y + after.height + 1,
  );
  await input.evaluate((element) => {
    element.textContent = "";
    element.dispatchEvent(new InputEvent("input", { bubbles: true }));
  });
});

test.describe("Workspace overflow menu at 1024×800", () => {
  test.use({ viewport: { width: 1024, height: 800 } });

  test("closes on Escape and restores focus after a tab selection at 200%", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:15173/workspace");
    await setDocumentFontScale(page, "200%");

    const more = page.getByRole("button", { name: "更多面板" });
    await expect(more).toBeVisible();
    await more.click();
    const menu = page.getByRole("menu", { name: "更多面板选项" });
    await expect(menu).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(more).toBeFocused();

    await more.click();
    const contextItem = page.getByRole("menuitemradio", { name: "上下文" });
    await contextItem.focus();
    await page.keyboard.press("Enter");
    await expect(menu).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "上下文" })).toBeFocused();
    await expect(page.getByRole("tabpanel")).toContainText("暂无上下文");
  });
});

test("Split-panel drag has no easing or leftover interception", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/workspace");

  const separator = page.getByRole("separator", {
    name: "调整任务与活动面板宽度",
  });
  const result = await separator.evaluate(async (separatorElement) => {
    const taskPanel = document.querySelector<HTMLElement>(
      '[aria-labelledby="agent-task-heading"]',
    );
    const activityPanel = document.querySelector<HTMLElement>(
      '[aria-label="活动面板"]',
    );
    if (!taskPanel || !activityPanel) return null;
    const beforeTaskWidth = taskPanel.getBoundingClientRect().width;
    const beforeActivityWidth = activityPanel.getBoundingClientRect().width;

    const box = separatorElement.getBoundingClientRect();
    separatorElement.dispatchEvent(
      new MouseEvent("mousedown", {
        bubbles: true,
        clientX: box.left,
        clientY: box.top + box.height / 2,
      }),
    );
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => resolve()),
    );

    const transitionDurations = [
      getComputedStyle(taskPanel).transitionDuration,
      getComputedStyle(activityPanel).transitionDuration,
    ];
    for (const offset of [12, 24, 36]) {
      document.dispatchEvent(
        new MouseEvent("mousemove", {
          bubbles: true,
          clientX: box.left + offset,
          clientY: box.top + box.height / 2,
        }),
      );
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
    }
    document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
    await new Promise<void>((resolve) =>
      requestAnimationFrame(() => resolve()),
    );

    return {
      beforeTaskWidth,
      beforeActivityWidth,
      afterTaskWidth: taskPanel.getBoundingClientRect().width,
      afterActivityWidth: activityPanel.getBoundingClientRect().width,
      transitionDurations,
      bodyCursor: document.body.style.cursor,
      bodyUserSelect: document.body.style.userSelect,
    };
  });

  const dragResult = requireValue(result, "split-panel drag result");
  expect(dragResult.transitionDurations).toEqual(["0s", "0s"]);
  expect(dragResult.afterTaskWidth).toBeGreaterThan(0);
  expect(dragResult.afterActivityWidth).toBeGreaterThan(0);
  expect(dragResult.afterTaskWidth).not.toBe(dragResult.beforeTaskWidth);
  expect(dragResult.afterActivityWidth).not.toBe(
    dragResult.beforeActivityWidth,
  );
  expect(dragResult.bodyCursor).toBe("");
  expect(dragResult.bodyUserSelect).toBe("");
  const activityToggle = page.getByRole("button", { name: "收起活动面板" });
  await activityToggle.click();
  await expect(
    page.getByRole("button", { name: "展开活动面板" }),
  ).toBeFocused();
});

test("Public share route renders the fixed safe boundary", async ({ page }) => {
  const errors = collectRuntimeErrors(page);
  const failedResponses: string[] = [];
  await page.route("**/api/public/shares/demo-token", (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: "{}" }),
  );
  page.on("response", (response) => {
    if (response.status() >= 400) failedResponses.push(response.url());
  });

  await page.goto("http://127.0.0.1:15173/share/demo-token");

  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();
  await expect(
    page.getByText("该链接可能无效、已撤销或已过期。"),
  ).toBeVisible();

  const retry = page.getByRole("button", { name: "重试" });
  const returnHome = page.getByRole("link", { name: "返回首页" });
  await expect(retry).toBeVisible();
  await expect(returnHome).toBeVisible();
  await expect(retry.locator("xpath=..")).toHaveCSS("display", "flex");
  await expect(retry).toHaveCSS("border-top-style", "solid");
  const retryMinHeight = Number.parseFloat(
    await retry.evaluate((element) => getComputedStyle(element).minHeight),
  );
  expect(retryMinHeight).toBeGreaterThanOrEqual(40);
  const retryBox = await requireBoundingBox(retry, "share retry button");
  const returnHomeBox = await requireBoundingBox(returnHome, "share home link");
  expect(retryBox.x).toBeLessThan(returnHomeBox.x);
  await retry.click();
  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();

  await expect(returnHome).toHaveAttribute("href", "/");
  expect(await page.locator("body").innerText()).not.toContain("demo-token");
  expect(
    failedResponses.filter(
      (url) => !url.includes("/api/public/shares/demo-token"),
    ),
  ).toEqual([]);
  expect(
    errors.filter((error) => !error.startsWith("Failed to load resource:")),
  ).toEqual([]);
});

test("Public share route never creates a private session", async ({ page }) => {
  const sessionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/sessions")) {
      sessionRequests.push(request.url());
    }
  });

  await page.goto("http://127.0.0.1:15173/share/demo-token");
  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();

  expect(sessionRequests).toEqual([]);
});

test("returning home from the share boundary lands on the Workspace host", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:15173/share/demo-token");
  await page.getByRole("link", { name: "返回首页" }).click();

  await expect(page).toHaveURL(/\/workspace$/u);
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
});
