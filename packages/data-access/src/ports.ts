/**
 * Repository Port interfaces.
 *
 * These ports define the read/write boundary between the frontend application
 * layer and data sources. Both the Demo Replay fixture adapter
 * (`createFixtureRepositories`) and the live HTTP adapter
 * (`createHttpRepositories`) implement them. Ports operate exclusively on
 * domain types — transport DTOs never leak through to consumers.
 *
 * The surface is intentionally narrowed to the operations the current UI and
 * the `/api` contract actually support. Each method maps to a real endpoint
 * (or its fixture equivalent) so an abstraction always has two concrete
 * adapters.
 */

import type {
  ArtifactVersionMetadata,
  CaseKey,
  CreateShareSnapshotRequest,
  DomainEntityId,
  Evidence,
  ExecutionMode,
  PaperAcquisitionReview,
  PaperSummaryReview,
  PublicShareSnapshot,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchContractInput,
  ResearchProject,
  ResearchPlanningCatalog,
  ResearchRun,
  ResearchThreadEntry,
  ResearchTurn,
  RunStepSnapshot,
  RunEvent,
  ShareSnapshot,
  ShareSnapshotCreated,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";

/** Fields a client may change on an editable draft (PATCH is partial). */
export interface UpdateResearchContractDraftInput {
  readonly intent?: string;
  readonly contract?: ResearchContractInput;
}

/** Minimal project creation payload; `case_key` stays the frozen main case. */
export interface CreateResearchProjectInput {
  readonly name: string;
  readonly description?: string;
  readonly caseKey: CaseKey;
  /** Stable per user action; reuse only when retrying that same action. */
  readonly idempotencyKey: string;
}

export interface UpdateResearchProjectInput {
  readonly name: string;
}

/** Payload for creating an editable draft bound to a session-owned project. */
export interface CreateResearchContractDraftInput {
  readonly intent: string;
  readonly contract: ResearchContractInput;
  /** Stable per user action; reuse only when retrying that same action. */
  readonly idempotencyKey: string;
}

/** A single page of a session-scoped project listing. */
export interface ResearchProjectPage {
  readonly items: readonly ResearchProject[];
  /** Cursor to resume listing, or null when the collection is fully drained. */
  readonly nextCursor: string | null;
}

export interface SubmitResearchTurnInput {
  readonly message: string;
  readonly answerToQuestionId: DomainEntityId | null;
  readonly idempotencyKey: string;
}

export interface ResearchThreadPage {
  readonly items: readonly ResearchThreadEntry[];
  readonly nextCursor: string | null;
}

/** Parameters for creating a ResearchRun (`execution_mode` lives on the Run). */
export interface CreateResearchRunInput {
  readonly projectId: DomainEntityId;
  readonly contractId: DomainEntityId;
  /** Stable per user action; reuse only when retrying that same action. */
  readonly idempotencyKey: string;
  readonly executionMode: ExecutionMode;
}

/** Snapshot-first RunEvent recovery result, capped to the authoritative tail. */
export interface RunEventRecovery {
  /** Events with `sequence <= latestSequence` only (authoritative tail). */
  readonly events: readonly RunEvent[];
  /** Cursor to resume incremental polling, or null when fully drained. */
  readonly nextCursor: string | null;
  /** The authoritative `latest_event_sequence` from the Run snapshot. */
  readonly latestSequence: number;
}

export interface ProjectRepository {
  getById(id: DomainEntityId): Promise<ResearchProject | null>;
  /** Session-scoped listing in a stable order; follows `cursor` when supplied. */
  list(cursor?: string | null): Promise<ResearchProjectPage>;
  create(input: CreateResearchProjectInput): Promise<ResearchProject>;
  update(
    id: DomainEntityId,
    input: UpdateResearchProjectInput,
    expectedRevision: number,
  ): Promise<ResearchProject>;
  delete(id: DomainEntityId, expectedRevision: number): Promise<void>;
}

export interface ResearchThreadRepository {
  list(
    projectId: DomainEntityId,
    cursor?: string | null,
  ): Promise<ResearchThreadPage>;
  submit(
    projectId: DomainEntityId,
    input: SubmitResearchTurnInput,
  ): Promise<ResearchTurn>;
}

export interface ResearchCatalogRepository {
  getForProject(projectId: DomainEntityId): Promise<ResearchPlanningCatalog>;
}

export interface ContractRepository {
  createDraft(
    projectId: DomainEntityId,
    input: CreateResearchContractDraftInput,
  ): Promise<ResearchContractDraft>;
  getDraftById(id: DomainEntityId): Promise<ResearchContractDraft | null>;
  updateDraft(
    draftId: DomainEntityId,
    expectedVersion: number,
    input: UpdateResearchContractDraftInput,
  ): Promise<ResearchContractDraft>;
  confirm(
    projectId: DomainEntityId,
    draftId: DomainEntityId,
    expectedDraftVersion: number,
  ): Promise<ResearchContract>;
  getContractById(id: DomainEntityId): Promise<ResearchContract | null>;
}

export interface RunRepository {
  getById(id: DomainEntityId): Promise<ResearchRun | null>;
  create(input: CreateResearchRunInput): Promise<ResearchRun>;
  /** All events for a run in ascending sequence order (aggregates pages). */
  listEvents(runId: DomainEntityId): Promise<readonly RunEvent[]>;
  /**
   * Snapshot-first recovery after an interrupted stream: reads the Run
   * snapshot's authoritative `latest_event_sequence` and returns only events
   * up to it, resuming from `fromCursor` when supplied.
   */
  recoverEvents(
    runId: DomainEntityId,
    fromCursor?: string | null,
  ): Promise<RunEventRecovery>;
  listSteps(runId: DomainEntityId): Promise<readonly RunStepSnapshot[]>;
}

export interface ArtifactReadRepository {
  listByRun(runId: DomainEntityId): Promise<readonly ResearchArtifact[]>;
  getArtifact(id: DomainEntityId): Promise<ResearchArtifact | null>;
  /**
   * Generic version read narrowed to identity + provenance metadata. Rich
   * kind-specific content (e.g. PaperCollection) is only readable through its
   * dedicated repository so it never passes through a loose content cast.
   */
  getVersion(id: DomainEntityId): Promise<ArtifactVersionMetadata | null>;
  getEvidence(id: DomainEntityId): Promise<Evidence | null>;
}

/**
 * Deep read boundary for the PaperCollection API paper acquisition review (Paper Acquisition Workspace).
 *
 * `getReview` hides the entire transport protocol: it reads the collection
 * read model, follows every candidate page by cursor, validates each payload
 * against the generated contract, guards against cursor loops / duplicate or
 * reordered candidates / count drift, and returns one complete domain object
 * in the authoritative server ranking order. Callers never see URLs, DTOs,
 * cursors, envelopes or page sizes. Failures surface as typed errors
 * (NotFound/RateLimited/Upstream/Validation/Network), never as `null`.
 */
export interface PaperAcquisitionRepository {
  getReview(artifactVersionId: DomainEntityId): Promise<PaperAcquisitionReview>;
}

/**
 * Deep read boundary for the PaperSummary API paper summary review (Literature Summary Workspace).
 *
 * `getSummary` hides the entire transport protocol: it reads the summary
 * read model, validates the payload against the generated contract, and
 * returns one complete domain object with server-validated support statuses.
 * Callers never see URLs, DTOs or envelopes. Failures surface as typed
 * errors (NotFound/RateLimited/Upstream/Validation/Network), never as `null`.
 */
export interface PaperSummaryRepository {
  getSummary(artifactVersionId: DomainEntityId): Promise<PaperSummaryReview>;
}

export interface WorkspaceSnapshotRepository {
  getByProjectId(projectId: DomainEntityId): Promise<WorkspaceSnapshot | null>;
  save(
    projectId: DomainEntityId,
    snapshot: WorkspaceSnapshotInput,
    expectedRevision: number,
  ): Promise<WorkspaceSnapshot>;
}

export interface ShareRepository {
  list(projectId: DomainEntityId): Promise<readonly ShareSnapshot[]>;
  create(
    projectId: DomainEntityId,
    request: CreateShareSnapshotRequest,
  ): Promise<ShareSnapshotCreated>;
  revoke(projectId: DomainEntityId, shareId: DomainEntityId): Promise<void>;
  getPublic(shareToken: string): Promise<PublicShareSnapshot | null>;
}

/**
 * The complete set of repository ports a workspace consumes. Both adapters
 * produce a ready-to-use `RepositorySet`; Evidence reads live on the artifact
 * read port (`getEvidence`) rather than a separate repository.
 */
export interface RepositorySet {
  readonly projects: ProjectRepository;
  readonly researchCatalog: ResearchCatalogRepository;
  readonly researchThread: ResearchThreadRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly artifacts: ArtifactReadRepository;
  readonly paperAcquisition: PaperAcquisitionRepository;
  readonly paperSummary: PaperSummaryRepository;
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
}

/**
 * Provenance summary for a data source. Only the fixture adapter reports a
 * transport-level provenance (`demo_replay` / `fixture`); the HTTP adapter does
 * not fabricate one because the transport does not determine a Run's
 * `execution_mode` or an ArtifactVersion's `source_mode` — those are read from
 * the domain objects themselves.
 */
export interface RepositoryProvenance {
  readonly state: import("@xingwen/domain").ProvenanceState;
}
