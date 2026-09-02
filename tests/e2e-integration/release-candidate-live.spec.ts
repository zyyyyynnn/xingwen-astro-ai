import { expect, test, type Locator, type Page } from "@playwright/test";
import type {
  ArtifactKind,
  ArtifactVersionDetail,
  ArtifactVersionSummary,
  DatasetArtifactRead,
  FieldDictionaryArtifactRead,
  GraphArtifactRead,
  GraphEdgeRead,
  GraphNodeRead,
  LiteratureClaimRead,
  LiteratureRelationRead,
  PaperCandidateInputBinding,
  PaperCollectionRead,
  PaperSummaryDocumentSourceRead,
  PaperSummaryRead,
  ResearchArtifact,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  ScientificArtifactRead,
  SourceCollectionArtifactRead,
} from "../../packages/contracts/src";
import { exoplanetHostStarFixture } from "@xingwen/data-access";
import { requestApi } from "./api-request";
import {
  readReleaseRuntime,
  readReleaseContainerState,
  readPlanningExecutions,
  restartActiveWorker,
  writeReleaseEvidence as report,
} from "./release-runtime";

const API_ORIGIN =
  process.env.REAL_INTEGRATION_API_ORIGIN ?? "http://127.0.0.1:8000";
const RUNTIME_QWEN_MODEL = process.env.RELEASE_CANDIDATE_QWEN_MODEL?.trim();
const EXPLICIT_REVISION =
  process.env.DASHSCOPE_EXPLICIT_MODEL_REVISION?.trim() || null;
const SOURCE_COMMIT = process.env.RELEASE_CANDIDATE_SOURCE_COMMIT;
const observedRuns = new Set<string>();
const observedProjects = new Set<string>();
const REQUIRED_ARTIFACT_KINDS = [
  "dataset",
  "field_dictionary",
  "source_collection",
  "paper_collection",
  "paper_summary",
  "literature_claims",
  "literature_relations",
  "graph",
] as const;
const SUMMARY_SECTIONS = [
  "background",
  "research_questions",
  "methodology",
  "dataset",
  "experiments",
  "discussion",
  "limitations",
] as const;

export const FULL_TEXT_REVISION_TIMEOUT_MS = 35 * 60_000;

// The repository distributes this author manuscript under its posted license.
// This is a real external input; it is never copied from the fixture bundle.
const PAPER = {
  doi: "10.3847/1538-3881/ab3467",
  title: "The Revised TESS Input Catalog and Candidate Target List",
  fullTextUrl: "https://arxiv.org/pdf/1905.10694",
  evidenceUrl: "https://arxiv.org/abs/1905.10694",
  accessStatement:
    "Author manuscript openly distributed by arXiv under its non-exclusive distribution license; no downstream redistribution license is asserted.",
};

interface ArtifactHandle {
  kind: ArtifactKind;
  title: string;
  detail: ArtifactVersionDetail;
}

async function apiData<T>(page: Page, pathname: string): Promise<T> {
  const response = await requestApi(page.request, API_ORIGIN + pathname);
  return ((await response.json()) as { data: T }).data;
}

const EVIDENCE_STAGE_KINDS: Record<string, readonly string[]> = {
  "live-source-acquisition.json": [
    "dataset",
    "field_dictionary",
    "source_collection",
  ],
  "live-paper-acquisition.json": ["paper_collection"],
  "live-document-summary.json": ["paper_summary"],
  "live-literature-evidence.json": [
    "literature_claims",
    "literature_relations",
  ],
  "live-graph-evidence.json": ["graph"],
};
const writtenEvidenceFiles = new Set<string>();

async function writeIncrementalRunEvidence(page: Page, runId: string) {
  let artifacts: ResearchArtifact[];
  try {
    artifacts = await apiData<ResearchArtifact[]>(
      page,
      "/api/runs/" + runId + "/artifacts?limit=100",
    );
  } catch {
    return;
  }
  const published = artifacts.filter((item) => item.latest_version_id);
  for (const [fileName, kinds] of Object.entries(EVIDENCE_STAGE_KINDS)) {
    if (writtenEvidenceFiles.has(fileName)) continue;
    const stageArtifacts = published.filter((item) =>
      kinds.includes(item.kind),
    );
    if (stageArtifacts.length !== kinds.length) continue;
    await report(fileName, {
      result: "stage_completed",
      run_id: runId,
      artifacts: stageArtifacts.map((item) => ({
        kind: item.kind,
        title: item.title,
        artifact_version_id: item.latest_version_id,
      })),
    });
    writtenEvidenceFiles.add(fileName);
  }
}

async function writeRunFailureEvidence(
  page: Page,
  run: ResearchRun,
): Promise<void> {
  const artifacts = await apiData<ResearchArtifact[]>(
    page,
    "/api/runs/" + run.id + "/artifacts?limit=100",
  ).catch(() => [] as ResearchArtifact[]);
  let runtime: Awaited<ReturnType<typeof readReleaseRuntime>> | null = null;
  try {
    runtime = await readReleaseRuntime(run.id);
  } catch {
    runtime = null;
  }
  const failedAttempt = runtime?.attempts
    .filter((attempt) => attempt.status === "failed")
    .at(-1);
  const failedProducers = failedAttempt
    ? (runtime?.producer_executions ?? []).filter(
        (execution) =>
          execution.step_attempt_id === failedAttempt.id &&
          execution.status !== "completed",
      )
    : [];
  await report("release-candidate-failure.json", {
    source_commit: SOURCE_COMMIT,
    run_id: run.id,
    step_key: failedAttempt?.step ?? null,
    attempt_number: failedAttempt?.attempt_number ?? null,
    error_code: failedAttempt?.error_code ?? run.failure_code ?? null,
    error_class: failedAttempt?.error_class ?? null,
    retryable: failedAttempt?.retryable ?? false,
    upstream_request_id: failedAttempt?.upstream_request_id ?? null,
    producer_errors: failedProducers.map((execution) => ({
      producer_execution_id: execution.id,
      producer_type: execution.producer_type,
      producer_name: execution.producer_name,
      error_code: execution.error_code,
    })),
    completed_artifact_version_ids: artifacts
      .filter((item) => item.latest_version_id)
      .map((item) => item.latest_version_id),
    completed_producer_execution_ids: (runtime?.producer_executions ?? [])
      .filter((item) => item.status === "completed")
      .map((item) => item.id),
    timestamp: new Date().toISOString(),
  }).catch(() => undefined);
}

