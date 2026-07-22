import type {
  DomainEntityId,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
  WorkspacePanelSlot,
} from "@xingwen/domain";

/**
 * Narrow port for workspace snapshot persistence.
 *
 * Defined here (not imported from `@xingwen/data-access`) so that
 * `workspace-core` depends only on `@xingwen/domain`. The full
 * `WorkspaceSnapshotRepository` in `data-access/ports` satisfies this
 * interface structurally.
 */
export interface WorkspaceSnapshotPort {
  getByProjectId(projectId: DomainEntityId): Promise<WorkspaceSnapshot | null>;
  save(
    projectId: DomainEntityId,
    snapshot: WorkspaceSnapshotInput,
    expectedRevision: number,
  ): Promise<WorkspaceSnapshot>;
}

export type WorkspaceState =
  | { readonly status: "idle" }
  | { readonly status: "loading"; readonly projectId: DomainEntityId }
  | { readonly status: "ready"; readonly snapshot: WorkspaceSnapshot }
  | { readonly status: "error"; readonly error: Error };

export type WorkspaceListener = (state: WorkspaceState) => void;

export interface WorkspaceController {
  getState(): WorkspaceState;
  subscribe(listener: WorkspaceListener): () => void;
  load(projectId: DomainEntityId): Promise<void>;
  setLayoutPreset(preset: string): Promise<void>;
  setPanelSlot(slot: WorkspacePanelSlot): Promise<void>;
  pinEvidence(evidenceId: DomainEntityId): Promise<void>;
  unpinEvidence(evidenceId: DomainEntityId): Promise<void>;
  setActiveRun(runId: DomainEntityId | null): Promise<void>;
}

export function createWorkspaceController(
  workspaces: WorkspaceSnapshotPort,
): WorkspaceController {
  let state: WorkspaceState = { status: "idle" };
  const listeners = new Set<WorkspaceListener>();

  const notify = () => {
    for (const listener of listeners) {
      listener(state);
    }
  };

  const updateSnapshot = async (
    updater: (input: WorkspaceSnapshotInput) => WorkspaceSnapshotInput,
  ): Promise<void> => {
    if (state.status !== "ready") {
      throw new Error("Cannot update workspace snapshot: workspace not ready");
    }

    const projectId = state.snapshot.projectId;
    const previousSnapshot = state.snapshot;
    const expectedRevision = previousSnapshot.revision;

    const input: WorkspaceSnapshotInput = {
      layoutPreset: previousSnapshot.layoutPreset,
      activeRunId: previousSnapshot.activeRunId,
      panelSlots: previousSnapshot.panelSlots,
      pinnedEvidenceIds: previousSnapshot.pinnedEvidenceIds,
      atlasState: previousSnapshot.atlasState,
      observatoryState: previousSnapshot.observatoryState,
      selectedObjectRef: previousSnapshot.selectedObjectRef,
    };

    const nextInput = updater(input);

    // Optimistically apply state changes
    state = {
      status: "ready",
      snapshot: {
        ...previousSnapshot,
        ...nextInput,
        revision: expectedRevision + 1, // optimistic rev
      },
    };
    notify();

    try {
      const savedSnapshot = await workspaces.save(
        projectId,
        nextInput,
        expectedRevision,
      );
      state = { status: "ready", snapshot: savedSnapshot };
      notify();
    } catch (err: unknown) {
      const error = err as Error;
      if (error.name === "ConflictError") {
        // Rollback and fetch the latest state
        const latest = await workspaces.getByProjectId(projectId);
        if (latest) {
          state = { status: "ready", snapshot: latest };
        } else {
          state = { status: "ready", snapshot: previousSnapshot };
        }
        notify();
        // Retry once transparently with the latest revision.
        if (latest) {
          try {
            const retrySaved = await workspaces.save(
              projectId,
              nextInput,
              latest.revision,
            );
            state = { status: "ready", snapshot: retrySaved };
            notify();
          } catch (retryErr: unknown) {
            // Retry also failed — keep state at `latest` and propagate.
            state = { status: "ready", snapshot: latest };
            notify();
            throw retryErr;
          }
        }
      } else {
        // Rollback and throw
        state = { status: "ready", snapshot: previousSnapshot };
        notify();
        throw err;
      }
    }
  };

  return {
    getState: () => state,
    subscribe: (listener: WorkspaceListener): (() => void) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    load: async (projectId: DomainEntityId): Promise<void> => {
      state = { status: "loading", projectId };
      notify();
      try {
        let snapshot = await workspaces.getByProjectId(projectId);
        if (!snapshot) {
          // If a workspace snapshot doesn't exist, we fallback to a default empty one
          // which is saved on the first mutation.
          snapshot = {
            id: `ws_${projectId}` as DomainEntityId,
            projectId,
            revision: 0,
            layoutPreset: "comparative",
            activeRunId: null,
            panelSlots: [],
            pinnedEvidenceIds: [],
            atlasState: null,
            observatoryState: null,
            selectedObjectRef: null,
            updatedAt: new Date().toISOString() as never,
          };
        }
        state = { status: "ready", snapshot };
        notify();
      } catch (err) {
        state = {
          status: "error",
          error: err instanceof Error ? err : new Error(String(err)),
        };
        notify();
      }
    },
    setLayoutPreset: (preset: string) =>
      updateSnapshot((input) => ({
        ...input,
        layoutPreset: preset,
      })),
    setPanelSlot: (slot: WorkspacePanelSlot) =>
      updateSnapshot((input) => {
        const otherSlots = input.panelSlots.filter(
          (s) => s.slotId !== slot.slotId,
        );
        return {
          ...input,
          panelSlots: [...otherSlots, slot],
        };
      }),
    pinEvidence: (evidenceId: DomainEntityId) =>
      updateSnapshot((input) => {
        if (input.pinnedEvidenceIds.includes(evidenceId)) return input;
        return {
          ...input,
          pinnedEvidenceIds: [...input.pinnedEvidenceIds, evidenceId],
        };
      }),
    unpinEvidence: (evidenceId: DomainEntityId) =>
      updateSnapshot((input) => ({
        ...input,
        pinnedEvidenceIds: input.pinnedEvidenceIds.filter(
          (id) => id !== evidenceId,
        ),
      })),
    setActiveRun: (runId: DomainEntityId | null) =>
      updateSnapshot((input) => ({
        ...input,
        activeRunId: runId,
      })),
  };
}
