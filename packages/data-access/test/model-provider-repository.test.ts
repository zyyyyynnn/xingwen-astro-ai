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

function envelope(revision: number, configured: boolean): Response {
  return new Response(
    JSON.stringify({
      data: {
        status: configured ? "ready" : "unconfigured",
        revision,
        source: configured ? "workspace" : null,
        preset: configured ? "dashscope" : null,
        base_url: configured
          ? "https://dashscope.aliyuncs.com/compatible-mode/v1"
          : null,
        dashscope_base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: configured ? "qwen-plus" : null,
        api_key_hint: configured ? "••••1234" : null,
        verified_at: configured ? "2026-08-24T00:00:00Z" : null,
        updated_at: configured ? "2026-08-24T00:00:00Z" : null,
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
    const responses = [
      { revision: 4, configured: true },
      { revision: 5, configured: true },
      { revision: 6, configured: false },
    ];
    const fetchImpl = (async (_input, init) => {
      requests.push({
        method: init?.method ?? "GET",
        headers: new Headers(init?.headers),
      });
      const response = responses.shift();
      if (response === undefined) throw new Error("unexpected request");
      return envelope(response.revision, response.configured);
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
    expect(removed.status).toBe("unconfigured");
    expect(removed.revision).toBe(6);
  });
});
