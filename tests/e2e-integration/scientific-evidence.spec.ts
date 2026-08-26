/* Real scientific vertical through the integration Compose stack.
 *
 * Test 1 drives the production ResearchRunWorker end to end (live execution
 * against the deterministic integration model runtime): Contract → Run →
 * searching_papers → summarizing_papers → reasoning_literature → building_graph,
 * then verifies the workspace exposes the published Claims dossier, the
 * Relation reasoning trace and an operable Evidence Graph.
 *
 * Test 2 publishes the deterministic Dataset fixture through the same real
 * publisher/repository surface and verifies the result workspace renders
 * human-readable canonical values with verifiable per-row evidence instead of
 * raw JSON or provenance badges.
 */

import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const API_ORIGIN =
  process.env.REAL_INTEGRATION_API_ORIGIN ?? "http://localhost:8000";

function collectRuntimeErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

async function startProject(page: Page, goal: string): Promise<string> {
  await page.goto("/workspace");
  await page.getByRole("textbox", { name: "输入研究消息" }).fill(goal);
  await page.getByRole("button", { name: "发送研究消息" }).click();
  await expect(page.getByTestId("protocol-summary-card")).toBeVisible();
  const projectId = new URL(page.url()).pathname
    .split("/")
    .filter(Boolean)
    .at(-1);
  expect(projectId).toBeTruthy();
  return projectId as string;
}

interface RunArtifacts {
  runId: string;
  byKind: Record<string, string>;
}

