import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

const API_ORIGIN =
  process.env.REAL_INTEGRATION_API_ORIGIN ?? "http://127.0.0.1:8000";
const RELEASE_GATE_ENABLED = process.env.RELEASE_CANDIDATE_E2E === "1";
const QUALIFYING_QWEN_MODEL =
  process.env.RELEASE_CANDIDATE_QWEN_MODEL ?? "qwen3.7-max-2026-06-08";
const PAPER_DOCUMENT_NAME = "cadieux-2025-l98-59-page-14.png";
const PAPER_DOCUMENT_PATH = path.resolve(
  "tests/fixtures/scientific-documents/papers",
  PAPER_DOCUMENT_NAME,
);
const ARTIFACT_SOURCE_MODES = new Set([
  "fixture",
  "recorded",
  "live",
  "cached",
]);

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

type RequiredArtifactKind = (typeof REQUIRED_ARTIFACT_KINDS)[number];

interface RunRead {
  readonly id: string;
  readonly execution_mode: string;
  readonly derivation_kind: string;
  readonly parent_run_id?: string | null;
  readonly status: string;
  readonly failure_code?: string | null;
  readonly failure_summary?: string | null;
}

interface ArtifactListItem {
  readonly id: string;
  readonly kind: RequiredArtifactKind;
  readonly title: string;
  readonly latest_version_id: string | null;
}

interface SourceSnapshotRead {
  readonly id: string;
  readonly source_id: string;
  readonly source_type: string;
  readonly query_hash: string;
  readonly content_hash: string;
}

interface EvidenceRead {
  readonly id: string;
  readonly source_snapshot_id: string;
  readonly locator: Record<string, unknown>;
}

interface ArtifactVersionDetail {
  readonly id: string;
  readonly artifact_id: string;
  readonly created_by_run_id: string;
  readonly version_number: number;
  readonly source_mode: string;
  readonly supersedes_version_id: string | null;
  readonly content: Record<string, unknown>;
  readonly producer: {
    readonly model_provider?: string | null;
    readonly requested_model?: string | null;
    readonly provider_returned_model?: string | null;
    readonly explicit_revision?: string | null;
  };
  readonly producer_execution: {
    readonly status: string;
    readonly provider_request_id?: string | null;
  };
  readonly source_snapshots: readonly SourceSnapshotRead[];
  readonly evidence: readonly EvidenceRead[];
}

interface ArtifactHandle {
  readonly kind: RequiredArtifactKind;
  readonly title: string;
  readonly artifactId: string;
  readonly versionId: string;
  readonly versionNumber: number;
  readonly sourceMode: string;
  readonly evidenceCount: number;
  readonly sourceSnapshotCount: number;
  readonly producerStatus: string;
}

interface ArtifactVersionSummary {
  readonly id: string;
  readonly artifact_id: string;
  readonly version_number: number;
  readonly supersedes_version_id: string | null;
}

interface ResearchInputRead {
  readonly id: string;
  readonly content_hash: string;
  readonly source_snapshot_id: string | null;
  readonly filename: string | null;
  readonly status: string;
}

interface DatasetRead {
  readonly dataset: {
    readonly row_count: number;
    readonly rows: readonly {
      readonly row_id: string;
      readonly evidence_ids: readonly string[];
      readonly source_snapshot_ids: readonly string[];
    }[];
    readonly transformation_evidence: readonly {
      readonly evidence_id: string;
      readonly dataset_row_id: string;
      readonly locator: {
        readonly document_parse_id?: string | null;
        readonly raw_candidate_id?: string | null;
        readonly source_snapshot_id: string;
      };
    }[];
  };
  readonly evidence: readonly EvidenceRead[];
  readonly source_snapshots: readonly SourceSnapshotRead[];
}

interface FieldDictionaryRead {
  readonly field_dictionary: {
    readonly field_definitions: readonly unknown[];
    readonly source_snapshot_ids: readonly string[];
  };
  readonly evidence: readonly EvidenceRead[];
}

interface SourceCollectionRead {
  readonly source_collection: {
    readonly source_snapshot_ids: readonly string[];
    readonly members: readonly {
      readonly member_kind: string;
      readonly source_snapshot_id: string;
      readonly source_snapshot_content_hash: string;
      readonly research_input_id?: string;
      readonly document_parse_ids?: readonly string[];
    }[];
  };
  readonly evidence: readonly EvidenceRead[];
}

