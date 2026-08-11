import type { DomainEntityId } from "@xingwen/domain";
import { researchAdapter } from "@xingwen/research-adapter";
import { describe, expect, it } from "vitest";

import { createWorkspaceRuntime } from "./runtime";

function entityId(value: string): DomainEntityId {
  return value as DomainEntityId;
}

describe("createWorkspaceRuntime", () => {
  it("uses the frozen fixture adapter when no API origin is configured", () => {
    const runtime = createWorkspaceRuntime({ apiBaseUrl: undefined });

    expect(runtime.adapterKind).toBe("fixture");
    expect(runtime.researchAdapter).toBe(researchAdapter);
    expect(runtime.workspaceController.getState()).toMatchObject({
      status: "idle",
    });
  });

  it("uses the HTTP adapter only for a valid API origin", () => {
    const runtime = createWorkspaceRuntime({
      apiBaseUrl: "https://api.example.test",
    });

    expect(runtime.adapterKind).toBe("http");
    expect(runtime.researchAdapter).toBe(researchAdapter);
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

  it("wires the real Fixture Repository Set and Workspace Controller", async () => {
    const runtime = createWorkspaceRuntime({ apiBaseUrl: undefined });
    if (runtime.adapterKind !== "fixture") {
      throw new Error("Expected Fixture runtime.");
    }

    const project = await runtime.repositories.projects.getById(
      entityId("proj_01JEXAMPLE"),
    );
    expect(project).not.toBeNull();
    if (project === null) {
      throw new Error("Expected the fixture project.");
    }
    const viewModel = runtime.researchAdapter.toProjectViewModel(project);
    expect(viewModel).toMatchObject({
      id: entityId("proj_01JEXAMPLE"),
      caseKey: "exoplanet_host_star",
    });
    expect("sessionId" in viewModel).toBe(false);
    await runtime.workspaceController.load(entityId("proj_01JEXAMPLE"));
    expect(runtime.workspaceController.getState()).toMatchObject({
      status: "draft",
    });
  });
});