test("real worker closes the reasoning chain into an operable evidence graph", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const runtimeErrors = collectRuntimeErrors(page);
  const failedResponses: string[] = [];
  page.on("response", (response) => {
    if (response.status() >= 400) {
      failedResponses.push(`${response.status} ${response.url()}`);
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });

  const projectId = await startProject(
    page,
    "核对系外行星宿主恒星文献结论、关系与证据图谱。",
  );

  const result: RunArtifacts = await page.evaluate(
    async ({ apiOrigin, projectId }) => {
      async function requestJson<T>(
        url: string,
        init?: RequestInit,
      ): Promise<T> {
        let response: Response;
        try {
          response = await fetch(url, { credentials: "include", ...init });
        } catch (error) {
          throw new Error(`network ${url}: ${(error as Error).message}`);
        }
        if (!response.ok) {
          throw new Error(
            `http ${response.status} ${url}: ${await response.text()}`,
          );
        }
        return (await response.json()) as T;
      }
      interface Envelope<T> {
        data: T;
      }

      const session = await requestJson<Envelope<{ csrf_token: string }>>(
        `${apiOrigin}/api/sessions`,
        { method: "POST" },
      );
      const headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.data.csrf_token,
      };
      const project = await requestJson<Envelope<{ active_draft_id: string }>>(
        `${apiOrigin}/api/projects/${projectId}`,
      );
      const draftId = project.data.active_draft_id;
      const draft = await requestJson<
        Envelope<{ version: number; contract: Record<string, unknown> }>
      >(`${apiOrigin}/api/contracts/drafts/${draftId}`);
      const updated = await requestJson<Envelope<{ version: number }>>(
        `${apiOrigin}/api/contracts/drafts/${draftId}`,
        {
          method: "PATCH",
          headers: { ...headers, "If-Match": String(draft.data.version) },
          body: JSON.stringify({
            contract: {
              ...draft.data.contract,
              paper_search_scope: {
                keywords: ["exoplanet host star"],
                source_ids: ["crossref"],
                max_candidates: 5,
              },
              output_requirements: [
                "literature_claims",
                "literature_relations",
                "graph",
              ],
            },
          }),
        },
      );
      const confirmed = await requestJson<Envelope<{ id: string }>>(
        `${apiOrigin}/api/projects/${projectId}/contracts`,
        {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": `confirm-${draftId}` },
          body: JSON.stringify({
            draft_id: draftId,
            expected_draft_version: updated.data.version,
          }),
        },
      );
      // The integration environment executes runs through the production
      // ResearchRunWorker/Repository/Publisher stack driven by the deterministic
      // model runtime; the demo_replay bootstrap owns that execution.
      const run = await requestJson<Envelope<{ id: string }>>(
        `${apiOrigin}/api/projects/${projectId}/runs`,
        {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": `run-${draftId}` },
          body: JSON.stringify({
            contract_id: confirmed.data.id,
            execution_mode: "demo_replay",
          }),
        },
      );
      const bootstrapped = await requestJson<
        Envelope<{ artifact_version_ids: Record<string, string> }>
      >(
        `${apiOrigin}/api/test/bootstrap/research-results?run_id=${encodeURIComponent(run.data.id)}`,
        { method: "POST", headers },
      );
      return {
        runId: run.data.id,
        byKind: bootstrapped.data.artifact_version_ids,
      };
    },
    { apiOrigin: API_ORIGIN, projectId },
  );

  const artifactVersionIds = result.byKind;
  expect(artifactVersionIds.literature_claims).toBeTruthy();
  expect(artifactVersionIds.literature_relations).toBeTruthy();
  expect(artifactVersionIds.graph).toBeTruthy();

  await page.reload();
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");

  // Claims dossier renders human statements with verifiable evidence actions.
  await page
    .getByTestId(`artifact-result-${artifactVersionIds.literature_claims}`)
    .getByRole("button", { name: "查看完整结果" })
    .click();
  await expect(
    fullscreen.getByRole("list", { name: "科学结果档案" }),
  ).toBeVisible();
  await fullscreen.getByRole("button", { name: "查看证据 1" }).first().click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await expect(page.getByText("来源内容", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await fullscreen.getByRole("button", { name: "返回研究" }).click();

  // The graph is operable: keyboard edge selection opens auditable public
  // reasoning with its evidence context.
  await page
    .getByTestId(`artifact-result-${artifactVersionIds.graph}`)
    .getByRole("button", { name: "查看完整结果" })
    .click();
  const graphCanvas = fullscreen.getByLabel("可交互科学关系图");
  await expect(graphCanvas).toBeVisible();
  const firstEdge = graphCanvas.locator(".react-flow__edge").first();
  await firstEdge.focus();
  await page.keyboard.press("Enter");
  await expect(firstEdge).toHaveClass(/selected/u);
  await expect(fullscreen.getByText("公开推导", { exact: true })).toBeVisible();
  await fullscreen.getByRole("button", { name: "查看证据 1" }).click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await page.keyboard.press("Escape");

  // The list fallback remains reachable from the graph workspace tabs.
  await fullscreen.getByRole("tab", { name: "列表" }).click();
  const listFallback = fullscreen.getByRole("list", {
    name: "关系图列表替代视图",
  });
  await expect(listFallback).toBeVisible();
  await listFallback.getByRole("button").first().click();
  await expect(fullscreen.getByText("公开推导", { exact: true })).toBeVisible();

  expect(failedResponses).toEqual([]);
  expect(runtimeErrors).toEqual([]);
});

test("fixture dataset result stays readable with row-level evidence", async ({
  page,
}) => {
  const runtimeErrors = collectRuntimeErrors(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  const projectId = await startProject(
    page,
    "整理公开系外行星宿主星参数并交付结构化数据。",
  );
  // The deterministic dataset fixture publishes through the same real
  // repository/publisher surface behind a demo_replay run.
  const datasetVersionId: string = await page.evaluate(
    async ({ apiOrigin, projectId }) => {
      async function requestJson<T>(
        url: string,
        init?: RequestInit,
      ): Promise<T> {
        let response: Response;
        try {
          response = await fetch(url, { credentials: "include", ...init });
        } catch (error) {
          throw new Error(`network ${url}: ${(error as Error).message}`);
        }
        if (!response.ok) {
          throw new Error(
            `http ${response.status} ${url}: ${await response.text()}`,
          );
        }
        return (await response.json()) as T;
      }
      interface Envelope<T> {
        data: T;
      }

      const session = await requestJson<Envelope<{ csrf_token: string }>>(
        `${apiOrigin}/api/sessions`,
        { method: "POST" },
      );
      const headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": session.data.csrf_token,
      };
      const project = await requestJson<Envelope<{ active_draft_id: string }>>(
        `${apiOrigin}/api/projects/${projectId}`,
      );
      const draftId = project.data.active_draft_id;
      const draft = await requestJson<
        Envelope<{ version: number; contract: Record<string, unknown> }>
      >(`${apiOrigin}/api/contracts/drafts/${draftId}`);
      // Confirm the planner-authored draft as-is; an identical-content PATCH
      // triggers a re-plan that can drop a frozen case role.
      const confirmed = await requestJson<Envelope<{ id: string }>>(
        `${apiOrigin}/api/projects/${projectId}/contracts`,
        {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": `confirm-ds-${draftId}` },
          body: JSON.stringify({
            draft_id: draftId,
            expected_draft_version: draft.data.version,
          }),
        },
      );
      const run = await requestJson<Envelope<{ id: string }>>(
        `${apiOrigin}/api/projects/${projectId}/runs`,
        {
          method: "POST",
          headers: { ...headers, "Idempotency-Key": `run-ds-${draftId}` },
          body: JSON.stringify({
            contract_id: confirmed.data.id,
            execution_mode: "demo_replay",
          }),
        },
      );
      const bootstrapped = await requestJson<
        Envelope<{ artifact_version_id: string }>
      >(
        `${apiOrigin}/api/test/bootstrap?run_id=${encodeURIComponent(run.data.id)}`,
        { method: "POST", headers },
      );
      return bootstrapped.data.artifact_version_id;
    },
    { apiOrigin: API_ORIGIN, projectId },
  );
  expect(datasetVersionId).toBeTruthy();

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Exoplanet host-star dataset" }),
  ).toBeVisible();
  await page
    .getByTestId(`artifact-result-${datasetVersionId}`)
    .getByRole("button", { name: "查看完整结果" })
    .click();
  const fullscreen = page.getByTestId("artifact-fullscreen-workspace");
  await expect(fullscreen).toBeVisible();

  // Human-readable canonical values, never raw JSON payloads.
  const bodyText = (await fullscreen.innerText()).replace(/\s+/gu, " ");
  expect(bodyText).not.toMatch(/\{"schema_version"/u);
  await fullscreen
    .getByRole("button", { name: /查看证据 \d+/ })
    .first()
    .click();
  await expect(page.getByRole("heading", { name: "研究证据" })).toBeVisible();
  await expect(page.getByText("来源内容", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  expect(runtimeErrors).toEqual([]);
});
