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

/** Fixture ArtifactVersion/Evidence publication result (#131 narrowed shape). */
interface BootstrapData {
  readonly run_id: string;
  readonly artifact_id: string;
  readonly artifact_version_id: string;
  readonly source_snapshot_id: string;
  readonly evidence_id: string;
  readonly execution_mode: "demo_replay";
  readonly source_mode: "fixture";
  readonly scenario: "exoplanet_host_star";
}

interface BootstrapEnvelope {
  readonly data: BootstrapData;
}

/** The full public-runtime chain plus the published fixture artifact ids. */
interface ChainData {
  readonly project_id: string;
  readonly draft_id: string;
  readonly contract_id: string;
  readonly run_id: string;
  readonly artifact_version_id: string;
  readonly evidence_id: string;
}

// Domain-shaped (camelCase) contract input consumed by the repository port;
// the adapter maps it to the snake_case transport DTO. Mirrors the frozen
// exoplanet host-star main case so drafts stay valid and hash-parity holds.
const NEW_CONTRACT_INPUT = {
  researchGoal: "Integrate exoplanet candidates and host-star parameters",
  targetObjects: ["exoplanet_candidate", "host_star"],
  dataRequirements: { unitPolicy: "canonical" },
  requestedFields: ["planet.toi_id", "star.tic_id"],
  sourceScope: { allowedSources: ["nasa_exoplanet_archive"] },
  paperSearchScope: {
    keywords: ["exoplanet", "host star parameters"],
    yearFrom: 2018,
    yearTo: 2026,
    sourceIds: ["nasa_exoplanet_archive"],
    maxCandidates: 5,
  },
  outputRequirements: ["dataset", "graph"],
  evidenceRequirements: {
    requireLocator: true,
    requireSourceSnapshot: true,
    minimumCoverage: 1,
  },
  qualityConstraints: {
    sourceCompletenessMin: 1,
    unitConsistencyMin: 1,
  },
} as const;

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

/**
 * Build the full M1 chain over the *public* runtime — create Project, Draft,
 * confirm Contract, create a demo_replay Run — then publish the deterministic
 * fixture ArtifactVersion/Evidence onto that run via the narrowed test-only
 * bootstrap. Nothing here injects prerequisite resources: the bootstrap only
 * attaches fixture outputs to a session-owned run.
 */
