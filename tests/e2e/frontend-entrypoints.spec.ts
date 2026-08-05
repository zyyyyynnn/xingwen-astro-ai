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
  await expect(
    page.getByRole("heading", {
      name: /让每一颗系外行星候选体/,
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "开始演示" })).toHaveAttribute(
    "href",
    "http://localhost:5173/tour",
  );
  await expect(page.getByRole("link", { name: "进入工作台" })).toHaveAttribute(
    "href",
    "http://localhost:5173/workspace",
  );
  await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();

  await context.close();
});

test("brand site exposes a clear not-found page", async ({ page }) => {
  await page.goto("http://127.0.0.1:4321/missing-page");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});

test("brand site has no runtime console errors", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:4321/");
  await expect(
    page.getByRole("heading", {
      name: /让每一颗系外行星候选体/,
    }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("brand site hero has a Poster fallback image", async ({ page }) => {
  await page.goto("http://127.0.0.1:4321/");
  // The Poster <img> is always present in the DOM; it stays visible until
  // the WebGL first frame is ready (covered by homepage-visual.spec.ts).
  const poster = page.locator(".hero-poster");
  await expect(poster).toHaveCount(1);
  await expect(poster).toHaveAttribute("alt", /系外行星 Transit/);
});

for (const entry of [
  ["/", "科研工作台入口", "入口"],
  ["/tour", "研究引导", "引导"],
  ["/workspace", "科研工作区", "工作区"],
  ["/share/demo-token", "共享结果不可用", null],
] as const) {
  test(`workspace route ${entry[0]} is directly addressable`, async ({
    page,
  }) => {
    const errors = collectRuntimeErrors(page);

    await page.goto(`http://127.0.0.1:5173${entry[0]}`);

    await expect(page.getByRole("heading", { name: entry[1] })).toBeVisible();
    const navigation = page.getByRole("navigation", { name: "主要导航" });
    if (entry[2]) {
      await expect(navigation).toBeVisible();
    } else {
      await expect(navigation).toHaveCount(0);
    }
    expect(errors).toEqual([]);
  });
}

test("workspace renders its not-found boundary", async ({ page }) => {
  await page.goto("http://127.0.0.1:5173/not-a-route");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});
