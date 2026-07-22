/**
 * Fixture adapter — the Demo Replay `RepositorySet` implementation.
 *
 * Validates every fixture DTO against the B-15 JSON Schemas, enforces Demo
 * Replay semantics (no `live`/`cached` data), maps payloads into the domain
 * model, and serves reads from in-memory stores. It implements the same
 * narrowed ports as the HTTP adapter so the two are structurally
 * interchangeable. Writes (draft update, contract confirm, run create,
 * workspace save, share create/revoke) mutate the stores deterministically via
 * an injectable clock and id factory so tests stay stable.
 */

import { validateV2Dto, type V2CoreModelName } from "@xingwen/contracts";
import type {
  CreateShareSnapshotRequest,
  DomainEntityId,
  PublicArtifactVersion,
  PublicEvidence,
  PublicShareSnapshot,
  ResearchContract,
  ResearchContractDraft,
  ResearchRun,
  RunEvent,
  ShareSnapshot,
  WorkspaceSnapshot,
  ContentHash,
  UtcIsoTimestamp,
} from "@xingwen/domain";

import { FixtureSemanticError, FixtureValidationError } from "./errors";
import { ConflictError, NotFoundError } from "./http-errors";
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
  ArtifactReadRepository,
  ContractRepository,
  CreateResearchRunInput,
  ProjectRepository,
  RepositoryProvenance,
  RunEventRecovery,
  RunRepository,
  ShareRepository,
  UpdateResearchContractDraftInput,
  WorkspaceSnapshotRepository,
} from "./ports";
import type { FixtureBundle } from "./fixture/bundle";

/** Optional deterministic clock and id factory for stable tests. */
export interface FixtureAdapterOptions {
  readonly clock?: () => UtcIsoTimestamp;
  readonly idFactory?: (prefix: string) => DomainEntityId;
}

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

/** In-memory keyed store. */
class MemoryStore<T extends { readonly id: DomainEntityId }> {
  private readonly entities = new Map<DomainEntityId, T>();

  constructor(entities: readonly T[]) {
    for (const entity of entities) this.entities.set(entity.id, entity);
  }

  get(id: DomainEntityId): T | null {
    return this.entities.get(id) ?? null;
  }

  upsert(entity: T): void {
    this.entities.set(entity.id, entity);
  }

  filter(predicate: (entity: T) => boolean): readonly T[] {
    return [...this.entities.values()].filter(predicate);
  }
}

interface ShareRecord {
  readonly snapshot: ShareSnapshot;
  readonly token: string;
  readonly artifactVersions: readonly PublicArtifactVersion[];
  readonly evidence: readonly PublicEvidence[];
}

export interface FixtureRepositorySet {
  readonly projects: ProjectRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly artifacts: ArtifactReadRepository;
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
  readonly provenance: RepositoryProvenance;
}

function defaultClock(): () => UtcIsoTimestamp {
  let tick = 0;
  const base = Date.parse("2026-07-21T09:00:00Z");
  return () => new Date(base + tick++ * 1000).toISOString() as UtcIsoTimestamp;
}

