import { researchAdapter } from "@xingwen/research-adapter";
import { describe, expect, it, vi } from "vitest";

import { createWorkspaceRuntime } from "./runtime";

describe("createWorkspaceRuntime", () => {
  it("fails explicitly when the production API origin is missing", () => {
    expect(() => createWorkspaceRuntime({ apiBaseUrl: undefined })).toThrow(
      /VITE_API_BASE_URL is required/u,
    );
    expect(() => createWorkspaceRuntime({ apiBaseUrl: "" })).toThrow(
      /VITE_API_BASE_URL is required/u,
    );
  });

  it("creates the single HTTP Workspace application boundary", () => {
    const runtime = createWorkspaceRuntime({
      apiBaseUrl: "https://api.example.test",
      siteUrl: "https://www.example.test",
      fetchImpl: vi.fn(),
    });

    expect(runtime.siteUrl).toBe("https://www.example.test");
    expect(runtime.researchAdapter).toBe(researchAdapter);
    expect(runtime.session.getCurrent()).toBeNull();
    expect(runtime.application.sessionGate.getSnapshot().status).toBe(
      "checking",
    );
    expect("adapterKind" in runtime).toBe(false);
    expect("provenance" in runtime.repositories).toBe(false);
  });

  it("rejects versioned paths instead of selecting another adapter", () => {
    expect(() =>
      createWorkspaceRuntime({ apiBaseUrl: "https://api.example.test/api" }),
    ).toThrow(/origin/u);
  });

  it("rejects a Site URL with path state", () => {
    expect(() =>
      createWorkspaceRuntime({
        apiBaseUrl: "https://api.example.test",
        siteUrl: "https://www.example.test/home",
      }),
    ).toThrow(/VITE_SITE_URL must be an HTTP Site origin/u);
  });
});
