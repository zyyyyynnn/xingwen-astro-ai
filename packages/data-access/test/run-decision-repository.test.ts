import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { createHttpRepositories } from "../src/http-adapter";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";
import {
  createSessionManagerForTest,
  httpServer,
  TEST_BASE_URL,
} from "./http-helpers";

function envelope<T>(data: T) {
  return {
    data,
    meta: {
      request_id: "req_decision_test",
      schema_version: "2.0.0",
      generated_at: "2026-07-21T08:30:00Z",
    },
  };
}

const RUN_ID = "run_01JEXAMPLE" as never;
const PROJECT_ID = "proj_01JEXAMPLE" as never;

function setupRepos() {
  const session = createSessionManagerForTest();
  return createHttpRepositories({
    baseUrl: TEST_BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  });
}

describe("run checkpoint and decision repositories", () => {
  it("maps a checkpoint and posts a generated decision request with concurrency headers", async () => {
    const fixtureCheckpoint = exoplanetHostStarFixture.data.runCheckpoints![0]!;
    const fixtureRun = exoplanetHostStarFixture.data.runs[0]!;
    let received: { headers: Headers; body: unknown } | null = null;
    httpServer.use(
      http.get(`${TEST_BASE_URL}/api/runs/:runId/checkpoint`, () =>
        HttpResponse.json(envelope(fixtureCheckpoint)),
      ),
      http.post(
        `${TEST_BASE_URL}/api/runs/:runId/decisions`,
        async ({ request }) => {
          received = {
            headers: request.headers,
            body: await request.json(),
          };
          return HttpResponse.json(
            envelope({
              decision: {
                id: "decision_01",
                parent_run_id: fixtureRun.id,
                child_run_id: "run_child_01",
                step_key: fixtureCheckpoint.step_key,
                decision: "resume",
                input_ids: ["input_01"],
                created_at: "2026-07-21T08:31:00Z",
              },
              run: {
                ...fixtureRun,
                id: "run_child_01",
                parent_run_id: fixtureRun.id,
                derivation_kind: "retry",
                status: "queued",
                revision: 1,
              },
            }),
          );
        },
      ),
    );
    const repos = setupRepos();
    const checkpoint = await repos.runs.getCheckpoint(RUN_ID);
    expect(checkpoint?.requiredInputTypes).toEqual(["pdf", "text"]);
    const result = await repos.runs.decide(
      RUN_ID,
      { decision: "resume", inputIds: ["input_01" as never] },
      4,
      "decision-replay-key",
    );
    expect(result.decision.childRunId).toBe("run_child_01");
    expect(result.run.id).toBe("run_child_01");
    expect(received?.body).toEqual({
      decision: "resume",
      input_ids: ["input_01"],
    });
    expect(received?.headers.get("If-Match")).toBe("4");
    expect(received?.headers.get("Idempotency-Key")).toBe(
      "decision-replay-key",
    );
  });
});

describe("research input repository", () => {
  it("lists, creates multipart uploads, and binds an input without a second DTO", async () => {
    const input = exoplanetHostStarFixture.data.researchInputs![0]!;
    let multipartContentType: string | null = null;
    httpServer.use(
      http.get(`${TEST_BASE_URL}/api/research-inputs`, () =>
        HttpResponse.json({
          data: [input],
          page: { next_cursor: null, has_more: false, limit: 100 },
        }),
      ),
      http.post(`${TEST_BASE_URL}/api/research-inputs`, async ({ request }) => {
        multipartContentType = request.headers.get("Content-Type");
        const form = await request.formData();
        expect(form.get("project_id")).toBe(String(PROJECT_ID));
        expect(form.get("type")).toBe("pdf");
        return HttpResponse.json(envelope(input), { status: 201 });
      }),
      http.post(
        `${TEST_BASE_URL}/api/research-inputs/:inputId/bind`,
        async ({ request }) => {
          expect(await request.json()).toEqual({
            project_id: String(PROJECT_ID),
            run_id: String(RUN_ID),
            contract_draft_id: null,
          });
          return HttpResponse.json(envelope(input));
        },
      ),
    );
    const repos = setupRepos();
    expect(await repos.researchInputs.listByProject(PROJECT_ID)).toHaveLength(
      1,
    );
    const created = await repos.researchInputs.create({
      type: "pdf",
      projectId: PROJECT_ID,
      content: new TextEncoder().encode("pdf fixture").buffer,
      filename: "source.pdf",
      mimeType: "application/pdf",
      idempotencyKey: "input-upload-key",
    });
    expect(created.id).toBe(input.id);
    expect(multipartContentType).toContain("multipart/form-data");
    expect(
      await repos.researchInputs.bindToRun(
        input.id as never,
        PROJECT_ID,
        RUN_ID,
      ),
    ).toEqual({
      contentHash: input.content_hash,
      createdAt: input.created_at,
      filename: input.filename,
      id: input.id,
      mimeType: input.mime_type,
      sizeBytes: input.size_bytes,
      sourceSnapshotId: input.source_snapshot_id,
      sourceType: input.source_type,
      status: input.status,
      type: input.type,
    });
  });

  it("supplies the canonical FITS MIME when the browser leaves File.type empty", async () => {
    const input = exoplanetHostStarFixture.data.researchInputs![0]!;
    httpServer.use(
      http.post(`${TEST_BASE_URL}/api/research-inputs`, async ({ request }) => {
        const form = await request.formData();
        expect(form.get("type")).toBe("fits");
        expect(form.get("mime_type")).toBe("application/fits");
        const file = form.get("file");
        expect(file).toBeInstanceOf(File);
        expect((file as File).type).toBe("application/fits");
        return HttpResponse.json(
          envelope({
            ...input,
            type: "fits",
            filename: "observation.fits",
            mime_type: "application/fits",
          }),
          { status: 201 },
        );
      }),
    );
    const repos = setupRepos();

    const created = await repos.researchInputs.create({
      type: "fits",
      projectId: PROJECT_ID,
      content: new Uint8Array([1, 2, 3]).buffer,
      filename: "observation.fits",
      mimeType: null,
      idempotencyKey: "fits-upload-key",
    });

    expect(created.type).toBe("fits");
    expect(created.mimeType).toBe("application/fits");
  });

  it("supplies canonical ZIP MIME for a typed image dataset", async () => {
    const input = exoplanetHostStarFixture.data.researchInputs![0]!;
    httpServer.use(
      http.post(`${TEST_BASE_URL}/api/research-inputs`, async ({ request }) => {
        const form = await request.formData();
        expect(form.get("type")).toBe("image_dataset");
        expect(form.get("mime_type")).toBe("application/zip");
        const file = form.get("file");
        expect(file).toBeInstanceOf(File);
        expect((file as File).type).toBe("application/zip");
        return HttpResponse.json(
          envelope({
            ...input,
            type: "image_dataset",
            filename: "training-images.zip",
            mime_type: "application/zip",
          }),
          { status: 201 },
        );
      }),
    );
    const repos = setupRepos();

    const created = await repos.researchInputs.create({
      type: "image_dataset",
      projectId: PROJECT_ID,
      content: new Uint8Array([80, 75, 3, 4]).buffer,
      filename: "training-images.zip",
      mimeType: null,
      idempotencyKey: "image-dataset-upload-key",
    });

    expect(created.type).toBe("image_dataset");
    expect(created.mimeType).toBe("application/zip");
  });
});
