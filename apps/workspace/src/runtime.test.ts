import { describe, expect, it } from "vitest";

import { createWorkspaceRuntime } from "./runtime";

describe("createWorkspaceRuntime", () => {
  it("uses the frozen fixture adapter when no API origin is configured", () => {
    const runtime = createWorkspaceRuntime({ apiBaseUrl: undefined });

    expect(runtime.adapterKind).toBe("fixture");
    if (runtime.adapterKind === "fixture") {
      expect(runtime.bootstrap.projectId).toBe("proj_01JEXAMPLE");
      expect(runtime.bootstrap.draftId).toBe("rcd_01JTOUR");
      expect(runtime.bootstrap.runId).toBe("run_01JEXAMPLE");
    }
  });

  it("uses the HTTP adapter only for a valid API origin", () => {
    const runtime = createWorkspaceRuntime({
      apiBaseUrl: "https://api.example.test",
    });

    expect(runtime.adapterKind).toBe("http");
    if (runtime.adapterKind === "http") {
      expect(runtime.session.getCurrent()).toBeNull();
    }
  });

  it("rejects a versioned API path instead of silently falling back to Fixture", () => {
    expect(() =>
      createWorkspaceRuntime({
        apiBaseUrl: "https://api.example.test/base/path",
      }),
    ).toThrow(/origin/u);
  });
});