async function buildChainWithAdapter() {
  const fetchImpl = cookieFetch();
  const session = createSessionManager({ baseUrl: API_ORIGIN, fetchImpl });
  await session.ensureSession();
  const repositories = createHttpRepositories({
    baseUrl: API_ORIGIN,
    fetchImpl,
    session,
  });

  const project = await repositories.projects.create({
    name: "Exoplanet host-star integration",
    description: "Evidence-bound integration for the frozen main case",
    caseKey: "exoplanet_host_star" as never,
    idempotencyKey: `chain-project-${String(Date.now())}`,
  });
  const draft = await repositories.contracts.createDraft(project.id, {
    intent: "Integrate exoplanet candidates and host-star parameters",
    contract: NEW_CONTRACT_INPUT as never,
    idempotencyKey: `chain-draft-${String(Date.now())}`,
  });
  const contract = await repositories.contracts.confirm(
    project.id,
    draft.id,
    draft.version,
  );
  const run = await repositories.runs.create({
    projectId: project.id,
    contractId: contract.id,
    executionMode: "demo_replay",
    idempotencyKey: `chain-run-${String(Date.now())}`,
  });

  const headers = new Headers({ "Content-Type": "application/json" });
  session.attachCsrf(headers);
  const response = await fetchImpl(
    `${API_ORIGIN}/api/test/bootstrap?run_id=${String(run.id)}`,
    { method: "POST", credentials: "include", headers },
  );
  expect(response.status).toBe(201);
  const published = ((await response.json()) as BootstrapEnvelope).data;

  const data: ChainData = {
    project_id: String(project.id),
    draft_id: String(draft.id),
    contract_id: String(contract.id),
    run_id: published.run_id,
    artifact_version_id: published.artifact_version_id,
    evidence_id: published.evidence_id,
  };
  return { data, repositories };
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
  const { data, repositories: http } = await buildChainWithAdapter();
  const contractId = data.contract_id;
  const runId = data.run_id;
  const artifactVersionId = data.artifact_version_id;
  const evidenceId = data.evidence_id;

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
  const { data, repositories: http } = await buildChainWithAdapter();
  const fixture = createFixtureRepositories(exoplanetHostStarFixture);

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
    if (request.url().startsWith(`${API_ORIGIN}/api/`)) {
      apiRequests.push(`${request.method()} ${request.url()}`);
    }
  });
  page.on("requestfailed", (request) => {
    requestFailures.push(
      `${request.method()} ${request.url()} ${request.failure()?.errorText ?? "unknown"}`,
    );
  });

  // #131: the browser creates the Project and Draft through the public
  // runtime UI (entry page) — no test-only bootstrap injection of prerequisites.
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "科研工作台入口" }),
  ).toBeVisible();
  try {
    await expect(page.getByText("HTTP 适配器", { exact: true })).toBeVisible();
  } catch {
    throw new Error(
      `HTTP session failed: ${JSON.stringify({ runtimeErrors, requestFailures, apiRequests })}`,
    );
  }

  const projectCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/projects") &&
      response.status() === 201,
  );
  await page.getByLabel("Project 名称").fill("Exoplanet host-star integration");
  await page.getByRole("button", { name: "创建 Project" }).click();
  const projectId = (
    (await (await projectCreated).json()) as { data: { id: string } }
  ).data.id;

  const draftCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/projects/${projectId}/contract-drafts`) &&
      response.status() === 201,
  );
  await page
    .getByRole("button", { name: "创建 Draft 并进入引导" })
    .first()
    .click();
  const draftId = (
    (await (await draftCreated).json()) as { data: { id: string } }
  ).data.id;
  const seed = { project_id: projectId, draft_id: draftId };

  await expect(page.getByRole("heading", { name: "研究引导" })).toBeVisible();

  await page
    .getByLabel("研究意图")
    .fill("Integrate exoplanet candidates with host-star evidence");
  await page
    .getByLabel("研究目标")
    .fill("Integrate exoplanet candidates and host-star parameters");
  const draftSaved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().includes(`/api/contracts/drafts/${seed.draft_id}`),
  );
  await page.getByRole("button", { name: "保存草稿" }).click();
  expect((await draftSaved).status()).toBe(200);

  const contractCreated = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith(`/api/projects/${seed.project_id}/contracts`),
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
      response.url().endsWith(`/api/projects/${seed.project_id}/runs`),
  );
  await page.getByRole("button", { name: "启动运行" }).click();
  const runResponse = await runCreated;
  expect(runResponse.status()).toBe(201);
  const runId = ((await runResponse.json()) as { data: { id: string } }).data
    .id;
  await expect(page.getByText(/demo_replay \/ queued/).first()).toBeVisible();

  // Publish the deterministic fixture ArtifactVersion/Evidence onto the
  // UI-created demo_replay run through the narrowed bootstrap. Resuming the
  // page's session (shared cookie jar) yields a CSRF valid for that owner.
  const resumeForBootstrap = await context.request.post(
    `${API_ORIGIN}/api/sessions`,
  );
  expect(resumeForBootstrap.status()).toBe(201);
  const bootstrapCsrf = (
    (await resumeForBootstrap.json()) as { data: { csrf_token: string } }
  ).data.csrf_token;
  const completed = await context.request.post(
    `${API_ORIGIN}/api/test/bootstrap?run_id=${runId}`,
    { headers: { "X-CSRF-Token": bootstrapCsrf } },
  );
  expect(completed.status()).toBe(201);
  const completeSeed = ((await completed.json()) as BootstrapEnvelope).data;
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
    `${API_ORIGIN}/api/sessions`,
  );
  expect(concurrentSession.status()).toBe(201);
  const concurrentSessionPayload = (await concurrentSession.json()) as {
    data: { csrf_token: string };
  };
  const serverWrite = await context.request.put(
    `${API_ORIGIN}/api/projects/${seed.project_id}/workspace-snapshot`,
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
        .endsWith(`/api/projects/${seed.project_id}/workspace-snapshot`) &&
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
        .endsWith(`/api/projects/${seed.project_id}/workspace-snapshot`) &&
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
      response.url().endsWith(`/api/projects/${seed.project_id}/shares`),
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
    if (request.url().includes("/api/sessions")) {
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

  const revokeUrl = `${API_ORIGIN}/api/projects/${seed.project_id}/shares/${share.data.id}`;
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
    apiRequests.some((request) => request.includes("/api/projects/")),
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
