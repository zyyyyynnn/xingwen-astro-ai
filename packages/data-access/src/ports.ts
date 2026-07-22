/**
 * Repository Port interfaces.
 *
 * These ports define the read, write and subscription boundary between the
 * frontend application layer and data sources. The fixture adapter
 * (`createFixtureRepositories`) and, later, the HTTP adapter (A-15) implement
 * these interfaces.
 *
 * All methods are asynchronous so the HTTP adapter can swap in without changing
 * call sites. Ports operate exclusively on domain types — transport DTOs never
 * leak through to consumers.
 */

import type {
  ArtifactVersion,
  DomainEntityId,
  Evidence,
  ProvenanceState,
  PublicShareSnapshot,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  RunEvent,
  ShareSnapshot,
  ShareSnapshotCreated,
  CreateShareSnapshotRequest,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
} from "@xingwen/domain";

/** Subscription cleanup function returned by `subscribe` methods. */
export type Unsubscribe = () => void;

/** Listener invoked when a repository's collection changes. */
export type Listener<T> = (entities: readonly T[]) => void;

export interface ProjectRepository {
  getById(id: DomainEntityId): Promise<ResearchProject | null>;
  list(): Promise<readonly ResearchProject[]>;
  save(project: ResearchProject): Promise<void>;
  subscribe(listener: Listener<ResearchProject>): Unsubscribe;
}

export interface ContractRepository {
  getDraftById(id: DomainEntityId): Promise<ResearchContractDraft | null>;
  listDrafts(): Promise<readonly ResearchContractDraft[]>;
  saveDraft(draft: ResearchContractDraft): Promise<void>;
  confirm(
    projectId: DomainEntityId,
    draftId: DomainEntityId,
    expectedDraftVersion: number,
  ): Promise<ResearchContract>;
  getContractById(id: DomainEntityId): Promise<ResearchContract | null>;
  listContracts(
    projectId: DomainEntityId,
  ): Promise<readonly ResearchContract[]>;
  subscribe(listener: Listener<ResearchContract>): Unsubscribe;
}

export interface RunRepository {
  getById(id: DomainEntityId): Promise<ResearchRun | null>;
  listByProject(projectId: DomainEntityId): Promise<readonly ResearchRun[]>;
  save(run: ResearchRun): Promise<void>;
  getEvents(runId: DomainEntityId): Promise<readonly RunEvent[]>;
  appendEvent(event: RunEvent): Promise<void>;
  subscribe(listener: Listener<ResearchRun>): Unsubscribe;
}

export interface ArtifactRepository {
  getArtifactById(id: DomainEntityId): Promise<ResearchArtifact | null>;
  listByProject(
    projectId: DomainEntityId,
  ): Promise<readonly ResearchArtifact[]>;
  getVersionById(id: DomainEntityId): Promise<ArtifactVersion | null>;
  listVersions(artifactId: DomainEntityId): Promise<readonly ArtifactVersion[]>;
  saveVersion(version: ArtifactVersion): Promise<void>;
  subscribe(listener: Listener<ResearchArtifact>): Unsubscribe;
}

export interface EvidenceRepository {
  getById(id: DomainEntityId): Promise<Evidence | null>;
  listByArtifactVersion(
    artifactVersionId: DomainEntityId,
  ): Promise<readonly Evidence[]>;
  save(evidence: Evidence): Promise<void>;
  subscribe(listener: Listener<Evidence>): Unsubscribe;
}

export interface WorkspaceSnapshotRepository {
  getById(id: DomainEntityId): Promise<WorkspaceSnapshot | null>;
  save(
    id: DomainEntityId,
    snapshot: WorkspaceSnapshotInput,
    expectedRevision: number,
  ): Promise<WorkspaceSnapshot>;
}

export interface ShareRepository {
  create(request: CreateShareSnapshotRequest): Promise<ShareSnapshotCreated>;
  getById(id: DomainEntityId): Promise<ShareSnapshot | null>;
  listByProject(projectId: DomainEntityId): Promise<readonly ShareSnapshot[]>;
  revoke(id: DomainEntityId): Promise<void>;
  getPublicShare(shareToken: string): Promise<PublicShareSnapshot | null>;
}

/**
 * The complete set of repository ports a workspace consumes.
 * The fixture adapter produces a ready-to-use `RepositorySet`.
 */
export interface RepositorySet {
  readonly projects: ProjectRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly artifacts: ArtifactRepository;
  readonly evidence: EvidenceRepository;
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
}

/**
 * Provenance summary for the active data source. The fixture adapter reports
 * `executionMode: "demo_replay"` and `sourceMode: "fixture"`; the HTTP adapter
 * (A-15) will report live provenance.
 */
export interface RepositoryProvenance {
  readonly state: ProvenanceState;
}
