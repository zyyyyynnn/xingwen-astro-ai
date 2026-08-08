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

test("Workspace right-panel toggle stays anchored while the panel collapses", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const leftSidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const rightPanel = page.locator("#workspace-activity-panel");
  const rightPanelContent = rightPanel.locator(":scope > div").first();
  await expect(leftSidebar).toHaveCSS("transition-property", "width");
  await expect(rightPanel).toHaveCSS("transition-property", "width");
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
  const initialPanelBox = await rightPanel.boundingBox();
  const initialContentBox = await rightPanelContent.boundingBox();
  expect(before).not.toBeNull();
  expect(initialHeadingBox).not.toBeNull();
  expect(initialPanelBox).not.toBeNull();
  expect(initialContentBox).not.toBeNull();
  expect(
    Math.abs(initialPanelBox!.width - initialContentBox!.width),
  ).toBeLessThan(1);

  await collapse.click();
  const expand = page.getByRole("button", { name: "展开活动面板" });
  await expect(expand).toBeVisible();
  await expect(expand).toBeFocused();

  const collapseFrames = await expand.evaluate(async (button) => {
    const buttonCenters: number[] = [];
    const headingWidths: number[] = [];
    const headingHeights: number[] = [];
    const heading = document.querySelector<HTMLElement>(
      "#workspace-activity-panel .oh-empty-state p",
    );
    if (!heading) throw new Error("Activity heading is missing");
    for (let frame = 0; frame < 16; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const buttonRect = button.getBoundingClientRect();
      const headingRect = heading.getBoundingClientRect();
      buttonCenters.push(buttonRect.x + buttonRect.width / 2);
      headingWidths.push(headingRect.width);
      headingHeights.push(headingRect.height);
    }
    return { buttonCenters, headingWidths, headingHeights };
  });

  expect(
    Math.max(...collapseFrames.buttonCenters) -
      Math.min(...collapseFrames.buttonCenters),
  ).toBeLessThan(1);
  expect(
    Math.abs(
      collapseFrames.buttonCenters.at(-1)! - (before!.x + before!.width / 2),
    ),
  ).toBeLessThan(1);
  expect(
    Math.max(...collapseFrames.headingWidths) -
      Math.min(...collapseFrames.headingWidths),
  ).toBeLessThan(1);
  expect(
    Math.max(...collapseFrames.headingHeights) -
      Math.min(...collapseFrames.headingHeights),
  ).toBeLessThan(1);
  expect(collapseFrames.headingHeights.at(-1)).toBe(initialHeadingBox!.height);
  const collapsedPanelBox = await rightPanel.boundingBox();
  const collapsedContentBox = await rightPanelContent.boundingBox();
  expect(collapsedPanelBox).not.toBeNull();
  expect(collapsedContentBox).not.toBeNull();
  expect(collapsedPanelBox!.width).toBeLessThanOrEqual(1);
  expect(
    Math.abs(collapsedContentBox!.width - initialContentBox!.width),
  ).toBeLessThan(1);
  const collapsedIntersection = await activityHeading.evaluate(
    (heading) =>
      new Promise<number>((resolve) => {
        const observer = new IntersectionObserver(([entry]) => {
          observer.disconnect();
          resolve(entry?.intersectionRatio ?? 0);
        });
        observer.observe(heading);
      }),
  );
  expect(collapsedIntersection).toBe(0);

  await expand.click();
  await expect(collapse).toBeFocused();
  const expansionFrames = await collapse.evaluate(async (button) => {
    const buttonCenters: number[] = [];
    const headingHeights: number[] = [];
    const heading = document.querySelector<HTMLElement>(
      "#workspace-activity-panel .oh-empty-state p",
    );
    if (!heading) throw new Error("Activity heading is missing");
    for (let frame = 0; frame < 16; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const buttonRect = button.getBoundingClientRect();
      buttonCenters.push(buttonRect.x + buttonRect.width / 2);
      headingHeights.push(heading.getBoundingClientRect().height);
    }
    return { buttonCenters, headingHeights };
  });
  expect(
    Math.max(...expansionFrames.buttonCenters) -
      Math.min(...expansionFrames.buttonCenters),
  ).toBeLessThan(1);
  expect(
    Math.max(...expansionFrames.headingHeights) -
      Math.min(...expansionFrames.headingHeights),
  ).toBeLessThan(1);
  const expandedIntersection = await activityHeading.evaluate(
    (heading) =>
      new Promise<number>((resolve) => {
        const observer = new IntersectionObserver(([entry]) => {
          observer.disconnect();
          resolve(entry?.intersectionRatio ?? 0);
        });
        observer.observe(heading);
      }),
  );
  expect(expandedIntersection).toBeGreaterThan(0);
});