async function waitForRun(
  page: Page,
  runId: string,
  timeout = 20 * 60_000,
): Promise<ResearchRun> {
  observedRuns.add(runId);
  let run = await apiData<ResearchRun>(page, "/api/runs/" + runId);
  await expect
    .poll(
      async () => {
        run = await apiData<ResearchRun>(page, "/api/runs/" + runId);
        if (
          run.status !== "completed" &&
          run.status !== "failed" &&
          run.status !== "cancelled"
        ) {
          await writeIncrementalRunEvidence(page, runId);
        }
        return run.status;
      },
      { timeout, intervals: [2_000, 3_000, 5_000] },
    )
    .toMatch(/^(completed|failed|cancelled)$/u);
  if (run.status !== "completed") {
    await writeRunFailureEvidence(page, run);
  }
  expect(
    run.status,
    JSON.stringify({
      run_id: run.id,
      failure_code: run.failure_code,
      failure_summary: run.failure_summary,
    }),
  ).toBe("completed");
  return run;
}

async function readRunArtifacts(page: Page, runId: string) {
  const artifacts = await apiData<ResearchArtifact[]>(
    page,
    "/api/runs/" + runId + "/artifacts?limit=100",
  );
  return Promise.all(
    artifacts.map(async (item): Promise<ArtifactHandle> => {
      if (!item.latest_version_id) throw new Error("Artifact is not published");
      return {
        kind: item.kind,
        title: item.title,
        detail: await apiData<ArtifactVersionDetail>(
          page,
          "/api/artifact-versions/" + item.latest_version_id,
        ),
      };
    }),
  );
}

function artifact(artifacts: readonly ArtifactHandle[], kind: ArtifactKind) {
  const found = artifacts.find((item) => item.kind === kind);
  if (!found) throw new Error("Missing published Artifact: " + kind);
  return found;
}

async function latestVersion(page: Page, artifactId: string) {
  const versions = await apiData<ArtifactVersionSummary[]>(
    page,
    "/api/artifacts/" + artifactId + "/versions?limit=100",
  );
  const latest = versions.sort(
    (a, b) => b.version_number - a.version_number,
  )[0];
  if (!latest) throw new Error("Artifact has no versions: " + artifactId);
  return apiData<ArtifactVersionDetail>(
    page,
    "/api/artifact-versions/" + latest.id,
  );
}

async function openThreadArtifact(
  page: Page,
  projectId: string,
  versionId: string,
) {
  // Every demonstrated result is entered through the actual thread attachment.
  await page.goto("/workspace/" + projectId);
  const attachment = page.getByTestId("artifact-result-" + versionId);
  await expect(attachment).toBeVisible({ timeout: 60_000 });
  await attachment.getByRole("button", { name: /^(打开|审查结果)：/u }).click();
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  await expect(fullscreen).toBeVisible();
  await expect(
    fullscreen.getByText(/操作暂时不可用|结果加载失败|无法加载研究结果/u),
  ).toHaveCount(0);
  return fullscreen;
}

async function createRevision(
  page: Page,
  fullscreen: Locator,
  instruction: string,
) {
  await fullscreen.getByRole("button", { name: "基于此结果重新分析" }).click();
  await page.getByRole("textbox", { name: "希望调整什么？" }).fill(instruction);
  await page.getByRole("button", { name: "生成修订计划" }).click();
  return confirmRevision(page);
}

async function confirmRevision(page: Page) {
  await expect(page.getByRole("heading", { name: "修订计划" })).toBeVisible();
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/revision-plans\/[^/]+\/confirm$/u.test(
        new URL(response.url()).pathname,
      ),
  );
  await page.getByRole("button", { name: "确认并创建派生研究" }).click();
  const response = await responsePromise;
  expect(response.ok(), await response.text()).toBe(true);
  return ((await response.json()) as { data: ResearchRun }).data.id;
}

async function shareAndExport(
  page: Page,
  fullscreen: Locator,
  title: string,
  exportLabel: string,
  extension: RegExp,
) {
  const downloadPromise = page.waitForEvent("download");
  await fullscreen.getByRole("button", { name: exportLabel }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(extension);
  await fullscreen.getByRole("button", { name: "分享" }).click();
  const dialog = page.getByRole("dialog", { name: "分享研究结果" });
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/shares$/u.test(new URL(response.url()).pathname),
  );
  await dialog.getByRole("button", { name: "创建链接" }).click();
  const shareResponse = await responsePromise;
  expect(shareResponse.ok(), await shareResponse.text()).toBe(true);
  const shareUrl = await dialog.getByLabel("分享链接").inputValue();
  const publicPage = await page.context().newPage();
  await publicPage.goto(shareUrl);
  await expect(
    publicPage.getByRole("heading", { name: title, level: 1 }),
  ).toBeVisible();
  await expect(publicPage.getByLabel("共享科研结果")).toBeVisible();
  await publicPage.close();
  await dialog.getByRole("button", { name: "完成" }).click();
}

