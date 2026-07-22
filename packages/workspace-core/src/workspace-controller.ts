import type { RepositorySet } from "@xingwen/data-access";
import type {
  DomainEntityId,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
  WorkspacePanelSlot,
} from "@xingwen/domain";

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
  repositories: RepositorySet,
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
      const savedSnapshot = await repositories.workspaces.save(
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
        const latest = await repositories.workspaces.getByProjectId(projectId);
        if (latest) {
          state = { status: "ready", snapshot: latest };
        } else {
          state = { status: "ready", snapshot: previousSnapshot };
        }
        notify();
        // Automatically retry once with the latest revision?
        // We'll retry once transparently.
        if (latest) {
          const retrySaved = await repositories.workspaces.save(
            projectId,
            nextInput,
            latest.revision,
          );
          state = { status: "ready", snapshot: retrySaved };
          notify();
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
        let snapshot = await repositories.workspaces.getByProjectId(projectId);
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
