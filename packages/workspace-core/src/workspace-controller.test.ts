import { describe, expect, it, vi } from "vitest";
import type {
  DomainEntityId,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";

import {
  createWorkspaceController,
  type WorkspaceSnapshotPort,
} from "./workspace-controller";

const projectId = "prj_123" as DomainEntityId;

const emptyWorkspaceInput: WorkspaceSnapshotInput = {
  layoutPreset: "comparative",
  activeRunId: null,
  panelSlots: [],
  pinnedEvidenceIds: [],
  atlasState: null,
  observatoryState: null,
  selectedObjectRef: null,
};

function snapshot(
  revision = 1,
  input: WorkspaceSnapshotInput = emptyWorkspaceInput,
): WorkspaceSnapshot {
  return {
    id: `ws_${projectId}` as DomainEntityId,
    projectId,
    revision,
    ...input,
    updatedAt: "2026-07-22T00:00:00Z" as never,
  };
}

function createPort(
  initialSnapshot: WorkspaceSnapshot | null = snapshot(),
): WorkspaceSnapshotPort & {
  getByProjectId: ReturnType<typeof vi.fn>;
  save: ReturnType<typeof vi.fn>;
} {
  let current = initialSnapshot;
  const getByProjectId = vi.fn(async () => current);
  const save = vi.fn(
    async (
      id: DomainEntityId,
      input: WorkspaceSnapshotInput,
      expectedRevision: number,
    ): Promise<WorkspaceSnapshot> => {
      const currentRevision = current?.revision ?? 0;
      if (currentRevision !== expectedRevision) {
        const error = new Error("Workspace revision conflict");
        error.name = "ConflictError";
        throw error;
      }
      current = snapshot(currentRevision + 1, input);
      return { ...current, id, projectId: id };
    },
  );

  return { getByProjectId, save };
}

describe("WorkspaceController", () => {
  it("starts in idle state", () => {
    const controller = createWorkspaceController(createPort());

    expect(controller.getState()).toEqual({ status: "idle" });
  });

  it("loads an existing server snapshot without marking it dirty", async () => {
    const serverSnapshot = snapshot(4);
    const controller = createWorkspaceController(createPort(serverSnapshot));

    await controller.load(projectId);

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot).toEqual(serverSnapshot);
      expect(state.draft).toEqual(emptyWorkspaceInput);
      expect(state.expectedRevision).toBe(4);
      expect(state.dirty).toBe(false);
    }
  });

  it("creates an identity-free local draft when no snapshot exists", async () => {
    const port = createPort(null);
    const controller = createWorkspaceController(port);

    await controller.load(projectId);

    const state = controller.getState();
    expect(state.status).toBe("draft");
    if (state.status === "draft") {
      expect(state.snapshot).toBeNull();
      expect(state.draft).toEqual(emptyWorkspaceInput);
      expect(state.expectedRevision).toBe(0);
      expect(state.draft).not.toHaveProperty("id");
      expect(state.draft).not.toHaveProperty("updatedAt");
    }
    expect(port.save).not.toHaveBeenCalled();
  });

  it("keeps edits local until an explicit save", async () => {
    const port = createPort(snapshot(1));
    const controller = createWorkspaceController(port);
    await controller.load(projectId);

    await controller.setLayoutPreset("focus");

    let state = controller.getState();
    expect(state.status).toBe("draft");
    if (state.status === "draft") {
      expect(state.draft.layoutPreset).toBe("focus");
      expect(state.dirty).toBe(true);
    }
    expect(port.save).not.toHaveBeenCalled();

    await controller.save();

    state = controller.getState();
    expect(port.save).toHaveBeenCalledWith(
      projectId,
      expect.objectContaining({ layoutPreset: "focus" }),
      1,
    );
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.revision).toBe(2);
      expect(state.snapshot.layoutPreset).toBe("focus");
      expect(state.dirty).toBe(false);
    }
  });

  it("uses revision zero for the first explicit save", async () => {
    const port = createPort(null);
    const controller = createWorkspaceController(port);
    await controller.load(projectId);

    await controller.save();

    expect(port.save).toHaveBeenCalledWith(projectId, emptyWorkspaceInput, 0);
    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot.revision).toBe(1);
    }
  });

  it("reads the latest snapshot once and preserves the attempted draft on conflict", async () => {
    const original = snapshot(1);
    const latest = snapshot(2, {
      ...emptyWorkspaceInput,
      layoutPreset: "grid",
    });
    const getByProjectId = vi
      .fn()
      .mockResolvedValueOnce(original)
      .mockResolvedValueOnce(latest);
    const conflict = new Error("Workspace revision conflict");
    conflict.name = "ConflictError";
    const save = vi.fn().mockRejectedValue(conflict);
    const controller = createWorkspaceController({ getByProjectId, save });
    await controller.load(projectId);
    await controller.setLayoutPreset("focus");

    await controller.save();

    const state = controller.getState();
    expect(save).toHaveBeenCalledTimes(1);
    expect(getByProjectId).toHaveBeenCalledTimes(2);
    expect(state.status).toBe("conflict");
    if (state.status === "conflict") {
      expect(state.attemptedDraft.layoutPreset).toBe("focus");
      expect(state.latestSnapshot).toEqual(latest);
      expect(state.expectedRevision).toBe(1);
    }
  });

  it("keeps the dirty draft when a non-conflict save fails", async () => {
    const port = createPort(snapshot(1));
    port.save.mockRejectedValueOnce(new Error("Network unavailable"));
    const controller = createWorkspaceController(port);
    await controller.load(projectId);
    await controller.setLayoutPreset("focus");

    await controller.save();

    const state = controller.getState();
    expect(state.status).toBe("error");
    if (state.status === "error") {
      expect(state.draft.layoutPreset).toBe("focus");
      expect(state.dirty).toBe(true);
      expect(state.error.message).toBe("Network unavailable");
    }
  });

  it("does not save an empty local draft after the initial load fails", async () => {
    const getByProjectId = vi.fn(async () => {
      throw new Error("Workspace read unavailable");
    });
    const save = vi.fn();
    const controller = createWorkspaceController({ getByProjectId, save });

    await controller.load(projectId);

    const state = controller.getState();
    expect(state.status).toBe("error");
    if (state.status === "error") {
      expect(state.dirty).toBe(false);
    }
    await expect(controller.save()).rejects.toThrow("not editable");
    expect(save).not.toHaveBeenCalled();
  });

  it("keeps the newest load result when an earlier read resolves late", async () => {
    let resolveFirst: (value: WorkspaceSnapshot | null) => void = () => {};
    const firstRead = new Promise<WorkspaceSnapshot | null>((resolve) => {
      resolveFirst = resolve;
    });
    const latest = snapshot(3, {
      ...emptyWorkspaceInput,
      layoutPreset: "grid",
    });
    const getByProjectId = vi
      .fn()
      .mockReturnValueOnce(firstRead)
      .mockResolvedValueOnce(latest);
    const controller = createWorkspaceController({
      getByProjectId,
      save: vi.fn(),
    });

    const firstLoad = controller.load(projectId);
    await controller.load(projectId);
    resolveFirst(snapshot(1));
    await firstLoad;

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot).toEqual(latest);
    }
  });

  it("adopts the latest server snapshot only after an explicit user action", async () => {
    const original = snapshot(1);
    const latest = snapshot(2, {
      ...emptyWorkspaceInput,
      layoutPreset: "grid",
    });
    const getByProjectId = vi
      .fn()
      .mockResolvedValueOnce(original)
      .mockResolvedValueOnce(latest);
    const conflict = new Error("Workspace revision conflict");
    conflict.name = "ConflictError";
    const save = vi.fn().mockRejectedValue(conflict);
    const controller = createWorkspaceController({ getByProjectId, save });
    await controller.load(projectId);
    await controller.setLayoutPreset("focus");
    await controller.save();

    controller.adoptLatest();

    const state = controller.getState();
    expect(state.status).toBe("ready");
    if (state.status === "ready") {
      expect(state.snapshot).toEqual(latest);
      expect(state.draft.layoutPreset).toBe("grid");
      expect(state.expectedRevision).toBe(2);
      expect(state.dirty).toBe(false);
    }
  });
});
