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

interface WorkspaceDraftState {
  readonly projectId: DomainEntityId;
  readonly snapshot: WorkspaceSnapshot | null;
  readonly draft: WorkspaceSnapshotInput;
  readonly expectedRevision: number;
  readonly dirty: boolean;
}

export type WorkspaceState =
  | { readonly status: "idle" }
  | { readonly status: "loading"; readonly projectId: DomainEntityId }
  | ({ readonly status: "ready"; readonly snapshot: WorkspaceSnapshot } & Omit<
      WorkspaceDraftState,
      "snapshot" | "dirty"
    > & { readonly dirty: false })
  | ({ readonly status: "draft" } & WorkspaceDraftState)
  | ({ readonly status: "saving" } & WorkspaceDraftState)
  | {
      readonly status: "conflict";
      readonly projectId: DomainEntityId;
      readonly attemptedDraft: WorkspaceSnapshotInput;
      readonly expectedRevision: number;
      readonly latestSnapshot: WorkspaceSnapshot | null;
    }
  | ({ readonly status: "error"; readonly error: Error } & WorkspaceDraftState);

export type WorkspaceListener = (state: WorkspaceState) => void;

export interface WorkspaceController {
  getState(): WorkspaceState;
  subscribe(listener: WorkspaceListener): () => void;
  load(projectId: DomainEntityId): Promise<void>;
  save(): Promise<void>;
  adoptLatest(): void;
  setLayoutPreset(preset: string): Promise<void>;
  setPanelSlot(slot: WorkspacePanelSlot): Promise<void>;
  pinEvidence(evidenceId: DomainEntityId): Promise<void>;
  unpinEvidence(evidenceId: DomainEntityId): Promise<void>;
  setActiveRun(runId: DomainEntityId | null): Promise<void>;
}

function createDraft(): WorkspaceSnapshotInput {
  return {
    layoutPreset: "comparative",
    activeRunId: null,
    panelSlots: [],
    pinnedEvidenceIds: [],
    atlasState: null,
    observatoryState: null,
    selectedObjectRef: null,
  };
}

function toInput(snapshot: WorkspaceSnapshot): WorkspaceSnapshotInput {
  return {
    layoutPreset: snapshot.layoutPreset,
    activeRunId: snapshot.activeRunId,
    panelSlots: snapshot.panelSlots,
    pinnedEvidenceIds: snapshot.pinnedEvidenceIds,
    atlasState: snapshot.atlasState,
    observatoryState: snapshot.observatoryState,
    selectedObjectRef: snapshot.selectedObjectRef,
  };
}

function toError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

function isConflict(error: Error): boolean {
  return error.name === "ConflictError";
}

function isEditableState(
  state: WorkspaceState,
): state is Extract<
  WorkspaceState,
  { readonly status: "ready" | "draft" | "error" }
> {
  return (
    state.status === "ready" ||
    state.status === "draft" ||
    (state.status === "error" && state.dirty)
  );
}

