import { describe, expect, it } from "vitest";

import { HttpClient } from "../src/http-client";
import { createModelProviderRepository } from "../src/model-provider-repository";
import type { SessionManager } from "../src/session";

function session(): SessionManager {
  return {
    ensureSession: async () => {
      throw new Error("not used");
    },
    getCurrent: () => null,
    revokeSession: async () => undefined,
    attachCsrf: (headers) => headers.set("X-CSRF-Token", "csrf-provider"),
    onSessionExpired: () => () => undefined,
    notifyExpired: () => undefined,
  };
}

function envelope(revision: number): Response {
  return new Response(
    JSON.stringify({
      data: {
        status: revision === 0 ? "unconfigured" : "ready",
        revision,
        source: revision === 0 ? null : "workspace",
        preset: revision === 0 ? null : "dashscope",
        base_url:
          revision === 0
            ? null
            : "https://dashscope.aliyuncs.com/compatible-mode/v1",
        dashscope_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: revision === 0 ? null : "qwen-plus",
        api_key_hint: revision === 0 ? null : "••••1234",
        verified_at: revision === 0 ? null : "2026-08-24T00:00:00Z",
        updated_at: revision === 0 ? null : "2026-08-24T00:00:00Z",
        editable: true,
      },
      meta: {
        request_id: "00000000-0000-0000-0000-000000000099",
        generated_at: "2026-08-24T00:00:00Z",
      },
      links: { self: "/api/model-provider/configuration" },
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("ModelProviderRepository", () => {
  it("carries the current revision through both configuration writes", async () => {
    const requests: Array<{
      readonly method: string;
      readonly headers: Headers;
    }> = [];
    const revisions = [4, 5, 0];
    const fetchImpl = (async (_input, init) => {
      requests.push({
        method: init?.method ?? "GET",
        headers: new Headers(init?.headers),
      });
      const revision = revisions.shift();
      if (revision === undefined) throw new Error("unexpected request");
      return envelope(revision);
    }) as typeof fetch;
    const repository = createModelProviderRepository(
      new HttpClient({
        baseUrl: "http://test.local",
        fetchImpl,
        session: session(),
      }),
    );

    const current = await repository.getConfiguration();
    const configured = await repository.configure(
      {
        preset: "dashscope",
        baseUrl: null,
        model: "qwen-plus",
        apiKey: "secret-key-1234",
      },
      current.revision,
    );
    const removed = await repository.removeConfiguration(configured.revision);

    expect(requests.map((request) => request.method)).toEqual([
      "GET",
      "PUT",
      "DELETE",
    ]);
    expect(requests[1]?.headers.get("If-Match")).toBe("4");
    expect(requests[2]?.headers.get("If-Match")).toBe("5");
    expect(removed.revision).toBe(0);
  });
});