function relationStatuses(relations: readonly LiteratureRelationRead[]) {
  const counts: Record<string, number> = {};
  for (const { relation } of relations) {
    counts[relation.status] = (counts[relation.status] ?? 0) + 1;
  }
  return counts;
}

function summaryCompleteness(read: PaperSummaryRead) {
  return {
    sections: Object.fromEntries(
      SUMMARY_SECTIONS.map((section) => [
        section,
        read.summary[section].length,
      ]),
    ),
    section_count: SUMMARY_SECTIONS.filter(
      (section) => read.summary[section].length > 0,
    ).length,
    locator_backed_evidence: read.summary.evidence.filter(
      (evidence) =>
        evidence.locator.document_parse_id &&
        evidence.locator.document_locator?.page_index !== undefined,
    ).length,
    evidence_count: read.evidence.length,
    unsupported_statements: SUMMARY_SECTIONS.flatMap(
      (section) => read.summary[section],
    ).filter((statement) => statement.status !== "supported").length,
  };
}

async function fixtureReference() {
  const data = exoplanetHostStarFixture.data;
  await report("fixture-structure-reference.json", {
    source_commit: SOURCE_COMMIT,
    qualifying: false,
    source_mode: "fixture",
    dataset: data.dataArtifactReads
      .filter((read): read is DatasetArtifactRead => "dataset" in read)
      .map((read) => ({
        rows: read.dataset.row_count,
        fields: read.dataset.field_count,
        source_snapshots: read.source_snapshots.length,
      })),
    papers: data.paperAcquisitions.map(
      ({ collection }) => collection.collection.metrics,
    ),
    summaries: data.paperSummaries.map(({ summary }) =>
      summaryCompleteness(summary),
    ),
    claims: data.literatureClaimReads.length,
    relations: relationStatuses(data.literatureRelationReads),
    graphs: data.graphArtifactReads.map((graph) => ({
      nodes: graph.node_count,
      edges: graph.edge_count,
    })),
    scientific_outputs: (data.scientificArtifactReads ?? []).map((read) => ({
      kind: read.content.kind,
      source_mode: read.source_mode,
      presentation: data.artifactPresentations[read.artifact_version_id],
    })),
  });
}

function qwenExecution(
  version: ArtifactVersionDetail,
  runtime: Awaited<ReturnType<typeof readReleaseRuntime>>,
) {
  expect(version.producer).toMatchObject({
    type: "model",
    model_provider: "dashscope",
    requested_model: RUNTIME_QWEN_MODEL,
    explicit_revision: EXPLICIT_REVISION,
  });
  expect(version.producer.provider_returned_model).toBeTruthy();
  const execution = version.producer_execution;
  const requests = runtime.model_executions.filter(
    (item) =>
      item.provider_request_id &&
      (execution.provider_request_id
        ? item.id === execution.id
        : item.step_attempt_id === execution.step_attempt_id &&
          item.step_key === execution.step_key &&
          item.prompt_name === version.producer.prompt_name &&
          item.prompt_hash === version.producer.prompt_hash),
  );
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.some((request) => request.status === "completed")).toBe(true);
  for (const request of requests) {
    expect(request).toMatchObject({
      model_provider: "dashscope",
      requested_model: RUNTIME_QWEN_MODEL,
      explicit_revision: EXPLICIT_REVISION,
    });
    expect(["completed", "failed"]).toContain(request.status);
    if (request.status === "failed") {
      expect(request.error_code).toBe("MODEL_RESPONSE_TRUNCATED");
    }
    expect(request.provider_returned_model).toBeTruthy();
    expect(request.parameters).toMatchObject({
      temperature: expect.any(Number),
      top_p: expect.any(Number),
    });
    expect(request.latency_ms).toBeGreaterThan(0);
    expect(
      Object.values(request.token_usage ?? {}).some((count) => count > 0),
    ).toBe(true);
  }
  expect(
    new Set(requests.map((request) => request.provider_returned_model)),
  ).toEqual(new Set([version.producer.provider_returned_model]));
  expect(version.producer_execution.status).toBe("completed");
  expect(version.producer.prompt_name).toBeTruthy();
  expect(version.producer.prompt_version).toBeTruthy();
  expect(version.producer.prompt_hash).toBeTruthy();
  expect(version.producer_execution.input_hash).toBeTruthy();
  expect(version.producer_execution.output_hash).toBeTruthy();
  expect(version.producer_execution.latency_ms).toBeGreaterThan(0);
  expect(
    Object.values(version.producer_execution.token_usage ?? {}).some(
      (count) => count > 0,
    ),
  ).toBe(true);
  return {
    artifact_version_id: version.id,
    producer: version.producer,
    execution: version.producer_execution,
    requests,
  };
}

test.use({ trace: "off" });

test.skip(
  process.env.RELEASE_CANDIDATE_E2E !== "1",
  "Requires the clean exact-HEAD release stack, real Qwen, and real external scientific sources.",
);

test.afterEach(async ({ page }, testInfo) => {
  if (process.env.RELEASE_CANDIDATE_E2E !== "1") return;
  const runtimes = [];
  const planning = [];
  for (const projectId of observedProjects) {
    try {
      planning.push({
        project_id: projectId,
        executions: await readPlanningExecutions(projectId),
      });
    } catch {
      planning.push({
        project_id: projectId,
        result: "runtime_read_unavailable",
      });
    }
  }
  for (const runId of observedRuns) {
    try {
      runtimes.push(await readReleaseRuntime(runId));
    } catch {
      runtimes.push({ run_id: runId, result: "runtime_read_unavailable" });
    }
  }
  await report("release-candidate-runtime.json", {
    result: testInfo.status === "passed" ? "passed" : "failed",
    route: new URL(page.url()).pathname,
    api_container: await readReleaseContainerState().catch(() => ({
      result: "container_state_unavailable",
    })),
    runtimes,
    planning,
  });
});

