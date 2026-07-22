/**
 * HTTP adapter — the live `/api/v2` RepositorySet implementation.
 *
 * Implements the same `RepositorySet` ports as the fixture adapter, but every
 * read/write is an HTTP call against `/api/v2`. DTOs returned by the server
 * are validated with `parseV2Dto` and mapped into the domain model via the
 * shared `mapping.ts` (reused from the fixture adapter so Fixture/HTTP
 * consistency is guaranteed by construction).
 *
 * Endpoints covered:
 * - Generated Contract (10 operationIds): getArtifactVersion, getResearchArtifact,
 *   getResearchProject, confirmResearchContract, createResearchRun,
 *   listShareSnapshots, createShareSnapshot, revokeShareSnapshot,
 *   getWorkspaceSnapshot, putWorkspaceSnapshot.
 * - API_CONTRACT.md-defined but not yet generated: ContractDraft create/update,
 *   Project list/create, Contract list, Run list, RunEvents, Evidence read.
 *
 * The fetch implementation is injectable so tests can use MSW and Node
 * environments can use undici/global fetch.
 */

import {
  parseV2Dto,
  type ConfirmResearchContractRequest,
  type UpdateResearchContractDraftRequest,
  type V2CoreModelName,
} from "@xingwen/contracts";
import type {
  ArtifactVersion,
  DomainEntityId,
  Evidence,
  ResearchArtifact,
  ResearchContract,
  ResearchContractDraft,
  ResearchProject,
  ResearchRun,
  RunEvent,
  WorkspaceSnapshot,
  WorkspaceSnapshotInput,
  ShareSnapshot,
  ShareSnapshotCreated,
  CreateShareSnapshotRequest,
  PublicShareSnapshot,
} from "@xingwen/domain";

import {
  mapArtifactVersion,
  mapDomainContractInputToDto,
  mapResearchArtifact,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchRun,
  mapRunEvent,
  mapWorkspaceSnapshot,
  mapWorkspaceSnapshotInputToDto,
  mapShareSnapshot,
  mapCreateShareSnapshotRequestToDto,
  mapPublicShareSnapshot,
} from "./mapping";
import { CapabilityUnavailableError } from "./errors";
import {
  mapProblemDetails,
  NetworkError,
  NotFoundError,
  SessionExpiredError,
  UnexpectedHttpError,
  type ProblemDetails,
} from "./http-errors";
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
import type { SessionManager } from "./session";

/** Common envelope for single-resource responses (API_CONTRACT.md §4). */
interface Envelope<T> {
  readonly data: T;
  readonly meta?: {
    readonly request_id?: string;
    readonly schema_version?: string;
    readonly generated_at?: string;
  };
  readonly links?: { readonly self?: string };
}

/** Envelope for collection responses with pagination. */
interface CollectionEnvelope<T> {
  readonly data: readonly T[];
  readonly meta?: {
    readonly request_id?: string;
    readonly schema_version?: string;
    readonly generated_at?: string;
  };
  readonly page?: {
    readonly next_cursor?: string | null;
    readonly has_more?: boolean;
    readonly limit?: number;
  };
}

export interface HttpAdapterConfig {
  /** Base URL without trailing slash, e.g. `http://127.0.0.1:8000`. */
  readonly baseUrl: string;
  /** Inject fetch implementation (defaults to global fetch). */
  readonly fetchImpl?: typeof fetch;
  /** Session manager for CSRF and session-expired handling. */
  readonly session: SessionManager;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** In-memory subscriber registry shared by all HTTP repositories. */
class HttpSubscribers<T> {
  private readonly listeners = new Set<Listener<T>>();
  subscribe(listener: Listener<T>): Unsubscribe {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }
  notify(entities: readonly T[]): void {
    for (const listener of this.listeners) {
      listener(entities);
    }
  }
}

/** Internal HTTP client wrapping fetch with envelope parsing and error mapping. */
class HttpClient {
  private readonly fetchImpl: typeof fetch;

  constructor(private readonly config: HttpAdapterConfig) {
    this.fetchImpl = config.fetchImpl ?? globalThis.fetch;
  }

  private buildUrl(path: string): string {
    return `${this.config.baseUrl}${path}`;
  }