export function createWorkspaceController(
  workspaces: WorkspaceSnapshotPort,
): WorkspaceController {
  let state: WorkspaceState = { status: "idle" };
  let requestSequence = 0;
  const listeners = new Set<WorkspaceListener>();

  const notify = () => {
    for (const listener of listeners) {
      listener(state);
    }
  };

  const updateDraft = async (
    updater: (input: WorkspaceSnapshotInput) => WorkspaceSnapshotInput,
  ): Promise<void> => {
    if (!isEditableState(state)) {
      throw new Error(
        "Cannot update workspace draft: workspace is not editable",
      );
    }

    state = {
      status: "draft",
      projectId: state.projectId,
      snapshot: state.snapshot,
      draft: updater(state.draft),
      expectedRevision: state.expectedRevision,
      dirty: true,
    };
    notify();
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
      const request = ++requestSequence;
      state = { status: "loading", projectId };
      notify();

      try {
        const snapshot = await workspaces.getByProjectId(projectId);
        if (request !== requestSequence) return;
        if (snapshot === null) {
          state = {
            status: "draft",
            projectId,
            snapshot: null,
            draft: createDraft(),
            expectedRevision: 0,
            dirty: false,
          };
        } else {
          state = {
            status: "ready",
            projectId,
            snapshot,
            draft: toInput(snapshot),
            expectedRevision: snapshot.revision,
            dirty: false,
          };
        }
      } catch (error) {
        if (request !== requestSequence) return;
        state = {
          status: "error",
          projectId,
          snapshot: null,
          draft: createDraft(),
          expectedRevision: 0,
          dirty: false,
          error: toError(error),
        };
      }
      if (request === requestSequence) notify();
    },
    save: async (): Promise<void> => {
      if (!isEditableState(state)) {
        throw new Error(
          "Cannot save workspace draft: workspace is not editable",
        );
      }
      if (state.status === "ready") {
        return;
      }

      const request = ++requestSequence;
      const attempted = {
        projectId: state.projectId,
        snapshot: state.snapshot,
        draft: state.draft,
        expectedRevision: state.expectedRevision,
        dirty: state.dirty,
      };
      state = { status: "saving", ...attempted };
      notify();

      try {
        const savedSnapshot = await workspaces.save(
          attempted.projectId,
          attempted.draft,
          attempted.expectedRevision,
        );
        if (request !== requestSequence) return;
        state = {
          status: "ready",
          projectId: attempted.projectId,
          snapshot: savedSnapshot,
          draft: toInput(savedSnapshot),
          expectedRevision: savedSnapshot.revision,
          dirty: false,
        };
      } catch (error) {
        if (request !== requestSequence) return;
        const saveError = toError(error);
        if (isConflict(saveError)) {
          try {
            const latestSnapshot = await workspaces.getByProjectId(
              attempted.projectId,
            );
            if (request !== requestSequence) return;
            state = {
              status: "conflict",
              projectId: attempted.projectId,
              attemptedDraft: attempted.draft,
              expectedRevision: attempted.expectedRevision,
              latestSnapshot,
            };
          } catch (readError) {
            if (request !== requestSequence) return;
            state = {
              status: "error",
              ...attempted,
              dirty: true,
              error: toError(readError),
            };
          }
        } else {
          state = {
            status: "error",
            ...attempted,
            dirty: true,
            error: saveError,
          };
        }
      }
      if (request === requestSequence) notify();
    },
    adoptLatest: (): void => {
      if (state.status !== "conflict" || state.latestSnapshot === null) {
        throw new Error(
          "Cannot adopt workspace snapshot: no server snapshot is available",
        );
      }
      state = {
        status: "ready",
        projectId: state.projectId,
        snapshot: state.latestSnapshot,
        draft: toInput(state.latestSnapshot),
        expectedRevision: state.latestSnapshot.revision,
        dirty: false,
      };
      notify();
    },
    setLayoutPreset: (preset: string) =>
      updateDraft((input) => ({
        ...input,
        layoutPreset: preset,
      })),
    setPanelSlot: (slot: WorkspacePanelSlot) =>
      updateDraft((input) => {
        const otherSlots = input.panelSlots.filter(
          (currentSlot) => currentSlot.slotId !== slot.slotId,
        );
        return {
          ...input,
          panelSlots: [...otherSlots, slot],
        };
      }),
    pinEvidence: (evidenceId: DomainEntityId) =>
      updateDraft((input) => {
        if (input.pinnedEvidenceIds.includes(evidenceId)) return input;
        return {
          ...input,
          pinnedEvidenceIds: [...input.pinnedEvidenceIds, evidenceId],
        };
      }),
    unpinEvidence: (evidenceId: DomainEntityId) =>
      updateDraft((input) => ({
        ...input,
        pinnedEvidenceIds: input.pinnedEvidenceIds.filter(
          (id) => id !== evidenceId,
        ),
      })),
    setActiveRun: (runId: DomainEntityId | null) =>
      updateDraft((input) => ({
        ...input,
        activeRunId: runId,
      })),
  };
}
