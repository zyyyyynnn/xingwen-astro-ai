import { expect, test, type ConsoleMessage } from "@playwright/test";

import { installWorkspaceHttpFixture } from "./workspace-http-fixture";

test.beforeEach(async ({ page }) => installWorkspaceHttpFixture(page));

function collectRuntimeErrors(
  page: import("@playwright/test").Page,
  shouldIgnore?: (message: ConsoleMessage) => boolean,
) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !shouldIgnore?.(message)) {
      errors.push(message.text());
    }
  });
  return errors;
}

test("brand site remains useful without client-side JavaScript", async ({
  browser,
}) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();

  await page.goto("http://127.0.0.1:14321/");

  await expect(page).toHaveTitle(/星文智析/);
  await expect(
    page.getByRole("heading", { name: /让每一颗系外行星候选体\s*都可溯源/ }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "进入工作台" })).toHaveAttribute(
    "href",
    "http://localhost:5173/workspace",
  );
  await expect(page.getByRole("link", { name: "开始演示" })).toHaveCount(0);
  await expect(page.getByText(/整合系外行星候选体与宿主恒星/)).toBeVisible();

  await context.close();
});

test("brand site exposes a clear not-found page", async ({ page }) => {
  await page.goto("http://127.0.0.1:14321/missing-page");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});

test("brand site has no runtime console errors", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:14321/");
  await expect(
    page.getByRole("heading", { name: /让每一颗系外行星候选体\s*都可溯源/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

for (const entry of [
  ["/", "新研究", true],
  ["/workspace", "新研究", true],
  ["/share/demo-token", "共享结果当前不可用", false],
] as const) {
  test(`workspace route ${entry[0]} is directly addressable`, async ({
    page,
  }) => {
    const expectedMissingShareUrl = entry[0].startsWith("/share/")
      ? `http://localhost:8000/api/public/shares/${entry[0].slice("/share/".length)}`
      : undefined;
    if (expectedMissingShareUrl) {
      await page.route(expectedMissingShareUrl, (route) =>
        route.fulfill({
          status: 404,
          contentType: "application/json",
          body: "{}",
        }),
      );
    }
    const errors = collectRuntimeErrors(
      page,
      expectedMissingShareUrl
        ? (message) =>
            message.location().url === expectedMissingShareUrl &&
            message.text() ===
              "Failed to load resource: the server responded with a status of 404 (Not Found)"
        : undefined,
    );

    await page.goto(`http://127.0.0.1:15173${entry[0]}`);

    await expect(page.getByRole("heading", { name: entry[1] })).toBeVisible();
    const navigation = page.getByRole("navigation", { name: "工作台导航" });
    if (entry[2]) {
      await expect(navigation).toBeVisible();
    } else {
      await expect(navigation).toHaveCount(0);
    }
    expect(errors).toEqual([]);
  });
}

test("workspace renders its not-found boundary", async ({ page }) => {
  await page.goto("http://127.0.0.1:15173/not-a-route");
  await expect(page.getByRole("heading", { name: "页面未找到" })).toBeVisible();
});