  private prepareHeaders(method: string, extra?: HeadersInit): Headers {
    const headers = new Headers(extra);
    if (method.toUpperCase() !== "GET") {
      headers.set("Content-Type", "application/json");
    }
    if (!SAFE_METHODS.has(method.toUpperCase())) {
      this.config.session.attachCsrf(headers);
    }
    return headers;
  }

  /** Single GET; returns parsed `data` or null on 404. */
  async get<T>(path: string): Promise<T | null> {
    try {
      const env = await this.request<Envelope<T>>("GET", path);
      return env ? env.data : null;
    } catch (err) {
      if (err instanceof NotFoundError) return null;
      throw err;
    }
  }

  /** Collection GET following cursor pagination; aggregates all pages. */
  async list<T>(path: string): Promise<readonly T[]> {
    const aggregated: T[] = [];
    let cursor: string | null = null;
    let url = path;
    do {
      if (cursor) {
        const sep = url.includes("?") ? "&" : "?";
        url = `${url}${sep}cursor=${encodeURIComponent(cursor)}`;
      }
      try {
        const env = await this.request<CollectionEnvelope<T>>("GET", url);
        if (!env) break;
        aggregated.push(...env.data);
        cursor = env.page?.next_cursor ?? null;
        if (!env.page?.has_more) break;
      } catch (err) {
        if (err instanceof NotFoundError) break;
        throw err;
      }
    } while (cursor);
    return aggregated;
  }

  /**
   * Single-page collection GET; returns the raw page envelope without
   * following `next_cursor`. Used by callers that poll incrementally
   * (e.g. RunEvent tailing). 404 is surfaced as `null` so the caller can
   * decide whether to treat it as an empty page.
   */
  async listPage<T>(path: string): Promise<CollectionEnvelope<T> | null> {
    try {
      return await this.request<CollectionEnvelope<T>>("GET", path);
    } catch (err) {
      if (err instanceof NotFoundError) return null;
      throw err;
    }
  }

  /** POST creating a resource; returns parsed `data`. */
  async post<T>(path: string, body: unknown): Promise<T> {
    const env = await this.request<Envelope<T>>("POST", path, body);
    if (!env) {
      throw new UnexpectedHttpError("Empty response body on POST", 200, null);
    }
    return env.data;
  }

  /** PATCH updating a resource; returns parsed `data` or null on 204. */
  async patch<T>(path: string, body: unknown): Promise<T | null> {
    const env = await this.request<Envelope<T>>("PATCH", path, body);
    return env ? env.data : null;
  }

  /** PUT; returns parsed `data` or null on 204. */
  async put<T>(
    path: string,
    body: unknown,
    headers?: HeadersInit,
  ): Promise<T | null> {
    const env = await this.request<Envelope<T>>("PUT", path, body, headers);
    return env ? env.data : null;
  }

  /** DELETE; returns true on 204 or 404 (idempotent). */
  async delete(path: string): Promise<boolean> {
    const response = await this.rawRequest("DELETE", path);
    if (response.status === 204 || response.status === 404) return true;
    if (!response.ok) {
      await this.throwFromResponse(response);
    }
    return true;
  }

  /** Raw request returning the Response, after session-expired detection. */
  private async rawRequest(
    method: string,
    path: string,
    body?: unknown,
    extraHeaders?: HeadersInit,
  ): Promise<Response> {
    const headers = this.prepareHeaders(method, extraHeaders);
    let response: Response;
    try {
      response = await this.fetchImpl(this.buildUrl(path), {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
        credentials: "include",
      });
    } catch (err) {
      throw new NetworkError(
        err instanceof Error ? err.message : "Network request failed",
        err,
      );
    }
    if (response.status === 401) {
      this.config.session.notifyExpired();
      const problem = await this.safeParseProblem(response);
      throw new SessionExpiredError(
        problem?.detail ?? "Session required or expired",
      );
    }
    return response;
  }

  /** Request with envelope parsing and non-2xx error mapping. */
  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    headers?: HeadersInit,
  ): Promise<T | null> {
    const response = await this.rawRequest(method, path, body, headers);
    if (response.status === 204) return null;
    if (response.status === 404) {
      // 404 is a valid "not found" outcome for single-resource GETs.
      const problem = await this.safeParseProblem(response);
      throw new NotFoundError(
        problem?.detail ?? "Resource not found",
        problem?.code ?? "NOT_FOUND",
      );
    }
    if (!response.ok) {
      await this.throwFromResponse(response);
    }
    const text = await response.text();
    if (!text) return null;
    return JSON.parse(text) as T;
  }

