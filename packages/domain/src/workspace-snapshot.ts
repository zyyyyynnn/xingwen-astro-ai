/**
 * WorkspaceSnapshot — the private recoverable workspace projection.
 *
 * Mirrors `WorkspaceSnapshot` in the Pydantic `/api` authoring source using
 * frontend camelCase convention. The snapshot captures layout, panel slots,
 * pinned evidence and selection state so a session can resume without losing
 * context. It is scoped to `session + project` and never serialises the
 * session id or sensitive tokens.
 *
 * Transport DTO mapping lives in `@xingwen/data-access`.
 */

import type { WorkspacePanelType } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";

/**
 * Stable reference to an object shown in the private workspace.
 */
export interface WorkspaceObjectRef {
  readonly artifactVersionId: DomainEntityId | null;
  readonly objectId: DomainEntityId;
  readonly objectType: string;
}

/**
 * Atlas-side workspace state (focus mode and selected object).
 */
export interface AtlasWorkspaceState {
  readonly focusMode: string | null;
  readonly selectedObjectRef: WorkspaceObjectRef | null;
}

/**
 * Observatory-side workspace state (active artifact version and evidence).
 */
export interface ObservatoryWorkspaceState {
  readonly activeArtifactVersionId: DomainEntityId | null;
  readonly activeEvidenceId: DomainEntityId | null;
}

/**
 * Bounded panel placement without persisting arbitrary window or GPU state.
 * A workspace snapshot may contain at most three panel slots.
 */
export interface WorkspacePanelSlot {
  readonly slotId: string;
  readonly panelType: WorkspacePanelType;
  readonly artifactVersionId: DomainEntityId | null;
  readonly evidenceId: DomainEntityId | null;
}

/**
 * Private recoverable workspace projection; the session id is never serialised.
 *
 * The `revision` field is the optimistic-concurrency guard: `PUT` uses
 * `If-Match` / `expectedRevision` and a stale revision yields `409
 * VERSION_CONFLICT` rather than silently overwriting.
 */
export interface WorkspaceSnapshot {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly revision: number;
  readonly layoutPreset: string;
  readonly activeRunId: DomainEntityId | null;
  readonly panelSlots: readonly WorkspacePanelSlot[];
  readonly pinnedEvidenceIds: readonly DomainEntityId[];
  readonly atlasState: AtlasWorkspaceState | null;
  readonly observatoryState: ObservatoryWorkspaceState | null;
  readonly selectedObjectRef: WorkspaceObjectRef | null;
  readonly updatedAt: UtcIsoTimestamp;
}

/**
 * Input shape accepted by the `PUT` endpoint. The adapter separates this from
 * the stored `WorkspaceSnapshot` so callers cannot accidentally set `id`,
 * `projectId` or `updatedAt` directly.
 */
export interface WorkspaceSnapshotInput {
  readonly layoutPreset: string;
  readonly activeRunId: DomainEntityId | null;
  readonly panelSlots: readonly WorkspacePanelSlot[];
  readonly pinnedEvidenceIds: readonly DomainEntityId[];
  readonly atlasState: AtlasWorkspaceState | null;
  readonly observatoryState: ObservatoryWorkspaceState | null;
  readonly selectedObjectRef: WorkspaceObjectRef | null;
}
