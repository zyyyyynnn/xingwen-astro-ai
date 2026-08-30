/**
 * Fixture adapter — the Demo Replay `RepositorySet` implementation.
 *
 * Validates every fixture DTO against the Core Domain and Transport Contract JSON Schemas, enforces Demo
 * Replay semantics (no `live`/`cached` data), maps payloads into the domain
 * model, and serves reads from in-memory stores. It implements the same
 * narrowed ports as the HTTP adapter so the two are structurally
 * interchangeable. Writes (draft update, contract confirm, run create,
 * workspace save, share create/revoke) mutate the stores deterministically via
 * an injectable clock and id factory so tests stay stable.
 */

import { validateDto, type CoreModelName } from "@xingwen/contracts";
import {
  asEntityId,
  type CreateShareSnapshotRequest,
  type ArtifactVersionMetadata,
  type DomainEntityId,
  type PublicArtifactVersion,
  type PublicArtifactPresentation,
  type PublicEvidence,
  type PublicShareSnapshot,
  type ResearchContract,
  type ResearchContractDraft,
  type ResearchProject,
  type ResearchRun,
  type ResearchThreadEntry,
  type RunEvent,
  type RunStepSnapshot,
  type ShareSnapshot,
  type SourceSnapshotSummary,
  type WorkspaceSnapshot,
  type ContentHash,
  type ModelProviderConfigurationStatus,
  type UtcIsoTimestamp,
} from "@xingwen/domain";

import { FixtureSemanticError, FixtureValidationError } from "./errors";
import { ConflictError, NotFoundError, UnexpectedHttpError } from "./errors";
import {
  buildFixtureProvenance,
  mapArtifactVersionMetadata,
  mapDomainContractInputToDto,
  mapEvidence,
  mapPublicArtifactPresentation,
  mapResearchArtifact,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchRun,
  mapRunEvent,
} from "./mapping";
import { computeContractContentHash } from "./contract-hash";
import { createFixtureArtifactExportRepository } from "./artifact-export-repository";
import { createFixtureDataArtifactRepository } from "./data-artifact-repository";
import { createFixtureGraphArtifactRepository } from "./graph-artifact-repository";
import { createFixtureLiteratureArtifactRepository } from "./literature-artifact-repository";
import { createFixtureRevisionRepository } from "./revision-repository";
import {
  assemblePaperAcquisitionReview,
  mapSnapshotSummary,
} from "./paper-acquisition-repository";
import { assemblePaperSummaryReview } from "./paper-summary-repository";
import { mapScientificArtifactRead } from "./scientific-artifact-repository";
import type {
  CreateResearchRunInput,
  ResearchInputRef,
  RepositoryProvenance,
  RepositorySet,
  RunEventRecovery,
  UpdateResearchProjectInput,
  UpdateResearchContractDraftInput,
} from "./ports";
import type { FixtureBundle } from "./fixture/bundle";

/** Optional deterministic clock and id factory for stable tests. */
export interface FixtureAdapterOptions {
  readonly clock?: () => UtcIsoTimestamp;
  readonly idFactory?: (prefix: string) => DomainEntityId;
}

const PUBLIC_SOURCE_URL_KEYS = [
  "source_url",
  "url",
  "original_url",
  "landing_url",
] as const;

