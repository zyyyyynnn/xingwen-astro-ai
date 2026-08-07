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
    without({ ...fixtureArtifacts[0]!, kind: "export" }, [
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
  const fixturePublicForBootstrap = {
    ...fixturePublic,
    artifactVersions: fixturePublic.artifactVersions.map((version) => ({
      ...version,
      kind: "export" as const,
    })),
  };
  expect(normalizeDomain(httpPublic, httpAliases, publicOmissions)).toEqual(
    normalizeDomain(fixturePublicForBootstrap, fixtureAliases, publicOmissions),
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

test("real browser session stays silent on the retired-safe Workspace and Share boundaries", async ({
  browser,
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

  // The host shell renders statically: the Workspace runtime boots the real
  // HTTP adapter but no API traffic leaves the page.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "研究工作台" })).toBeVisible();
  expect(apiRequests).toEqual([]);
  expect(requestFailures).toEqual([]);

  // Build the full M1 chain over the live API through the public runtime
  // (same code path and payloads as the parity tests above).
  const { data, repositories } = await buildChainWithAdapter();
  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
  const share = await repositories.shares.create(asEntityId(data.project_id), {
    title: "X-01 browser share",
    artifactVersionIds: [asEntityId(data.artifact_version_id)],
    evidenceIds: [asEntityId(data.evidence_id)],
    expiresAt,
    redactionPolicy: "public_metadata_only",
  });

  // The public share route stays a fixed safe boundary: no private session,
  // no share content, and the token never reaches the DOM or the console.
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

  await publicPage.goto(`/share/${share.shareToken}`);
  await expect(
    publicPage.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();
  await expect(
    publicPage.getByText("该链接可能无效、已撤销或已过期。"),
  ).toBeVisible();
  expect(publicSessionRequests).toEqual([]);
  expect(await publicPage.locator("body").innerText()).not.toContain(
    share.shareToken,
  );
  expect(publicErrors.join("\n")).not.toContain(share.shareToken);

  await publicPage.reload();
  await expect(
    publicPage.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();
  expect(publicSessionRequests).toEqual([]);

  // Revoking the share keeps the boundary fixed and session-free.
  await repositories.shares.revoke(
    asEntityId(data.project_id),
    asEntityId(share.id),
  );
  await publicPage.reload();
  await expect(
    publicPage.getByRole("heading", { name: "共享结果当前不可用" }),
  ).toBeVisible();
  expect(publicSessionRequests).toEqual([]);

  // Chromium reports a completed 404 fetch as a console error once the API
  // no longer resolves the revoked token; the boundary and UI prove it stays
  // fixed and quiet.
  expect(
    publicErrors.filter(
      (error) =>
        error !==
        "Failed to load resource: the server responded with a status of 404 (Not Found)",
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
  await publicContext.close();
});
