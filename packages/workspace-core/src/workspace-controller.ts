import type {
  DomainEntityId,
  WorkspaceObjectRef,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
  WorkspacePanelSlot,
} from "@xingwen/domain";

/**
 * Main Stage view encoded in `WorkspaceSnapshot.layoutPreset`.
 *
 * The frozen schema uses a free-form string; these values are the canonical
 * views the A-17 shell renders. Legacy values ("comparative", "focus",
 * "grid") are mapped to the closest equivalent by {@link getMainStageView}.
 */
export type MainStageView =
  "brief" | "active" | "artifact_review" | "source_review" | "completion";

/**
 * Context Rail mode encoded in `AtlasWorkspaceState.focusMode`.
 */
export type ContextRailMode = "hidden" | "summary" | "detail";

const MAIN_STAGE_VIEWS: readonly MainStageView[] = [
  "brief",
  "active",
  "artifact_review",
  "source_review",
  "completion",
];

const DEFAULT_MAIN_STAGE_VIEW: MainStageView = "active";
const DEFAULT_CONTEXT_RAIL_MODE: ContextRailMode = "summary";

function asMainStageView(value: string | undefined): MainStageView {
  if (value && (MAIN_STAGE_VIEWS as readonly string[]).includes(value)) {
    return value as MainStageView;
  }
  return DEFAULT_MAIN_STAGE_VIEW;
}

function asContextRailMode(value: string | null | undefined): ContextRailMode {
  if (value === "hidden") return "hidden";
  if (value === "detail") return "detail";
  if (value === "summary") return "summary";
  return DEFAULT_CONTEXT_RAIL_MODE;
}

/**
 * Read the current {@link MainStageView} from a workspace state.
 *
 * Returns `"active"` for idle/loading states where no draft exists yet.
 */
export function getMainStageView(state: WorkspaceState): MainStageView {
  return asMainStageView(getWorkspaceInput(state)?.layoutPreset);
}

/**
 * Read the current {@link ContextRailMode} from a workspace state.
 *
 * Returns `"summary"` when no atlas state exists (the default, non-hidden
 * rail).
 */
export function getContextRailMode(state: WorkspaceState): ContextRailMode {
  return asContextRailMode(getWorkspaceInput(state)?.atlasState?.focusMode);
}

/**
 * Read the pinned object (persisted in `atlasState.selectedObjectRef`).
 *
 * Distinct from the *selected* object (`selectedObjectRef` at the top
 * level): selected is what the user is currently looking at; pinned is
 * what stays visible in the Context Rail even when navigating away.
 */
export function getPinnedObject(
  state: WorkspaceState,
): WorkspaceObjectRef | null {
  return getWorkspaceInput(state)?.atlasState?.selectedObjectRef ?? null;
}

/**
 * Session-local state that is NOT persisted in WorkspaceSnapshot.
 *
 * Context History and Rail Width are ephemeral navigation/UI preferences
 * that would be stale after a page refresh; the frozen v1 schema has no
 * fields for them, so they live only in the controller's in-memory state.
 */
export interface WorkspaceSessionState {
  readonly contextHistory: readonly WorkspaceObjectRef[];
  readonly railWidth: number | null;
}

const DEFAULT_SESSION_STATE: WorkspaceSessionState = {
  contextHistory: [],
  railWidth: null,
};

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
  getSessionState(): WorkspaceSessionState;
  subscribe(listener: WorkspaceListener): () => void;
  load(projectId: DomainEntityId): Promise<void>;
  save(): Promise<void>;
  adoptLatest(): void;
  setLayoutPreset(preset: string): Promise<void>;
  setPanelSlot(slot: WorkspacePanelSlot): Promise<void>;
  pinEvidence(evidenceId: DomainEntityId): Promise<void>;
  unpinEvidence(evidenceId: DomainEntityId): Promise<void>;
  setActiveRun(runId: DomainEntityId | null): Promise<void>;
  setMainStageView(view: string): Promise<void>;
  setContextRailMode(mode: ContextRailMode): Promise<void>;
  setActiveContextPanel(panel: string | null): Promise<void>;
  setSelectedObject(ref: WorkspaceObjectRef | null): Promise<void>;
  pinObject(ref: WorkspaceObjectRef): Promise<void>;
  unpinObject(): Promise<void>;
  pushContextHistory(ref: WorkspaceObjectRef): void;
  popContextHistory(): void;
  clearContextHistory(): void;
  setRailWidth(width: number): void;
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

/**
 * Read the most recent draft/input from any non-idle workspace state.
 *
 * For the `conflict` state this returns the attempted draft so the UI can
 * reflect what the user tried to save. Returns `null` for idle/loading.
 */
function getWorkspaceInput(
  state: WorkspaceState,
): WorkspaceSnapshotInput | null {
  if (
    state.status === "ready" ||
    state.status === "draft" ||
    state.status === "saving" ||
    state.status === "error"
  ) {
    return state.draft;
  }
  if (state.status === "conflict") {
    return state.attemptedDraft;
  }
  return null;
}

export function createWorkspaceController(
  workspaces: WorkspaceSnapshotPort,
): WorkspaceController {
  let state: WorkspaceState = { status: "idle" };
  let sessionState: WorkspaceSessionState = DEFAULT_SESSION_STATE;
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
    getSessionState: () => sessionState,
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
    setMainStageView: (view: string) =>
      updateDraft((input) => ({
        ...input,
        layoutPreset: view,
      })),
    setContextRailMode: (mode: ContextRailMode) =>
      updateDraft((input) => ({
        ...input,
        atlasState: {
          focusMode: mode,
          selectedObjectRef: input.atlasState?.selectedObjectRef ?? null,
        },
      })),
    setActiveContextPanel: (panel: string | null) =>
      updateDraft((input) => {
        const otherSlots = input.panelSlots.filter(
          (slot) => !slot.slotId.startsWith("context:"),
        );
        if (panel === null) {
          return { ...input, panelSlots: otherSlots };
        }
        return {
          ...input,
          panelSlots: [
            ...otherSlots,
            {
              slotId: `context:${panel}`,
              panelType: "observatory",
              artifactVersionId: null,
              evidenceId: null,
            },
          ],
        };
      }),
    setSelectedObject: (ref: WorkspaceObjectRef | null) =>
      updateDraft((input) => ({
        ...input,
        selectedObjectRef: ref,
      })),
    pinObject: (ref: WorkspaceObjectRef) =>
      updateDraft((input) => ({
        ...input,
        atlasState: {
          focusMode: input.atlasState?.focusMode ?? null,
          selectedObjectRef: ref,
        },
      })),
    unpinObject: () =>
      updateDraft((input) => ({
        ...input,
        atlasState: {
          focusMode: input.atlasState?.focusMode ?? null,
          selectedObjectRef: null,
        },
      })),
    pushContextHistory: (ref: WorkspaceObjectRef) => {
      sessionState = {
        ...sessionState,
        contextHistory: [...sessionState.contextHistory, ref],
      };
      notify();
    },
    popContextHistory: () => {
      sessionState = {
        ...sessionState,
        contextHistory: sessionState.contextHistory.slice(0, -1),
      };
      notify();
    },
    clearContextHistory: () => {
      sessionState = {
        ...sessionState,
        contextHistory: [],
      };
      notify();
    },
    setRailWidth: (width: number) => {
      sessionState = {
        ...sessionState,
        railWidth: width,
      };
      notify();
    },
  };
}