test("Sidebar toggle tracks the rail edge throughout collapse and expansion", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  const samples = await sidebar.evaluate(async (sidebarElement) => {
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
    const readings = [readGeometry()];

    toggle.click();
    for (let frame = 0; frame < 14; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      readings.push(readGeometry());
    }
    toggle.click();
    for (let frame = 0; frame < 14; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      readings.push(readGeometry());
    }
    return readings;
  });

  expect(samples).toHaveLength(29);
  const initialToggleGap = samples[0].toggleRightGap;
  const initialNewTaskCenter = samples[0].newTaskIconCenter;
  expect(
    Math.max(
      ...samples.map(({ toggleRightGap }) =>
        Math.abs(toggleRightGap - initialToggleGap),
      ),
    ),
  ).toBeLessThanOrEqual(3);
  expect(
    Math.max(
      ...samples.map(({ newTaskIconCenter }) =>
        Math.abs(newTaskIconCenter - initialNewTaskCenter),
      ),
    ),
  ).toBeLessThanOrEqual(3);
});

test("Sidebar text remains horizontal on the first expansion frames", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const sidebar = page.getByRole("complementary", { name: "工作台侧栏" });
  await page.getByRole("button", { name: "收起侧栏" }).click();
  await expect(sidebar).toHaveCSS("width", "56px");

  const textHeights = await sidebar.evaluate(async (sidebarElement) => {
    const toggle = sidebarElement.querySelector<HTMLButtonElement>(
      'button[aria-label="展开侧栏"]',
    );
    if (!toggle) return [];

    toggle.click();
    const samples: Array<{ brand: number; emptyTask: number }> = [];
    for (let frame = 0; frame < 4; frame += 1) {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const brandTitle = sidebarElement.querySelector<HTMLElement>(
        ".xw-brand-mark__title",
      );
      const emptyTask = sidebarElement.querySelector<HTMLElement>(
        '[aria-label="任务列表"] p',
      );
      if (brandTitle && emptyTask) {
        samples.push({
          brand: brandTitle.getBoundingClientRect().height,
          emptyTask: emptyTask.getBoundingClientRect().height,
        });
      }
    }
    return samples;
  });

  expect(textHeights).toHaveLength(4);
  expect(
    Math.max(...textHeights.map(({ brand }) => brand)),
  ).toBeLessThanOrEqual(24);
  expect(
    Math.max(...textHeights.map(({ emptyTask }) => emptyTask)),
  ).toBeLessThanOrEqual(24);
});

test("Composer stays transparent without a full-width hover line", async ({
  page,
}) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  const composer = page.getByTestId("chat-input-container");
  await expect(composer).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");

  const gripIndicator = page
    .getByRole("separator", { name: "调整指令输入区高度" })
    .locator("span");
  await page.getByTestId("chat-input").hover();
  await expect(gripIndicator).toHaveCSS("opacity", "0");
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
  await expect(search.locator("..")).toHaveCSS("border-bottom-width", "2px");

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
  await expect(composerSeparator).toHaveAttribute("aria-valuenow", "128");
  await composerSeparator.focus();
  await page.keyboard.press("ArrowUp");
  await expect(composerSeparator).toHaveAttribute("aria-valuenow", "144");
  await composerSeparator.focus();
  await page.keyboard.press("Home");
  await expect(composerSeparator).toHaveAttribute("aria-valuenow", "112");
});

test("Split-panel drag uses one shield without width easing", async ({
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

    let shieldAdds = 0;
    const observer = new MutationObserver((records) => {
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (
            node instanceof HTMLElement &&
            node.hasAttribute("data-panel-drag-shield")
          ) {
            shieldAdds += 1;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true });

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

    const transitionProperties = [
      getComputedStyle(taskPanel).transitionProperty,
      getComputedStyle(activityPanel).transitionProperty,
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
    observer.disconnect();

    return { shieldAdds, transitionProperties };
  });

  expect(result).not.toBeNull();
  expect(result!.transitionProperties).toEqual(["none", "none"]);
  expect(result!.shieldAdds).toBe(1);
  await expect(page.locator("[data-panel-drag-shield]")).toHaveCount(0);
});

test("Workspace host exposes no retired product UI", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/workspace");

  await expect(page.locator("#research-canvas")).toHaveCount(0);
  await expect(page.locator(".research-atlas")).toHaveCount(0);
  await expect(page.locator(".provenance-observatory")).toHaveCount(0);
  await expect(page.locator(".workspace-shell")).toHaveCount(0);
  await expect(page.getByText(/研究引导|引导/u)).toHaveCount(0);
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
