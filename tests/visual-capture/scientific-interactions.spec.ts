import { expect, test } from "@playwright/test";

test("graph fits its initial canvas and keeps keyboard selection readable", async ({
  page,
}) => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(
      "/workspace/proj_01JEXAMPLE?artifactVersionId=artv_graph_01",
    );
    const canvas = page.locator(".graph-workspace__canvas-holder");
    const nodes = page.locator(".react-flow__node");
    await expect(nodes.first()).toBeVisible();
    const clippedNodes = (selectedOnly: boolean) =>
      canvas.evaluate((element, selected) => {
        const bounds = element.getBoundingClientRect();
        return [
          ...element.querySelectorAll(
            selected ? ".react-flow__node.selected" : ".react-flow__node",
          ),
        ].flatMap((node) => {
          const rect = node.getBoundingClientRect();
          return rect.left < bounds.left ||
            rect.right > bounds.right ||
            rect.top < bounds.top ||
            rect.bottom > bounds.bottom
            ? [node.getAttribute("aria-label")]
            : [];
        });
      }, selectedOnly);
    await expect.poll(() => clippedNodes(false)).toEqual([]);
    const rightmostIndex = await nodes.evaluateAll((elements) =>
      elements.reduce(
        (rightmost, element, index) =>
          element.getBoundingClientRect().right >
          elements[rightmost]!.getBoundingClientRect().right
            ? index
            : rightmost,
        0,
      ),
    );
    const target = nodes.nth(rightmostIndex);
    const title = await target.locator("strong").innerText();
    await expect(target.locator("strong")).toHaveAttribute("title", title);
    await target.focus();
    await page.keyboard.press("Enter");
    const inspector = page.locator(".graph-workspace__side-inspector");
    await expect(inspector.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.locator(".react-flow__node.selected")).toHaveCount(1);
    await expect.poll(() => clippedNodes(true)).toEqual([]);
    await expect.poll(() => clippedNodes(false)).toEqual([]);
    const wrappedLabels = await inspector.locator("dt").evaluateAll((labels) =>
      labels.flatMap((label) => {
        const range = document.createRange();
        range.selectNodeContents(label);
        return range.getClientRects().length > 1 ? [label.textContent] : [];
      }),
    );
    expect(wrappedLabels).toEqual([]);
    await page.getByRole("button", { name: "聚焦选择" }).click();
    await expect.poll(() => clippedNodes(true)).toEqual([]);
  }
});

test("light-curve axes remain readable at supported desktop sizes", async ({
  page,
}) => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 1440, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    await page.goto(
      "/workspace/proj_toi_transit?artifactVersionId=artv_b_lc_01",
    );
    for (const name of [/确定性演示序列/, /相位展示/, /目录周期标记/]) {
      await page.getByRole("tab", { name }).click();
      const plot = page.locator(".light-curve-workspace__plot svg");
      await expect(plot).toBeVisible();
      const problems = await plot.evaluate((svg) => {
        const bounds = svg.getBoundingClientRect();
        const labels = [
          ...svg.querySelectorAll(".scientific-plot__axis-label"),
        ].map((label) => label.getBoundingClientRect());
        return [
          ...svg.querySelectorAll(".scientific-plot__ticks text"),
        ].flatMap((tick) => {
          const rect = tick.getBoundingClientRect();
          const clipped =
            rect.left < bounds.left ||
            rect.right > bounds.right ||
            rect.top < bounds.top ||
            rect.bottom > bounds.bottom;
          const overlap = labels.some(
            (label) =>
              rect.left < label.right &&
              rect.right > label.left &&
              rect.top < label.bottom &&
              rect.bottom > label.top,
          );
          return clipped || overlap ? [tick.textContent] : [];
        });
      });
      expect(problems).toEqual([]);
    }
  }
});

test("WWT preserves the requested angular field of view and refreshes actual time", async ({
  page,
}) => {
  await page.goto(
    "/workspace/proj_l9859_spectroscopy?artifactVersionId=artv_c_wwt_01",
  );
  await expect(page.getByTestId("wwt-viewport")).toHaveAttribute(
    "data-state",
    "ready",
    { timeout: 30000 },
  );
  const readback = page.getByRole("definition");
  const fov = page
    .locator(".wwt-viewport__readback div")
    .filter({ hasText: "实际视场" })
    .locator("dd");
  await expect(fov).toHaveText("2.500°");
  await page.getByRole("button", { name: "定位与视角" }).click();
  await page.getByLabel("视场（度）", { exact: true }).fill("1.2");
  await page.getByRole("button", { name: "前往坐标", exact: true }).click();
  await expect(fov).toHaveText("1.200°");
  await page.keyboard.press("Escape");
  const clock = page
    .locator(".wwt-viewport__readback div")
    .filter({ hasText: "实际时间" })
    .locator("dd");
  const before = await clock.innerText();
  await expect(clock).not.toHaveText(before);
  await expect(readback.filter({ hasText: "使用当前系统时间" })).toBeVisible();
});

test("empty composer shows its hint again after text is removed", async ({
  page,
}) => {
  await page.goto("/workspace");
  const input = page.getByRole("textbox", { name: "输入研究消息" });
  await expect(input).toBeVisible();
  const hint = () =>
    input.evaluate((element) => getComputedStyle(element, "::before").content);
  expect(await hint()).not.toBe("none");
  await input.fill("检查恒星参数");
  expect(await hint()).toBe("none");
  await input.fill("");
  expect(await hint()).not.toBe("none");
});

test("coordinate errors stay inside the open editor and empty numbers are rejected", async ({
  page,
}) => {
  await page.goto(
    "/workspace/proj_l9859_spectroscopy?artifactVersionId=artv_c_wwt_01",
  );
  await page.getByRole("button", { name: "定位与视角" }).click();
  await page.getByLabel("中心赤经（小时）").fill("");
  await page.getByRole("button", { name: "前往坐标", exact: true }).click();
  const editor = page.locator(".wwt-scene-controls__coordinate-panel");
  await expect(editor.getByRole("alert")).toContainText("赤经必须");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "观测点", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "使用本地地平坐标系" }),
  ).toBeVisible();
  await expect(
    page.locator(".wwt-scene-controls__observer").getByRole("alert"),
  ).toHaveCount(0);
});
