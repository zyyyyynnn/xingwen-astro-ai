import { http, HttpResponse } from "msw";
import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { createHttpRepositories } from "../src/http-adapter";
import {
  createSessionManagerForTest,
  httpServer,
  TEST_BASE_URL,
} from "./http-helpers";

const exportRead = {
  id: "export_dataset_json_01",
  artifact_version_id: "artv_dataset_01",
  project_id: "proj_01JEXAMPLE",
  format: "json" as const,
  status: "completed" as const,
  content_hash: `sha256:${"a".repeat(64)}`,
  generated_at: "2026-08-14T00:00:00Z",
  expires_at: "2026-08-15T00:00:00Z",
  download_url: "/api/exports/export_dataset_json_01/download",
};

function envelope(data: unknown) {
  return {
    data,
    meta: {
      request_id: "req_export_test",
      schema_version: "2.0.0",
      generated_at: "2026-08-14T00:00:00Z",
    },
  };
}

function setupRepos() {
  const session = createSessionManagerForTest();
  return createHttpRepositories({
    baseUrl: TEST_BASE_URL,
    fetchImpl: globalThis.fetch,
    session,
  });
}

describe("artifact export repository", () => {
  it("validates the formal read model and downloads only through the export endpoint", async () => {
    let idempotencyKey: string | null = null;
    httpServer.use(
      http.post(
        `${TEST_BASE_URL}/api/artifact-versions/:versionId/exports`,
        async ({ params, request }) => {
          expect(params.versionId).toBe(exportRead.artifact_version_id);
          expect(await request.json()).toEqual({ format: "json" });
          idempotencyKey = request.headers.get("Idempotency-Key");
          return HttpResponse.json(envelope(exportRead), { status: 201 });
        },
      ),
      http.get(`${TEST_BASE_URL}/api/exports/:exportId`, ({ params }) => {
        expect(params.exportId).toBe(exportRead.id);
        return HttpResponse.json(envelope(exportRead));
      }),
      http.get(
        `${TEST_BASE_URL}/api/exports/:exportId/download`,
        ({ params }) => {
          expect(params.exportId).toBe(exportRead.id);
          return new HttpResponse(JSON.stringify({ rows: 1 }), {
            headers: { "Content-Type": "application/json" },
          });
        },
      ),
    );
    const repository = setupRepos().artifactExports;

    const created = await repository.create(
      asEntityId(exportRead.artifact_version_id),
      "json",
    );
    expect(idempotencyKey).toMatch(/^artifact-export-artv_dataset_01-/u);
    expect(created).toMatchObject({
      id: exportRead.id,
      artifactVersionId: exportRead.artifact_version_id,
      projectId: exportRead.project_id,
      format: "json",
      status: "completed",
    });
    const current = await repository.get(created.id);
    const download = await repository.download(current);
    expect(download.fileName).toBe("artv_dataset_01.json");
    expect(new TextDecoder().decode(download.bytes)).toBe('{"rows":1}');
  });

  it("rejects an export response that is outside ArtifactExportRead", async () => {
    httpServer.use(
      http.get(`${TEST_BASE_URL}/api/exports/:exportId`, () =>
        HttpResponse.json(
          envelope({ ...exportRead, status: "pending", unexpected: true }),
        ),
      ),
    );

    await expect(
      setupRepos().artifactExports.get(asEntityId(exportRead.id)),
    ).rejects.toThrow("contract validation failed for ArtifactExportRead");
  });
});