  private async safeParseProblem(
    response: Response,
  ): Promise<ProblemDetails | null> {
    try {
      const text = await response.clone().text();
      if (!text) return null;
      return JSON.parse(text) as ProblemDetails;
    } catch {
      return null;
    }
  }

  private async throwFromResponse(response: Response): Promise<never> {
    const problem = await this.safeParseProblem(response);
    const filled: ProblemDetails = {
      ...problem,
      status: problem?.status ?? response.status,
      detail: problem?.detail ?? problem?.title ?? response.statusText,
    };
    throw mapProblemDetails(filled, response.headers);
  }
}

/** Validate and map a DTO through the shared mapping layer. */
function validateAndMap<TDto, TDomain>(
  model: V2CoreModelName,
  payload: unknown,
  map: (dto: TDto) => TDomain,
): TDomain {
  const dto = parseV2Dto<TDto>(model, payload);
  return map(dto);
}

/** Single page of RunEvents with pagination metadata for incremental polling. */
export interface RunEventPage {
  readonly events: readonly RunEvent[];
  readonly nextCursor: string | null;
  readonly hasMore: boolean;
}

/**
 * HTTP-specific Run repository extension.
 *
 * Adds incremental event reading (cursor-based polling) and snapshot-first
 * recovery: when the event stream is interrupted, the caller re-GETs the Run
 * snapshot (which carries `latest_event_sequence`) and resumes polling from
 * the last known sequence. The snapshot is the authoritative state; the event
 * stream is a derivative tail.
 */
export interface HttpRunRepository extends RunRepository {
  /**
   * Fetch a single page of RunEvents starting at `cursor` (or the beginning).
   * Used for cursor-based polling without aggregating all pages at once.
   */
  listEventsPage(
    runId: DomainEntityId,
    cursor?: string | null,
    limit?: number,
  ): Promise<RunEventPage>;
  /**
   * Get the `latest_event_sequence` from the authoritative Run snapshot.
   * Used as the recovery anchor when the event stream is interrupted.
   */
  getLatestEventSequence(runId: DomainEntityId): Promise<number>;
  /**
   * Snapshot-first recovery: fetch the Run snapshot to learn the authoritative
   * `latest_event_sequence`, then drain the event stream page by page from
   * `fromCursor` (or the beginning) until the events caught up to the
   * snapshot's sequence. Returns the aggregated events and the next cursor
   * to use for subsequent polling.
   */
  recoverEventsFromSnapshot(
    runId: DomainEntityId,
    fromCursor?: string | null,
  ): Promise<RunEventPage & { readonly latestSequence: number }>;
}

export interface HttpRepositorySet {
  readonly projects: ProjectRepository;
  readonly contracts: ContractRepository;
  readonly runs: HttpRunRepository;
  readonly artifacts: ArtifactRepository;
  readonly evidence: EvidenceRepository;
  readonly workspaces: WorkspaceSnapshotRepository;
  readonly shares: ShareRepository;
  readonly provenance: RepositoryProvenance;
}

/**
 * Create a `RepositorySet` backed by real `/api/v2` endpoints.
 *
 * Reads issue GETs and map DTOs via the shared `mapping.ts`. Writes issue
 * POST/PATCH/PUT/DELETE with CSRF attached. 401 responses trigger the session
 * manager's expired notification.
 */
