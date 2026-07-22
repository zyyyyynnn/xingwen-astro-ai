/**
 * Fixture adapter — the Demo Replay `RepositorySet` implementation.
 *
 * This adapter validates every fixture DTO against the B-15 JSON Schemas,
 * enforces Demo Replay semantic constraints (no `live` or `cached` data),
 * maps payloads into the domain model, and serves reads from in-memory
 * stores. Writes update the stores and notify subscribers so workspace
 * previews can exercise the full read/write/subscribe contract without a
 * backend.
 *
 * The HTTP adapter (A-15) will implement the same `RepositorySet` interface
 * against real `/api/v2` endpoints.
 */

import { validateV2Dto, type V2CoreModelName } from "@xingwen/contracts";
import type {
  ArtifactVersion,
  ContentHash,
  DomainEntityId,
  Evidence,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  WorkspaceSnapshot,
  ShareSnapshot,
  RunEvent,
} from "@xingwen/domain";

import { FixtureSemanticError, FixtureValidationError } from "./errors";
import {
  buildFixtureProvenance,
  mapArtifactVersion,
  mapEvidence,
  mapResearchArtifact,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchRun,
  mapRunEvent,
} from "./mapping";
import type {
  ArtifactRepository,
  ContractRepository,
  EvidenceRepository,
  Listener,
  ProjectRepository,
  RepositoryProvenance,
  RunRepository,
  ShareRepository,
  Unsubscribe,
  WorkspaceSnapshotRepository,
} from "./ports";
import type { FixtureBundle } from "./fixture/bundle";

