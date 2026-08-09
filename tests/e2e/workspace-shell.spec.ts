import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

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
    header.boundingBox(),
    rightHeader.boundingBox(),
  ]);
  expect(headerBox).not.toBeNull();
  expect(rightHeaderBox).not.toBeNull();
  expect(headerBox!.height).toBe(48);
  expect(rightHeaderBox!.height).toBe(48);

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
  await page.keyboard.press("ArrowRight");
  await expect(panelSeparator).toHaveAttribute("aria-valuenow", "60");

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
  const composerBox = await composer.boundingBox();
  const viewport = page.viewportSize();
  expect(composerBox).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(composerBox!.y + composerBox!.height).toBeGreaterThan(
    viewport!.height - 180,
  );
}

test("root entry redirects to the Workspace host", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/");
  await expect(page).toHaveURL(/\/workspace$/u);
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Workspace host renders the desktop shell", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/workspace");

  const heading = page.getByRole("heading", { name: "研究工作台" });
  const runtimeStatus = page.getByText("运行服务未连接", { exact: true });
  await expect(heading).toBeVisible();
  await expect(runtimeStatus).toHaveCount(1);
  const headingBox = await heading.boundingBox();
  const runtimeStatusBox = await runtimeStatus.boundingBox();
  expect(headingBox).not.toBeNull();
  expect(runtimeStatusBox).not.toBeNull();
  expect(
    Math.abs(
      headingBox!.y +
        headingBox!.height / 2 -
        (runtimeStatusBox!.y + runtimeStatusBox!.height / 2),
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
  await page.goto("http://127.0.0.1:5173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const sidebarBar = sidebar.locator("header");
  const workspaceBar = page
    .getByRole("heading", { name: "研究工作台" })
    .locator("xpath=ancestor::header");
  const activityBar = page
    .getByRole("tablist", { name: "工作区面板" })
    .locator("..");

  const barBoxes = await Promise.all(
    [sidebarBar, workspaceBar, activityBar].map((bar) => bar.boundingBox()),
  );
  for (const box of barBoxes) {
    expect(box).not.toBeNull();
    expect(box!.y).toBe(0);
    expect(box!.height).toBe(48);
  }
  for (const bar of [sidebarBar, workspaceBar, activityBar]) {
    await expect(bar).toHaveCSS("border-bottom-width", "1px");
  }

  await expect(page.locator(".xw-brand-mark__title")).toHaveCSS(
    "font-size",
    "14px",
  );
  await expect(page.getByRole("heading", { name: "研究工作台" })).toHaveCSS(
    "font-size",
    "14px",
  );
  await expect(page.getByRole("tab", { name: "活动" })).toHaveCSS(
    "font-size",
    "14px",
  );
  await expect(page.getByText("运行服务未连接", { exact: true })).toHaveCSS(
    "font-size",
    "12px",
  );
});

test.describe("Workspace desktop shell at 1440×900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("keeps the desktop mechanics aligned", async ({ page }) => {
    await page.goto("http://127.0.0.1:5173/workspace");
    await assertDesktopWorkspacePath(page);
  });
});

test.describe("Workspace desktop shell at 1280×800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("keeps the desktop mechanics aligned at normal scale", async ({
    page,
  }) => {
    await page.goto("http://127.0.0.1:5173/workspace");
    await assertDesktopWorkspacePath(page);
  });
});

test("Workspace right-panel toggle stays anchored while the panel collapses", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

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
  const before = await collapse.boundingBox();
  const activityHeading = rightPanel.getByText("尚无 Agent 活动", {
    exact: true,
  });
  const initialHeadingBox = await activityHeading.boundingBox();
  expect(before).not.toBeNull();
  expect(initialHeadingBox).not.toBeNull();
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
  expect(collapsedSurfaceMetrics).not.toBeNull();
  expect(
    Math.abs(
      collapsedSurfaceMetrics!.surfaceWidth -
        collapsedSurfaceMetrics!.taskPanelWidth,
    ),
  ).toBeLessThanOrEqual(1);
  const collapsedAnchor = await expand.boundingBox();
  expect(collapsedAnchor).not.toBeNull();
  expect(Math.abs(collapsedAnchor!.x - before!.x)).toBeLessThanOrEqual(2);

  await expand.click();
  await expect(collapse).toBeFocused();
  await expect(rightPanel).toBeVisible();
  await expect(rightPanel).toHaveAttribute("aria-hidden", "false");
  expect(await rightPanel.evaluate((element) => element.inert)).toBe(false);
  const expandedHeadingBox = await activityHeading.boundingBox();
  expect(expandedHeadingBox).not.toBeNull();
  expect(
    Math.abs(expandedHeadingBox!.height - initialHeadingBox!.height),
  ).toBeLessThanOrEqual(1);
  const expandedAnchor = await collapse.boundingBox();
  expect(expandedAnchor).not.toBeNull();
  expect(Math.abs(expandedAnchor!.x - before!.x)).toBeLessThanOrEqual(2);
  await expect(activityHeading).toBeVisible();
});

