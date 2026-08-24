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

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("real Compose exposes the current empty Research Workspace without provider secrets", async ({
  page,
}) => {
  const runtimeErrors = collectRuntimeErrors(page);
  const requestFailures: string[] = [];
  page.on("requestfailed", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) {
      requestFailures.push(
        `${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`,
      );
    }
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace");
  await expect(page.getByTestId("root-layout")).toBeVisible();
  await expect(page.getByText("开始你的研究", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "输入研究消息" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "添加研究资料" }),
  ).toBeVisible();

  // Sidebar owns the single explicit Project creation action.
  await expect(page.getByRole("button", { name: "新建研究" })).toHaveCount(1);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: "配置模型服务" }).click();
  await expect(page.getByRole("dialog", { name: "模型服务" })).toBeVisible();
  await expect(page.getByLabel("Base URL")).toHaveValue(
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
  );
  await expect(page.getByLabel("Base URL")).toHaveAttribute("readonly");
  await page.getByRole("combobox", { name: "连接方式" }).click();
  await page.getByRole("option", { name: "自定义 OpenAI 兼容接口" }).click();
  await expect(page.getByLabel("Base URL")).not.toHaveAttribute("readonly");
  await expect(page.getByText("qwen3.7-max")).toHaveCount(0);
  await expect(
    page.getByRole("textbox", { name: "API 密钥", exact: true }),
  ).toHaveValue("");
  await page.getByRole("button", { name: "后续配置" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  for (const viewport of [
    { width: 1440, height: 900 },
    { width: 1280, height: 800 },
    { width: 1024, height: 768 },
  ]) {
    await page.setViewportSize(viewport);
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
  await expect(page.getByTestId("interactive-chat-box")).toBeVisible();
  expect(
    requestFailures.filter((failure) => !failure.includes("net::ERR_ABORTED")),
  ).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});

test("mandatory browser path establishes a Project, exposes public analysis, confirms Contract, and starts the returned Contract", async ({
  page,
}) => {
  const runtimeErrors = collectRuntimeErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace");

  const goal =
    "比较公开系外行星候选体及其宿主恒星参数，并形成可核验的数据结果。";
  const composer = page.getByRole("textbox", { name: "输入研究消息" });
  await composer.fill(goal);
  await page.getByRole("button", { name: "发送研究消息" }).click();

  await expect(
    page.getByTestId("user-message").getByText(goal, { exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/workspace\/[^/]+$/);
  await expect(page.getByTestId("collapsible-thinking")).toBeVisible();
  await expect(
    page.getByTestId("agent-message-stream").locator("article").nth(1),
  ).toBeVisible();
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认协议并开始研究" }),
  ).toBeVisible();

  const confirmResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/contracts$/.test(
        new URL(response.url()).pathname,
      ),
  );
  const runRequestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      /\/api\/projects\/[^/]+\/runs$/.test(new URL(request.url()).pathname),
  );
  await page.getByRole("button", { name: "确认协议并开始研究" }).click();
  const [confirmResponse, runRequest] = await Promise.all([
    confirmResponsePromise,
    runRequestPromise,
  ]);
  expect(confirmResponse.ok()).toBe(true);
  const confirmed = (await confirmResponse.json()) as { data: { id: string } };
  const runPayload = runRequest.postDataJSON() as { contract_id: string };
  expect(runPayload.contract_id).toBe(confirmed.data.id);

  await expect(page.getByText("已确认", { exact: true })).toHaveCount(1);
  // The queued state is mirrored by the topbar and research plan section, so
  // scope the lifecycle assertion to its canonical control.
  await expect(
    page
      .getByTestId("run-lifecycle-controls")
      .getByText("已排队", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "输入研究消息" }),
  ).toBeEnabled();
  await expect(page.getByRole("button", { name: "停止研究" })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
});