function defaultIdFactory(): (prefix: string) => DomainEntityId {
  let seq = 0;
  return (prefix) =>
    `${prefix}_${String(++seq).padStart(4, "0")}` as DomainEntityId;
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
  options: FixtureAdapterOptions = {},
): FixtureRepositorySet {
  validateBundleSemantics(bundle);
  validateBundlePayloads(bundle);

  const clock = options.clock ?? defaultClock();
  const nextId = options.idFactory ?? defaultIdFactory();

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

  const runEvents = new Map<DomainEntityId, RunEvent[]>();
  for (const dto of bundle.data.runEvents) {
    const event = mapRunEvent(dto);
    const existing = runEvents.get(event.runId) ?? [];
    existing.push(event);
    existing.sort((a, b) => a.sequence - b.sequence);
    runEvents.set(event.runId, existing);
  }

  const shares = new Map<DomainEntityId, ShareRecord>();
  const shareByToken = new Map<string, DomainEntityId>();
  const runsByIdempotencyKey = new Map<
    string,
    { readonly request: string; readonly run: ResearchRun }
  >();

  function toPublicVersion(
    projectId: DomainEntityId,
    versionId: DomainEntityId,
  ): PublicArtifactVersion {
    const version = versions.get(versionId);
    if (version === null || version.projectId !== projectId) {
      throw new NotFoundError(
        `ArtifactVersion ${versionId} not found for Project ${projectId}`,
        "ARTIFACT_VERSION_NOT_FOUND",
      );
    }
    const artifact = artifacts.get(version.artifactId);
    if (artifact === null || artifact.projectId !== projectId) {
      throw new NotFoundError(
        `Artifact ${version.artifactId} not found for Project ${projectId}`,
        "ARTIFACT_NOT_FOUND",
      );
    }
    return {
      id: version.id,
      artifactId: version.artifactId,
      kind: artifact.kind,
      title: artifact.title,
      versionNumber: version.versionNumber,
      schemaVersion: version.schemaVersion,
      contentHash: version.contentHash,
      sourceMode: version.sourceMode,
      createdAt: version.createdAt,
    };
  }

  function toPublicEvidence(
    projectId: DomainEntityId,
    allowedVersionIds: ReadonlySet<DomainEntityId>,
    evidenceId: DomainEntityId,
  ): PublicEvidence {
    const entity = evidenceStore.get(evidenceId);
    const version = entity ? versions.get(entity.artifactVersionId) : null;
    if (
      entity === null ||
      entity.sourceSnapshotId === null ||
      version === null ||
      version.projectId !== projectId
    ) {
      throw new NotFoundError(
        `Evidence ${evidenceId} not found for Project ${projectId}`,
        "EVIDENCE_NOT_FOUND",
      );
    }
    if (!allowedVersionIds.has(entity.artifactVersionId)) {
      throw new FixtureValidationError("CreateShareSnapshotRequest", [
        `Evidence ${evidenceId} must belong to a selected ArtifactVersion`,
      ]);
    }
    return {
      id: entity.id,
      artifactVersionId: entity.artifactVersionId,
      sourceSnapshotId: entity.sourceSnapshotId,
    };
  }

  function validateShareRequest(
    request: CreateShareSnapshotRequest,
    now: UtcIsoTimestamp,
  ): void {
    const errors: string[] = [];
    if (request.artifactVersionIds.length === 0) {
      errors.push("artifactVersionIds must contain at least one value");
    }
    if (
      request.artifactVersionIds.length !==
      new Set(request.artifactVersionIds).size
    ) {
      errors.push("artifactVersionIds must not contain duplicates");
    }
    if (request.evidenceIds.length !== new Set(request.evidenceIds).size) {
      errors.push("evidenceIds must not contain duplicates");
    }
    const expiry = Date.parse(request.expiresAt);
    if (Number.isNaN(expiry) || expiry <= Date.parse(now)) {
      errors.push("expiresAt must be in the future");
    }
    if (errors.length > 0) {
      throw new FixtureValidationError("CreateShareSnapshotRequest", errors);
    }
  }

  function shareStatus(
    snapshot: ShareSnapshot,
    now: UtcIsoTimestamp,
  ): ShareSnapshot {
    const status =
      snapshot.revokedAt !== null
        ? "revoked"
        : Date.parse(snapshot.expiresAt) <= Date.parse(now)
          ? "expired"
          : "active";
    return snapshot.status === status ? snapshot : { ...snapshot, status };
  }

  return {
    projects: {
      getById: async (id) => projects.get(id),
    },
    contracts: {
      getDraftById: async (id) => drafts.get(id),
      updateDraft: async (
        draftId,
        expectedVersion,
        input: UpdateResearchContractDraftInput,
      ) => {
        const draft = drafts.get(draftId);
        if (draft === null) {
          throw new FixtureValidationError("ResearchContractDraft", [
            `Draft ${draftId} not found`,
          ]);
        }
        if (draft.status !== "draft") {
          throw new ConflictError(
            "Only a draft in the draft state can be updated",
            "DRAFT_NOT_EDITABLE",
          );
        }
        if (draft.version !== expectedVersion) {
          throw new ConflictError(
            `Draft revision conflict: expected ${expectedVersion}, got ${draft.version}`,
            "VERSION_CONFLICT",
          );
        }
        const updated: ResearchContractDraft = {
          ...draft,
          intent: input.intent ?? draft.intent,
          contract: input.contract ?? draft.contract,
          version: draft.version + 1,
          updatedAt: clock(),
        };
        drafts.upsert(updated);
        return updated;
      },
      confirm: async (projectId, draftId, expectedDraftVersion) => {
        const draft = drafts.get(draftId);
        if (draft === null) {
          throw new FixtureValidationError("ResearchContractDraft", [
            `Draft ${draftId} not found`,
          ]);
        }
        if (draft.status !== "draft") {
          throw new ConflictError(
            "Only a draft in the draft state can be confirmed",
            "DRAFT_NOT_EDITABLE",
          );
        }
        if (draft.version !== expectedDraftVersion) {
          throw new ConflictError(
            `Draft revision conflict: expected ${expectedDraftVersion}, got ${draft.version}`,
            "VERSION_CONFLICT",
          );
        }
        const now = clock();
        const contract: ResearchContract = {
          ...draft.contract,
          id: nextId("rc"),
          projectId,
          version:
            Math.max(
              0,
              ...contracts
                .filter((existing) => existing.projectId === projectId)
                .map((existing) => existing.version),
            ) + 1,
          createdFromDraftId: draft.id,
          createdAt: now,
          contentHash: ("sha256:" + "0".repeat(64)) as ContentHash,
        };
        contracts.upsert(contract);
        drafts.upsert({ ...draft, status: "confirmed", updatedAt: now });
        const project = projects.get(projectId);
        if (project !== null) {
          projects.upsert({ ...project, activeContractId: contract.id });
        }
        return contract;
      },
      getContractById: async (id) => contracts.get(id),
    },
    runs: {
      getById: async (id) => runs.get(id),
      create: async (input: CreateResearchRunInput) => {
        if (input.executionMode !== "demo_replay") {
          throw new FixtureSemanticError(
            `Fixture Run executionMode must be "demo_replay"; got "${input.executionMode}".`,
          );
        }
        const request = JSON.stringify({
          projectId: input.projectId,
          contractId: input.contractId,
          executionMode: input.executionMode,
          derivationKind: input.derivationKind ?? "original",
          parentRunId: input.parentRunId ?? null,
          retryFromStep: input.retryFromStep ?? null,
          cachePolicy: input.cachePolicy ?? "fallback_on_recoverable_failure",
        });
        const replay = runsByIdempotencyKey.get(input.idempotencyKey);
        if (replay) {
          if (replay.request !== request) {
            throw new ConflictError(
              "Idempotency key was already used for a different Run request",
              "IDEMPOTENCY_CONFLICT",
            );
          }
          return replay.run;
        }
        const id = nextId("run");
        const now = clock();
        const run: ResearchRun = {
          id,
          projectId: input.projectId,
          contractId: input.contractId,
          executionMode: input.executionMode,
          status: "queued",
          progress: 0,
          parentRunId: input.parentRunId ?? null,
          derivationKind: input.derivationKind ?? "original",
          retryFromStep: input.retryFromStep ?? null,
          cachePolicy: input.cachePolicy ?? "fallback_on_recoverable_failure",
          startedAt: null,
          finishedAt: null,
          createdAt: now,
          updatedAt: now,
          latestEventSequence: 1,
          failureCode: null,
          failureSummary: null,
        };
        runs.upsert(run);
        runEvents.set(id, [
          {
            runId: id,
            sequence: 1,
            eventType: "run.queued" as DomainEntityId,
            stepKey: null,
            progress: 0,
            publicMessage: "Run queued",
            artifactVersionIds: [],
            occurredAt: now,
          },
        ]);
        runsByIdempotencyKey.set(input.idempotencyKey, { request, run });
        return run;
      },
      listEvents: async (runId) => {
        if (runs.get(runId) === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        return [...(runEvents.get(runId) ?? [])];
      },
      recoverEvents: async (
        runId,
        fromCursor = null,
      ): Promise<RunEventRecovery> => {
        const run = runs.get(runId);
        if (run === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        const latestSequence = run.latestEventSequence;
        const after = fromCursor ? Number(fromCursor) : 0;
        const events = (runEvents.get(runId) ?? []).filter(
          (e) => e.sequence > after && e.sequence <= latestSequence,
        );
        return { events, nextCursor: null, latestSequence };
      },
    },
    artifacts: {
      listByRun: async (runId) => {
        const versionArtifactIds = new Set(
          versions
            .filter((v) => v.createdByRunId === runId)
            .map((v) => v.artifactId),
        );
        return artifacts.filter((a) => versionArtifactIds.has(a.id));
      },
      getArtifact: async (id) => artifacts.get(id),
      getVersion: async (id) => versions.get(id),
      getEvidence: async (id) => evidenceStore.get(id),
    },
    workspaces: {
      getByProjectId: async (projectId) =>
        workspaces.filter((w) => w.projectId === projectId)[0] ?? null,
      save: async (projectId, snapshotInput, expectedRevision) => {
        const existing = workspaces.filter((w) => w.projectId === projectId)[0];
        const currentRevision = existing ? existing.revision : 0;
        if (currentRevision !== expectedRevision) {
          throw new ConflictError(
            `Workspace revision conflict: expected ${expectedRevision}, got ${currentRevision}`,
            "VERSION_CONFLICT",
          );
        }
        const snapshot: WorkspaceSnapshot = {
          id: existing?.id ?? nextId("ws"),
          projectId,
          revision: currentRevision + 1,
          layoutPreset: snapshotInput.layoutPreset,
          panelSlots: snapshotInput.panelSlots,
          activeRunId: snapshotInput.activeRunId,
          pinnedEvidenceIds: snapshotInput.pinnedEvidenceIds,
          atlasState: snapshotInput.atlasState,
          observatoryState: snapshotInput.observatoryState,
          selectedObjectRef: snapshotInput.selectedObjectRef,
          updatedAt: clock(),
        };
        workspaces.upsert(snapshot);
        return snapshot;
      },
    },
    shares: {
      list: async (projectId) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const now = clock();
        return [...shares.values()]
          .filter((record) => record.snapshot.projectId === projectId)
          .map((record) => shareStatus(record.snapshot, now));
      },
      create: async (projectId, request: CreateShareSnapshotRequest) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const id = nextId("share");
        const token = `token_${id}`;
        const now = clock();
        validateShareRequest(request, now);
        const artifactVersions = request.artifactVersionIds.map((versionId) =>
          toPublicVersion(projectId, versionId),
        );
        const allowed = new Set(request.artifactVersionIds);
        const evidence = request.evidenceIds.map((evidenceId) =>
          toPublicEvidence(projectId, allowed, evidenceId),
        );
        const snapshot: ShareSnapshot = {
          id,
          projectId,
          title: request.title,
          status: "active",
          redactionPolicy: request.redactionPolicy,
          artifactVersionIds: request.artifactVersionIds,
          evidenceIds: request.evidenceIds,
          createdAt: now,
          expiresAt: request.expiresAt,
          revokedAt: null,
        };
        shares.set(id, { snapshot, token, artifactVersions, evidence });
        shareByToken.set(token, id);
        return { ...snapshot, shareToken: token, shareUrl: `/share/${token}` };
      },
      revoke: async (projectId, shareId) => {
        const record = shares.get(shareId);
        if (
          projects.get(projectId) === null ||
          record === undefined ||
          record.snapshot.projectId !== projectId
        ) {
          throw new NotFoundError(
            `Share ${shareId} not found for Project ${projectId}`,
            "SHARE_NOT_FOUND",
          );
        }
        if (record.snapshot.revokedAt !== null) return;
        shares.set(shareId, {
          ...record,
          snapshot: {
            ...record.snapshot,
            status: "revoked",
            revokedAt: clock(),
          },
        });
      },
      getPublic: async (shareToken): Promise<PublicShareSnapshot | null> => {
        const shareId = shareByToken.get(shareToken);
        if (!shareId) return null;
        const record = shares.get(shareId);
        if (
          !record ||
          shareStatus(record.snapshot, clock()).status !== "active"
        ) {
          return null;
        }
        return {
          id: record.snapshot.id,
          title: record.snapshot.title,
          redactionPolicy: record.snapshot.redactionPolicy,
          createdAt: record.snapshot.createdAt,
          expiresAt: record.snapshot.expiresAt,
          artifactVersions: record.artifactVersions,
          evidence: record.evidence,
        };
      },
    },
    provenance: {
      state: buildFixtureProvenance(
        bundle.schemaVersion,
        bundle.generatedAt,
        bundle.data.evidence.length,
        bundle.data.evidence.length,
        bundle.provenanceNote,
      ),
    },
  };
}
