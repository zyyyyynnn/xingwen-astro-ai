import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import {
  createHttpRepositories,
  createSessionManager,
} from "@xingwen/data-access";

const API_ORIGIN =
  process.env.REAL_INTEGRATION_API_ORIGIN ?? "http://localhost:8000";

function cookieFetch(): typeof fetch {
  let cookie = "";
  return async (input, init) => {
    const headers = new Headers(init?.headers);
    if (cookie) headers.set("Cookie", cookie);
    const response = await fetch(input, { ...init, headers });
    const responseHeaders = response.headers as Headers & {
      getSetCookie?: () => string[];
    };
    const setCookie =
      responseHeaders.getSetCookie?.()[0] ?? response.headers.get("set-cookie");
    if (setCookie) cookie = setCookie.split(";", 1)[0] ?? "";
    return response;
  };
}

test("real HTTP Research Thread reaches the configured Qwen runtime", async () => {
  test.skip(
    process.env.REAL_INTEGRATION_QWEN_ENABLED !== "1",
    "BLOCKED: REAL_INTEGRATION_QWEN_ENABLED=1 and a configured API DASHSCOPE_API_KEY are required for live model evidence.",
  );

  const fetchImpl = cookieFetch();
  const session = createSessionManager({ baseUrl: API_ORIGIN, fetchImpl });
  await session.ensureSession();
  const repositories = createHttpRepositories({
    baseUrl: API_ORIGIN,
    fetchImpl,
    session,
  });
  const project = await repositories.projects.create({
    name: "Live Research Thread evidence",
    description: "Provider-backed integration evidence",
    caseKey: "exoplanet_host_star" as never,
    idempotencyKey: `thread-project-${String(Date.now())}`,
  });

  const turn = await repositories.researchThread.submit(project.id, {
    message:
      "比较 2020 年后的公开 TESS 系外行星候选体及其宿主恒星质量、半径和有效温度；仅使用 NASA 系外行星档案，交付结构化数据、字段字典、文献候选与证据图谱，证据覆盖率至少 80%。",
    answerToQuestionId: null,
    idempotencyKey: `thread-turn-${String(Date.now())}`,
  });

  expect([
    "clarification_required",
    "draft_ready",
    "partial",
    "unsupported",
    "refused",
  ]).toContain(turn.outcome);
  expect(turn.entries.map((entry) => entry.kind)).toEqual(
    expect.arrayContaining([
      "user_message",
      "assistant_analysis",
      "assistant_message",
    ]),
  );
  const persisted = await repositories.researchThread.list(project.id);
  expect(persisted.items.length).toBeGreaterThanOrEqual(turn.entries.length);
  expect(persisted.items.every((entry) => entry.publicContent.length > 0)).toBe(
    true,
  );
});

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("real browser persists Research Thread and exposes the Run Record path", async ({
  page,
}) => {
  test.skip(
    process.env.REAL_INTEGRATION_QWEN_ENABLED !== "1",
    "BLOCKED: REAL_INTEGRATION_QWEN_ENABLED=1 and a configured API DASHSCOPE_API_KEY are required for live model evidence.",
  );
  const runtimeErrors = collectRuntimeErrors(page);
  const apiRequests: string[] = [];
  const apiResponses: string[] = [];
  const requestFailures: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) {
      apiRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) {
      requestFailures.push(
        `${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`,
      );
    }
  });
  page.on("response", (response) => {
    if (new URL(response.url()).pathname.startsWith("/api/")) {
      apiResponses.push(`${String(response.status())} ${response.url()}`);
    }
  });

  await page.goto("/workspace");
  const rootLayout = page.getByTestId("root-layout");
  const loadFailure = page.getByRole("heading", { name: "页面载入失败" });
  await expect
    .poll(async () =>
      Math.max(await rootLayout.count(), await loadFailure.count()),
    )
    .toBeGreaterThan(0);
  if ((await rootLayout.count()) === 0) {
    throw new Error(
      `Workspace load failed. responses=${JSON.stringify(apiResponses)} failures=${JSON.stringify(requestFailures)} runtime=${JSON.stringify(runtimeErrors)}`,
    );
  }
  await expect(rootLayout).toBeVisible();
  await expect(page.getByRole("heading", { name: "新研究" })).toBeVisible();

  await page.getByRole("button", { name: "新建研究项目" }).click();
  const projectName = `浏览器真实纵向链 ${String(Date.now())}`;
  await page.getByRole("textbox", { name: "项目名称" }).fill(projectName);
  await page
    .getByRole("textbox", { name: "研究说明" })
    .fill("验证 Session、协议、运行快照与公开活动的真实闭环");
  await page.getByRole("button", { name: "创建并进入项目" }).click();

  await expect(page.locator("#research-project-heading")).toHaveText(
    projectName,
  );
  const intent =
    "比较 2020 年后的公开 TESS 系外行星候选体及其宿主恒星质量、半径和有效温度；仅使用 NASA 系外行星档案，交付结构化数据、字段字典、文献候选与证据图谱，证据覆盖率至少 80%。";
  await page.getByRole("textbox", { name: "输入研究消息" }).fill(intent);
  await page.getByRole("button", { name: "发送研究消息" }).click();
  await expect(page.getByText(intent, { exact: true })).toBeVisible();

  const draftButton = page.getByRole("button", { name: "查看协议" });
  for (
    let clarificationRound = 0;
    clarificationRound < 3;
    clarificationRound += 1
  ) {
    const answerButton = page
      .getByRole("button", { name: /回答这个问题|填写其他回答/u })
      .last();
    try {
      await expect
        .poll(async () =>
          Math.max(await draftButton.count(), await answerButton.count()),
        )
        .toBeGreaterThan(0);
    } catch (error) {
      throw new Error(
        `Research turn did not reach a protocol outcome. responses=${JSON.stringify(apiResponses)} failures=${JSON.stringify(requestFailures)} runtime=${JSON.stringify(runtimeErrors)}`,
        { cause: error },
      );
    }
    if ((await draftButton.count()) > 0) break;
    await answerButton.click();
    await page
      .getByRole("textbox", { name: "输入研究消息" })
      .fill(
        "研究范围限定为 2020 年后的公开 TESS 候选体和 NASA 系外行星档案宿主星参数；交付结构化数据、字段字典、文献候选与证据图谱，证据覆盖率至少 80%。",
      );
    await page.getByRole("button", { name: "发送研究消息" }).click();
  }
  await expect(draftButton).toBeVisible();
  expect(runtimeErrors).toEqual([]);

  await draftButton.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "确认研究协议" }).click();
  const confirmedContractButton = page.getByRole("button", {
    name: "研究协议 · 已确认",
  });
  await expect(confirmedContractButton).toBeVisible();
  await confirmedContractButton.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "开始真实研究" }).click();
  await expect(page.getByRole("region", { name: "研究过程" })).toBeVisible();

  for (const width of [1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await expect(page.getByTestId("interactive-chat-box")).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <=
          document.documentElement.clientWidth,
      ),
    ).toBe(true);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    page.getByRole("complementary", { name: "悬浮研究概览" }),
  ).toHaveCSS("transition-property", "none");
  await page.evaluate(() => {
    document.documentElement.style.fontSize = "200%";
  });
  await expect(page.getByTestId("interactive-chat-box")).toBeVisible();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.evaluate(() => {
    document.documentElement.style.removeProperty("font-size");
  });
  await expect
    .poll(() =>
      apiRequests.some(
        (request) =>
          request.startsWith("GET ") &&
          /\/api\/runs\/[^/]+$/u.test(request.split(" ", 2)[1] ?? ""),
      ),
    )
    .toBe(true);
  await expect
    .poll(() =>
      apiRequests.some(
        (request) => request.startsWith("GET ") && request.includes("/steps"),
      ),
    )
    .toBe(true);
  expect(runtimeErrors).toEqual([]);

  await page.reload();
  await expect(page.getByTestId("root-layout")).toBeVisible();
  await expect(page.locator("#research-project-heading")).toHaveText(
    projectName,
  );
  await expect(
    page.getByRole("complementary", { name: "悬浮研究概览" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "研究过程" })).toBeVisible();

  expect(
    requestFailures.filter((failure) => !failure.includes("net::ERR_ABORTED")),
  ).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});
