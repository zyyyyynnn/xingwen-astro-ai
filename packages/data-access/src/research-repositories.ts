/**
 * Research chain repositories over `/api/v2`: Project, ContractDraft, Contract,
 * Run and RunEvent. Every write carries the contract-required concurrency or
 * idempotency header, and RunEvent recovery is capped to the authoritative
 * `latest_event_sequence`.
 */

import type {
  ConfirmResearchContractRequest,
  CreateRunRequest,
  UpdateResearchContractDraftRequest,
} from "@xingwen/contracts";
import type {
  ResearchContract,
  ResearchContractDraft,
  ResearchRun,
  RunEvent,
} from "@xingwen/domain";

import {
  HttpClient,
  seg,
  stableIdempotencyKey,
  validateAndMap,
} from "./http-client";
import { NotFoundError } from "./http-errors";
import {
  mapDomainContractInputToDto,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchRun,
  mapRunEvent,
} from "./mapping";
import type {
  ContractRepository,
  CreateResearchRunInput,
  ProjectRepository,
  RunEventRecovery,
  RunRepository,
  UpdateResearchContractDraftInput,
} from "./ports";

const EVENT_PAGE_LIMIT = 100;

interface ResearchRepositories {
  readonly projects: ProjectRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
}

export function createResearchRepositories(
  http: HttpClient,
): ResearchRepositories {
  const projects: ProjectRepository = {
    async getById(id) {
      const payload = await http.get<unknown>(`/api/v2/projects/${seg(id)}`);
      return payload
        ? validateAndMap("ResearchProject", payload, mapResearchProject)
        : null;
    },
  };

  const contracts: ContractRepository = {
    async getDraftById(id) {
      const payload = await http.get<unknown>(
        `/api/v2/research-contract-drafts/${seg(id)}`,
      );
      return payload
        ? validateAndMap(
            "ResearchContractDraft",
            payload,
            mapResearchContractDraft,
          )
        : null;
    },
    async updateDraft(
      draftId,
      expectedVersion,
      input: UpdateResearchContractDraftInput,
    ): Promise<ResearchContractDraft> {
      const body: UpdateResearchContractDraftRequest = {
        intent: input.intent ?? null,
        contract: input.contract
          ? mapDomainContractInputToDto(input.contract)
          : null,
      };
      const payload = await http.patch<unknown>(
        `/api/v2/research-contract-drafts/${seg(draftId)}`,
        body,
        { "If-Match": String(expectedVersion) },
      );
      return validateAndMap(
        "ResearchContractDraft",
        payload,
        mapResearchContractDraft,
      );
    },
    async confirm(
      projectId,
      draftId,
      expectedDraftVersion,
    ): Promise<ResearchContract> {
      const body: ConfirmResearchContractRequest = {
        draft_id: draftId,
        expected_draft_version: expectedDraftVersion,
      };
      const payload = await http.post<unknown>(
        `/api/v2/projects/${seg(projectId)}/contracts`,
        body,
        { "Idempotency-Key": stableIdempotencyKey("confirm-contract", body) },
      );
      return validateAndMap("ResearchContract", payload, mapResearchContract);
    },
    async getContractById(id) {
      const payload = await http.get<unknown>(
        `/api/v2/research-contracts/${seg(id)}`,
      );
      return payload
        ? validateAndMap("ResearchContract", payload, mapResearchContract)
        : null;
    },
  };

  async function fetchEventsPage(
    runId: string,
    cursor: string | null,
  ): Promise<{
    readonly events: readonly RunEvent[];
    readonly nextCursor: string | null;
    readonly hasMore: boolean;
  }> {
    const params: string[] = [`limit=${String(EVENT_PAGE_LIMIT)}`];
    if (cursor) params.push(`cursor=${encodeURIComponent(cursor)}`);
    const path = `/api/v2/runs/${seg(runId)}/events?${params.join("&")}`;
    const env = await http.getPage<unknown>(path);
    return {
      events: env.data.map((p) => validateAndMap("RunEvent", p, mapRunEvent)),
      nextCursor: env.page?.next_cursor ?? null,
      hasMore: env.page?.has_more ?? false,
    };
  }

  const runs: RunRepository = {
    async getById(id) {
      const payload = await http.get<unknown>(`/api/v2/runs/${seg(id)}`);
      return payload
        ? validateAndMap("ResearchRun", payload, mapResearchRun)
        : null;
    },
    async create(input: CreateResearchRunInput): Promise<ResearchRun> {
      const body: CreateRunRequest = {
        contract_id: input.contractId,
        execution_mode: input.executionMode,
        derivation_kind: input.derivationKind ?? "original",
        parent_run_id: input.parentRunId ?? null,
        retry_from_step: input.retryFromStep ?? null,
        cache_policy: input.cachePolicy ?? "fallback_on_recoverable_failure",
      };
      const payload = await http.post<unknown>(
        `/api/v2/projects/${seg(input.projectId)}/runs`,
        body,
        { "Idempotency-Key": stableIdempotencyKey("create-run", body) },
      );
      return validateAndMap("ResearchRun", payload, mapResearchRun);
    },
    async listEvents(runId): Promise<readonly RunEvent[]> {
      const payloads = await http.list<unknown>(
        `/api/v2/runs/${seg(runId)}/events`,
      );
      return payloads.map((p) => validateAndMap("RunEvent", p, mapRunEvent));
    },
    async recoverEvents(runId, fromCursor = null): Promise<RunEventRecovery> {
      // Snapshot-first: the Run's latest_event_sequence is authoritative.
      const payload = await http.get<unknown>(`/api/v2/runs/${seg(runId)}`);
      if (!payload) {
        throw new NotFoundError(
          "Run not found; cannot recover events",
          "RUN_NOT_FOUND",
        );
      }
      const run = validateAndMap("ResearchRun", payload, mapResearchRun);
      const latestSequence = run.latestEventSequence;
      const aggregated: RunEvent[] = [];
      let cursor: string | null = fromCursor;
      let hasMore = true;
      while (hasMore) {
        const page = await fetchEventsPage(runId, cursor);
        // Only events up to the authoritative snapshot sequence are trusted.
        for (const event of page.events) {
          if (event.sequence <= latestSequence) aggregated.push(event);
        }
        const maxSeq = page.events.reduce(
          (m, e) => (e.sequence > m ? e.sequence : m),
          0,
        );
        const crossedAuthoritativeTail = page.events.some(
          (event) => event.sequence > latestSequence,
        );
        cursor = crossedAuthoritativeTail
          ? String(latestSequence)
          : page.nextCursor;
        hasMore = page.hasMore && cursor !== null && maxSeq < latestSequence;
      }
      return { events: aggregated, nextCursor: cursor, latestSequence };
    },
  };

  return { projects, contracts, runs };
}
