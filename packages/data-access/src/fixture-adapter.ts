/**
 * Fixture adapter — the Demo Replay `RepositorySet` implementation.
 *
 * Validates contract-registered fixture DTOs against the Core Domain and
 * Transport Contract JSON Schemas, enforces Demo Replay semantics (no
 * `live`/`cached` data), maps payloads into the domain model, and serves reads
 * from in-memory stores. Dedicated rich read ports use the same strict
 * transport mappers as the HTTP adapter. It implements the same
 * narrowed ports as the HTTP adapter so the two are structurally
 * interchangeable. Writes (draft update, contract confirm, run create,
 * workspace save, share create/revoke) mutate the stores deterministically via
 * an injectable clock and id factory so tests stay stable.
 */

import { validateDto, type CoreModelName } from "@xingwen/contracts";
import type {
  CreateShareSnapshotRequest,
  ArtifactVersionMetadata,
  DomainEntityId,
  PublicArtifactVersion,
  PublicEvidence,
  PublicShareSnapshot,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  RunCheckpoint,
  RunDecisionResult,
  ResearchInputRef,
  CreateResearchInput,
  ResearchThreadEntry,
  RunEvent,
  RunStepSnapshot,
  ShareSnapshot,
  WorkspaceSnapshot,
  ContentHash,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { asEntityId } from "@xingwen/domain";

import { FixtureSemanticError, FixtureValidationError } from "./errors";
import { ConflictError, NotFoundError, UnexpectedHttpError } from "./errors";
import {
  buildFixtureProvenance,
  mapArtifactVersionMetadata,
  mapDomainContractInputToDto,
  mapEvidence,
  mapResearchArtifact,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchRun,
  mapRunEvent,
  mapRunCheckpoint,
  mapResearchInputRef,
} from "./mapping";
import { mapScientificArtifactRead } from "./scientific-artifact-repository";
import { createFixtureDataArtifactRepository } from "./data-artifact-repository";
import { createFixtureArtifactExportRepository } from "./artifact-export-repository";
import { createFixtureGraphArtifactRepository } from "./graph-artifact-repository";
import { createFixtureLiteratureArtifactRepository } from "./literature-artifact-repository";
import { computeContractContentHash } from "./contract-hash";
import { assemblePaperAcquisitionReview } from "./paper-acquisition-repository";
import { assemblePaperSummaryReview } from "./paper-summary-repository";
import type {
  ArtifactExportRepository,
  ArtifactReadRepository,
  ContractRepository,
  CreateResearchRunInput,
  PaperAcquisitionRepository,
  PaperSummaryRepository,
  ProjectRepository,
  ResearchCatalogRepository,
  ResearchThreadRepository,
  RepositoryProvenance,
  RunEventRecovery,
  RunRepository,
  ResearchInputRepository,
  RunDecisionInput,
  ScientificArtifactRepository,
  DataArtifactRepository,
  GraphArtifactRepository,
  LiteratureArtifactRepository,
  UpdateResearchProjectInput,
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
  // Defensive runtime check: an old-shaped bundle without the paperSummaries
  // array must fail as an explicit fixture contract error, never a TypeError.
  if (!Array.isArray(bundle.data.paperSummaries)) {
    throw new FixtureSemanticError(
      "Fixture bundle must carry a paperSummaries array of rich immutable " +
        "paper summary entries.",
    );
  }
  if (!Array.isArray(bundle.data.scientificArtifacts)) {
    throw new FixtureSemanticError(
      "Fixture bundle must carry a scientificArtifacts array of rich immutable entries.",
    );
  }
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
  const formalDataReads = [
    ...bundle.data.dataArtifactReads,
    ...bundle.data.fieldDictionaryArtifactReads,
    ...bundle.data.sourceCollectionArtifactReads,
  ];
  for (const read of formalDataReads) {
    if (read.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture data read ${read.artifact_version_id} must have source_mode "fixture"; got "${read.source_mode}".`,
      );
    }
  }
  const formalLiteratureReads = [
    ...bundle.data.literatureClaimReads,
    ...bundle.data.literatureRelationReads,
    ...bundle.data.literatureReasoningTraceReads,
  ];
  for (const read of formalLiteratureReads) {
    if (read.version.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture literature read ${read.version.artifact_version_id} must have source_mode "fixture"; got "${read.version.source_mode}".`,
      );
    }
  }
  for (const read of bundle.data.graphArtifactReads) {
    if (read.version.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture graph read ${read.version.artifact_version_id} must have source_mode "fixture"; got "${read.version.source_mode}".`,
      );
    }
  }
  for (const read of [
    ...bundle.data.graphNodeReads,
    ...bundle.data.graphEdgeReads,
  ]) {
    if (read.version.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture graph row ${read.version.artifact_version_id} must have source_mode "fixture"; got "${read.version.source_mode}".`,
      );
    }
  }
  for (const acquisition of bundle.data.paperAcquisitions) {
    const { version, collection } = acquisition;
    // Defensive runtime check: an old-shaped bundle without the rich version
    // must fail as an explicit fixture contract error, never a TypeError.
    if (version === undefined || version === null) {
      throw new FixtureSemanticError(
        `Fixture paper collection ${collection.artifact_version_id} must ` +
          "carry its full immutable ArtifactVersion detail",
      );
    }
    if (bundle.data.artifactVersions.some((item) => item.id === version.id)) {
      throw new FixtureSemanticError(
        `Paper collection version ${version.id} must have one rich immutable ` +
          "fixture representation, not a second generic ArtifactVersion",
      );
    }
    if (
      version.id !== collection.artifact_version_id ||
      version.artifact_id !== collection.artifact_id ||
      version.project_id !== collection.project_id ||
      version.content_hash !== collection.content_hash ||
      version.input_hash !== collection.input_hash ||
      version.source_mode !== collection.source_mode ||
      version.created_at !== collection.created_at ||
      JSON.stringify(version.content) !== JSON.stringify(collection.collection)
    ) {
      throw new FixtureSemanticError(
        `Paper collection version ${version.id} identity must match its ` +
          "dedicated collection read",
      );
    }
    if (acquisition.collection.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture paper collection ${acquisition.collection.artifact_version_id} ` +
          `must have source_mode "fixture"; got "${acquisition.collection.source_mode}".`,
      );
    }
    for (const execution of acquisition.collection.collection
      .source_executions) {
      if (execution.source_mode !== "fixture") {
        throw new FixtureSemanticError(
          `Fixture paper source execution ${execution.source_id} must have ` +
            `source_mode "fixture"; got "${execution.source_mode}".`,
        );
      }
    }
  }
  for (const entry of bundle.data.paperSummaries) {
    const { version, summary } = entry;
    // Defensive runtime check: an old-shaped bundle without the rich version
    // must fail as an explicit fixture contract error, never a TypeError.
    if (version === undefined || version === null) {
      throw new FixtureSemanticError(
        `Fixture paper summary ${summary.artifact_version_id} must ` +
          "carry its full immutable ArtifactVersion detail",
      );
    }
    if (bundle.data.artifactVersions.some((item) => item.id === version.id)) {
      throw new FixtureSemanticError(
        `Paper summary version ${version.id} must have one rich immutable ` +
          "fixture representation, not a second generic ArtifactVersion",
      );
    }
    if (
      version.id !== summary.artifact_version_id ||
      version.artifact_id !== summary.artifact_id ||
      version.project_id !== summary.project_id ||
      version.content_hash !== summary.content_hash ||
      version.input_hash !== summary.input_hash ||
      version.source_mode !== summary.source_mode ||
      version.created_at !== summary.created_at ||
      JSON.stringify(version.content) !== JSON.stringify(summary.summary)
    ) {
      throw new FixtureSemanticError(
        `Paper summary version ${version.id} identity must match its ` +
          "dedicated summary read",
      );
    }
    if (summary.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture paper summary ${summary.artifact_version_id} ` +
          `must have source_mode "fixture"; got "${summary.source_mode}".`,
      );
    }
  }
  for (const entry of bundle.data.scientificArtifacts) {
    const { version, read } = entry;
    if (version === undefined || version === null) {
      throw new FixtureSemanticError(
        `Fixture scientific read ${read.artifact_version_id} must carry its full immutable ArtifactVersion detail`,
      );
    }
    if (bundle.data.artifactVersions.some((item) => item.id === version.id)) {
      throw new FixtureSemanticError(
        `Scientific version ${version.id} must have one rich immutable fixture representation`,
      );
    }
    if (
      version.id !== read.artifact_version_id ||
      version.artifact_id !== read.artifact_id ||
      version.project_id !== read.project_id ||
      version.content_hash !== read.content_hash ||
      version.input_hash !== read.input_hash ||
      version.source_mode !== read.source_mode ||
      version.created_at !== read.created_at ||
      JSON.stringify(version.content) !== JSON.stringify(read.content)
    ) {
      throw new FixtureSemanticError(
        `Scientific version ${version.id} identity must match its dedicated read`,
      );
    }
    if (read.source_mode !== "fixture") {
      throw new FixtureSemanticError(
        `Fixture scientific read ${read.artifact_version_id} must have source_mode "fixture"`,
      );
    }
  }
}

