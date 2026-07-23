import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import {
  createFixtureRepositories,
  createHttpRepositories,
  createSessionManager,
  exoplanetHostStarFixture,
} from "@xingwen/data-access";
import { asEntityId } from "@xingwen/domain";

const API_ORIGIN = process.env.X01_API_ORIGIN ?? "http://localhost:8000";

interface BootstrapData {
  readonly project_id: string;
  readonly draft_id: string;
  readonly contract_id: string | null;
  readonly run_id: string | null;
  readonly artifact_version_id: string | null;
  readonly evidence_id: string | null;
  readonly execution_mode: "demo_replay";
  readonly source_mode: "fixture";
  readonly scenario: "exoplanet_host_star";
}

interface BootstrapEnvelope {
  readonly data: BootstrapData;
}

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

async function bootstrapWithAdapter(complete = true) {
  const fetchImpl = cookieFetch();
  const session = createSessionManager({ baseUrl: API_ORIGIN, fetchImpl });
  await session.ensureSession();
  const headers = new Headers({ "Content-Type": "application/json" });
  session.attachCsrf(headers);
  const response = await fetchImpl(
    `${API_ORIGIN}/api/v2/test/bootstrap?complete=${String(complete)}`,
    { method: "POST", credentials: "include", headers },
  );
  expect(response.status).toBe(201);
  const payload = (await response.json()) as BootstrapEnvelope;
  return {
    data: payload.data,
    repositories: createHttpRepositories({
      baseUrl: API_ORIGIN,
      fetchImpl,
      session,
    }),
  };
}

function without(value: object, keys: readonly string[]) {
  return Object.fromEntries(
    Object.entries(value).filter(([key]) => !keys.includes(key)),
  );
}

function expectNoSnakeCase(value: unknown): void {
  if (Array.isArray(value)) {
    for (const item of value) expectNoSnakeCase(item);
    return;
  }
  if (value === null || typeof value !== "object") return;
  for (const [key, nested] of Object.entries(value)) {
    if (!key.includes(".")) expect(key).not.toContain("_");
    expectNoSnakeCase(nested);
  }
}