function validateBundleSemantics(bundle: FixtureBundle): void {
  // Defensive runtime check: an old-shaped bundle without the paperSummaries
  // array must fail as an explicit fixture contract error, never a TypeError.
  if (!Array.isArray(bundle.data.paperSummaries)) {
    throw new FixtureSemanticError(
      "Fixture bundle must carry a paperSummaries array of rich immutable " +
        "paper summary entries.",
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

  const allVersions = [
    ...bundle.data.artifactVersions,
    ...bundle.data.paperAcquisitions.map((item) => item.version),
    ...bundle.data.paperSummaries.map((item) => item.version),
  ];
  const artifactKindById = new Map(
    bundle.data.artifacts.map((artifact) => [artifact.id, artifact.kind]),
  );
  const evidenceIdsByVersion = new Map(
    allVersions.map((version) => [version.id, new Set(version.evidence_ids)]),
  );
  const referencedEvidenceIds = (
    presentation: (typeof bundle.data.artifactPresentations)[string],
  ): readonly string[] => [
    ...(presentation.sections ?? []).flatMap((section) =>
      section.paragraphs.flatMap((paragraph) => paragraph.evidence_ids ?? []),
    ),
    ...(presentation.entries ?? []).flatMap((entry) => [
      ...(entry.evidence_ids ?? []),
      ...(entry.reasoning_trace?.evidence_ids ?? []),
    ]),
    ...(presentation.graph_edges ?? []).flatMap(
      (edge) => edge.evidence_ids ?? [],
    ),
  ];
  for (const version of allVersions) {
    const presentation = bundle.data.artifactPresentations[version.id];
    const artifactKind = artifactKindById.get(version.artifact_id);
    if (!presentation || !artifactKind || presentation.kind !== artifactKind) {
      throw new FixtureSemanticError(
        `Artifact presentation ${version.id} is missing or has the wrong kind`,
      );
    }
    const allowedEvidenceIds =
      evidenceIdsByVersion.get(version.id) ?? new Set();
    const foreignEvidenceId = referencedEvidenceIds(presentation).find(
      (evidenceId) => !allowedEvidenceIds.has(evidenceId),
    );
    if (foreignEvidenceId) {
      throw new FixtureSemanticError(
        `Artifact presentation ${version.id} references Evidence outside its immutable version`,
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
      model: "PublicArtifactPresentation",
      payloads: Object.values(bundle.data.artifactPresentations),
    },
    {
      model: "ArtifactVersionDetail",
      payloads: [
        ...bundle.data.paperAcquisitions.map((item) => item.version),
        ...bundle.data.paperSummaries.map((item) => item.version),
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
    { model: "DatasetArtifactRead", payloads: bundle.data.dataArtifactReads },
    {
      model: "FieldDictionaryArtifactRead",
      payloads: bundle.data.fieldDictionaryArtifactReads,
    },
    {
      model: "SourceCollectionArtifactRead",
      payloads: bundle.data.sourceCollectionArtifactReads,
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

export interface FixtureRepositorySet extends RepositorySet {
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
  const threadEntries = new MemoryStore<ResearchThreadEntry>(
    bundle.data.threadEntries,
  );
  const runs = new MemoryStore(
    bundle.data.runs.map((dto) => mapResearchRun(dto)),
  );
  const artifacts = new MemoryStore(
    bundle.data.artifacts.map((dto) => mapResearchArtifact(dto)),
  );
  const versions = new MemoryStore<ArtifactVersionMetadata>([
    ...bundle.data.artifactVersions.map((dto) =>
      mapArtifactVersionMetadata(
        dto,
        bundle.data.artifactPresentations[dto.id],
      ),
    ),
    ...bundle.data.paperAcquisitions.map((item) =>
      mapArtifactVersionMetadata(
        item.version,
        bundle.data.artifactPresentations[item.version.id],
      ),
    ),
    ...bundle.data.paperSummaries.map((item) =>
      mapArtifactVersionMetadata(
        item.version,
        bundle.data.artifactPresentations[item.version.id],
      ),
    ),
  ]);
  const evidenceStore = new MemoryStore(
    bundle.data.evidence.map((entity) => mapEvidence(entity)),
  );
  const sourceSnapshotsById = new Map<string, SourceSnapshotSummary>();
  const sourceSnapshotDtos = [
    ...bundle.data.paperAcquisitions.flatMap(
      (item) => item.collection.source_snapshots,
    ),
    ...bundle.data.paperSummaries.flatMap(
      (item) => item.summary.source_snapshots,
    ),
    ...bundle.data.dataArtifactReads.flatMap((read) => read.source_snapshots),
    ...bundle.data.fieldDictionaryArtifactReads.flatMap(
      (read) => read.source_snapshots,
    ),
    ...bundle.data.sourceCollectionArtifactReads.flatMap(
      (read) => read.source_snapshots,
    ),
    ...bundle.data.literatureClaimReads.flatMap(
      (read) => read.source_snapshots,
    ),
    ...bundle.data.literatureRelationReads.flatMap(
      (read) => read.source_snapshots,
    ),
    ...(bundle.data.scientificArtifactReads ?? []).flatMap(
      (read) => read.source_snapshots,
    ),
  ];
  for (const dto of sourceSnapshotDtos) {
    const snapshot = mapSnapshotSummary(dto);
    sourceSnapshotsById.set(snapshot.id, snapshot);
  }
  const workspaces = new MemoryStore<WorkspaceSnapshot>([]);
  const researchInputs = new MemoryStore<ResearchInputRef>([]);
  const researchInputContent = new Map<DomainEntityId, Blob>();
  const researchInputProjects = new Map<DomainEntityId, DomainEntityId>();

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
  const fixtureModelProvider: ModelProviderConfigurationStatus = {
    status: "ready",
    revision: 1,
    source: "workspace",
    preset: "dashscope",
    baseUrl: null,
    dashscopeBaseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "演示回放（不执行模型调用）",
    apiKeyHint: "Demo Replay",
    verifiedAt: null,
    updatedAt: null,
    editable: true,
  };
  const fixtureArtifactExports = createFixtureArtifactExportRepository(
    bundle.data.projects[0]?.id
      ? asEntityId(bundle.data.projects[0].id)
      : asEntityId("proj_fixture"),
  );

  function publicPresentation(
    kind: PublicArtifactVersion["kind"],
    versionId: DomainEntityId,
  ): PublicArtifactPresentation {
    const dto = bundle.data.artifactPresentations[String(versionId)];
    if (!dto || dto.kind !== kind) {
      throw new FixtureSemanticError(
        `Artifact presentation ${versionId} is missing or has the wrong kind`,
      );
    }
    return mapPublicArtifactPresentation(dto);
  }
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
      presentation: publicPresentation(artifact.kind, version.id),
      evidenceIds: [...version.evidenceIds],
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
      entity?.source === null ||
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
    const locator = entity.locator;
    const publicLocator = {
      kind: (locator?.kind ?? "source") as PublicEvidence["locator"]["kind"],
      page: locator?.kind === "paper_text" ? locator.page : null,
      paragraph: locator?.kind === "paper_text" ? locator.paragraph : null,
      section: locator?.kind === "paper_text" ? locator.section : null,
      textRange: locator?.kind === "paper_text" ? locator.range : null,
      field: locator?.kind === "database_cell" ? String(locator.field) : null,
      rowKey: locator?.kind === "database_cell" ? locator.rowKey : null,
      blockId: null,
      readingOrder: null,
      tableId: null,
      cellId: null,
      bbox: null,
    };
    const publicRequestMetadata = Object.fromEntries(
      PUBLIC_SOURCE_URL_KEYS.flatMap((key) => {
        const value = entity.source?.requestMetadata[key];
        return typeof value === "string" ? [[key, value]] : [];
      }),
    );
    return {
      id: entity.id,
      artifactVersionId: entity.artifactVersionId,
      sourceSnapshotId: entity.sourceSnapshotId,
      locator: publicLocator,
      quoteOrValue: entity.quoteOrValue,
      createdAt: entity.createdAt,
      source: {
        sourceId: entity.source.sourceId,
        sourceType: entity.source.sourceType,
        retrievedAt: entity.source.retrievedAt,
        licenseNote: entity.source.licenseNote,
        requestMetadata: publicRequestMetadata,
      },
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
    if (request.redactionPolicy !== "redacted_public_snapshot") {
      errors.push('redactionPolicy must be "redacted_public_snapshot"');
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

  const paperCandidateBindings = new Map<string, DomainEntityId>();

  // Seed authorized PDF research input for demo replay
  const seededResearchInputId = asEntityId("ri_paper_pdf_01");
  const seededResearchInputRef: ResearchInputRef = {
    id: seededResearchInputId,
    type: "pdf",
    sourceType: "upload",
    contentHash:
      "sha256:5b78bfb739358af0bcfdca12cdba54c25277cd26d1c4f40523737749bcb2e100",
    filename: "stassun-2019-revised-tic.pdf",
    mimeType: "application/pdf",
    sizeBytes: 4349822,
    createdAt: bundle.generatedAt,
    sourceSnapshotId: null,
    status: "accepted",
  };
  researchInputs.upsert(seededResearchInputRef);
  if (bundle.data.projects[0]) {
    researchInputProjects.set(
      seededResearchInputId,
      asEntityId(bundle.data.projects[0].id),
    );
  }

  const scientificBinaryStore = buildScientificBinaryStore(
    bundle.data.scientificArtifactReads ?? [],
  );

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
        return {
          projectId,
          caseKey: "exoplanet_host_star",
          targetObjects: [
            {
              value: asEntityId("exoplanet_candidate"),
              label: "系外行星候选体 (TOI)",
              description: "TESS 候选行星目标",
              group: "common",
            },
            {
              value: asEntityId("host_star"),
              label: "宿主恒星 (Host Star)",
              description: "系外行星宿主恒星参数与光谱",
              group: "common",
            },
            {
              value: asEntityId("spectroscopic_target"),
              label: "光谱学目标天体",
              description: "高分辨率视向速度观测天体",
              group: "advanced",
            },
          ],
          requestedFields: [
            {
              value: asEntityId("planet.toi_id"),
              label: "TOI 候选体编号",
              description: "TESS 候选行星标准编号",
              group: "common",
            },
            {
              value: asEntityId("planet.name"),
              label: "行星名称",
              description: "已确认系外行星或常用命名",
              group: "common",
            },
            {
              value: asEntityId("planet.period"),
              label: "轨道周期 (天)",
              description: "行星公转周期",
              group: "common",
            },
            {
              value: asEntityId("planet.radius"),
              label: "行星半径 (R_Earth)",
              description: "物理半径",
              group: "common",
            },
            {
              value: asEntityId("planet.mass"),
              label: "行星质量 (M_Earth)",
              description: "动力学反演质量",
              group: "common",
            },
            {
              value: asEntityId("planet.equilibrium_temperature"),
              label: "平衡温度 (K)",
              description: "行星表面平衡温度",
              group: "common",
            },
            {
              value: asEntityId("star.tic_id"),
              label: "TIC 恒星编号",
              description: "TESS Input Catalog 标识",
              group: "common",
            },
            {
              value: asEntityId("star.effective_temperature"),
              label: "恒星有效温度 (K)",
              description: "宿主恒星有效表面温度",
              group: "common",
            },
            {
              value: asEntityId("star.radius"),
              label: "恒星半径 (R_Sun)",
              description: "恒星物理半径",
              group: "common",
            },
            {
              value: asEntityId("star.mass"),
              label: "恒星质量 (M_Sun)",
              description: "恒星物理质量",
              group: "common",
            },
            {
              value: asEntityId("star.metallicity"),
              label: "金属丰度 [Fe/H]",
              description: "恒星金属丰度",
              group: "advanced",
            },
            {
              value: asEntityId("star.log_g"),
              label: "表面重力 log(g)",
              description: "表面重力加速度对数值",
              group: "advanced",
            },
            {
              value: asEntityId("star.distance"),
              label: "恒星距离 (pc)",
              description: "Gaia DR3 视差测距",
              group: "advanced",
            },
            {
              value: asEntityId("planet.discovery_year"),
              label: "发现年份",
              description: "首次发布或确认年份",
              group: "advanced",
            },
          ],
          allowedSources: [
            {
              value: asEntityId("nasa_exoplanet_archive"),
              label: "NASA Exoplanet Archive",
              description: "NASA 官方系外行星档案库",
              group: "common",
            },
            {
              value: asEntityId("toi_catalog"),
              label: "TESS TOI Catalog",
              description: "MIT / TESS 官方候选体星表",
              group: "common",
            },
            {
              value: asEntityId("gaia_dr3"),
              label: "Gaia DR3 星表",
              description: "ESA Gaia 空间天体测量数据",
              group: "common",
            },
            {
              value: asEntityId("exofop"),
              label: "ExoFOP-TESS",
              description: "后续观测协同工作平台",
              group: "advanced",
            },
            {
              value: asEntityId("simbad"),
              label: "SIMBAD 数据库",
              description: "Strasbourg 天文天体标识数据库",
              group: "advanced",
            },
          ],
          scientificSkills: [
            {
              value: "catalog_crossmatch",
              label: "多源星表检索与交叉证认",
              description: "跨星表坐标对齐与参数提取",
              group: "common",
            },
            {
              value: "light_curve_analysis",
              label: "时序光变曲线分析与凌星拟合",
              description: "从光变曲线提取科学结论",
              group: "common",
            },
            {
              value: "tabular_machine_learning",
              label: "科学推导与可比性审查",
              description: "主张关系推导与冲突判别",
              group: "advanced",
            },
          ],
          outputRequirements: [
            {
              value: "dataset",
              label: "宿主星结构化数据集",
              description: "40 颗宿主星完整数据集",
              group: "common",
            },
            {
              value: "field_dictionary",
              label: "字段与测量规范字典",
              description: "14 个字段规范定义",
              group: "common",
            },
            {
              value: "source_collection",
              label: "观测来源元数据集合",
              description: "3 个数据源快照元数据",
              group: "common",
            },
            {
              value: "paper_summary",
              label: "核心文献研读报告",
              description: "论文结构化摘要与证据定位",
              group: "common",
            },
            {
              value: "literature_claims",
              label: "科学主张条目",
              description: "6 条可检验科学事实",
              group: "common",
            },
            {
              value: "literature_relations",
              label: "主张关系与推导",
              description: "5 条主张间关系",
              group: "common",
            },
            {
              value: "graph",
              label: "领域知识图谱",
              description: "16 节点 20 边知识图谱",
              group: "advanced",
            },
            {
              value: "analysis_report",
              label: "科学分析报告",
              description: "综合分析推导报告",
              group: "advanced",
            },
            {
              value: "visualization",
              label: "交互式科学图表",
              description: "周期-半径图表",
              group: "advanced",
            },
            {
              value: "spectrum",
              label: "高分辨率光谱图谱",
              description: "HARPS 恒星光谱",
              group: "advanced",
            },
            {
              value: "light_curve",
              label: "测光光变曲线",
              description: "TESS 光变曲线",
              group: "advanced",
            },
            {
              value: "model_evaluation",
              label: "模型评估报告",
              description: "凌星分类评估报告",
              group: "advanced",
            },
            {
              value: "model_artifact",
              label: "ONNX 模型产物",
              description: "标准推理 ONNX 模型",
              group: "advanced",
            },
          ],
        };
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
          progress: 0,
          revision: 1,
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
            activityId: `run:${id}`,
            activityKind: "status",
            activityPhase: "queued",
            activityName: "研究任务",
            stepKey: null,
            progress: 0,
            content: "研究任务已进入执行队列。",
            details: {},
            artifactVersionIds: [],
            occurredAt: now,
          },
        ]);
        runsByIdempotencyKey.set(input.idempotencyKey, { request, run });
        return run;
      },
      cancel: async (runId) => {
        const run = runs.get(runId);
        if (run === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        const updated: ResearchRun = {
          ...run,
          status: "cancelled",
          updatedAt: clock(),
        };
        runs.upsert(updated);
        return updated;
      },
      retry: async (runId) => {
        const run = runs.get(runId);
        if (run === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
        const newId = nextId("run");
        const now = clock();
        const derived: ResearchRun = {
          id: newId,
          projectId: run.projectId,
          contractId: run.contractId,
          executionMode: run.executionMode,
          status: "queued",
          progress: 0,
          revision: run.revision,
          parentRunId: run.id,
          derivationKind: "retry",
          retryFromStep: run.retryFromStep,
          cachePolicy: run.cachePolicy,
          startedAt: null,
          finishedAt: null,
          createdAt: now,
          updatedAt: now,
          latestEventSequence: 0,
          failureCode: null,
          failureSummary: null,
        };
        runs.upsert(derived);
        return derived;
      },
      getCheckpoint: async () => null,
      submitCheckpointDecision: async (runId) => {
        const run = runs.get(runId);
        if (run === null) {
          throw new NotFoundError(`Run ${runId} not found`, "RUN_NOT_FOUND");
        }
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
      listVersions: async (artifactId) =>
        versions.filter((v) => v.artifactId === artifactId),
      // Same narrowing as the HTTP adapter: generic reads expose identity and
      // provenance metadata only; rich content stays behind its dedicated port.
      getVersion: async (id) => versions.get(id),
      getEvidence: async (id) => evidenceStore.get(id),
      getSourceSnapshot: async (id) => sourceSnapshotsById.get(id) ?? null,
    },
    researchInputs: {
      create: async (input) => {
        if (projects.get(input.projectId) === null) {
          throw new NotFoundError(
            `Project ${input.projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const now = clock();
        const ref: ResearchInputRef = {
          id: nextId("ri"),
          type: input.type,
          sourceType: "upload",
          contentHash: `fixture:${String(nextId("hash"))}`,
          filename: input.filename,
          mimeType: input.mimeType,
          sizeBytes: input.file.size,
          createdAt: now,
          sourceSnapshotId: null,
          status: "accepted",
        };
        researchInputs.upsert(ref);
        researchInputContent.set(ref.id, input.file);
        researchInputProjects.set(ref.id, input.projectId);
        return ref;
      },
      list: async (projectId) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        return researchInputs.filter(
          (ref) => researchInputProjects.get(ref.id) === projectId,
        );
      },
      delete: async (inputId) => {
        researchInputs.remove(inputId);
        researchInputContent.delete(inputId);
        researchInputProjects.delete(inputId);
      },
      bindToDraft: async (inputId, projectId) => {
        if (projects.get(projectId) === null) {
          throw new NotFoundError(
            `Project ${projectId} not found`,
            "PROJECT_NOT_FOUND",
          );
        }
        const ref = researchInputs.get(inputId);
        if (ref === null) {
          throw new NotFoundError(
            `Research input ${inputId} not found`,
            "RESEARCH_INPUT_NOT_FOUND",
          );
        }
        return ref;
      },
      getContentUrl: (inputId: DomainEntityId) =>
        inputId === seededResearchInputId
          ? "/fixture-papers/stassun-2019-revised-tic.pdf"
          : `/api/research-inputs/${inputId}/content`,
      getContent: async (inputId: DomainEntityId) =>
        researchInputContent.get(inputId) ?? new Blob([""]),
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
      bindResearchInput: async (input) => {
        const resInput = researchInputs.get(input.researchInputId);
        if (!resInput) {
          throw new NotFoundError(
            `Research input ${input.researchInputId} not found`,
            "RESEARCH_INPUT_NOT_FOUND",
          );
        }
        paperCandidateBindings.set(input.candidateId, input.researchInputId);
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
      getDocumentSource: async (artifactVersionId) => {
        const entry = bundle.data.paperSummaries.find(
          (item) => item.summary.artifact_version_id === artifactVersionId,
        );
        if (!entry) {
          // Mirrors the PaperSummary API backend: an unknown version id is a
          // generic ARTIFACT_VERSION_NOT_FOUND, never an "empty source" state.
          throw new NotFoundError(
            `Paper summary ${artifactVersionId} not found`,
            "ARTIFACT_VERSION_NOT_FOUND",
          );
        }
        const bound = paperCandidateBindings.get(entry.summary.paper.paper_id);
        if (bound) {
          return { researchInputId: bound, documentKind: "pdf" };
        }
        if (artifactVersionId === "artv_papsum_01") {
          return {
            researchInputId: seededResearchInputId,
            documentKind: "pdf",
          };
        }
        return { researchInputId: null, documentKind: null };
      },
      export: async (artifactVersionId, format) => {
        const summary = await (async () => {
          const entry = bundle.data.paperSummaries.find(
            (item) => item.summary.artifact_version_id === artifactVersionId,
          );
          if (!entry) {
            throw new NotFoundError(
              `Paper summary ${artifactVersionId} not found`,
              "ARTIFACT_VERSION_NOT_FOUND",
            );
          }
          return entry.summary;
        })();
        const markdown = `# ${summary.paper.title}\n\nDemo Replay 论文摘要。\n`;
        const bytes = new TextEncoder().encode(
          format === "markdown" ? markdown : JSON.stringify(summary),
        );
        return {
          bytes: bytes.buffer,
          fileName: `paper-summary-${artifactVersionId}.${format === "markdown" ? "md" : "json"}`,
          mediaType:
            format === "markdown"
              ? "text/markdown; charset=utf-8"
              : "application/json",
        };
      },
    },
    dataArtifacts: createFixtureDataArtifactRepository([
      ...(bundle.data.dataArtifactReads ?? []),
      ...(bundle.data.fieldDictionaryArtifactReads ?? []),
      ...(bundle.data.sourceCollectionArtifactReads ?? []),
    ]),
    literatureArtifacts: createFixtureLiteratureArtifactRepository(
      bundle.data.literatureClaimReads ?? [],
      bundle.data.literatureRelationReads ?? [],
      Object.fromEntries(
        Object.entries(bundle.data.artifactPresentations).map(
          ([versionId, presentation]) => [
            versionId,
            mapPublicArtifactPresentation(presentation),
          ],
        ),
      ),
    ),
    graphArtifacts: createFixtureGraphArtifactRepository(
      bundle.data.graphArtifactReads ?? [],
      bundle.data.graphNodeReads ?? [],
      bundle.data.graphEdgeReads ?? [],
    ),
    scientificArtifacts: {
      getReview: async (artifactVersionId) => {
        const read = (bundle.data.scientificArtifactReads ?? []).find(
          (item) => item.artifact_version_id === artifactVersionId,
        );
        if (!read) {
          throw new NotFoundError(
            `Scientific artifact ${artifactVersionId} is not available in the fixture`,
            "SCIENTIFIC_ARTIFACT_NOT_FOUND",
          );
        }
        return mapScientificArtifactRead(read);
      },
      getContent: async (artifactVersionId, contentHash) => {
        const read = (bundle.data.scientificArtifactReads ?? []).find(
          (item) => item.artifact_version_id === artifactVersionId,
        );
        if (!read) {
          throw new NotFoundError(
            `Scientific content for ${artifactVersionId} is not available in the fixture`,
            "SCIENTIFIC_ARTIFACT_NOT_FOUND",
          );
        }
        const bytes = scientificBinaryStore.get(contentHash);
        if (!bytes) {
          throw new NotFoundError(
            `No immutable fixture binary registered for ${artifactVersionId}:${contentHash}`,
            "SCIENTIFIC_CONTENT_NOT_FOUND",
          );
        }
        return bytes;
      },
    },
    artifactExports: fixtureArtifactExports,
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
        if (shareId) {
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
        }

        if (
          shareToken === "token_fixture_dataset" &&
          bundle.data.projects[0] &&
          versions.get(asEntityId("artv_dataset_01"))
        ) {
          const defaultProjectId = asEntityId(bundle.data.projects[0].id);
          try {
            const defaultPublicVersions = [
              toPublicVersion(defaultProjectId, asEntityId("artv_dataset_01")),
            ];
            const defaultPublicEvidence = [
              toPublicEvidence(
                defaultProjectId,
                new Set([asEntityId("artv_dataset_01")]),
                asEntityId("evd_01"),
              ),
            ];
            return {
              id: asEntityId("share_fixture_dataset"),
              title: "系外行星宿主星研究结果公开分享",
              redactionPolicy: "redacted_public_snapshot",
              createdAt: bundle.generatedAt,
              expiresAt: "2030-01-01T00:00:00Z",
              artifactVersions: defaultPublicVersions,
              evidence: defaultPublicEvidence,
            };
          } catch {
            return null;
          }
        }
        return null;
      },
      downloadPublicDatasetCsv: async (shareToken, artifactVersionId) => {
        let version: PublicArtifactVersion | undefined;
        const shareId = shareByToken.get(shareToken);
        if (shareId) {
          const record = shares.get(shareId);
          if (
            !record ||
            shareStatus(record.snapshot, clock()).status !== "active"
          ) {
            throw new NotFoundError(
              "Public share unavailable",
              "SHARE_NOT_FOUND",
            );
          }
          version = record.artifactVersions.find(
            (candidate) => candidate.id === artifactVersionId,
          );
        } else if (
          shareToken === "token_fixture_dataset" &&
          bundle.data.projects[0] &&
          artifactVersionId === "artv_dataset_01"
        ) {
          version = toPublicVersion(
            asEntityId(bundle.data.projects[0].id),
            asEntityId("artv_dataset_01"),
          );
        }
        if (!version || version.kind !== "dataset") {
          throw new NotFoundError(
            "Public share unavailable",
            "SHARE_NOT_FOUND",
          );
        }
        const exportRecord = await fixtureArtifactExports.create(
          artifactVersionId,
          "csv",
        );
        return fixtureArtifactExports.download(exportRecord);
      },
    },
    revisions: createFixtureRevisionRepository(),
    modelProvider: {
      getConfiguration: async () => fixtureModelProvider,
      configure: async () => fixtureModelProvider,
      removeConfiguration: async () => fixtureModelProvider,
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

const FITS_BLOCK = 2880;

function fitsCard(keyword: string, value: string): string {
  return `${keyword.padEnd(8)}= ${value.padStart(20)} `.padEnd(80);
}

/** Minimal but structurally valid FITS image: padded header + BITPIX=16 data. */
function buildFitsBytes(seed: string): ArrayBuffer {
  const width = 64;
  const height = 64;
  const cards = [
    fitsCard("SIMPLE", "T"),
    fitsCard("BITPIX", "16"),
    fitsCard("NAXIS", "2"),
    fitsCard("NAXIS1", String(width)),
    fitsCard("NAXIS2", String(height)),
    fitsCard("CTYPE1", "'RA---TAN'"),
    fitsCard("CTYPE2", "'DEC--TAN'"),
    fitsCard("CRVAL1", "186.615"),
    fitsCard("CRVAL2", "-51.365"),
    fitsCard("CRPIX1", "32.5"),
    fitsCard("CRPIX2", "32.5"),
    fitsCard("CDELT1", "-0.001"),
    fitsCard("CDELT2", "0.001"),
    fitsCard("RADESYS", "'ICRS'"),
    fitsCard("ORIGIN", "'xingwen-fixture'"),
    fitsCard("OBJECT", `'${seed.slice(0, 16)}'`),
    "END".padEnd(80),
  ];
  let header = cards.join("");
  header = header.padEnd(Math.ceil(header.length / FITS_BLOCK) * FITS_BLOCK);

  const dataBytes = width * height * 2;
  const dataPadded = Math.ceil(dataBytes / FITS_BLOCK) * FITS_BLOCK;
  const buffer = new ArrayBuffer(header.length + dataPadded);
  const view = new DataView(buffer);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < header.length; i++) bytes[i] = header.charCodeAt(i);

  let offset = header.length;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const radial = Math.sqrt((x - 32) ** 2 + (y - 32) ** 2);
      const value = Math.max(
        0,
        Math.min(32767, Math.round(4000 * Math.exp(-radial / 9))),
      );
      view.setInt16(offset, value, false);
      offset += 2;
    }
  }
  return buffer;
}

function buildCsvBytes(seed: string): ArrayBuffer {
  const lines = ["ra,dec,phot_g_mean_mag"];
  for (let i = 0; i < 40; i++) {
    const ra = (71.855 + Math.sin(i * 12.9898 + seed.length) * 0.25).toFixed(5);
    const dec = (-17.251 + Math.cos(i * 78.233 + seed.length) * 0.25).toFixed(
      5,
    );
    const mag = (8 + ((i * 37) % 60) / 10).toFixed(2);
    lines.push(`${ra},${dec},${mag}`);
  }
  return new TextEncoder().encode(`${lines.join("\r\n")}\r\n`).buffer;
}

interface ScientificBinarySpecLike {
  readonly mode?: string;
  readonly content_hash?: string;
  readonly fits_layers?: readonly { readonly content_hash: string }[];
  readonly table_layers?: readonly { readonly content_hash: string }[];
}

function buildScientificBinaryStore(
  reads: readonly unknown[],
): Map<string, ArrayBuffer> {
  const store = new Map<string, ArrayBuffer>();
  for (const item of reads) {
    const read = item as { readonly content?: { readonly spec?: unknown } };
    const spec = read.content?.spec as ScientificBinarySpecLike | undefined;
    if (!spec) continue;
    if (spec.mode === "fits_image" && spec.content_hash) {
      store.set(spec.content_hash, buildFitsBytes(spec.content_hash));
    }
    if (spec.mode === "wwt_scene") {
      for (const layer of spec.fits_layers ?? []) {
        store.set(layer.content_hash, buildFitsBytes(layer.content_hash));
      }
      for (const layer of spec.table_layers ?? []) {
        store.set(layer.content_hash, buildCsvBytes(layer.content_hash));
      }
    }
  }
  return store;
}