function validateBundlePayloads(bundle: FixtureBundle): void {
  const entries: readonly {
    readonly model: CoreModelName;
    readonly payloads: readonly unknown[];
  }[] = [
    { model: "ResearchProject", payloads: bundle.data.projects },
    { model: "ResearchContractDraft", payloads: bundle.data.contractDrafts },
    { model: "ResearchContract", payloads: bundle.data.contracts },
    { model: "ResearchRun", payloads: bundle.data.runs },
    { model: "RunEvent", payloads: bundle.data.runEvents },
    { model: "ArtifactVersion", payloads: bundle.data.artifactVersions },
    {
      model: "ArtifactVersionDetail",
      payloads: [
        ...bundle.data.paperAcquisitions.map((item) => item.version),
        ...bundle.data.paperSummaries.map((item) => item.version),
        ...bundle.data.scientificArtifacts.map((item) => item.version),
      ],
    },
    { model: "ResearchArtifact", payloads: bundle.data.artifacts },
    {
      model: "PaperCollectionRead",
      payloads: bundle.data.paperAcquisitions.map((item) => item.collection),
    },
    {
      model: "PaperCollectionCandidateRead",
      payloads: bundle.data.paperAcquisitions.flatMap(
        (item) => item.candidates,
      ),
    },
    {
      model: "PaperSummaryRead",
      payloads: bundle.data.paperSummaries.map((item) => item.summary),
    },
    {
      model: "ScientificArtifactRead",
      payloads: bundle.data.scientificArtifacts.map((item) => item.read),
    },
  ];
  for (const { model, payloads } of entries) {
    for (const payload of payloads) {
      const result = validateDto(model, payload);
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

  remove(id: DomainEntityId): void {
    this.entities.delete(id);
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
  readonly researchCatalog: ResearchCatalogRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly researchInputs: ResearchInputRepository;
  readonly researchThread: ResearchThreadRepository;
  readonly artifacts: ArtifactReadRepository;
  readonly paperAcquisition: PaperAcquisitionRepository;
  readonly paperSummary: PaperSummaryRepository;
  readonly scientificArtifacts: ScientificArtifactRepository;
  readonly dataArtifacts: DataArtifactRepository;
  readonly artifactExports: ArtifactExportRepository;
  readonly literatureArtifacts: LiteratureArtifactRepository;
  readonly graphArtifacts: GraphArtifactRepository;
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

/** Session id all fixture-owned resources belong to (single Demo Replay owner). */
const FIXTURE_SESSION_ID = "sess_01JEXAMPLE" as DomainEntityId;

/** Matches the runtime default page size for `listResearchProjects`. */
const PROJECT_PAGE_LIMIT = 20;

function encodeProjectCursor(projectId: DomainEntityId): string {
  return btoa(String(projectId)).replace(/=+$/u, "");
}

function decodeProjectCursor(cursor: string): DomainEntityId {
  try {
    const padded = cursor.padEnd(
      cursor.length + ((4 - (cursor.length % 4)) % 4),
      "=",
    );
    return atob(padded) as DomainEntityId;
  } catch {
    throw new UnexpectedHttpError(
      "The pagination cursor is invalid for this collection",
      400,
      "INVALID_CURSOR",
    );
  }
}

/**
 * Create a `RepositorySet` backed by a validated fixture bundle.
 *
 * @throws {FixtureValidationError} when any DTO fails contract validation.
 * @throws {FixtureSemanticError} when the bundle violates Demo Replay
 *   constraints (e.g. `live` or `cached` source labels).
 */
export function createFixtureRepositories(
  bundle: FixtureBundle,
  options: FixtureAdapterOptions = {},
): FixtureRepositorySet {
  validateBundleSemantics(bundle);
  validateBundlePayloads(bundle);
  const exportProject = bundle.data.projects[0];
  if (!exportProject) {
    throw new FixtureSemanticError(
      "Fixture bundle must carry a Project for version-pinned exports.",
    );
  }

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
  const threadEntries = new MemoryStore<ResearchThreadEntry>([]);
  const runs = new MemoryStore(
    bundle.data.runs.map((dto) => mapResearchRun(dto)),
  );
  const artifacts = new MemoryStore(
    bundle.data.artifacts.map((dto) => mapResearchArtifact(dto)),
  );
  const versions = new MemoryStore<ArtifactVersionMetadata>([
    ...bundle.data.artifactVersions.map((dto) =>
      mapArtifactVersionMetadata(dto),
    ),
    ...bundle.data.paperAcquisitions.map((item) =>
      mapArtifactVersionMetadata(item.version),
    ),
    ...bundle.data.paperSummaries.map((item) =>
      mapArtifactVersionMetadata(item.version),
    ),
    ...bundle.data.scientificArtifacts.map((item) =>
      mapArtifactVersionMetadata(item.version),
    ),
  ]);
  const evidenceStore = new MemoryStore(
    bundle.data.evidence.map((entity) => mapEvidence(entity)),
  );
  const workspaces = new MemoryStore<WorkspaceSnapshot>([]);
  const checkpoints = new Map<DomainEntityId, RunCheckpoint>(
    (bundle.data.runCheckpoints ?? []).map((dto) => {
      const checkpoint = mapRunCheckpoint(dto);
      return [checkpoint.id, checkpoint] as const;
    }),
  );
  const researchInputs = new MemoryStore<ResearchInputRef>(
    (bundle.data.researchInputs ?? []).map((dto) => mapResearchInputRef(dto)),
  );
  const inputProjectIds = new Map<DomainEntityId, DomainEntityId>(
    (bundle.data.researchInputs ?? []).map((dto) => [
      asEntityId(dto.id),
      bundle.data.projects[0]?.id
        ? asEntityId(bundle.data.projects[0].id)
        : asEntityId("project_fixture"),
    ]),
  );

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
  const projectsByIdempotencyKey = new Map<
    string,
    { readonly request: string; readonly project: ResearchProject }
  >();
  const draftsByIdempotencyKey = new Map<
    string,
    { readonly request: string; readonly draft: ResearchContractDraft }
  >();
  const decisionsByIdempotencyKey = new Map<
    string,
    { readonly request: string; readonly result: RunDecisionResult }
  >();
  const inputByIdempotencyKey = new Map<
    string,
    { readonly request: string; readonly input: ResearchInputRef }
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
    const title = request.title.trim();
    if (title.length === 0 || title.length > 200) {
      errors.push("title must contain between 1 and 200 characters");
    }
    if (request.artifactVersionIds.length === 0) {
      errors.push("artifactVersionIds must contain at least one value");
    }
    if (request.artifactVersionIds.length > 100) {
      errors.push("artifactVersionIds must contain at most 100 values");
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
    if (request.evidenceIds.length > 500) {
      errors.push("evidenceIds must contain at most 500 values");
    }
    if (request.redactionPolicy !== "public_metadata_only") {
      errors.push('redactionPolicy must be "public_metadata_only"');
    }
    const expiry = Date.parse(request.expiresAt);
    if (Number.isNaN(expiry) || !/(?:Z|[+-]00:00)$/u.test(request.expiresAt)) {
      errors.push("expiresAt must be a UTC datetime");
    } else if (expiry <= Date.parse(now)) {
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
      list: async (cursor = null) => {
        // Deterministic order matching the runtime: newest first by
        // (createdAt DESC, id DESC), paginated with an opaque id cursor.
        const ordered = [...projects.filter(() => true)].sort((a, b) => {
          if (a.createdAt !== b.createdAt) {
            return a.createdAt < b.createdAt ? 1 : -1;
          }
          return a.id < b.id ? 1 : -1;
        });
        let start = 0;
        if (cursor !== null) {
          const anchor = decodeProjectCursor(cursor);
          const index = ordered.findIndex((project) => project.id === anchor);
          if (index === -1) {
            throw new UnexpectedHttpError(
              "The pagination cursor is invalid for this collection",
              400,
              "INVALID_CURSOR",
            );
          }
          start = index + 1;
        }
        const items = ordered.slice(start, start + PROJECT_PAGE_LIMIT);
        const hasMore = start + items.length < ordered.length;
        const nextCursor =
          items.length > 0 && hasMore
            ? encodeProjectCursor(items[items.length - 1]!.id)
            : null;
        return { items, nextCursor };
      },
      create: async (input) => {
        const replayKey = `create-project:${input.idempotencyKey}`;
        const replay = projectsByIdempotencyKey.get(replayKey);
        const requestHash = JSON.stringify({
          name: input.name,
          description: input.description ?? "",
          caseKey: input.caseKey,
        });
        if (replay) {
          if (replay.request !== requestHash) {
            throw new ConflictError(
              "The idempotency key was already used with a different request",
              "IDEMPOTENCY_CONFLICT",
            );
          }
          return replay.project;
        }
        const now = clock();
        const project: ResearchProject = {
          id: nextId("proj"),
          sessionId: FIXTURE_SESSION_ID,
          name: input.name,
          description: input.description ?? "",
          caseKey: input.caseKey,
          activeDraftId: null,
          activeContractId: null,
          latestRunId: null,
          threadSummary: {
            hasThreadEntries: false,
            latestThreadActor: null,
            hasUnansweredClarification: false,
          },
          createdAt: now,
          updatedAt: now,
          revision: 1,
        };
        projects.upsert(project);
        projectsByIdempotencyKey.set(replayKey, {
          request: requestHash,
          project,
        });
        return project;
      },
      update: async (
        id,
        input: UpdateResearchProjectInput,
        expectedRevision,
      ) => {
        const project = projects.get(id);
        if (project === null) {
          throw new NotFoundError(
            `Project ${id} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        if (project.revision !== expectedRevision) {
          throw new ConflictError(
            "Project revision conflict",
            "VERSION_CONFLICT",
          );
        }
        const updated = {
          ...project,
          name: input.name,
          revision: project.revision + 1,
          updatedAt: clock(),
        };
        projects.upsert(updated);
        return updated;
      },
      delete: async (id, expectedRevision) => {
        const project = projects.get(id);
        if (project === null) return;
        if (project.revision !== expectedRevision) {
          throw new ConflictError(
            "Project revision conflict",
            "VERSION_CONFLICT",
          );
        }
        projects.remove(id);
        for (const entry of threadEntries.filter(
          (item) => item.projectId === id,
        )) {
          threadEntries.remove(entry.id);
        }
      },
    },
    researchCatalog: {
      getForProject: async (projectId) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        throw new FixtureSemanticError(
          "Demo Replay fixtures do not author production Research Contracts; use the HTTP catalog.",
        );
      },
    },
    researchThread: {
      list: async (projectId, cursor = null) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const after = cursor === null ? 0 : Number(cursor);
        const ordered = [
          ...threadEntries.filter((entry) => entry.projectId === projectId),
        ].sort((a, b) => a.sequence - b.sequence);
        const items = ordered
          .filter((entry) => entry.sequence > after)
          .slice(0, 100);
        const hasMore = ordered.some(
          (entry) =>
            entry.sequence > (items[items.length - 1]?.sequence ?? after),
        );
        return {
          items,
          nextCursor:
            hasMore && items.length > 0
              ? String(items[items.length - 1]!.sequence)
              : null,
        };
      },
      submit: async (projectId) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        throw new FixtureSemanticError(
          "Demo Replay fixtures cannot execute the production research assistant; use the HTTP runtime with a configured model provider.",
        );
      },
    },
    contracts: {
      createDraft: async (projectId, input) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const replayKey = `create-draft:${input.idempotencyKey}`;
        const replay = draftsByIdempotencyKey.get(replayKey);
        const requestHash = JSON.stringify({
          intent: input.intent,
          contract: mapDomainContractInputToDto(input.contract),
        });
        if (replay) {
          if (replay.request !== requestHash) {
            throw new ConflictError(
              "The idempotency key was already used with a different request",
              "IDEMPOTENCY_CONFLICT",
            );
          }
          return replay.draft;
        }
        const now = clock();
        const draft: ResearchContractDraft = {
          id: nextId("rcd"),
          sessionId: FIXTURE_SESSION_ID,
          version: 1,
          intent: input.intent,
          status: "draft",
          contract: input.contract,
          warnings: [],
          createdAt: now,
          updatedAt: now,
          expiresAt: new Date(
            Date.parse(now) + 3_600_000,
          ).toISOString() as UtcIsoTimestamp,
        };
        drafts.upsert(draft);
        const project = projects.get(projectId);
        if (project !== null) {
          projects.upsert({ ...project, activeDraftId: draft.id });
        }
        draftsByIdempotencyKey.set(replayKey, {
          request: requestHash,
          draft,
        });
        return draft;
      },
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
          contentHash: (await computeContractContentHash(
            mapDomainContractInputToDto(draft.contract),
          )) as ContentHash,
        };
        contracts.upsert(contract);
        drafts.upsert({ ...draft, status: "confirmed", updatedAt: now });
        const project = projects.get(projectId);
        if (project !== null) {
          projects.upsert({
            ...project,
            activeDraftId: null,
            activeContractId: contract.id,
          });
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
          revision: 1,
          progress: 0,
          parentRunId: null,
          derivationKind: "original",
          retryFromStep: null,
          cachePolicy: "disabled",
          startedAt: null,
          finishedAt: null,
          createdAt: now,
          updatedAt: now,
          latestEventSequence: 1,
          failureCode: null,
          failureSummary: null,
        };
        runs.upsert(run);
        const project = projects.get(input.projectId);
        if (project !== null) {
          projects.upsert({ ...project, latestRunId: run.id });
        }
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
      getCheckpoint: async (runId) => {
        for (const checkpoint of checkpoints.values()) {
          if (checkpoint.runId === runId) return checkpoint;
        }
        return null;
      },
      decide: async (
        runId,
        input: RunDecisionInput,
        expectedRevision,
        idempotencyKey,
      ): Promise<RunDecisionResult> => {
        const parent = runs.get(runId);
        if (parent === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        if (parent.revision !== expectedRevision) {
          throw new ConflictError("Run revision conflict", "VERSION_CONFLICT");
        }
        const request = JSON.stringify({ runId, input });
        const replay = decisionsByIdempotencyKey.get(idempotencyKey);
        if (replay) {
          if (replay.request !== request) {
            throw new ConflictError(
              "Idempotency key was already used for a different decision",
              "IDEMPOTENCY_CONFLICT",
            );
          }
          return replay.result;
        }
        const now = clock();
        let resultRun: ResearchRun = {
          ...parent,
          status: input.decision === "cancel" ? "cancelled" : "queued",
          revision: parent.revision + 1,
          updatedAt: now,
        };
        let childRunId: DomainEntityId | null = null;
        if (input.decision === "retry") {
          childRunId = nextId("run");
          resultRun = {
            ...parent,
            id: childRunId,
            status: "queued",
            revision: 1,
            parentRunId: parent.id,
            derivationKind: "retry",
            retryFromStep: asEntityId(input.stepKey),
            startedAt: null,
            finishedAt: null,
            createdAt: now,
            updatedAt: now,
            latestEventSequence: 1,
            failureCode: null,
            failureSummary: null,
          };
          runs.upsert(resultRun);
          runEvents.set(childRunId, [
            {
              runId: childRunId,
              sequence: 1,
              eventType: asEntityId("run.queued"),
              stepKey: null,
              progress: 0,
              publicMessage: "Retry queued",
              artifactVersionIds: [],
              occurredAt: now,
            },
          ]);
        } else {
          runs.upsert(resultRun);
        }
        const checkpoint = [...checkpoints.values()].find(
          (item) => item.runId === runId && item.status === "open",
        );
        if (checkpoint) {
          checkpoints.set(checkpoint.id, {
            ...checkpoint,
            status: input.decision === "cancel" ? "cancelled" : "resolved",
            resolvedAt: now,
            resolutionRunId: resultRun.id,
          });
        }
        const decision: RunDecisionResult["decision"] = {
          childRunId,
          createdAt: now,
          decision: input.decision,
          id: nextId("decision"),
          inputIds: input.decision === "resume" ? [...input.inputIds] : [],
          parentRunId: parent.id,
          stepKey:
            input.decision === "retry"
              ? input.stepKey
              : (checkpoint?.stepKey ?? "checkpoint"),
        };
        const result = { decision, run: resultRun };
        decisionsByIdempotencyKey.set(idempotencyKey, { request, result });
        return result;
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
      listSteps: async (runId): Promise<readonly RunStepSnapshot[]> => {
        if (runs.get(runId) === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        return [];
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
      // Same narrowing as the HTTP adapter: generic reads expose identity and
      // provenance metadata only; rich content stays behind its dedicated port.
      getVersion: async (id) => versions.get(id),
      getEvidence: async (id) => evidenceStore.get(id),
    },
    researchInputs: {
      listByProject: async (projectId) =>
        researchInputs.filter(
          (input) => inputProjectIds.get(input.id) === projectId,
        ),
      create: async (input: CreateResearchInput) => {
        const request = JSON.stringify({
          projectId: input.projectId,
          type: input.type,
          filename: input.filename ?? null,
          mimeType: input.mimeType ?? null,
          textContent: input.type === "text" ? input.textContent : undefined,
          url: input.type === "url" ? input.url : undefined,
          size: input.type === "text" ? input.textContent.length : 0,
        });
        const replay = inputByIdempotencyKey.get(input.idempotencyKey);
        if (replay) {
          if (replay.request !== request) {
            throw new ConflictError(
              "Idempotency key was already used for a different input",
              "IDEMPOTENCY_CONFLICT",
            );
          }
          return replay.input;
        }
        if (projects.get(input.projectId) === null) {
          throw new NotFoundError(
            `Project ${input.projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const id = nextId("input");
        const sizeBytes =
          input.type === "text"
            ? new TextEncoder().encode(input.textContent).byteLength
            : input.type === "url"
              ? 0
              : input.content.byteLength;
        const record: ResearchInputRef = {
          contentHash: `sha256:${"0".repeat(64)}`,
          createdAt: clock(),
          filename: input.filename ?? null,
          id,
          mimeType: input.mimeType ?? null,
          sizeBytes,
          sourceSnapshotId: null,
          sourceType: input.type === "url" ? "url" : "fixture",
          status: "accepted",
          type: input.type,
        };
        researchInputs.upsert(record);
        inputProjectIds.set(id, input.projectId);
        inputByIdempotencyKey.set(input.idempotencyKey, {
          request,
          input: record,
        });
        return record;
      },
      bindToRun: async (inputId, projectId, runId) => {
        const input = researchInputs.get(inputId);
        const run = runs.get(runId);
        if (input === null || inputProjectIds.get(inputId) !== projectId) {
          throw new NotFoundError(
            `Research input ${inputId} not found`,
            "RESEARCH_INPUT_NOT_FOUND",
          );
        }
        if (run === null || run.projectId !== projectId) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        return input;
      },
    },
    paperAcquisition: {
      getReview: async (artifactVersionId) => {
        const entry = bundle.data.paperAcquisitions.find(
          (item) => item.collection.artifact_version_id === artifactVersionId,
        );
        if (!entry) {
          throw new NotFoundError(
            `Paper collection ${artifactVersionId} not found`,
            "ARTIFACT_VERSION_NOT_FOUND",
          );
        }
        // Identical assembly path to the HTTP adapter, so both return the
        // exact same domain shape for the same contract payloads.
        return assemblePaperAcquisitionReview(entry.collection, [
          ...entry.candidates,
        ]);
      },
    },
    paperSummary: {
      getSummary: async (artifactVersionId) => {
        const entry = bundle.data.paperSummaries.find(
          (item) => item.summary.artifact_version_id === artifactVersionId,
        );
        if (!entry) {
          // Mirrors the PaperSummary API backend: an unknown version id is a generic
          // ARTIFACT_VERSION_NOT_FOUND, never an "empty summary" state.
          throw new NotFoundError(
            `Paper summary ${artifactVersionId} not found`,
            "ARTIFACT_VERSION_NOT_FOUND",
          );
        }
        // Identical assembly path to the HTTP adapter, so both return the
        // exact same domain shape for the same contract payloads.
        return assemblePaperSummaryReview(entry.summary);
      },
    },
    scientificArtifacts: {
      getReview: async (artifactVersionId) => {
        const entry = bundle.data.scientificArtifacts.find(
          (item) => item.read.artifact_version_id === artifactVersionId,
        );
        if (!entry) {
          throw new NotFoundError(
            `Scientific Artifact ${artifactVersionId} not found in Demo Replay`,
            "ARTIFACT_VERSION_NOT_FOUND",
          );
        }
        return mapScientificArtifactRead(entry.read);
      },
      getContent: async (artifactVersionId, contentHash) => {
        const entry = bundle.data.scientificArtifacts.find(
          (item) => item.read.artifact_version_id === artifactVersionId,
        );
        const blob = entry?.contentBlobs.find(
          (item) => item.content_hash === contentHash,
        );
        if (!blob) {
          throw new NotFoundError(
            `Scientific Artifact content ${artifactVersionId}/${contentHash} not found in Demo Replay`,
            "SCIENTIFIC_CONTENT_NOT_FOUND",
          );
        }
        const bytes = Uint8Array.from(atob(blob.bytes_base64), (value) =>
          value.charCodeAt(0),
        );
        return bytes.buffer;
      },
    },
    dataArtifacts: createFixtureDataArtifactRepository([
      ...bundle.data.dataArtifactReads,
      ...bundle.data.fieldDictionaryArtifactReads,
      ...bundle.data.sourceCollectionArtifactReads,
    ]),
    artifactExports: createFixtureArtifactExportRepository(
      asEntityId(exportProject.id),
    ),
    literatureArtifacts: createFixtureLiteratureArtifactRepository(
      bundle.data.literatureClaimReads,
      bundle.data.literatureRelationReads,
      bundle.data.literatureReasoningTraceReads,
    ),
    graphArtifacts: createFixtureGraphArtifactRepository(
      bundle.data.graphArtifactReads,
      bundle.data.graphNodeReads,
      bundle.data.graphEdgeReads,
    ),
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
          atlasState: snapshotInput.atlasState ?? {
            focusMode: null,
            selectedObjectRef: null,
          },
          observatoryState: snapshotInput.observatoryState ?? {
            activeArtifactVersionId: null,
            activeEvidenceId: null,
          },
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
          title: request.title.trim() as typeof request.title,
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
        return {
          ...snapshot,
          shareToken: token,
          shareUrl: `/api/public/shares/${token}`,
        };
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
