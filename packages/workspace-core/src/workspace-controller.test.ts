import { describe, expect, it, vi } from "vitest";
import type { DomainEntityId, WorkspaceSnapshot } from "@xingwen/domain";
import {
  createWorkspaceController,
  type WorkspaceSnapshotPort,
} from "./workspace-controller";

describe("WorkspaceController", () => {
  const mockProjectId = "prj_123" as DomainEntityId;

  const mockSnapshot: WorkspaceSnapshot = {
    id: `ws_${mockProjectId}` as DomainEntityId,
    projectId: mockProjectId,
    revision: 1,
    layoutPreset: "comparative",
    activeRunId: null,
    panelSlots: [],
    pinnedEvidenceIds: [],
    atlasState: null,
    observatoryState: null,
    selectedObjectRef: null,
    updatedAt: "2026-07-22T00:00:00Z" as never,
  };

  const createMockPort = (
    initialSnapshot: WorkspaceSnapshot | null = mockSnapshot,
  ): WorkspaceSnapshotPort => {
    let current = initialSnapshot;
    return {
      getByProjectId: vi.fn().mockImplementation(async () => current),
      save: vi.fn().mockImplementation(async (id, input, expectedRev) => {
        if (current && current.revision !== expectedRev) {
          const err = new Error("Conflict");
          err.name = "ConflictError";
          throw err;
        }
        current = {
          ...current,
          ...input,
          revision: expectedRev + 1,
          id: `ws_${id}`,
          projectId: id,
          updatedAt: "2026-07-22T01:00:00Z",
        } as WorkspaceSnapshot;
        return current;
      }),
    };
  };

  it("starts in idle state", () => {
    const controller = createWorkspaceController(createMockPort());
    expect(controller.getState().status).toBe("idle");
  });

  it("loads existing snapshot", async () => {
    const port = createMockPort();
    const controller = createWorkspaceController(port);

    await controller.load(mockProjectId);

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.layoutPreset).toBe("comparative");
    }
  });

  it("initializes default snapshot if none exists", async () => {
    const port = createMockPort(null);
    const controller = createWorkspaceController(port);

    await controller.load(mockProjectId);

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.layoutPreset).toBe("comparative");
      expect(state.snapshot.revision).toBe(0);
    }
  });

  it("updates layout preset and increments revision", async () => {
    const port = createMockPort();
    const controller = createWorkspaceController(port);
    await controller.load(mockProjectId);

    await controller.setLayoutPreset("focus");

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.layoutPreset).toBe("focus");
      expect(state.snapshot.revision).toBe(2);
    }
  });

  it("recovers from 409 conflict transparently", async () => {
    const port = createMockPort();
    const controller = createWorkspaceController(port);
    await controller.load(mockProjectId);

    // Simulate someone else updating the snapshot directly in the DB
    // by calling the mock save function to increment the revision.
    await port.save(
      mockProjectId,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      { layoutPreset: "grid" } as any,
      1,
    );

    // Now our controller has revision 1, but DB has revision 2.
    // Our update should fail on revision 1, fetch latest (rev 2), and retry automatically.
    await controller.setLayoutPreset("focus");

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.layoutPreset).toBe("focus");
      expect(state.snapshot.revision).toBe(3); // 2 + 1
    }
  });
});