interface PaperSummaryRead {
  readonly source_mode: string;
  readonly summary: {
    readonly producer: { readonly model_name: string };
    readonly input_versions: {
      readonly paper_collection_version_id: string | null;
      readonly source_snapshots: readonly {
        readonly source_snapshot_id: string;
        readonly content_hash: string;
      }[];
    };
    readonly evidence: readonly {
      readonly source_snapshot_id: string;
      readonly locator: {
        readonly document_parse_id?: string | null;
        readonly document_parse_output_hash?: string | null;
        readonly document_locator?: {
          readonly page_index: number;
          readonly block_id?: string | null;
          readonly bbox?: Record<string, number> | null;
        } | null;
      };
    }[];
  };
  readonly source_snapshots: readonly SourceSnapshotRead[];
  readonly evidence: readonly EvidenceRead[];
}

interface PaperSummaryDocumentSourceRead {
  readonly research_input: ResearchInputRead | null;
}

interface LiteratureRelationRead {
  readonly relation: {
    readonly relation_id: string;
    readonly status: string;
    readonly review_reason: string | null;
    readonly adjudication: {
      readonly decision: string;
      readonly feedback_id: string;
    } | null;
  };
  readonly reasoning_trace: {
    readonly trace_id: string;
    readonly steps: readonly unknown[];
  } | null;
  readonly source_snapshots: readonly SourceSnapshotRead[];
  readonly evidence: readonly EvidenceRead[];
  readonly graph_eligible: boolean;
}

interface GraphRead {
  readonly edge_count: number;
  readonly evidence_use_count: number;
  readonly integrity_report: {
    readonly status: string;
    readonly counts: { readonly relation_edge_count: number };
  };
}

interface GraphEdgeRead {
  readonly edge: { readonly edge_id: string };
  readonly evidence: readonly {
    readonly evidence: EvidenceRead;
    readonly source_snapshot: SourceSnapshotRead;
  }[];
  readonly relation: LiteratureRelationRead | null;
}

async function apiData<T>(page: Page, pathname: string): Promise<T> {
  const response = await page.request.get(`${API_ORIGIN}${pathname}`);
  expect(
    response.ok(),
    `${pathname} failed with HTTP ${response.status()}: ${await response.text()}`,
  ).toBe(true);
  return ((await response.json()) as { data: T }).data;
}

async function apiCollection<T>(page: Page, pathname: string): Promise<T[]> {
  return apiData<T[]>(page, pathname);
}

async function waitForRun(
  page: Page,
  runId: string,
  timeoutMs = 12 * 60_000,
): Promise<RunRead> {
  const deadline = Date.now() + timeoutMs;
  let run: RunRead | null = null;
  while (Date.now() < deadline) {
    run = await apiData<RunRead>(page, `/api/runs/${runId}`);
    if (["completed", "failed", "cancelled"].includes(run.status)) break;
    await page.waitForTimeout(2_000);
  }
  expect(
    run?.status,
    `run ${runId} ended as ${String(run?.status)}: ${String(run?.failure_code ?? "")} ${String(run?.failure_summary ?? "")}`,
  ).toBe("completed");
  return run as RunRead;
}

async function readRunArtifacts(
  page: Page,
  runId: string,
): Promise<ArtifactHandle[]> {
  const artifacts = await apiCollection<ArtifactListItem>(
    page,
    `/api/runs/${runId}/artifacts?limit=100`,
  );
  return Promise.all(
    artifacts.map(async (item) => {
      expect(item.latest_version_id).not.toBeNull();
      const detail = await apiData<ArtifactVersionDetail>(
        page,
        `/api/artifact-versions/${item.latest_version_id}`,
      );
      return {
        kind: item.kind,
        title: item.title,
        artifactId: item.id,
        versionId: detail.id,
        versionNumber: detail.version_number,
        sourceMode: detail.source_mode,
        evidenceCount: detail.evidence.length,
        sourceSnapshotCount: detail.source_snapshots.length,
        producerStatus: detail.producer_execution.status,
      };
    }),
  );
}

function artifact(
  artifacts: readonly ArtifactHandle[],
  kind: RequiredArtifactKind,
): ArtifactHandle {
  const found = artifacts.find((item) => item.kind === kind);
  expect(found, `missing ${kind} Artifact`).toBeDefined();
  return found as ArtifactHandle;
}

async function latestVersion(
  page: Page,
  artifactId: string,
): Promise<ArtifactVersionDetail> {
  const versions = await apiCollection<ArtifactVersionSummary>(
    page,
    `/api/artifacts/${artifactId}/versions?limit=100`,
  );
  const latest = [...versions].sort(
    (left, right) => right.version_number - left.version_number,
  )[0];
  expect(latest).toBeDefined();
  return apiData<ArtifactVersionDetail>(
    page,
    `/api/artifact-versions/${String(latest?.id)}`,
  );
}

