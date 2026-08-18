import { asEntityId } from "@xingwen/domain";
import { describe, expect, it } from "vitest";

import { HttpClient } from "../src/http-client";
import { createResearchInputRepository } from "../src/research-input-repository";
import type { SessionManager } from "../src/session";

const PROJECT_ID = asEntityId("proj_01JEXAMPLE");
const INPUT_ID = asEntityId("ri_01JEXAMPLE");
const REF = {
  id: INPUT_ID,
  type: "pdf",
  source_type: "upload",
  content_hash: `sha256:${"a".repeat(64)}`,
  filename: "observations.pdf",
  mime_type: "application/pdf",
  size_bytes: 7,
  created_at: "2026-08-16T00:00:00Z",
  source_snapshot_id: null,
  status: "accepted",
};

function makeSession(): SessionManager {
  return {
    ensureSession: async () => {
      throw new Error("not used");
    },
    getCurrent: () => null,
    revokeSession: async () => undefined,
    attachCsrf: (headers) => headers.set("X-CSRF-Token", "csrf-test"),
    onSessionExpired: () => () => undefined,
    notifyExpired: () => undefined,
  };
}

describe("ResearchInputRepository", () => {
  it("uploads multipart data through HttpClient and maps the server reference", async () => {
    let requestBody: BodyInit | null | undefined;
    let requestHeaders: Headers | undefined;
    const fetchImpl = (async (_input, init) => {
      requestBody = init?.body as BodyInit | null | undefined;
      requestHeaders = new Headers(init?.headers);
      return new Response(
        JSON.stringify({ data: REF, meta: { request_id: "req-test" } }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
    const http = new HttpClient({
      baseUrl: "http://test.local",
      fetchImpl,
      session: makeSession(),
    });
    const repository = createResearchInputRepository(http);

    const result = await repository.create({
      projectId: PROJECT_ID,
      type: "pdf",
      file: new Blob(["%PDF-1.7"]),
      filename: "observations.pdf",
      mimeType: "application/pdf",
      idempotencyKey: "research-input-test-1",
    });

    expect(result.id).toBe(INPUT_ID);
    expect(result.filename).toBe("observations.pdf");
    expect(requestBody).toBeInstanceOf(FormData);
    const form = requestBody as FormData;
    expect(form.get("project_id")).toBe(String(PROJECT_ID));
    expect(form.get("type")).toBe("pdf");
    expect(form.get("file")).toBeInstanceOf(Blob);
    expect(requestHeaders?.get("Content-Type")).not.toBe("application/json");
    expect(requestHeaders?.get("X-CSRF-Token")).toBe("csrf-test");
    expect(requestHeaders?.get("Idempotency-Key")).toBe(
      "research-input-test-1",
    );
  });
});
