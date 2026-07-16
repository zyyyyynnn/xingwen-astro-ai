import { expect, test } from "@playwright/test";

function collectRuntimeErrors(page: import("@playwright/test").Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("brand site remains useful without client-side JavaScript", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  await page.goto("http://127.0.0.1:4321/");

  await expect(page).toHaveTitle(/星文智析/);
  await expect(page.getByRole("heading", { name: "星文智析" })).toBeVisible();
  await expect(
    page.getByText(/面向天文科研证据整合与可复现分析的智能工作平台/),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "进入科研工作台" }),
  ).toHaveAttribute("href", "http://localhost:5173/workspace");

  await context.close();
});

test("brand site exposes a clear not-found page", async ({ page }) => {
  await page.goto("http://127.0.0.1:4321/missing-page");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});

test("brand site has no runtime console errors", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:4321/");
  await expect(page.getByRole("heading", { name: "星文智析" })).toBeVisible();
  expect(errors).toEqual([]);
});

for (const entry of [
  ["/", "科研工作台入口"],
  ["/tour", "引导入口"],
  ["/workspace", "科研工作区"],
  ["/share/demo-token", "共享入口"],
] as const) {
  test(`workspace route ${entry[0]} is directly addressable`, async ({
    page,
  }) => {
    const errors = collectRuntimeErrors(page);

    await page.goto(`http://127.0.0.1:5173${entry[0]}`);

    await expect(page.getByRole("heading", { name: entry[1] })).toBeVisible();
    await expect(
      page.getByRole("navigation", { name: "主要导航" }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("workspace renders its not-found boundary", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/not-a-route");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});