test("fresh Workspace completes real acquisition, document evidence, and research revision", async ({
  page,
}, testInfo) => {
  test.setTimeout(80 * 60_000);
  if (!RUNTIME_QWEN_MODEL) {
    throw new Error(
      "RELEASE_CANDIDATE_QWEN_MODEL must explicitly select the runtime model",
    );
  }
  expect(SOURCE_COMMIT).toMatch(/^[0-9a-f]{40}$/u);
  await fixtureReference();
  const warnings: string[] = [];
  const intent =
    "研究附近系外行星候选体与宿主恒星，使用当前案例的 20 pc 内已确认宿主选择范围，获取 NASA Exoplanet Archive 的 TOI 与 Planetary Systems 公开表；核对 TOI 和 TIC 身份、行星与恒星名称、候选状态、赤经赤纬、轨道周期、行星半径、恒星有效温度、半径和质量，统一为标准单位，不将论文数值混入数据表。检索 Crossref 中 2019 年以来的 TESS Input Catalog Candidate Target List 研究，最多保留 10 篇候选文献，比较方法和限制。成果需要结构化数据、字段字典、来源汇总、文献候选、文献总结、文献主张及关系、证据图谱。当前仅获取与整理数据和文献，不运行额外科学计算技能；后续另行确认数据质量分析。";
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace");
  await page.getByRole("textbox", { name: "输入研究消息" }).fill(intent);
  const turnPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/research-turns$/u.test(
        new URL(response.url()).pathname,
      ),
    { timeout: 360_000 },
  );
  await page.getByRole("button", { name: "发送研究消息" }).click();
  const turnResponse = await turnPromise;
  const requestedProjectId = new URL(turnResponse.url()).pathname.split("/")[3];
  if (!requestedProjectId)
    throw new Error("Planning response has no project route");
  observedProjects.add(requestedProjectId);
  expect(turnResponse.ok(), await turnResponse.text()).toBe(true);
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible({
    timeout: 120_000,
  });
  const projectId = new URL(page.url()).pathname
    .split("/")
    .filter(Boolean)
    .at(-1);
  if (!projectId) throw new Error("Research intent did not create a project");

  const sessionResponse = await requestApi(
    page.request,
    API_ORIGIN + "/api/sessions",
    {
      method: "POST",
    },
  );
  const session = (await sessionResponse.json()) as {
    data: { csrf_token: string };
  };
  const project = await apiData<ResearchProject>(
    page,
    "/api/projects/" + projectId,
  );
  const draft = await apiData<ResearchContractDraft>(
    page,
    "/api/contracts/drafts/" + project.active_draft_id,
  );
  // Freeze scope, not answers: all records and scientific conclusions come from production acquisition.
  await requestApi(
    page.request,
    API_ORIGIN + "/api/contracts/drafts/" + draft.id,
    {
      method: "PATCH",
      headers: {
        "If-Match": String(draft.version),
        "X-CSRF-Token": session.data.csrf_token,
      },
      data: {
        contract: {
          ...draft.contract,
          research_goal: intent,
          target_objects: ["exoplanet_candidate", "host_star"],
          requested_fields: [
            "planet.toi_id",
            "planet.name",
            "planet.disposition",
            "star.tic_id",
            "star.name",
            "system.right_ascension",
            "system.declination",
            "planet.orbital_period",
            "planet.radius",
            "star.effective_temperature",
            "star.radius",
            "star.mass",
          ],
          data_requirements: {
            unit_policy: "canonical",
            document_source_policy: "disabled",
          },
          source_scope: { allowed_sources: ["nasa_exoplanet_archive"] },
          paper_search_scope: {
            keywords: ["TESS Input Catalog Candidate Target List"],
            year_from: 2019,
            year_to: new Date().getUTCFullYear(),
            source_ids: ["crossref"],
            max_candidates: 10,
          },
          output_requirements: [...REQUIRED_ARTIFACT_KINDS],
          scientific_tasks: [],
        },
      },
    },
  );
  await page.reload();
  const runPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/runs$/u.test(new URL(response.url()).pathname),
  );
  await page.getByRole("button", { name: "确认协议并开始研究" }).click();
  const runResponse = await runPromise;
  expect(runResponse.ok(), await runResponse.text()).toBe(true);
  const createdRun = ((await runResponse.json()) as { data: ResearchRun }).data;
  const initialRunId = createdRun.id;
  observedRuns.add(initialRunId);
  await report("confirmed-research-contract.json", {
    project_id: projectId,
    run_id: initialRunId,
    intent,
    contract: await apiData(page, "/api/contracts/" + createdRun.contract_id),
  });
  await restartActiveWorker(page, initialRunId);
  const initialRun = await waitForRun(page, initialRunId);
  expect(initialRun).toMatchObject({
    execution_mode: "live",
    derivation_kind: "original",
  });
  const initialArtifacts = await readRunArtifacts(page, initialRunId);
  for (const kind of REQUIRED_ARTIFACT_KINDS) {
    const { detail } = artifact(initialArtifacts, kind);
    expect(
      detail.source_mode,
      kind + " must not consume fixture/recorded results",
    ).toBe("live");
    expect(detail.producer_execution.status).toBe("completed");
    expect(
      detail.source_snapshots.length,
      kind + " source closure",
    ).toBeGreaterThan(0);
  }

  const datasetArtifact = artifact(initialArtifacts, "dataset");
  const dictionaryArtifact = artifact(initialArtifacts, "field_dictionary");
  const sourcesArtifact = artifact(initialArtifacts, "source_collection");
  const collectionArtifact = artifact(initialArtifacts, "paper_collection");
  const summaryArtifact = artifact(initialArtifacts, "paper_summary");
  const claimsArtifact = artifact(initialArtifacts, "literature_claims");
  const relationsArtifact = artifact(initialArtifacts, "literature_relations");
  const graphArtifact = artifact(initialArtifacts, "graph");
  const dataset = await apiData<DatasetArtifactRead>(
    page,
    "/api/artifact-versions/" + datasetArtifact.detail.id + "/dataset",
  );
  const dictionary = await apiData<FieldDictionaryArtifactRead>(
    page,
    "/api/artifact-versions/" +
      dictionaryArtifact.detail.id +
      "/field-dictionary",
  );
  const sources = await apiData<SourceCollectionArtifactRead>(
    page,
    "/api/artifact-versions/" +
      sourcesArtifact.detail.id +
      "/source-collection",
  );
  const collection = await apiData<PaperCollectionRead>(
    page,
    "/api/artifact-versions/" +
      collectionArtifact.detail.id +
      "/paper-collection",
  );
  await report("live-source-acquisition.json", {
    dataset,
    dictionary,
    sources,
  });
  expect(dataset.dataset.row_count).toBeGreaterThanOrEqual(15);
  expect(dataset.dataset.field_count).toBeGreaterThanOrEqual(10);
  expect(dataset.source_snapshots.length).toBeGreaterThanOrEqual(2);
  const cells = dataset.evidence.filter(
    (item) => item.locator.kind === "database_cell",
  );
  expect(
    new Set(cells.map((item) => item.target_id)).size,
  ).toBeGreaterThanOrEqual(3);
  expect(
    new Set(
      cells.map((item) => JSON.stringify(item.locator.row_key)).filter(Boolean),
    ).size,
  ).toBeGreaterThanOrEqual(2);
  expect(dictionary.field_dictionary.field_definitions.length).toBe(
    dataset.dataset.field_count,
  );
  expect(sources.source_collection.source_snapshot_ids).toEqual(
    expect.arrayContaining(dataset.dataset.source_snapshot_ids),
  );
  const candidates = collection.collection.candidates ?? [];
  expect(candidates.length).toBeGreaterThanOrEqual(3);
  const paper = candidates.find(
    (candidate) => candidate.selected && candidate.doi === PAPER.doi,
  );
  if (!paper)
    throw new Error(
      "Live search did not return the independently verified open paper",
    );
  if (collection.collection.acquisition_run.status !== "completed")
    warnings.push("Paper acquisition is partial.");

  let fullscreen = await openThreadArtifact(
    page,
    projectId,
    datasetArtifact.detail.id,
  );
  await shareAndExport(
    page,
    fullscreen,
    datasetArtifact.title,
    "导出 CSV",
    /\.csv$/u,
  );
  const datasetTable = fullscreen.getByRole("table", {
    name: "研究数据集中的规范化字段与数据行",
  });
  await expect(datasetTable.getByRole("rowheader").first()).not.toHaveText(
    /^[-\d.]+$/u,
  );
  await expect(datasetTable).not.toContainText(
    /earth_radius|solar_mass|\bnone\b/u,
  );
  for (const [entityLevel, label, screenshot] of [
    ["host_star", "宿主恒星", "live-dataset-host-stars.png"],
    ["planet_assertion", "行星记录", "live-dataset-planets.png"],
    ["planet_candidate", "候选体", "live-dataset-candidates.png"],
  ] as const) {
    const rows = dataset.dataset.rows.filter(
      (row) =>
        "entity_level" in row.row_authority &&
        row.row_authority.entity_level === entityLevel,
    );
    expect(rows.length).toBeGreaterThan(0);
    await fullscreen
      .getByRole("tab", { name: `${label} ${rows.length}`, exact: true })
      .click();
    await expect(datasetTable.getByRole("rowheader")).toHaveCount(rows.length);
    const projected = new Set(rows.flatMap((row) => row.projected_field_ids));
    for (const column of dataset.dataset.columns) {
      if (!projected.has(column.field.field_id)) {
        await expect(
          datasetTable.getByRole("columnheader", {
            name: column.field.meaning_zh,
          }),
        ).toHaveCount(0);
      }
    }
    await page.screenshot({ path: testInfo.outputPath(screenshot) });
  }
  await fullscreen.getByRole("tab", { name: /^宿主恒星 /u }).click();
  await page.screenshot({ path: testInfo.outputPath("live-dataset.png") });

  // Full-text acquisition is available at the selected paper, not a test bootstrap or hidden upload.
  fullscreen = await openThreadArtifact(
    page,
    projectId,
    collectionArtifact.detail.id,
  );
  const paperRow = fullscreen
    .getByRole("listitem")
    .filter({ hasText: paper.title });
  await paperRow.getByRole("button", { name: "关联全文", exact: true }).click();
  const fullTextForm = fullscreen.getByRole("form", { name: "关联论文全文" });
  await fullTextForm
    .getByLabel("全文地址", { exact: true })
    .fill(PAPER.fullTextUrl);
  await fullTextForm.getByRole("combobox", { name: "开放来源" }).click();
  await page.getByRole("option", { name: "开放存储库" }).click();
  await fullTextForm
    .getByLabel("许可或开放获取依据")
    .fill(PAPER.accessStatement);
  await fullTextForm.getByLabel("开放获取说明页面").fill(PAPER.evidenceUrl);
  await page.screenshot({
    path: testInfo.outputPath("live-paper-full-text-form.png"),
  });
  const bindingPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/paper-candidates\/[^/]+\/research-input$/u.test(
        new URL(response.url()).pathname,
      ),
    { timeout: 120_000 },
  );
  await fullTextForm.getByRole("button", { name: "获取并关联全文" }).click();
  const bindingResponse = await bindingPromise;
  expect(bindingResponse.ok(), await bindingResponse.text()).toBe(true);
  const binding = (
    (await bindingResponse.json()) as { data: PaperCandidateInputBinding }
  ).data;
  expect(binding.outcome).toBe("accepted");
  expect(binding.research_input?.status).toBe("accepted");
  if (!binding.research_input)
    throw new Error("Full text did not create a ResearchInput");
  await expect(fullTextForm.getByRole("status")).toContainText("全文已关联");

  fullscreen = await openThreadArtifact(
    page,
    projectId,
    summaryArtifact.detail.id,
  );
  const documentRunId = await createRevision(
    page,
    fullscreen,
    "使用刚关联的完整开放论文重新生成摘要、论点和关系，保留页码、段落定位和证据限制；不得把元数据推断当成全文结论。",
  );
  // Full-text revisions use the production native-first parser. Visual
  // inference is selective and bounded when the native text layer is
  // insufficient; a healthy RC must finish within the full-text revision budget.
  const documentRun = await waitForRun(
    page,
    documentRunId,
    FULL_TEXT_REVISION_TIMEOUT_MS,
  );
  const documentRuntime = await readReleaseRuntime(documentRunId);
  expect(documentRun).toMatchObject({
    execution_mode: "live",
    derivation_kind: "revision",
    parent_run_id: initialRunId,
  });
  const documentVersions = await Promise.all(
    [summaryArtifact, claimsArtifact, relationsArtifact, graphArtifact].map(
      async (item) => {
        const detail = await latestVersion(page, item.detail.artifact_id);
        expect(detail.created_by_run_id).toBe(documentRunId);
        expect(detail.supersedes_version_id).toBe(item.detail.id);
        expect(detail.source_mode).toBe("live");
        return { ...item, detail };
      },
    ),
  );
  const summaryVersion = artifact(documentVersions, "paper_summary").detail;
  const claimsVersion = artifact(documentVersions, "literature_claims").detail;
  let relationsVersion = artifact(
    documentVersions,
    "literature_relations",
  ).detail;
  let graphVersion = artifact(documentVersions, "graph").detail;
  const summary = await apiData<PaperSummaryRead>(
    page,
    "/api/artifact-versions/" + summaryVersion.id + "/paper-summary",
  );
  const documentSource = await apiData<PaperSummaryDocumentSourceRead>(
    page,
    "/api/artifact-versions/" +
      summaryVersion.id +
      "/paper-summary/document-source",
  );
  await report("live-document-evidence.json", {
    summary,
    document_source: documentSource,
  });
  expect(documentSource.research_input?.id).toBe(binding.research_input.id);
  expect(documentSource.research_input?.content_hash).toBe(
    binding.research_input.content_hash,
  );
  const parseRefs = summary.summary.input_versions.document_parses ?? [];
  expect(parseRefs.length).toBeGreaterThan(0);
  expect(parseRefs[0]?.research_input_id).toBe(binding.research_input.id);
  expect(
    summary.summary.evidence.some(
      (evidence) =>
        evidence.locator.document_parse_id &&
        evidence.locator.document_locator?.page_index !== undefined,
    ),
  ).toBe(true);
  expect(summaryCompleteness(summary).section_count).toBeGreaterThanOrEqual(4);
  expect(
    summaryCompleteness(summary).locator_backed_evidence,
  ).toBeGreaterThanOrEqual(3);
  const claims = await apiData<LiteratureClaimRead[]>(
    page,
    "/api/artifact-versions/" +
      claimsVersion.id +
      "/literature-claims?limit=100",
  );
  expect(claims.length).toBeGreaterThanOrEqual(3);
  expect(
    claims.every((claim) =>
      claim.evidence.some(
        (evidence) =>
          Object.keys(evidence.locator).length > 0 &&
          claim.source_snapshots.some(
            (source) => source.id === evidence.source_snapshot_id,
          ),
      ),
    ),
  ).toBe(true);
  let relations = await apiData<LiteratureRelationRead[]>(
    page,
    "/api/artifact-versions/" +
      relationsVersion.id +
      "/literature-relations?limit=100",
  );
  expect(
    relations.length,
    "No real relation was produced; do not manufacture one",
  ).toBeGreaterThan(0);
  const qwenExecutions = [summaryVersion, claimsVersion, relationsVersion].map(
    (version) => qwenExecution(version, documentRuntime),
  );
  await report("live-literature-evidence.json", {
    summary,
    claims,
    relations,
    executions: qwenExecutions,
  });
  const relationStatusesBeforeReview = relationStatuses(relations);

  fullscreen = await openThreadArtifact(page, projectId, summaryVersion.id);
  await expect(fullscreen.getByTestId("paper-result-workspace")).toBeVisible();
  await expect(
    fullscreen.getByRole("link", { name: "下载论文原文" }),
  ).toBeVisible();
  await shareAndExport(
    page,
    fullscreen,
    summaryArtifact.title,
    "导出 Markdown",
    /\.md$/u,
  );
  await page.screenshot({
    path: testInfo.outputPath("live-document-summary.png"),
  });

  // A pending model relation is not scientific authority merely because an E2E is running.
  // Withhold graph admission when independent scientific review has not happened.
  const candidate = relations.find(
    (item) => item.relation.status === "candidate",
  );
  let adjudicationRunId: string | null = null;
  if (candidate) {
    fullscreen = await openThreadArtifact(page, projectId, relationsVersion.id);
    await fullscreen
      .getByTestId("literature-entry-" + candidate.relation.relation_id)
      .click();
    await fullscreen
      .getByRole("button", { name: "拒绝且不进入图谱", exact: true })
      .click();
    await expect(
      page.getByRole("radio", { name: /拒绝且不进入图谱/u }),
    ).toBeChecked();
    await page
      .getByRole("textbox", { name: "审定理由" })
      .fill(
        "暂不纳入正式图谱：当前仅完成模型公开依据的自动核验，尚未进行独立科研复核；不能把流程验收代替科学审定。",
      );
    await page.getByRole("button", { name: "生成修订计划" }).click();
    adjudicationRunId = await confirmRevision(page);
    await waitForRun(page, adjudicationRunId);
    const previousRelations = relationsVersion;
    const previousGraph = graphVersion;
    relationsVersion = await latestVersion(
      page,
      relationsArtifact.detail.artifact_id,
    );
    graphVersion = await latestVersion(page, graphArtifact.detail.artifact_id);
    expect(relationsVersion.supersedes_version_id).toBe(previousRelations.id);
    expect(graphVersion.supersedes_version_id).toBe(previousGraph.id);
    expect(
      (await latestVersion(page, claimsArtifact.detail.artifact_id)).id,
    ).toBe(claimsVersion.id);
    relations = await apiData<LiteratureRelationRead[]>(
      page,
      "/api/artifact-versions/" +
        relationsVersion.id +
        "/literature-relations?limit=100",
    );
    const adjudicated = relations.find(
      (item) => item.relation.relation_id === candidate.relation.relation_id,
    );
    expect(adjudicated?.relation.adjudication?.decision).toBe("rejected");
    expect(adjudicated?.graph_eligible).toBe(false);
  } else {
    warnings.push(
      "No candidate relation produced; adjudication was not triggered.",
    );
  }

  const graph = await apiData<GraphArtifactRead>(
    page,
    "/api/artifact-versions/" + graphVersion.id + "/graph",
  );
  const edges = await apiData<GraphEdgeRead[]>(
    page,
    "/api/artifact-versions/" + graphVersion.id + "/graph/edges?limit=100",
  );
  const nodes = await apiData<GraphNodeRead[]>(
    page,
    "/api/artifact-versions/" + graphVersion.id + "/graph/nodes?limit=100",
  );
  await report("live-graph-evidence.json", { graph, nodes, edges });
  expect(graph.integrity_report.status).toBe("passed");
  expect(graph.node_count).toBeGreaterThanOrEqual(6);
  expect(graph.edge_count).toBeGreaterThanOrEqual(3);
  expect(
    graph.integrity_report.counts.relation_edge_count,
  ).toBeGreaterThanOrEqual(1);
  expect(
    nodes.filter(({ node }) => node.node_type === "claim").length,
  ).toBeGreaterThanOrEqual(3);
  expect(
    edges.every((edge) => !edge.relation || edge.relation.graph_eligible),
  ).toBe(true);
  const edgeWithEvidence = edges.find((edge) => edge.evidence.length > 0);
  if (!edgeWithEvidence) throw new Error("Graph has no evidence-backed edge");
  fullscreen = await openThreadArtifact(page, projectId, graphVersion.id);
  const canvas = fullscreen.getByLabel("可交互科学关系图");
  await expect(canvas).toBeVisible();
  const edge = canvas.locator(
    '.react-flow__edge[data-id="' + edgeWithEvidence.edge.edge_id + '"]',
  );
  await edge.focus();
  await page.keyboard.press("Enter");
  await expect(edge).toHaveClass(/selected/u);
  await fullscreen
    .getByRole("button", { name: /查看证据/u })
    .first()
    .click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await expect(page.getByText("来源内容", { exact: true })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("live-graph-evidence.png"),
  });

  // Profile the actual published Dataset through the existing Contract/Worker
  // chain. The input is a fixed ArtifactVersion, not a fabricated observation.
  const scientificSessionResponse = await requestApi(
    page.request,
    API_ORIGIN + "/api/sessions",
    { method: "POST" },
  );
  const scientificSession = (await scientificSessionResponse.json()) as {
    data: { csrf_token: string };
  };
  await requestApi(
    page.request,
    API_ORIGIN + "/api/projects/" + projectId + "/contract-drafts",
    {
      method: "POST",
      headers: {
        "Idempotency-Key": "profile-" + datasetArtifact.detail.id,
        "X-CSRF-Token": scientificSession.data.csrf_token,
      },
      data: {
        intent: "检查已发布参数数据集的缺失情况、数值分布与质量限制。",
        contract: {
          ...draft.contract,
          research_goal: "检查已发布参数数据集的缺失情况、数值分布与质量限制。",
          target_objects: ["exoplanet_candidate", "host_star"],
          data_requirements: {
            unit_policy: "canonical",
            document_source_policy: "disabled",
          },
          source_scope: { allowed_sources: ["nasa_exoplanet_archive"] },
          paper_search_scope: {
            keywords: [],
            source_ids: [],
            max_candidates: 1,
          },
          output_requirements: ["analysis_report"],
          scientific_tasks: [
            {
              task_id: "profile-research-dataset",
              skill_id: "data_profile",
              input_refs: [datasetArtifact.detail.id],
              parameters: {},
            },
          ],
        },
      },
    },
  );
  await page.goto("/workspace/" + projectId);
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible();
  const scientificRunPromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/runs$/u.test(new URL(response.url()).pathname),
  );
  await page.getByRole("button", { name: "确认协议并开始研究" }).click();
  const scientificRunResponse = await scientificRunPromise;
  expect(scientificRunResponse.ok(), await scientificRunResponse.text()).toBe(
    true,
  );
  const scientificRunId = (
    (await scientificRunResponse.json()) as { data: ResearchRun }
  ).data.id;
  await waitForRun(page, scientificRunId);
  const analysisArtifact = artifact(
    await readRunArtifacts(page, scientificRunId),
    "analysis_report",
  );
  const analysis = await apiData<ScientificArtifactRead>(
    page,
    "/api/artifact-versions/" + analysisArtifact.detail.id + "/scientific",
  );
  expect(analysis.source_mode).toBe("live");
  expect(analysis.content.kind).toBe("analysis_report");
  if (analysis.content.kind !== "analysis_report")
    throw new Error("Dataset profiling did not publish an analysis report");
  expect(analysis.evidence.length).toBeGreaterThan(0);
  const analysisMetrics = analysis.content.metrics ?? [];
  expect(analysisMetrics.length).toBeGreaterThan(0);
  expect(analysis.content.findings?.length ?? 0).toBeGreaterThan(0);
  const profileRows = analysis.content.result_blocks.flatMap<unknown>(
    (block) => {
      const payload = block.payload;
      if (!payload || typeof payload !== "object" || Array.isArray(payload))
        return [];
      return "rows" in payload && Array.isArray(payload.rows)
        ? payload.rows
        : [];
    },
  );
  for (const column of dataset.dataset.columns) {
    const projected = dataset.dataset.rows.flatMap((row) =>
      row.fields.filter(
        (field) => field.canonical_field_id === column.field.field_id,
      ),
    );
    const profile = profileRows.find(
      (row) =>
        row !== null &&
        typeof row === "object" &&
        !Array.isArray(row) &&
        "field" in row &&
        row.field === column.field.field_id,
    );
    expect(profile).toMatchObject({
      present_count: projected.length,
      absent_count: dataset.dataset.rows.length - projected.length,
      null_count: projected.filter((field) => field.status !== "mapped").length,
      non_null_count: projected.filter((field) => field.status === "mapped")
        .length,
    });
  }
  await report("live-analysis-evidence.json", { analysis });
  fullscreen = await openThreadArtifact(
    page,
    projectId,
    analysisArtifact.detail.id,
  );
  await expect(
    fullscreen.getByRole("heading", {
      name: analysis.content.title,
      exact: true,
    }),
  ).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("live-data-profile.png") });

  const finalArtifacts = initialArtifacts
    .map(
      (item) =>
        documentVersions.find((version) => version.kind === item.kind) ?? item,
    )
    .map((item) =>
      item.kind === "graph"
        ? { ...item, detail: graphVersion }
        : item.kind === "literature_relations"
          ? { ...item, detail: relationsVersion }
          : item,
    );
  finalArtifacts.push(analysisArtifact);
  const records: Partial<Record<ArtifactKind, number>> = {
    dataset: dataset.dataset.row_count,
    field_dictionary: dictionary.field_dictionary.field_definitions.length,
    source_collection: sources.source_collection.members.length,
    paper_collection: candidates.length,
    paper_summary: SUMMARY_SECTIONS.reduce(
      (count, section) => count + summary.summary[section].length,
      0,
    ),
    literature_claims: claims.length,
    literature_relations: relations.length,
    graph: graph.node_count,
    analysis_report: analysisMetrics.length,
  };
  await report("release-candidate-real-data-report.json", {
    source_commit: SOURCE_COMMIT,
    research_target: intent,
    project_id: projectId,
    execution_mode: "live",
    runs: {
      initial: initialRunId,
      document_revision: documentRunId,
      adjudication: adjudicationRunId,
    },
    artifact_matrix: finalArtifacts.map(({ kind, detail }) => ({
      kind,
      artifact_id: detail.artifact_id,
      version_id: detail.id,
      source_mode: detail.source_mode,
      records: records[kind],
      source_snapshots: detail.source_snapshots.length,
      evidence: detail.evidence.length,
      producer_status: detail.producer_execution.status,
    })),
    dataset: {
      rows: dataset.dataset.row_count,
      fields: dataset.dataset.field_count,
    },
    papers: collection.collection.metrics,
    document: {
      source: PAPER,
      research_input: binding.research_input,
      parses: parseRefs,
      parse_quality: documentRuntime.document_parses,
    },
    summary: summaryCompleteness(summary),
    claims: claims.length,
    relations: {
      before_review: relationStatusesBeforeReview,
      after_review: relationStatuses(relations),
    },
    graph: {
      nodes: graph.node_count,
      edges: graph.edge_count,
      relation_edges: graph.integrity_report.counts.relation_edge_count,
    },
    qwen_executions: qwenExecutions,
    scientific_capabilities: {
      live: {
        skill: "data_profile",
        run_id: scientificRunId,
        artifact_version_id: analysisArtifact.detail.id,
      },
      other_presentations:
        "Fixture/Recorded scientific views are not qualifying live proof.",
    },
    warnings,
    result: "passed",
  });
  await report("release-candidate-qwen-evidence.json", {
    gate: "release-candidate-qwen",
    source_commit: SOURCE_COMMIT,
    generated_at: new Date().toISOString(),
    model: {
      provider: "dashscope",
      configured_official_route: documentRuntime.qwen_route,
      requested_model: RUNTIME_QWEN_MODEL,
      explicit_revision: EXPLICIT_REVISION,
      provider_returned_model: (() => {
        const returnedModels = new Set(
          qwenExecutions.flatMap((item) =>
            item.requests
              .map((request) => request.provider_returned_model)
              .filter((model): model is string => Boolean(model)),
          ),
        );
        expect(returnedModels.size).toBe(1);
        return [...returnedModels][0];
      })(),
    },
    producer_request_ids: qwenExecutions.flatMap((item) =>
      item.requests.map((request) => request.provider_request_id),
    ),
    runs: {
      initial: initialRunId,
      document_revision: documentRunId,
      adjudication: adjudicationRunId,
    },
    qualifying_artifact_versions: qwenExecutions.map(
      (execution) => execution.artifact_version_id,
    ),
    executions: qwenExecutions,
    result: "passed",
  });
});