export function createHttpRepositories(
  config: HttpAdapterConfig,
): HttpRepositorySet {
  const http = new HttpClient(config);
  const projectSubs = new HttpSubscribers<ResearchProject>();
  const contractSubs = new HttpSubscribers<ResearchContract>();
  const runSubs = new HttpSubscribers<ResearchRun>();
  const artifactSubs = new HttpSubscribers<ResearchArtifact>();
  const evidenceSubs = new HttpSubscribers<Evidence>();

  const projects: ProjectRepository = {
    async getById(id: DomainEntityId): Promise<ResearchProject | null> {
      const payload = await http.get<unknown>(
        `/api/v2/projects/${encodeURIComponent(id)}`,
      );
      if (!payload) return null;
      return validateAndMap("ResearchProject", payload, mapResearchProject);
    },
    async list(): Promise<readonly ResearchProject[]> {
      throw new CapabilityUnavailableError(
        "projects.list",
        "OpenAPI does not define a project list endpoint",
      );
    },
    async save(project: ResearchProject): Promise<void> {
      void project;
      throw new CapabilityUnavailableError(
        "projects.save",
        "OpenAPI does not define a project save/update endpoint",
      );
    },
    subscribe(listener: Listener<ResearchProject>): Unsubscribe {
      return projectSubs.subscribe(listener);
    },
  };

  const contracts: ContractRepository = {
    async getDraftById(
      id: DomainEntityId,
    ): Promise<ResearchContractDraft | null> {
      const payload = await http.get<unknown>(
        `/api/v2/research-contract-drafts/${encodeURIComponent(id)}`,
      );
      if (!payload) return null;
      return validateAndMap(
        "ResearchContractDraft",
        payload,
        mapResearchContractDraft,
      );
    },
    async listDrafts(): Promise<readonly ResearchContractDraft[]> {
      throw new CapabilityUnavailableError(
        "contracts.listDrafts",
        "OpenAPI does not define a contract drafts list endpoint",
      );
    },
    async saveDraft(draft: ResearchContractDraft): Promise<void> {
      const body: UpdateResearchContractDraftRequest = {
        contract: mapDomainContractInputToDto(draft.contract),
        intent: draft.intent,
      };
      await http.patch<unknown>(
        `/api/v2/research-contract-drafts/${encodeURIComponent(draft.id)}`,
        body,
      );
    },
    async getContractById(
      contractId: DomainEntityId,
    ): Promise<ResearchContract | null> {
      const payload = await http.get<unknown>(
        `/api/v2/research-contracts/${encodeURIComponent(contractId)}`,
      );
      if (!payload) return null;
      return validateAndMap("ResearchContract", payload, mapResearchContract);
    },
    async listContracts(
      projectId: DomainEntityId,
    ): Promise<readonly ResearchContract[]> {
      void projectId;
      throw new CapabilityUnavailableError(
        "contracts.listContracts",
        "OpenAPI does not define a contract list endpoint",
      );
    },
    async confirm(
      projectId: DomainEntityId,
      draftId: DomainEntityId,
      expectedDraftVersion: number,
    ): Promise<ResearchContract> {
      const body: ConfirmResearchContractRequest = {
        draft_id: draftId,
        expected_draft_version: expectedDraftVersion,
      };
      const payload = await http.post<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/contracts`,
        body,
      );
      if (!payload) {
        throw new UnexpectedHttpError(
          "Confirm endpoint returned no payload",
          200,
          null,
        );
      }
      return validateAndMap("ResearchContract", payload, mapResearchContract);
    },
    subscribe(listener: Listener<ResearchContract>): Unsubscribe {
      return contractSubs.subscribe(listener);
    },
  };

  const runs: HttpRunRepository = {
    async getById(id: DomainEntityId): Promise<ResearchRun | null> {
      const payload = await http.get<unknown>(
        `/api/v2/runs/${encodeURIComponent(id)}`,
      );
      if (!payload) return null;
      return validateAndMap("ResearchRun", payload, mapResearchRun);
    },
    async listByProject(
      projectId: DomainEntityId,
    ): Promise<readonly ResearchRun[]> {
      void projectId;
      throw new CapabilityUnavailableError(
        "runs.listByProject",
        "OpenAPI does not define a run list-by-project endpoint",
      );
    },
    async save(run: ResearchRun): Promise<void> {
      // Run creation uses POST /api/v2/projects/{project_id}/runs with
      // Idempotency-Key. This method is primarily for create; updates to
      // run status are server-driven.
      await http.post<unknown>(
        `/api/v2/projects/${encodeURIComponent(run.projectId)}/runs`,
        {
          contract_id: run.contractId,
          execution_mode: run.executionMode,
          parent_run_id: run.parentRunId,
          derivation_kind: run.derivationKind,
          retry_from_step: run.retryFromStep,
          cache_policy: run.cachePolicy,
        },
      );
    },
    async getEvents(runId: DomainEntityId): Promise<readonly RunEvent[]> {
      const payloads = await http.list<unknown>(
        `/api/v2/runs/${encodeURIComponent(runId)}/events`,
      );
      return payloads.map((p) => validateAndMap("RunEvent", p, mapRunEvent));
    },
    async listEventsPage(
      runId: DomainEntityId,
      cursor?: string | null,
      limit?: number,
    ): Promise<RunEventPage> {
      // Single-page fetch; does not follow next_cursor. Used by callers that
      // poll incrementally. 404 on the events endpoint is treated as an empty
      // page so a deleted-but-snapshotted run still returns gracefully.
      let path = `/api/v2/runs/${encodeURIComponent(runId)}/events`;
      const params: string[] = [];
      if (cursor) params.push(`cursor=${encodeURIComponent(cursor)}`);
      if (limit !== undefined) params.push(`limit=${String(limit)}`);
      if (params.length > 0) path = `${path}?${params.join("&")}`;
      const env = await http.listPage<unknown>(path);
      if (!env) {
        return { events: [], nextCursor: null, hasMore: false };
      }
      const events = env.data.map((p) =>
        validateAndMap("RunEvent", p, mapRunEvent),
      );
      return {
        events,
        nextCursor: env.page?.next_cursor ?? null,
        hasMore: env.page?.has_more ?? false,
      };
    },
    async getLatestEventSequence(runId: DomainEntityId): Promise<number> {
      // Snapshot-first recovery anchor: GET /api/v2/runs/{run_id} and read
      // the authoritative `latest_event_sequence`. The Run snapshot is the
      // source of truth; the event stream is a derivative tail.
      const payload = await http.get<{ latest_event_sequence?: number }>(
        `/api/v2/runs/${encodeURIComponent(runId)}`,
      );
      if (!payload) {
        throw new NotFoundError(
          "Run not found; cannot recover event sequence",
          "RUN_NOT_FOUND",
        );
      }
      // Validate the Run DTO (so we don't trust an unvalidated shape) and
      // read the field from the validated/mapped domain entity instead.
      const run = validateAndMap("ResearchRun", payload, mapResearchRun);
      return run.latestEventSequence;
    },
    async recoverEventsFromSnapshot(
      runId: DomainEntityId,
      fromCursor?: string | null,
    ): Promise<RunEventPage & { readonly latestSequence: number }> {
      // 1. GET /api/v2/runs/{run_id} — authoritative snapshot with
      //    latest_event_sequence.
      // 2. Drain events page by page starting from `fromCursor` (or the
      //    beginning) until either has_more is false or the highest sequence
      //    in a page reaches latestSequence.
      // 3. Return aggregated events + the next cursor for subsequent polls.
      const latestSequence = await this.getLatestEventSequence(runId);
      const aggregated: RunEvent[] = [];
      let cursor = fromCursor ?? null;
      let hasMore = true;
      while (hasMore) {
        const page = await this.listEventsPage(runId, cursor);
        aggregated.push(...page.events);
        cursor = page.nextCursor;
        hasMore = page.hasMore;
        const maxSeq = page.events.reduce(
          (m, e) => (e.sequence > m ? e.sequence : m),
          0,
        );
        if (maxSeq >= latestSequence) {
          hasMore = false;
        }
        if (!cursor) {
          hasMore = false;
        }
      }
      return {
        events: aggregated,
        nextCursor: cursor,
        hasMore,
        latestSequence,
      };
    },
    async appendEvent(event: RunEvent): Promise<void> {
      // RunEvents are server-emitted; clients cannot append directly.
      // This method is a no-op for the HTTP adapter — it exists only to
      // satisfy the RepositorySet port shared with the fixture adapter.
      void event;
    },
    subscribe(listener: Listener<ResearchRun>): Unsubscribe {
      return runSubs.subscribe(listener);
    },
  };

  const artifacts: ArtifactRepository = {
    async getArtifactById(
      id: DomainEntityId,
    ): Promise<ResearchArtifact | null> {
      const payload = await http.get<unknown>(
        `/api/v2/artifacts/${encodeURIComponent(id)}`,
      );
      if (!payload) return null;
      return validateAndMap("ResearchArtifact", payload, mapResearchArtifact);
    },
    async listByProject(
      projectId: DomainEntityId,
    ): Promise<readonly ResearchArtifact[]> {
      void projectId;
      throw new CapabilityUnavailableError(
        "artifacts.listByProject",
        "OpenAPI does not define an artifact list-by-project endpoint",
      );
    },
    async getVersionById(id: DomainEntityId): Promise<ArtifactVersion | null> {
      const payload = await http.get<unknown>(
        `/api/v2/artifact-versions/${encodeURIComponent(id)}`,
      );
      if (!payload) return null;
      return validateAndMap("ArtifactVersion", payload, mapArtifactVersion);
    },
    async listVersions(
      artifactId: DomainEntityId,
    ): Promise<readonly ArtifactVersion[]> {
      void artifactId;
      throw new CapabilityUnavailableError(
        "artifacts.listVersions",
        "OpenAPI does not define an artifact version list endpoint",
      );
    },
    async saveVersion(version: ArtifactVersion): Promise<void> {
      // ArtifactVersions are created by runs, not by direct client writes.
      void version;
    },
    subscribe(listener: Listener<ResearchArtifact>): Unsubscribe {
      return artifactSubs.subscribe(listener);
    },
  };

  const evidence: EvidenceRepository = {
    async getById(id: DomainEntityId): Promise<Evidence | null> {
      void id;
      throw new CapabilityUnavailableError(
        "evidence.getById",
        "OpenAPI does not define an evidence read endpoint",
      );
    },
    async listByArtifactVersion(
      artifactVersionId: DomainEntityId,
    ): Promise<readonly Evidence[]> {
      void artifactVersionId;
      throw new CapabilityUnavailableError(
        "evidence.listByArtifactVersion",
        "OpenAPI does not define an evidence list-by-artifact-version endpoint",
      );
    },
    async save(evidence: Evidence): Promise<void> {
      void evidence;
    },
    subscribe(listener: Listener<Evidence>): Unsubscribe {
      return evidenceSubs.subscribe(listener);
    },
  };

  const workspaces: WorkspaceSnapshotRepository = {
    async getByProjectId(
      projectId: DomainEntityId,
    ): Promise<WorkspaceSnapshot | null> {
      const payload = await http.get<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/workspace-snapshot`,
      );
      if (!payload) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return mapWorkspaceSnapshot(payload as any);
    },
    async save(
      projectId: DomainEntityId,
      snapshot: WorkspaceSnapshotInput,
      expectedRevision: number,
    ): Promise<WorkspaceSnapshot> {
      const payload = await http.put<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/workspace-snapshot`,
        mapWorkspaceSnapshotInputToDto(snapshot),
        { "If-Match": `"${expectedRevision}"` },
      );
      if (!payload) {
        throw new UnexpectedHttpError(
          "Workspace save returned no data",
          200,
          null,
        );
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return mapWorkspaceSnapshot(payload as any);
    },
  };

  const shares: ShareRepository = {
    async create(
      projectId: DomainEntityId,
      request: CreateShareSnapshotRequest,
    ): Promise<ShareSnapshotCreated> {
      const payload = await http.post<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/shares`,
        mapCreateShareSnapshotRequestToDto(request),
      );
      return payload as ShareSnapshotCreated;
    },
    async getByProjectIdAndShareId(
      projectId: DomainEntityId,
      shareId: DomainEntityId,
    ): Promise<ShareSnapshot | null> {
      const payload = await http.get<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/shares/${encodeURIComponent(shareId)}`,
      );
      if (!payload) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return mapShareSnapshot(payload as any);
    },
    async listByProject(
      projectId: DomainEntityId,
    ): Promise<readonly ShareSnapshot[]> {
      const payload = await http.list<unknown>(
        `/api/v2/projects/${encodeURIComponent(projectId)}/shares`,
      );
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (payload as any[]).map((p) => mapShareSnapshot(p));
    },
    async revoke(
      projectId: DomainEntityId,
      shareId: DomainEntityId,
    ): Promise<void> {
      await http.delete(
        `/api/v2/projects/${encodeURIComponent(projectId)}/shares/${encodeURIComponent(shareId)}`,
      );
    },
    async getPublicShare(
      shareToken: string,
    ): Promise<PublicShareSnapshot | null> {
      const payload = await http.get<unknown>(
        `/api/v2/shares/${encodeURIComponent(shareToken)}`,
      );
      if (!payload) return null;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return mapPublicShareSnapshot(payload as any);
    },
  };

  const provenance: RepositoryProvenance = {
    state: {
      executionMode: "live",
      sourceMode: "live",
      schemaVersion: "2.0.0",
      retrievedAt: new Date().toISOString() as never,
      evidenceCompleteness: { covered: 0, total: 0 },
      note: "HTTP adapter — live /api/v2 data",
    },
  };

  return {
    projects,
    contracts,
    runs,
    artifacts,
    evidence,
    workspaces,
    shares,
    provenance,
  };
}