async function openVersion(page: Page, projectId: string, versionId: string) {
  await page.goto(`/workspace/${projectId}?artifactVersionId=${versionId}`);
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  await expect(fullscreen).toBeVisible({ timeout: 60_000 });
  return fullscreen;
}

async function confirmRevision(page: Page): Promise<string> {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/revision-plans\/[^/]+\/confirm$/u.test(
        new URL(response.url()).pathname,
      ),
  );
  await page.getByRole("button", { name: "确认并创建派生研究" }).click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  return ((await response.json()) as { data: { id: string } }).data.id;
}

async function createPublicShare(
  page: Page,
  fullscreen: ReturnType<Page["getByTestId"]>,
  expectedTitle: string,
) {
  await fullscreen.getByRole("button", { name: "分享" }).click();
  const dialog = page.getByRole("dialog", { name: "分享研究结果" });
  await expect(dialog).toBeVisible();
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/shares$/u.test(new URL(response.url()).pathname),
  );
  await dialog.getByRole("button", { name: "创建链接" }).click();
  expect((await responsePromise).ok()).toBe(true);
  const shareUrl = await dialog.getByLabel("分享链接").inputValue();
  expect(shareUrl).toContain("/share/");

  const publicPage = await page.context().newPage();
  const response = await publicPage.goto(shareUrl);
  expect(response?.ok()).toBe(true);
  await expect(
    publicPage.getByRole("heading", { name: expectedTitle, level: 1 }),
  ).toBeVisible({ timeout: 60_000 });
  await expect(publicPage.getByLabel("共享科研结果")).toBeVisible();
  await publicPage.close();
  await dialog.getByRole("button", { name: "完成" }).click();
}

test.skip(
  !RELEASE_GATE_ENABLED,
  "Set RELEASE_CANDIDATE_E2E=1 only against the fresh release-gate stack with real Qwen. The committed document input is Fixture evidence; any recorded visual response remains Recorded and is never a Live document proof.",
);