function normalizeDomain(
  value: unknown,
  aliases: ReadonlyMap<string, string>,
  omittedKeys: ReadonlySet<string>,
): unknown {
  if (typeof value === "string") {
    let normalized = value;
    const orderedAliases = [...aliases].sort(
      ([left], [right]) => right.length - left.length,
    );
    for (const [source, alias] of orderedAliases) {
      normalized = normalized.split(source).join(alias);
    }
    return normalized;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normalizeDomain(item, aliases, omittedKeys));
  }
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key]) => !omittedKeys.has(key))
      .map(([key, nested]) => [
        key,
        normalizeDomain(nested, aliases, omittedKeys),
      ]),
  );
}

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("real HTTP Adapter returns the same M1 Domain Model as the frozen Fixture", async () => {
  const { data, repositories: http } = await bootstrapWithAdapter();
  const contractId = data.contract_id;
  const runId = data.run_id;
  const artifactVersionId = data.artifact_version_id;
  const evidenceId = data.evidence_id;
  if (
    contractId === null ||
    runId === null ||
    artifactVersionId === null ||
    evidenceId === null
  ) {
    throw new Error("Integration bootstrap omitted required M1 entity ids");
  }

  const fixture = createFixtureRepositories(exoplanetHostStarFixture);
  const [httpProject, fixtureProject] = await Promise.all([
    http.projects.getById(asEntityId(data.project_id)),
    fixture.projects.getById(asEntityId("proj_01JEXAMPLE")),
  ]);
  const [httpDraft, fixtureDraft] = await Promise.all([
    http.contracts.getDraftById(asEntityId(data.draft_id)),
    fixture.contracts.getDraftById(asEntityId("rcd_01JEXAMPLE")),
  ]);
  const [httpContract, fixtureContract] = await Promise.all([
    http.contracts.getContractById(asEntityId(contractId)),
    fixture.contracts.getContractById(asEntityId("rc_01JEXAMPLE")),
  ]);
  const [httpRun, fixtureRun] = await Promise.all([
    http.runs.getById(asEntityId(runId)),
    fixture.runs.getById(asEntityId("run_01JEXAMPLE")),
  ]);
  const [httpArtifacts, fixtureArtifacts] = await Promise.all([
    http.artifacts.listByRun(asEntityId(runId)),
    fixture.artifacts.listByRun(asEntityId("run_01JEXAMPLE")),
  ]);
  const [httpVersion, fixtureVersion] = await Promise.all([
    http.artifacts.getVersion(asEntityId(artifactVersionId)),
    fixture.artifacts.getVersion(asEntityId("artv_dataset_01")),
  ]);
  const [httpEvidence, fixtureEvidence] = await Promise.all([
    http.artifacts.getEvidence(asEntityId(evidenceId)),
    fixture.artifacts.getEvidence(asEntityId("evd_01")),
  ]);
  const recovery = await http.runs.recoverEvents(asEntityId(runId));

  expect(httpProject).not.toBeNull();
  expect(httpDraft).not.toBeNull();
  expect(httpContract).not.toBeNull();
  expect(httpRun).not.toBeNull();
  expect(httpArtifacts).toHaveLength(1);
  expect(httpVersion).not.toBeNull();
  expect(httpEvidence).not.toBeNull();

  expect(
    without(httpProject!, [
      "id",
      "sessionId",
      "activeContractId",
      "latestRunId",
      "createdAt",
      "updatedAt",
    ]),
  ).toEqual(
    without(fixtureProject!, [
      "id",
      "sessionId",
      "activeContractId",
      "latestRunId",
      "createdAt",
      "updatedAt",
    ]),
  );
  expect(
    without(httpDraft!, [
      "id",
      "sessionId",
      "createdAt",
      "updatedAt",
      "expiresAt",
    ]),
  ).toEqual(
    without(fixtureDraft!, [
      "id",
      "sessionId",
      "createdAt",
      "updatedAt",
      "expiresAt",
    ]),
  );
  expect(
    without(httpContract!, [
      "id",
      "projectId",
      "createdFromDraftId",
      "createdAt",
      "contentHash",
    ]),
  ).toEqual(
    without(fixtureContract!, [
      "id",
      "projectId",
      "createdFromDraftId",
      "createdAt",
      "contentHash",
    ]),
  );
  expect(
    without(httpRun!, [
      "id",
      "projectId",
      "contractId",
      "status",
      "progress",
      "startedAt",
      "finishedAt",
      "createdAt",
      "updatedAt",
      "latestEventSequence",
    ]),
  ).toEqual(
    without(fixtureRun!, [
      "id",
      "projectId",
      "contractId",
      "status",
      "progress",
      "startedAt",
      "finishedAt",
      "createdAt",
      "updatedAt",
      "latestEventSequence",
    ]),
  );
  expect(
    without(httpArtifacts[0]!, [
      "id",
      "projectId",
      "createdAt",
      "latestVersionId",
    ]),
  ).toEqual(
    without(fixtureArtifacts[0]!, [
      "id",
      "projectId",
      "createdAt",
      "latestVersionId",
    ]),
  );
  expect(
    without(httpVersion!, [
      "id",
      "artifactId",
      "projectId",
      "createdByRunId",
      "contentHash",
      "inputHash",
      "producer",
      "sourceSnapshotIds",
      "evidenceIds",
      "createdAt",
    ]),
  ).toEqual(
    without(fixtureVersion!, [
      "id",
      "artifactId",
      "projectId",
      "createdByRunId",
      "contentHash",
      "inputHash",
      "producer",
      "sourceSnapshotIds",
      "evidenceIds",
      "createdAt",
    ]),
  );
  expect(
    without(httpEvidence!, [
      "id",
      "artifactVersionId",
      "sourceSnapshotId",
      "createdAt",
    ]),
  ).toEqual(
    without(fixtureEvidence!, [
      "id",
      "artifactVersionId",
      "sourceSnapshotId",
      "createdAt",
    ]),
  );
  expect(recovery.events.length).toBeGreaterThan(1);
  expect(
    Math.max(...recovery.events.map((event) => event.sequence)),
  ).toBeLessThanOrEqual(httpRun!.latestEventSequence);

  for (const entity of [
    httpProject,
    httpDraft,
    httpContract,
    httpRun,
    httpArtifacts,
    httpVersion,
    httpEvidence,
    recovery.events,
  ]) {
    expectNoSnakeCase(entity);
  }
});

