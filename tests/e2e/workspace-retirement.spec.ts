import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

/**
 * A-20 退役验收：旧工作台入口（/ 与 /tour）的迁移语义、/workspace 宿主
 * 与 /share 固定边界。旧产品层选择器与假能力文案一旦回归即失败。
 */

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

const VALID_TOUR_QUERY =
  "projectId=proj_01JEXAMPLE&draftId=rcd_01JEXAMPLE&contractId=rc_01JEXAMPLE&runId=run_01JEXAMPLE";

test("legacy entry redirects to the Workspace host", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/");
  await expect(page).toHaveURL(/\/workspace$/u);
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("legacy tour route forwards validated identifiers and drops unknown parameters", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await page.goto(
    `http://127.0.0.1:5173/tour?${VALID_TOUR_QUERY}&utm_source=external`,
  );
  await expect(page).toHaveURL(/\/workspace/u);

  const url = new URL(page.url());
  expect(url.pathname).toBe("/workspace");
  expect(url.searchParams.get("projectId")).toBe("proj_01JEXAMPLE");
  expect(url.searchParams.get("draftId")).toBe("rcd_01JEXAMPLE");
  expect(url.searchParams.get("contractId")).toBe("rc_01JEXAMPLE");
  expect(url.searchParams.get("runId")).toBe("run_01JEXAMPLE");
  expect(url.searchParams.get("utm_source")).toBeNull();

  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("legacy tour route never forwards invalid identifiers", async ({
  page,
}) => {
  const errors = collectRuntimeErrors(page);

  await page.goto(`http://127.0.0.1:5173/tour?projectId=${"a".repeat(129)}`);

  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  const url = new URL(page.url());
  expect(url.pathname).toBe("/workspace");
  expect(url.search).toBe("");
  expect(errors).toEqual([]);
});

test("Workspace host renders the desktop shell", async ({ page }) => {
  const errors = collectRuntimeErrors(page);

  await page.goto("http://127.0.0.1:5173/workspace");

  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  await expect(page.getByText("星文智析")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "跳到主要内容" }),
  ).toHaveAttribute("href", "#main-content");
  await expect(page.getByText("请使用桌面设备")).toBeHidden();
  expect(errors).toEqual([]);
});

test("Workspace host exposes no legacy product UI", async ({ page }) => {
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
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(
    page.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();

  await expect(page.getByRole("link", { name: "返回首页" })).toHaveAttribute(
    "href",
    "/",
  );
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