test("fresh Workspace completes the scientific, literature, and reasoning chains", async ({
  page,
}) => {
  test.setTimeout(30 * 60_000);

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/workspace");

  const intent =
    "核对 L 98-59 行星系统的公开轨道、质量和半径参数，检索该系统的最新同行评议论文，并形成带证据的结构化数据、文献结论与图谱。";
  await page.getByRole("textbox", { name: "输入研究消息" }).fill(intent);
  const turnResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/research-turns$/u.test(
        new URL(response.url()).pathname,
      ),
  );
  await page.getByRole("button", { name: "发送研究消息" }).click();
  const turnResponse = await turnResponsePromise;
  expect(
    turnResponse.ok(),
    `research turn failed with HTTP ${turnResponse.status()}: ${await turnResponse.text()}`,
  ).toBe(true);
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible({
    timeout: 120_000,
  });

  const projectId = new URL(page.url()).pathname
    .split("/")
    .filter(Boolean)
    .at(-1);
  expect(projectId).toBeTruthy();

  const input = page.getByLabel("选择研究资料");
  const rejectedResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname === "/api/research-inputs",
  );
  await input.setInputFiles({
    name: "mismatched.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  });
  const rejectedResponse = await rejectedResponsePromise;
  expect(rejectedResponse.status()).toBe(415);
  expect(await rejectedResponse.json()).toMatchObject({
    code: "RESEARCH_INPUT_MIME_REJECTED",
  });
  const failedAttachment = page
    .getByTestId("research-attachment-strip")
    .locator('[data-status="failed"]');
  await expect(failedAttachment).toContainText("mismatched.pdf");
  await expect(failedAttachment.getByRole("alert")).toHaveText(
    "输入未通过校验",
  );
  await failedAttachment
    .getByRole("button", { name: "移除 mismatched.pdf" })
    .click();

  await input.setInputFiles(PAPER_DOCUMENT_PATH);
  const uploadedAttachment = page
    .getByTestId("research-attachment-strip")
    .locator('[data-status="uploaded"]');
  await expect(uploadedAttachment).toContainText(PAPER_DOCUMENT_NAME, {
    timeout: 120_000,
  });

  const sessionResponse = await page.request.post(`${API_ORIGIN}/api/sessions`);
  expect(sessionResponse.ok()).toBe(true);
  const session = (await sessionResponse.json()) as {
    data: { csrf_token: string };
  };
  const project = await apiData<{ active_draft_id: string }>(
    page,
    `/api/projects/${projectId}`,
  );
  const draft = await apiData<{
    version: number;
    contract: Record<string, unknown> & {
      data_requirements: Record<string, unknown>;
    };
  }>(page, `/api/contracts/drafts/${project.active_draft_id}`);
  const patchResponse = await page.request.patch(
    `${API_ORIGIN}/api/contracts/drafts/${project.active_draft_id}`,
    {
      headers: {
        "Content-Type": "application/json",
        "If-Match": String(draft.version),
        "X-CSRF-Token": session.data.csrf_token,
      },
      data: {
        contract: {
          ...draft.contract,
          data_requirements: {
            ...draft.contract.data_requirements,
            document_source_policy: "research_input",
          },
          paper_search_scope: {
            keywords: [
              "Detailed Architecture of the L 98-59 System and Confirmation of a Fifth Planet in the Habitable Zone",
            ],
            year_from: 2025,
            year_to: 2025,
            source_ids: ["crossref"],
            max_candidates: 5,
          },
          output_requirements: [...REQUIRED_ARTIFACT_KINDS],
        },
      },
    },
  );
  expect(
    patchResponse.ok(),
    `contract patch failed: ${await patchResponse.text()}`,
  ).toBe(true);

  await page.reload();
  const runResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/projects\/[^/]+\/runs$/u.test(new URL(response.url()).pathname),
  );
  await page.getByRole("button", { name: "确认协议并开始研究" }).click();
  const runResponse = await runResponsePromise;
  expect(runResponse.ok()).toBe(true);
  const initialRunId = ((await runResponse.json()) as { data: { id: string } })
    .data.id;
  const initialRun = await waitForRun(page, initialRunId);
  expect(initialRun.execution_mode).toBe("live");
  expect(initialRun.derivation_kind).toBe("original");
  expect(initialRun.parent_run_id).toBeNull();

  const initialArtifacts = await readRunArtifacts(page, initialRunId);
  expect(new Set(initialArtifacts.map((item) => item.kind))).toEqual(
    new Set(REQUIRED_ARTIFACT_KINDS),
  );
  expect(
    initialArtifacts.every((item) =>
      ARTIFACT_SOURCE_MODES.has(item.sourceMode),
    ),
  ).toBe(true);
  expect(artifact(initialArtifacts, "paper_collection").sourceMode).toBe(
    "live",
  );
  expect(
    initialArtifacts.every((item) => item.producerStatus === "completed"),
  ).toBe(true);
  for (const kind of [
    "dataset",
    "paper_summary",
    "literature_claims",
    "graph",
  ] as const) {
    const current = artifact(initialArtifacts, kind);
    expect(
      current.evidenceCount,
      `${kind} must expose admitted Evidence`,
    ).toBeGreaterThan(0);
    expect(
      current.sourceSnapshotCount,
      `${kind} must expose SourceSnapshot provenance`,
    ).toBeGreaterThan(0);
  }

  const datasetArtifact = artifact(initialArtifacts, "dataset");
  const dictionaryArtifact = artifact(initialArtifacts, "field_dictionary");
  const sourcesArtifact = artifact(initialArtifacts, "source_collection");
  const dataset = await apiData<DatasetRead>(
    page,
    `/api/artifact-versions/${datasetArtifact.versionId}/dataset`,
  );
  const dictionary = await apiData<FieldDictionaryRead>(
    page,
    `/api/artifact-versions/${dictionaryArtifact.versionId}/field-dictionary`,
  );
  const sources = await apiData<SourceCollectionRead>(
    page,
    `/api/artifact-versions/${sourcesArtifact.versionId}/source-collection`,
  );
  expect(dataset.dataset.row_count).toBeGreaterThan(0);
  expect(dictionary.field_dictionary.field_definitions.length).toBeGreaterThan(
    0,
  );

  const documentEvidence = dataset.evidence.find(
    (item) => item.locator.kind === "document_observation",
  );
  expect(documentEvidence).toBeDefined();
  const documentLocator = documentEvidence?.locator.document_locator as
    | {
        readonly page_index: number;
        readonly block_id?: string | null;
        readonly table_id?: string | null;
        readonly cell_id?: string | null;
        readonly bbox?: Record<string, number> | null;
      }
    | undefined;
  const documentParseId = String(documentEvidence?.locator.document_parse_id);
  const paperResearchInputId = String(
    documentEvidence?.locator.research_input_id,
  );
  const pipelineSourceSnapshotId = String(
    documentEvidence?.locator.source_snapshot_id,
  );
  const persistedSourceSnapshotId = String(
    documentEvidence?.source_snapshot_id,
  );
  expect(documentLocator?.page_index).toBeGreaterThanOrEqual(0);
  expect(documentLocator?.block_id).toBeTruthy();
  expect(documentLocator?.table_id).toBeTruthy();
  expect(documentLocator?.cell_id).toBeTruthy();
  expect(documentLocator?.bbox).toBeTruthy();
  expect(documentParseId).not.toBe("undefined");
  expect(paperResearchInputId).not.toBe("undefined");
  expect(pipelineSourceSnapshotId).toBe(
    `research-input.${paperResearchInputId}`,
  );
  expect(persistedSourceSnapshotId).not.toBe("undefined");

  const persistedInput = await apiData<ResearchInputRead>(
    page,
    `/api/research-inputs/${paperResearchInputId}`,
  );
  const persistedSnapshot = await apiData<SourceSnapshotRead>(
    page,
    `/api/source-snapshots/${persistedSourceSnapshotId}`,
  );
  expect(persistedInput.filename).toBe(PAPER_DOCUMENT_NAME);
  expect(persistedInput.status).toBe("accepted");
  expect(persistedInput.source_snapshot_id).toBe(persistedSourceSnapshotId);
  expect(persistedSnapshot.source_id).toBe(
    `research_input:${paperResearchInputId}`,
  );
  expect(persistedSnapshot.content_hash).toBe(persistedInput.content_hash);
  expect(documentEvidence?.locator.source_snapshot_content_hash).toBe(
    persistedInput.content_hash,
  );
  const documentMember = sources.source_collection.members.find(
    (item) => item.member_kind === "document",
  );
  expect(documentMember).toMatchObject({
    source_snapshot_id: pipelineSourceSnapshotId,
    source_snapshot_content_hash: persistedInput.content_hash,
    research_input_id: paperResearchInputId,
  });
  expect(documentMember?.document_parse_ids).toContain(documentParseId);
  const documentTransformation = dataset.dataset.transformation_evidence.find(
    (item) =>
      item.locator.document_parse_id === documentParseId &&
      item.locator.raw_candidate_id ===
        documentEvidence?.locator.raw_candidate_id,
  );
  expect(documentTransformation).toBeDefined();
  expect(
    dataset.dataset.rows.some(
      (row) =>
        row.row_id === documentTransformation?.dataset_row_id &&
        row.evidence_ids.includes(documentTransformation.evidence_id) &&
        row.source_snapshot_ids.includes(pipelineSourceSnapshotId),
    ),
  ).toBe(true);
  expect(dictionary.field_dictionary.source_snapshot_ids).toContain(
    pipelineSourceSnapshotId,
  );
  expect(sources.source_collection.source_snapshot_ids).toContain(
    pipelineSourceSnapshotId,
  );

  let fullscreen = await openVersion(
    page,
    projectId ?? "",
    datasetArtifact.versionId,
  );
  const datasetDownloadPromise = page.waitForEvent("download");
  await fullscreen.getByRole("button", { name: "导出 CSV" }).click();
  const datasetDownload = await datasetDownloadPromise;
  expect(datasetDownload.suggestedFilename()).toMatch(/\.csv$/u);
  await createPublicShare(page, fullscreen, datasetArtifact.title);

  fullscreen = await openVersion(
    page,
    projectId ?? "",
    sourcesArtifact.versionId,
  );
  await fullscreen.getByRole("button", { name: "基于此结果重新分析" }).click();
  await page
    .getByRole("textbox", { name: "希望调整什么？" })
    .fill("重新获取冻结来源并核对来源身份，生成新的固定版本数据结果。");
  await page.getByRole("button", { name: "生成修订计划" }).click();
  await expect(page.getByRole("heading", { name: "修订计划" })).toBeVisible();
  const dataRevisionRunId = await confirmRevision(page);
  const dataRevisionRun = await waitForRun(page, dataRevisionRunId);
  expect(dataRevisionRun.derivation_kind).toBe("revision");
  expect(dataRevisionRun.parent_run_id).toBe(initialRunId);
  const revisedDataset = await latestVersion(page, datasetArtifact.artifactId);
  expect(revisedDataset.id).not.toBe(datasetArtifact.versionId);
  expect(revisedDataset.supersedes_version_id).toBe(datasetArtifact.versionId);
  expect(revisedDataset.created_by_run_id).toBe(dataRevisionRunId);

  fullscreen = await openVersion(page, projectId ?? "", revisedDataset.id);
  await fullscreen.getByRole("button", { name: "比较结果" }).click();
  await expect(page.getByLabel("科学结果变化")).toBeVisible();
  await page.keyboard.press("Escape");
  await fullscreen.getByRole("button", { name: "返回研究" }).click();

  const paperCollectionArtifact = artifact(
    initialArtifacts,
    "paper_collection",
  );
  const paperCollectionBeforeDocument = await latestVersion(
    page,
    paperCollectionArtifact.artifactId,
  );
  fullscreen = await openVersion(
    page,
    projectId ?? "",
    paperCollectionBeforeDocument.id,
  );
  await fullscreen.getByLabel("选择已上传科研文档").click();
  await page.getByRole("option", { name: PAPER_DOCUMENT_NAME }).click();
  await fullscreen.getByRole("button", { name: "绑定到所选论文" }).click();
  await expect(
    fullscreen.getByText(
      "全文绑定已保存；可通过修订运行重新生成全文证据摘要。",
    ),
  ).toBeVisible({ timeout: 60_000 });
  await fullscreen.getByRole("button", { name: "返回研究" }).click();

  const summaryArtifact = artifact(initialArtifacts, "paper_summary");
  const claimsArtifact = artifact(initialArtifacts, "literature_claims");
  const relationsArtifact = artifact(initialArtifacts, "literature_relations");
  const graphArtifact = artifact(initialArtifacts, "graph");
  const summaryBeforeDocument = await latestVersion(
    page,
    summaryArtifact.artifactId,
  );
  const claimsBeforeDocument = await latestVersion(
    page,
    claimsArtifact.artifactId,
  );
  const relationsBeforeDocument = await latestVersion(
    page,
    relationsArtifact.artifactId,
  );
  const graphBeforeDocument = await latestVersion(
    page,
    graphArtifact.artifactId,
  );
  fullscreen = await openVersion(
    page,
    projectId ?? "",
    summaryBeforeDocument.id,
  );
  await fullscreen.getByRole("button", { name: "基于此结果重新分析" }).click();
  await page
    .getByRole("textbox", { name: "希望调整什么？" })
    .fill("使用刚绑定的论文表格页重新生成带页码与文档定位的摘要、论点和关系。");
  await page.getByRole("button", { name: "生成修订计划" }).click();
  await expect(page.getByRole("heading", { name: "修订计划" })).toBeVisible();
  const documentRevisionRunId = await confirmRevision(page);
  const documentRevisionRun = await waitForRun(page, documentRevisionRunId);
  expect(documentRevisionRun.derivation_kind).toBe("revision");
  expect(documentRevisionRun.parent_run_id).toBe(dataRevisionRunId);

  const documentSummaryVersion = await latestVersion(
    page,
    summaryArtifact.artifactId,
  );
  const documentClaimsVersion = await latestVersion(
    page,
    claimsArtifact.artifactId,
  );
  const candidateRelationsVersion = await latestVersion(
    page,
    relationsArtifact.artifactId,
  );
  const candidateGraphVersion = await latestVersion(
    page,
    graphArtifact.artifactId,
  );
  for (const [version, baseline] of [
    [documentSummaryVersion, summaryBeforeDocument],
    [documentClaimsVersion, claimsBeforeDocument],
    [candidateRelationsVersion, relationsBeforeDocument],
    [candidateGraphVersion, graphBeforeDocument],
  ] as const) {
    expect(version.created_by_run_id).toBe(documentRevisionRunId);
    expect(ARTIFACT_SOURCE_MODES.has(version.source_mode)).toBe(true);
    expect(version.source_mode).toBe(baseline.source_mode);
  }
  expect(documentSummaryVersion.supersedes_version_id).toBe(
    summaryBeforeDocument.id,
  );
  expect(documentClaimsVersion.supersedes_version_id).toBe(
    claimsBeforeDocument.id,
  );
  expect(candidateRelationsVersion.supersedes_version_id).toBe(
    relationsBeforeDocument.id,
  );
  expect(candidateGraphVersion.supersedes_version_id).toBe(
    graphBeforeDocument.id,
  );

  const documentSummary = await apiData<PaperSummaryRead>(
    page,
    `/api/artifact-versions/${documentSummaryVersion.id}/paper-summary`,
  );
  const documentSource = await apiData<PaperSummaryDocumentSourceRead>(
    page,
    `/api/artifact-versions/${documentSummaryVersion.id}/paper-summary/document-source`,
  );
  expect(documentSource.research_input?.id).toBe(paperResearchInputId);
  expect(documentSource.research_input?.content_hash).toBe(
    persistedInput.content_hash,
  );
  expect(
    documentSummary.summary.input_versions.paper_collection_version_id,
  ).toBeNull();
  expect(documentSummary.summary.producer.model_name).toBe(
    QUALIFYING_QWEN_MODEL,
  );
  expect(
    documentSummary.summary.evidence.some(
      (item) =>
        item.locator.document_parse_id &&
        item.locator.document_parse_output_hash &&
        item.locator.document_locator?.bbox,
    ),
  ).toBe(true);
  expect(
    documentSummary.source_snapshots.some(
      (snapshot) => snapshot.id === persistedSourceSnapshotId,
    ),
  ).toBe(true);
  expect(documentSummary.evidence.length).toBeGreaterThan(0);

  expect(documentSummaryVersion.producer).toMatchObject({
    model_provider: "dashscope",
    requested_model: QUALIFYING_QWEN_MODEL,
    explicit_revision: QUALIFYING_QWEN_MODEL,
  });
  const providerReturnedModel =
    documentSummaryVersion.producer.provider_returned_model;
  expect(typeof providerReturnedModel).toBe("string");
  expect((providerReturnedModel ?? "").length).toBeGreaterThan(0);
  const providerRequestId =
    documentSummaryVersion.producer_execution.provider_request_id;
  expect(providerRequestId).toBeTruthy();
  expect(candidateRelationsVersion.producer).toMatchObject({
    model_provider: "dashscope",
    requested_model: QUALIFYING_QWEN_MODEL,
    explicit_revision: QUALIFYING_QWEN_MODEL,
  });

  const candidateRelations = await apiCollection<LiteratureRelationRead>(
    page,
    `/api/artifact-versions/${candidateRelationsVersion.id}/literature-relations?limit=100`,
  );
  expect(candidateRelations).toHaveLength(1);
  expect(candidateRelations[0]?.relation.status).toBe("candidate");
  expect(candidateRelations[0]?.relation.adjudication).toBeNull();
  expect(candidateRelations[0]?.graph_eligible).toBe(false);
  expect(candidateRelations[0]?.reasoning_trace?.steps.length).toBeGreaterThan(
    0,
  );
  expect(JSON.stringify(candidateRelations)).not.toMatch(
    /chain[_ -]?of[_ -]?thought|reasoning_content/iu,
  );
  const graphBeforeAdjudication = await apiData<GraphRead>(
    page,
    `/api/artifact-versions/${candidateGraphVersion.id}/graph`,
  );
  expect(graphBeforeAdjudication.integrity_report.status).toBe("passed");
  expect(graphBeforeAdjudication.edge_count).toBeGreaterThan(0);
  expect(
    graphBeforeAdjudication.integrity_report.counts.relation_edge_count,
  ).toBe(0);

  fullscreen = await openVersion(
    page,
    projectId ?? "",
    documentSummaryVersion.id,
  );
  await expect(fullscreen.getByTestId("paper-result-workspace")).toBeVisible();
  await expect(
    fullscreen.getByRole("link", { name: "下载论文原文" }),
  ).toBeVisible();
  const summaryDownloadPromise = page.waitForEvent("download");
  await fullscreen.getByRole("button", { name: "导出 Markdown" }).click();
  const summaryDownload = await summaryDownloadPromise;
  expect(summaryDownload.suggestedFilename()).toMatch(/\.md$/u);
  await createPublicShare(page, fullscreen, summaryArtifact.title);
  await fullscreen.getByRole("button", { name: "返回研究" }).click();

  fullscreen = await openVersion(
    page,
    projectId ?? "",
    candidateRelationsVersion.id,
  );
  await fullscreen.getByRole("button", { name: "基于此结果重新分析" }).click();
  await expect(page.getByLabel("选择候选关系")).toBeVisible();
  await expect(
    page.getByRole("radiogroup", { name: "选择关系审定结论" }),
  ).toContainText("接受并进入图谱");
  await page
    .getByRole("textbox", { name: "审定理由" })
    .fill("接受该候选关系，并将其作为经人工审定的关系进入证据图谱。");
  await page.getByRole("button", { name: "生成修订计划" }).click();
  await expect(page.getByRole("heading", { name: "修订计划" })).toBeVisible();
  const adjudicationRunId = await confirmRevision(page);
  const adjudicationRun = await waitForRun(page, adjudicationRunId);
  expect(adjudicationRun.derivation_kind).toBe("revision");
  expect(adjudicationRun.parent_run_id).toBe(documentRevisionRunId);

  const claimsAfterAdjudication = await latestVersion(
    page,
    claimsArtifact.artifactId,
  );
  const acceptedRelationsVersion = await latestVersion(
    page,
    relationsArtifact.artifactId,
  );
  const acceptedGraphVersion = await latestVersion(
    page,
    graphArtifact.artifactId,
  );
  expect(claimsAfterAdjudication.id).toBe(documentClaimsVersion.id);
  expect(acceptedRelationsVersion.supersedes_version_id).toBe(
    candidateRelationsVersion.id,
  );
  expect(acceptedGraphVersion.supersedes_version_id).toBe(
    candidateGraphVersion.id,
  );
  expect(acceptedRelationsVersion.created_by_run_id).toBe(adjudicationRunId);
  expect(acceptedGraphVersion.created_by_run_id).toBe(adjudicationRunId);

  const acceptedRelations = await apiCollection<LiteratureRelationRead>(
    page,
    `/api/artifact-versions/${acceptedRelationsVersion.id}/literature-relations?limit=100`,
  );
  expect(acceptedRelations).toHaveLength(1);
  expect(acceptedRelations[0]?.relation.status).toBe("accepted");
  expect(acceptedRelations[0]?.relation.adjudication?.decision).toBe(
    "accepted",
  );
  expect(acceptedRelations[0]?.graph_eligible).toBe(true);

  const acceptedGraph = await apiData<GraphRead>(
    page,
    `/api/artifact-versions/${acceptedGraphVersion.id}/graph`,
  );
  expect(acceptedGraph.integrity_report.status).toBe("passed");
  expect(acceptedGraph.integrity_report.counts.relation_edge_count).toBe(1);
  const graphEdges = await apiCollection<GraphEdgeRead>(
    page,
    `/api/artifact-versions/${acceptedGraphVersion.id}/graph/edges?limit=100`,
  );
  const relationEdge = graphEdges.find((item) => item.relation !== null);
  expect(relationEdge).toBeDefined();
  expect(relationEdge?.relation?.relation.adjudication?.decision).toBe(
    "accepted",
  );
  expect(relationEdge?.evidence.length).toBeGreaterThan(0);
  expect(
    relationEdge?.evidence.every(
      (item) =>
        item.evidence.source_snapshot_id === item.source_snapshot.id &&
        item.source_snapshot.content_hash.length > 0,
    ),
  ).toBe(true);

  fullscreen = await openVersion(
    page,
    projectId ?? "",
    acceptedGraphVersion.id,
  );
  const graphCanvas = fullscreen.getByLabel("可交互科学关系图");
  await expect(graphCanvas).toBeVisible();
  const graphRelationEdge = graphCanvas.locator(
    `.react-flow__edge[data-id="${String(relationEdge?.edge.edge_id)}"]`,
  );
  await graphRelationEdge.focus();
  await page.keyboard.press("Enter");
  await expect(graphRelationEdge).toHaveClass(/selected/u);
  await expect(fullscreen.getByText("人工审定", { exact: true })).toBeVisible();
  await expect(fullscreen.getByText("公开推导", { exact: true })).toBeVisible();
  await fullscreen
    .getByRole("button", { name: /查看证据/u })
    .first()
    .click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await expect(page.getByText("来源内容", { exact: true })).toBeVisible();

  const releaseEvidence = {
    gate: "release-candidate-qwen",
    source_commit: process.env.RELEASE_CANDIDATE_SOURCE_COMMIT ?? null,
    generated_at: new Date().toISOString(),
    model: {
      provider: "dashscope",
      requested_model: QUALIFYING_QWEN_MODEL,
      explicit_revision: QUALIFYING_QWEN_MODEL,
      provider_returned_model: providerReturnedModel,
    },
    producer_request_id: providerRequestId,
    runs: {
      initial: initialRunId,
      data_revision: dataRevisionRunId,
      document_revision: documentRevisionRunId,
      adjudication: adjudicationRunId,
    },
    artifact_versions: {
      document_summary: documentSummaryVersion.id,
      candidate_relations: candidateRelationsVersion.id,
      accepted_relations: acceptedRelationsVersion.id,
      accepted_graph: acceptedGraphVersion.id,
    },
    adjudication: {
      decision: "accepted",
      accepted_relation_count: acceptedRelations.length,
      graph_relation_edge_count:
        acceptedGraph.integrity_report.counts.relation_edge_count,
    },
    result: "passed",
  };
  const evidenceDir = path.resolve(".artifacts");
  await mkdir(evidenceDir, { recursive: true });
  await writeFile(
    path.join(evidenceDir, "release-candidate-qwen-evidence.json"),
    `${JSON.stringify(releaseEvidence, null, 2)}\n`,
    "utf8",
  );
});