function validateBundleSemantics(bundle: FixtureBundle): void {
  if (bundle.executionMode !== "demo_replay") {
    throw new FixtureSemanticError(
      `Fixture bundle executionMode must be "demo_replay"; got "${bundle.executionMode}".`,
    );
  }
  if (bundle.sourceMode !== "fixture") {
    throw new FixtureSemanticError(
      `Fixture bundle sourceMode must be "fixture"; got "${bundle.sourceMode}".`,
    );
  }

  for (const run of bundle.data.runs) {
    if (run.execution_mode !== "demo_replay") {
      throw new FixtureSemanticError(
        `Fixture run ${run.id} must have execution_mode "demo_replay"; got "${run.execution_mode}".`,
      );
    }
  }

  for (const version of bundle.data.artifactVersions) {
    if (version.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture artifact version ${version.id} must have source_mode "fixture"; got "${version.source_mode}".`,
      );
    }
  }
}

function validateBundlePayloads(bundle: FixtureBundle): void {
  const entries: readonly {
    readonly model: V2CoreModelName;
    readonly payloads: readonly unknown[];
  }[] = [
    { model: "ResearchProject", payloads: bundle.data.projects },
    { model: "ResearchContractDraft", payloads: bundle.data.contractDrafts },
    { model: "ResearchContract", payloads: bundle.data.contracts },
    { model: "ResearchRun", payloads: bundle.data.runs },
    { model: "RunEvent", payloads: bundle.data.runEvents },
    { model: "ArtifactVersion", payloads: bundle.data.artifactVersions },
    { model: "ResearchArtifact", payloads: bundle.data.artifacts },
  ];

  for (const { model, payloads } of entries) {
    for (const payload of payloads) {
      const result = validateV2Dto(model, payload);
      if (!result.ok) {
        throw new FixtureValidationError(
          model,
          result.errors.map((e) => `${e.path}: ${e.message}`),
        );
      }
    }
  }
}

/** In-memory store with subscription support. */
class MemoryStore<T extends { readonly id: DomainEntityId }> {
  private readonly entities = new Map<DomainEntityId, T>();
  private readonly listeners = new Set<Listener<T>>();

  constructor(entities: readonly T[]) {
    for (const entity of entities) {
      this.entities.set(entity.id, entity);
    }
  }

  getAll(): readonly T[] {
    return [...this.entities.values()];
  }

  get(id: DomainEntityId): T | null {
    return this.entities.get(id) ?? null;
  }

  upsert(entity: T): void {
    this.entities.set(entity.id, entity);
    this.notify();
  }

  filter(predicate: (entity: T) => boolean): readonly T[] {
    return [...this.entities.values()].filter(predicate);
  }

  subscribe(listener: Listener<T>): Unsubscribe {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify(): void {
    const snapshot = this.getAll();
    for (const listener of this.listeners) {
      listener(snapshot);
    }
  }
}

export interface FixtureRepositorySet {
  readonly projects: ProjectRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly artifacts: ArtifactRepository;
  readonly evidence: EvidenceRepository;
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
  readonly provenance: RepositoryProvenance;
}

/**
 * Create a `RepositorySet` backed by a validated fixture bundle.
 *
 * @throws {FixtureValidationError} when any DTO fails v2 contract validation.
 * @throws {FixtureSemanticError} when the bundle violates Demo Replay
 *   constraints (e.g. `live` or `cached` source labels).
 */
export function createFixtureRepositories(
  bundle: FixtureBundle,
): FixtureRepositorySet {
  validateBundleSemantics(bundle);
  validateBundlePayloads(bundle);

  const projects = new MemoryStore(
    bundle.data.projects.map((dto) => mapResearchProject(dto)),
  );
  const contracts = new MemoryStore(
    bundle.data.contracts.map((dto) => mapResearchContract(dto)),
  );
  const drafts = new MemoryStore(
    bundle.data.contractDrafts.map((dto) => mapResearchContractDraft(dto)),
  );
  const runs = new MemoryStore(
    bundle.data.runs.map((dto) => mapResearchRun(dto)),
  );
  const artifacts = new MemoryStore(
    bundle.data.artifacts.map((dto) => mapResearchArtifact(dto)),
  );
  const versions = new MemoryStore(
    bundle.data.artifactVersions.map((dto) => mapArtifactVersion(dto)),
  );
  const evidenceStore = new MemoryStore(
    bundle.data.evidence.map((entity) => mapEvidence(entity)),
  );
  const workspaces = new MemoryStore<WorkspaceSnapshot>([]);
  const shares = new MemoryStore<ShareSnapshot>([]);

  const runEvents = new Map<DomainEntityId, RunEvent[]>();
  for (const dto of bundle.data.runEvents) {
    const event = mapRunEvent(dto);
    const existing = runEvents.get(event.runId) ?? [];
    existing.push(event);
    runEvents.set(event.runId, existing);
  }

  const provenance: RepositoryProvenance = {
    state: buildFixtureProvenance(
      bundle.schemaVersion,
      bundle.generatedAt,
      bundle.data.evidence.length,
      bundle.data.evidence.length,
      bundle.provenanceNote,
    ),
  };

  return {
    projects: {
      getById: async (id) => projects.get(id),
      list: async () => projects.getAll(),
      save: async (project: ResearchProject) => projects.upsert(project),
      subscribe: (listener) => projects.subscribe(listener),
    },
    contracts: {
      getDraftById: async (id) => drafts.get(id),
      listDrafts: async () => drafts.getAll(),
      saveDraft: async (draft: ResearchContractDraft) => drafts.upsert(draft),
      confirm: async (projectId, draftId, expectedDraftVersion) => {
        const draft = drafts.get(draftId);
        if (draft === null) {
          throw new FixtureValidationError("ResearchContractDraft", [
            `Draft ${draftId} not found`,
          ]);
        }
        if (draft.version !== expectedDraftVersion) {
          throw new FixtureValidationError("ResearchContractDraft", [
            `Expected draft version ${expectedDraftVersion} but found ${draft.version}`,
          ]);
        }
        const contractId = `rc_${draft.id}` as DomainEntityId;
        const contract: ResearchContract = {
          ...draft.contract,
          id: contractId,
          projectId,
          version: 1,
          createdFromDraftId: draft.id,
          createdAt: draft.updatedAt,
          contentHash: `hash_${draft.id}` as ContentHash,
        };
        contracts.upsert(contract);
        return contract;
      },
      getContractById: async (id) => contracts.get(id),
      listContracts: async (projectId) =>
        contracts.filter((c) => c.projectId === projectId),
      subscribe: (listener) => contracts.subscribe(listener),
    },
    runs: {
      getById: async (id) => runs.get(id),
      listByProject: async (projectId) =>
        runs.filter((r) => r.projectId === projectId),
      save: async (run: ResearchRun) => runs.upsert(run),
      getEvents: async (runId) => [...(runEvents.get(runId) ?? [])],
      appendEvent: async (event: RunEvent) => {
        const existing = runEvents.get(event.runId) ?? [];
        existing.push(event);
        runEvents.set(event.runId, existing);
      },
      subscribe: (listener) => runs.subscribe(listener),
    },
    artifacts: {
      getArtifactById: async (id) => artifacts.get(id),
      listByProject: async (projectId) =>
        artifacts.filter((a) => a.projectId === projectId),
      getVersionById: async (id) => versions.get(id),
      listVersions: async (artifactId) =>
        versions.filter((v) => v.artifactId === artifactId),
      saveVersion: async (version: ArtifactVersion) => versions.upsert(version),
      subscribe: (listener) => artifacts.subscribe(listener),
    },
    evidence: {
      getById: async (id) => evidenceStore.get(id),
      listByArtifactVersion: async (artifactVersionId) =>
        evidenceStore.filter((e) => e.artifactVersionId === artifactVersionId),
      save: async (entity: Evidence) => evidenceStore.upsert(entity),
      subscribe: (listener) => evidenceStore.subscribe(listener),
    },
    workspaces: {
      getByProjectId: async (projectId) => {
        const matches = workspaces.filter((w) => w.projectId === projectId);
        return matches[0] ?? null;
      },
      save: async (projectId, snapshotInput, expectedRevision) => {
        const existing = workspaces.filter((w) => w.projectId === projectId)[0];
        const currentRevision = existing ? existing.revision : 0;

        if (currentRevision !== expectedRevision) {
          const { ConflictError } = await import("./http-errors");
          throw new ConflictError(
            `Workspace snapshot revision conflict: expected ${expectedRevision}, got ${currentRevision}`,
            "VERSION_CONFLICT",
          );
        }

        const newRevision = currentRevision + 1;
        const snapshot: WorkspaceSnapshot = {
          id: `ws_${projectId}` as DomainEntityId,
          projectId,
          revision: newRevision,
          layoutPreset: snapshotInput.layoutPreset,
          panelSlots: snapshotInput.panelSlots,
          activeRunId: snapshotInput.activeRunId,
          pinnedEvidenceIds: snapshotInput.pinnedEvidenceIds,
          atlasState: snapshotInput.atlasState,
          observatoryState: snapshotInput.observatoryState,
          selectedObjectRef: snapshotInput.selectedObjectRef,
          updatedAt: new Date().toISOString() as never,
        };
        workspaces.upsert(snapshot);
        return snapshot;
      },
    },
    shares: {
      create: async (projectId, request) => {
        const id = `share_${Date.now()}` as DomainEntityId;
        const token = `token_${id}`;
        const snapshot: ShareSnapshot = {
          id,
          projectId,
          title: request.title,
          shareToken: token,
          createdAt: new Date().toISOString() as never,
          expiresAt: request.expiresAt,
          status: "active",
          redactionPolicy: request.redactionPolicy,
          artifactVersionIds: request.artifactVersionIds,
          evidenceIds: request.evidenceIds,
          revokedAt: null,
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } as any; // Type coercion for ShareSnapshot since we just need simple mock
        shares.upsert(snapshot);
        return {
          ...snapshot,
          shareToken: token,
          shareUrl: `https://example.com/share/${token}`,
        };
      },
      getByProjectIdAndShareId: async (projectId, shareId) => {
        const share = shares.get(shareId);
        return share?.projectId === projectId ? share : null;
      },
      listByProject: async (projectId) =>
        shares.filter((s) => s.projectId === projectId),
      revoke: async (projectId, shareId) => {
        const share = shares.get(shareId);
        if (share && share.projectId === projectId) {
          shares.upsert({ ...share, status: "revoked" });
        }
      },
      getPublicShare: async (shareToken) => {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const share = shares.filter(
          (s) => (s as any).shareToken === shareToken,
        )[0];
        if (!share || share.status !== "active") return null;
        // In fixture we just return a stubbed PublicShareSnapshot
        // Since we don't have the artifact inline in fixture share, we'd need to mock it if requested.
        return null;
      },
    },
    provenance,
  };
}