test("Sidebar toggle tracks the rail edge throughout collapse and expansion", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const geometry = await sidebar.evaluate((sidebarElement) => {
    const toggle = sidebarElement.querySelector<HTMLButtonElement>(
      'button[aria-label="收起侧栏"]',
    );
    const initialNewTaskIcon = sidebarElement.querySelector<SVGElement>(
      'button[aria-label="新建任务"] svg',
    );
    if (!toggle || !initialNewTaskIcon) return [];

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

  expect(geometry).not.toBeNull();
  expect(
    Math.abs(
      geometry!.expanded.toggleRightGap - geometry!.restored.toggleRightGap,
    ),
  ).toBeLessThanOrEqual(2);
  expect(
    Math.abs(
      geometry!.expanded.newTaskIconCenter -
        geometry!.restored.newTaskIconCenter,
    ),
  ).toBeLessThanOrEqual(2);
});

test("Sidebar text stays horizontal after expansion", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  await page.getByRole("button", { name: "收起侧栏" }).click();
  await expect(sidebar).toHaveCSS("width", "56px");

  const textHeights = await sidebar.evaluate((sidebarElement) => {
    const toggle = sidebarElement.querySelector<HTMLButtonElement>(
      'button[aria-label="展开侧栏"]',
    );
    if (!toggle) return [];

    toggle.click();
    const brandTitle = sidebarElement.querySelector<HTMLElement>(
      ".xw-brand-mark__title",
    );
    const emptyTask = sidebarElement.querySelector<HTMLElement>(
      '[aria-label="任务列表"] p',
    );
    if (!brandTitle || !emptyTask) return null;
    return {
      brand: brandTitle.getBoundingClientRect().height,
      emptyTask: emptyTask.getBoundingClientRect().height,
    };
  });

  expect(textHeights).not.toBeNull();
  expect(textHeights!.brand).toBeLessThanOrEqual(24);
  expect(textHeights!.emptyTask).toBeLessThanOrEqual(24);
});

test("Composer stays transparent without a full-width hover line", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const composer = page.getByTestId("chat-input-container");
  await expect(composer).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(composer.locator("..")).toHaveCSS("border-top-width", "0px");
  const composerBox = await composer.boundingBox();
  const conversationBox = await page
    .getByTestId("conversation-main")
    .boundingBox();
  expect(composerBox).not.toBeNull();
  expect(conversationBox).not.toBeNull();
  expect(composerBox!.height).toBeGreaterThanOrEqual(60);
  expect(composerBox!.height).toBeLessThanOrEqual(64);
  expect(composerBox!.y + composerBox!.height).toBeGreaterThan(
    conversationBox!.y + conversationBox!.height - 24,
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
  await page.goto("http://127.0.0.1:5173/workspace");
  const trigger = page.getByRole("button", { name: "打开命令菜单" });
  await trigger.focus();

  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", { name: "搜索命令" });
  await expect(search).toBeVisible();
  await expect(search).toBeFocused();
  await expect(search).toHaveCSS("outline-style", "none");
  await expect(search.locator("..")).toHaveCSS("border-bottom-width", "1px");

  await page.keyboard.press("Tab");
  await expect(search).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "命令菜单" })).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

test("Workspace tabs and split panel support keyboard control", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

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
  await expect(separator).toHaveAttribute("aria-valuenow", "58");
  await page.keyboard.press("ArrowRight");
  await expect(separator).toHaveAttribute("aria-valuenow", "60");

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
  await page.goto("http://127.0.0.1:5173/workspace");

  const input = page.getByRole("textbox", { name: "向 Agent 发送指令" });
  const composer = page.getByTestId("chat-input-container");
  const actions = page.getByTestId("chat-input-actions");
  const before = await composer.boundingBox();
  expect(before).not.toBeNull();

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
    .toBeGreaterThan(before!.height);
  const after = await composer.boundingBox();
  const actionsBox = await actions.boundingBox();
  expect(after).not.toBeNull();
  expect(actionsBox).not.toBeNull();
  expect(after!.height).toBeGreaterThan(before!.height);
  expect(actionsBox!.y + actionsBox!.height).toBeLessThanOrEqual(
    after!.y + after!.height + 1,
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
    await page.goto("http://127.0.0.1:5173/workspace");
    await page.addStyleTag({
      content: "html { font-size: 200% !important; }",
    });

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
  await page.goto("http://127.0.0.1:5173/workspace");

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

  expect(result).not.toBeNull();
  expect(result!.transitionDurations).toEqual(["0s", "0s"]);
  expect(result!.afterTaskWidth).toBeGreaterThan(0);
  expect(result!.afterActivityWidth).toBeGreaterThan(0);
  expect(result!.afterTaskWidth).not.toBe(result!.beforeTaskWidth);
  expect(result!.afterActivityWidth).not.toBe(result!.beforeActivityWidth);
  expect(result!.bodyCursor).toBe("");
  expect(result!.bodyUserSelect).toBe("");
  const activityToggle = page.getByRole("button", { name: "收起活动面板" });
  await activityToggle.click();
  await expect(
    page.getByRole("button", { name: "展开活动面板" }),
  ).toBeFocused();
});

test("Public share route renders the fixed safe boundary", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/share/demo-token");

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
  await expect(retry).toHaveCSS("min-height", "40px");
  expect((await retry.boundingBox())!.x).toBeLessThan(
    (await returnHome.boundingBox())!.x,
  );
  await retry.click();
  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();

  await expect(returnHome).toHaveAttribute("href", "/");
  expect(await page.locator("body").innerText()).not.toContain("demo-token");
  expect(errors).toEqual([]);
});

test("Public share route never creates a private session", async ({ page }) => {
  const sessionRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/sessions")) {
      sessionRequests.push(request.url());
    }
  });

  await page.goto("http://127.0.0.1:5173/share/demo-token");
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
  await page.goto("http://127.0.0.1:5173/share/demo-token");
  await page.getByRole("link", { name: "返回首页" }).click();

  await expect(page).toHaveURL(/\/workspace$/u);
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
});