test("real HTTP and Fixture adapters align Workspace and Share Domain Models", async () => {
  const { data, repositories: http } = await bootstrapWithAdapter();
  const fixture = createFixtureRepositories(exoplanetHostStarFixture);
  if (
    data.run_id === null ||
    data.artifact_version_id === null ||
    data.evidence_id === null
  ) {
    throw new Error(
      "Complete bootstrap did not return the required entity ids",
    );
  }

  const httpProjectId = asEntityId(data.project_id);
  const httpRunId = asEntityId(data.run_id);
  const httpVersionId = asEntityId(data.artifact_version_id);
  const httpEvidenceId = asEntityId(data.evidence_id);
  const fixtureProjectId = asEntityId("proj_01JEXAMPLE");
  const fixtureRunId = asEntityId("run_01JEXAMPLE");
  const fixtureVersionId = asEntityId("artv_dataset_01");
  const fixtureEvidenceId = asEntityId("evd_01");

  const [httpWorkspace, fixtureWorkspace] = await Promise.all([
    http.workspaces.save(
      httpProjectId,
      {
        layoutPreset: "focus",
        panelSlots: [],
        activeRunId: httpRunId,
        pinnedEvidenceIds: [httpEvidenceId],
        atlasState: null,
        observatoryState: null,
        selectedObjectRef: null,
      },
      0,
    ),
    fixture.workspaces.save(
      fixtureProjectId,
      {
        layoutPreset: "focus",
        panelSlots: [],
        activeRunId: fixtureRunId,
        pinnedEvidenceIds: [fixtureEvidenceId],
        atlasState: null,
        observatoryState: null,
        selectedObjectRef: null,
      },
      0,
    ),
  ]);
  const httpWorkspaceAliases = new Map([
    [httpWorkspace.id, "workspace"],
    [data.project_id, "project"],
    [data.run_id, "run"],
    [data.evidence_id, "evidence"],
  ]);
  const fixtureWorkspaceAliases = new Map([
    [fixtureWorkspace.id, "workspace"],
    ["proj_01JEXAMPLE", "project"],
    ["run_01JEXAMPLE", "run"],
    ["evd_01", "evidence"],
  ]);
  expect(
    normalizeDomain(
      httpWorkspace,
      httpWorkspaceAliases,
      new Set(["updatedAt"]),
    ),
  ).toEqual(
    normalizeDomain(
      fixtureWorkspace,
      fixtureWorkspaceAliases,
      new Set(["updatedAt"]),
    ),
  );

  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  const [httpShare, fixtureShare] = await Promise.all([
    http.shares.create(httpProjectId, {
      title: "X-01 adapter parity share",
      artifactVersionIds: [httpVersionId],
      evidenceIds: [httpEvidenceId],
      expiresAt,
      redactionPolicy: "public_metadata_only",
    }),
    fixture.shares.create(fixtureProjectId, {
      title: "X-01 adapter parity share",
      artifactVersionIds: [fixtureVersionId],
      evidenceIds: [fixtureEvidenceId],
      expiresAt,
      redactionPolicy: "public_metadata_only",
    }),
  ]);
  const [httpListed, fixtureListed, httpPublic, fixturePublic] =
    await Promise.all([
      http.shares.list(httpProjectId),
      fixture.shares.list(fixtureProjectId),
      http.shares.getPublic(httpShare.shareToken),
      fixture.shares.getPublic(fixtureShare.shareToken),
    ]);
  expect(httpPublic).not.toBeNull();
  expect(fixturePublic).not.toBeNull();
  if (httpPublic === null || fixturePublic === null) {
    throw new Error("Created share did not resolve to a public projection");
  }
  const httpPublicVersion = httpPublic.artifactVersions[0];
  const httpPublicEvidence = httpPublic.evidence[0];
  const fixturePublicVersion = fixturePublic.artifactVersions[0];
  const fixturePublicEvidence = fixturePublic.evidence[0];
  if (
    httpPublicVersion === undefined ||
    httpPublicEvidence === undefined ||
    fixturePublicVersion === undefined ||
    fixturePublicEvidence === undefined
  ) {
    throw new Error("Public share omitted its frozen version or evidence");
  }

  const httpAliases = new Map([
    [httpShare.id, "share"],
    [httpShare.shareToken, "share-token"],
    [httpShare.expiresAt, "expires-at"],
    [data.project_id, "project"],
    [data.artifact_version_id, "version"],
    [data.evidence_id, "evidence"],
    [httpPublicVersion.artifactId, "artifact"],
    [httpPublicEvidence.sourceSnapshotId, "source-snapshot"],
  ]);
  const fixtureAliases = new Map([
    [fixtureShare.id, "share"],
    [fixtureShare.shareToken, "share-token"],
    [fixtureShare.expiresAt, "expires-at"],
    ["proj_01JEXAMPLE", "project"],
    ["artv_dataset_01", "version"],
    ["evd_01", "evidence"],
    [fixturePublicVersion.artifactId, "artifact"],
    [fixturePublicEvidence.sourceSnapshotId, "source-snapshot"],
  ]);
  const shareOmissions = new Set(["createdAt"]);
  const publicOmissions = new Set(["contentHash", "createdAt"]);

  expect(normalizeDomain(httpShare, httpAliases, shareOmissions)).toEqual(
    normalizeDomain(fixtureShare, fixtureAliases, shareOmissions),
  );
  expect(normalizeDomain(httpListed, httpAliases, shareOmissions)).toEqual(
    normalizeDomain(fixtureListed, fixtureAliases, shareOmissions),
  );
  expect(normalizeDomain(httpPublic, httpAliases, publicOmissions)).toEqual(
    normalizeDomain(fixturePublic, fixtureAliases, publicOmissions),
  );

  await Promise.all([
    http.shares.revoke(httpProjectId, httpShare.id),
    fixture.shares.revoke(fixtureProjectId, fixtureShare.id),
  ]);
  await expect(http.shares.getPublic(httpShare.shareToken)).resolves.toBeNull();
  await expect(
    fixture.shares.getPublic(fixtureShare.shareToken),
  ).resolves.toBeNull();
});