test("mandatory real HTTP fixture path renders private Evidence and a frozen public share", async ({
  page,
}) => {
  const runtimeErrors = collectRuntimeErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace");

  const goal = "整理公开系外行星宿主星参数并交付结构化数据。";
  await page.getByRole("textbox", { name: "输入研究消息" }).fill(goal);
  await page.getByRole("button", { name: "发送研究消息" }).click();
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible();
  const projectId = new URL(page.url()).pathname
    .split("/")
    .filter(Boolean)
    .at(-1);
  expect(projectId).toBeTruthy();

  const bootstrap = await page.evaluate(
    async ({ apiOrigin, projectId }) => {
      async function json(response: Response) {
        if (!response.ok)
          throw new Error(`${response.status} ${await response.text()}`);
        return response.json();
      }
      const session = await json(
        await fetch(`${apiOrigin}/api/sessions`, {
          method: "POST",
          credentials: "include",
        }),
      );
      const csrf = session.data.csrf_token as string;
      const headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf,
      };
      const project = await json(
        await fetch(`${apiOrigin}/api/projects/${projectId}`, {
          credentials: "include",
        }),
      );
      const draftId = project.data.active_draft_id as string;
      const draft = await json(
        await fetch(`${apiOrigin}/api/contracts/drafts/${draftId}`, {
          credentials: "include",
        }),
      );
      const confirmed = await json(
        await fetch(`${apiOrigin}/api/projects/${projectId}/contracts`, {
          method: "POST",
          credentials: "include",
          headers: { ...headers, "Idempotency-Key": "browser-fixture-confirm" },
          body: JSON.stringify({
            draft_id: draftId,
            expected_draft_version: draft.data.version,
          }),
        }),
      );
      const run = await json(
        await fetch(`${apiOrigin}/api/projects/${projectId}/runs`, {
          method: "POST",
          credentials: "include",
          headers: { ...headers, "Idempotency-Key": "browser-fixture-run" },
          body: JSON.stringify({
            contract_id: confirmed.data.id,
            execution_mode: "demo_replay",
          }),
        }),
      );
      const seeded = await json(
        await fetch(
          `${apiOrigin}/api/test/bootstrap?run_id=${encodeURIComponent(run.data.id)}`,
          {
            method: "POST",
            credentials: "include",
            headers,
          },
        ),
      );
      return {
        runId: run.data.id as string,
        versionId: seeded.data.artifact_version_id as string,
      };
    },
    { apiOrigin: API_ORIGIN, projectId: projectId ?? "" },
  );
  expect(bootstrap.runId).toBeTruthy();
  expect(bootstrap.versionId).toBeTruthy();

  await page.reload();
  // The published result appears as an in-thread result card (title heading
  // plus an open action) and in the Right Rail result index.
  await expect(
    page.getByRole("heading", { name: "Exoplanet host-star dataset" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看完整结果" }).first().click();
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  const returnButton = fullscreen.getByRole("button", { name: "返回研究" });
  const evidenceButton = fullscreen.getByRole("button", {
    name: "证据",
    exact: true,
  });
  await expect(fullscreen).toBeVisible();
  await expect(fullscreen).toHaveAttribute("aria-modal", "true");
  await expect(returnButton).toBeFocused();
  await expect(page.getByText("演示数据", { exact: true })).toBeVisible();

  await page.setViewportSize({ width: 1024, height: 768 });
  expect(
    await fullscreen.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  expect(
    await fullscreen
      .getByTestId("artifact-fullscreen-header")
      .evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);

  await expect(fullscreen).not.toHaveAttribute("aria-hidden", "true");
  await expect(evidenceButton).toBeVisible();
  await evidenceButton.click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await expect(page.getByText("来源内容", { exact: true })).toBeVisible();
  await expect(page.getByText("来源", { exact: true })).toBeVisible();
  await expect(page.getByText(/获取于/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("heading", { name: "研究证据" })).toHaveCount(0);

  await fullscreen.getByRole("button", { name: "分享", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "分享研究结果" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "创建链接" }).click();
  const shareLink = page.getByLabel("分享链接");
  await expect(shareLink).toHaveValue(/\/share\/[^/]+$/);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: new URL(page.url()).origin,
  });
  await page.getByRole("button", { name: "复制链接" }).click();
  await expect(page.getByText("已复制", { exact: true })).toBeVisible();
  const shareUrl = await shareLink.inputValue();

  await page.goto(shareUrl);
  await expect(
    page.getByRole("heading", { name: "Exoplanet host-star dataset" }).first(),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("共享科研结果")
      .getByRole("heading", { name: "Exoplanet host-star dataset" }),
  ).toBeVisible();
  await expect(page.getByText(/创建分享时冻结的公开副本/)).toBeVisible();
  await expect(page.locator('meta[name="referrer"]')).toHaveAttribute(
    "content",
    "no-referrer",
  );
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "查看证据 1", exact: true }).click();
  await expect(page.getByRole("heading", { name: "证据 1" })).toBeVisible();
  await expect(page.getByText("来源类型", { exact: true })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
});

test("provider-backed Research Thread reaches the configured Qwen runtime", async () => {
  test.skip(
    process.env.REAL_INTEGRATION_QWEN_ENABLED !== "1",
    "REAL_INTEGRATION_QWEN_ENABLED=1 and DASHSCOPE_API_KEY are required for provider-backed verification.",
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
    expect.arrayContaining(["user_message", "assistant_message"]),
  );
  const persisted = await repositories.researchThread.list(project.id);
  expect(persisted.items.length).toBeGreaterThanOrEqual(turn.entries.length);
  expect(persisted.items.every((entry) => entry.publicContent.length > 0)).toBe(
    true,
  );
});