test("real browser completes Tour to frozen Public Share with conflict and refresh recovery", async ({
  browser,
  context,
  page,
}) => {
  const runtimeErrors = collectRuntimeErrors(page);
  const apiRequests: string[] = [];
  const requestFailures: string[] = [];
  page.on("request", (request) => {
    if (request.url().startsWith(`${API_ORIGIN}/api/v2/`)) {
      apiRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    requestFailures.push(
      `${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`,
    );
  });

  const createdSession = await context.request.post(
    `${API_ORIGIN}/api/v2/sessions`,
  );
  expect(createdSession.status()).toBe(201);
  const sessionPayload = (await createdSession.json()) as {
    data: { csrf_token: string };
  };
  const bootstrapHeaders = { "X-CSRF-Token": sessionPayload.data.csrf_token };
  const partial = await context.request.post(
    `${API_ORIGIN}/api/v2/test/bootstrap?complete=false`,
    { headers: bootstrapHeaders },
  );
  expect(partial.status()).toBe(201);
  const seed = ((await partial.json()) as BootstrapEnvelope).data;
  expect(seed.contract_id).toBeNull();
  expect(seed.run_id).toBeNull();

  const tourSearch = new URLSearchParams({
    projectId: seed.project_id,
    draftId: seed.draft_id,
  });
  await page.goto(`/tour?${tourSearch.toString()}`);
  await expect(page.getByRole("heading", { name: "研究引导" })).toBeVisible();
  try {
    await expect(page.getByText("HTTP 适配器", { exact: true })).toBeVisible();
  } catch {
    throw new Error(
      `HTTP session failed: ${JSON.stringify({ runtimeErrors, requestFailures, apiRequests })}`,
    );
  }

  await page
    .getByLabel("研究意图")
    .fill("Integrate exoplanet candidates with host-star evidence");
  await page
    .getByLabel("研究目标")
    .fill("Integrate exoplanet candidates and host-star parameters");
  const draftSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response
        .url()
        .includes(`/api/v2/research-contract-drafts/${seed.draft_id}`),
  );
  await page.getByRole("button", { name: "保存草稿" }).click();
  expect((await draftSaved).status()).toBe(200);

  const contractCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v2/projects/${seed.project_id}/contracts`),
  );
  await page.getByRole("button", { name: "确认 Contract" }).click();
  const contractResponse = await contractCreated;
  expect(contractResponse.status()).toBe(201);
  const contractId = (
    (await contractResponse.json()) as { data: { id: string } }
  ).data.id;
  await expect(
    page.getByRole("heading", { name: "已确认 Contract" }),
  ).toBeVisible();

  await page.getByLabel("Demo Replay").check();
  const runCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v2/projects/${seed.project_id}/runs`),
  );
  await page.getByRole("button", { name: "启动运行" }).click();
  const runResponse = await runCreated;
  expect(runResponse.status()).toBe(201);
  const runId = ((await runResponse.json()) as { data: { id: string } }).data
    .id;
  await expect(page.getByText(/demo_replay \/ queued/).first()).toBeVisible();

  const completed = await context.request.post(
    `${API_ORIGIN}/api/v2/test/bootstrap?complete=true`,
    { headers: bootstrapHeaders },
  );
  expect(completed.status()).toBe(201);
  const completeSeed = ((await completed.json()) as BootstrapEnvelope).data;
  expect(completeSeed.contract_id).toBe(contractId);
  expect(completeSeed.run_id).toBe(runId);
  expect(completeSeed.artifact_version_id).not.toBeNull();
  expect(completeSeed.evidence_id).not.toBeNull();

  const workspaceSearch = new URLSearchParams({
    projectId: seed.project_id,
    draftId: seed.draft_id,
    contractId,
    runId,
  });
  await page.goto(`/workspace?${workspaceSearch.toString()}`);
  await expect(page.getByRole("heading", { name: "科研工作区" })).toBeVisible();
  await expect(page.getByText("Adapter: HTTP", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Execution: demo_replay", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Source: fixture", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "恢复运行事件" }).click();
  await expect(
    page.getByText(/Deterministic demo_replay fixture published/),
  ).toBeVisible();

  await page
    .getByRole("button", { name: "Exoplanet host-star dataset" })
    .click();
  await page.getByRole("button", { name: completeSeed.evidence_id! }).click();
  await page.getByLabel("布局").selectOption("focus");

  const concurrentSession = await context.request.post(
    `${API_ORIGIN}/api/v2/sessions`,
  );
  expect(concurrentSession.status()).toBe(201);
  const concurrentSessionPayload = (await concurrentSession.json()) as {
    data: { csrf_token: string };
  };
  const serverWrite = await context.request.put(
    `${API_ORIGIN}/api/v2/projects/${seed.project_id}/workspace-snapshot`,
    {
      headers: {
        "X-CSRF-Token": concurrentSessionPayload.data.csrf_token,
        "If-Match": "0",
      },
      data: { layout_preset: "grid", active_run_id: runId },
    },
  );
  expect(serverWrite.status()).toBe(200);

  const conflictResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response
        .url()
        .endsWith(`/api/v2/projects/${seed.project_id}/workspace-snapshot`) &&
      response.status() === 409,
  );
  await page.getByRole("button", { name: "保存工作区" }).click();
  await conflictResponse;
  await expect(
    page.getByRole("heading", { name: "工作区版本冲突" }),
  ).toBeVisible();
  await expect(
    page.getByText("本地更改尚未保存。", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "采用服务器最新版本" }).click();
  await expect(page.getByLabel("布局")).toHaveValue("grid");

  await page
    .getByRole("button", { name: "Exoplanet host-star dataset" })
    .click();
  await page.getByRole("button", { name: completeSeed.evidence_id! }).click();
  await page.getByLabel("布局").selectOption("focus");
  const savedResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "PUT" &&
      response
        .url()
        .endsWith(`/api/v2/projects/${seed.project_id}/workspace-snapshot`) &&
      response.status() === 200,
  );
  await page.getByRole("button", { name: "保存工作区" }).click();
  await savedResponse;
  await expect(
    page.getByText("已保存 revision 2", { exact: true }),
  ).toBeVisible();

  await page.reload();
  await expect(
    page.getByText("已保存 revision 2", { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel("布局")).toHaveValue("focus");
  await expect(
    page.getByText(completeSeed.artifact_version_id!, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText(completeSeed.evidence_id!, { exact: true }).first(),
  ).toBeVisible();

  const shareCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/v2/projects/${seed.project_id}/shares`),
  );
  await page.getByRole("button", { name: "创建只读分享" }).click();
  const shareResponse = await shareCreated;
  expect(shareResponse.status()).toBe(201);
  const share = (await shareResponse.json()) as {
    data: { share_token: string; id: string };
  };
  const shareLink = page.getByRole("link", { name: "打开只读分享" });
  const shareHref = await shareLink.getAttribute("href");
  expect(shareHref).toBe(`/share/${share.data.share_token}`);
  expect(await page.locator("body").innerText()).not.toContain(
    share.data.share_token,
  );
  expect(page.url()).not.toContain(share.data.share_token);
  expect(runtimeErrors.join("\n")).not.toContain(share.data.share_token);

  const publicContext = await browser.newContext({
    baseURL: new URL(page.url()).origin,
  });
  const publicPage = await publicContext.newPage();
  const publicErrors = collectRuntimeErrors(publicPage);
  const publicSessionRequests: string[] = [];
  publicPage.on("request", (request) => {
    if (request.url().includes("/api/v2/sessions")) {
      publicSessionRequests.push(request.url());
    }
  });
  await publicPage.goto(shareHref!);
  await expect(
    publicPage.getByText("只读共享结果", { exact: true }),
  ).toBeVisible();
  await expect(
    publicPage
      .getByRole("region", { name: "ArtifactVersion" })
      .getByText(completeSeed.artifact_version_id!, { exact: true }),
  ).toBeVisible();
  await expect(
    publicPage
      .getByRole("region", { name: "Evidence" })
      .getByText(completeSeed.evidence_id!, { exact: true }),
  ).toBeVisible();
  await expect(
    publicPage.locator("input, textarea, select, button"),
  ).toHaveCount(0);
  expect(publicSessionRequests).toEqual([]);
  expect(await publicPage.locator("body").innerText()).not.toContain(
    share.data.share_token,
  );
  expect(publicErrors).toEqual([]);

  await publicPage.reload();
  await expect(
    publicPage.getByText("只读共享结果", { exact: true }),
  ).toBeVisible();
  expect(publicSessionRequests).toEqual([]);

  const revokeUrl = `${API_ORIGIN}/api/v2/projects/${seed.project_id}/shares/${share.data.id}`;
  const revoked = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" && response.url() === revokeUrl,
  );
  await page
    .getByRole("button", { name: "撤销 Exoplanet host-star dataset v1" })
    .click();
  expect((await revoked).status()).toBe(204);
  await expect(
    page.getByRole("button", { name: "撤销 Exoplanet host-star dataset v1" }),
  ).toHaveCount(0);
  await publicPage.reload();
  await expect(
    publicPage.getByRole("heading", { name: "共享结果不可用" }),
  ).toBeVisible();
  expect(publicSessionRequests).toEqual([]);

  expect(
    apiRequests.some((request) => request.includes("/api/v2/projects/")),
  ).toBe(true);
  expect(
    apiRequests.some((request) => request.includes("/workspace-snapshot")),
  ).toBe(true);
  expect(apiRequests.some((request) => request.includes("/shares"))).toBe(true);
  // Chromium reports a completed 204 fetch as ERR_ABORTED after exposing its
  // response. The status and UI state above prove the revoke completed.
  expect(
    requestFailures.filter(
      (failure) => failure !== `DELETE ${revokeUrl} net::ERR_ABORTED`,
    ),
  ).toEqual([]);
  expect(
    runtimeErrors.filter(
      (error) =>
        !/^Failed to load resource: the server responded with a status of (404 \(Not Found\)|409 \(Conflict\))$/u.test(
          error,
        ),
    ),
  ).toEqual([]);
  expect(
    publicErrors.filter(
      (error) =>
        error !==
        "Failed to load resource: the server responded with a status of 404 (Not Found)",
    ),
  ).toEqual([]);
  expect(
    `${runtimeErrors.join("\n")}\n${publicErrors.join("\n")}`,
  ).not.toContain(share.data.share_token);
  await publicContext.close();
});
