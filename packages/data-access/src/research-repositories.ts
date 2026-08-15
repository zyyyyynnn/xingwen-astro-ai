/**
 * Research chain repositories over `/api`: Project, ContractDraft, Contract,
 * Run and RunEvent. Every write carries the contract-required concurrency or
 * idempotency header, and RunEvent recovery is capped to the authoritative
 * `latest_event_sequence`.
 */

import type {
  ConfirmResearchContractRequest,
  CreateResearchContractDraftRequest,
  CreateResearchProjectRequest,
  CreateRunRequest,
  CancelRunDecisionRequest,
  ResumeRunDecisionRequest,
  RetryRunDecisionRequest,
  RunDecisionResult as RunDecisionResultDto,
  RunCheckpointRead as RunCheckpointReadDto,
  ResearchTurnRequest,
  UpdateResearchProjectRequest,
  UpdateResearchContractDraftRequest,
} from "@xingwen/contracts";
import type {
  ResearchContract,
  ResearchContractDraft,
  ResearchRun,
  ResearchTurn,
  RunStepSnapshot,
  RunEvent,
  RunCheckpoint,
  RunDecisionResult,
} from "@xingwen/domain";

import {
  HttpClient,
  seg,
  stableIdempotencyKey,
  validateAndMap,
} from "./http-client";
import { NotFoundError } from "./errors";
import {
  mapDomainContractInputToDto,
  mapResearchContract,
  mapResearchContractDraft,
  mapResearchProject,
  mapResearchPlanningCatalog,
  mapResearchRun,
  mapResearchThreadEntry,
  mapResearchTurn,
  mapRunStep,
  mapRunEvent,
  mapRunCheckpoint,
  mapRunDecisionResult,
} from "./mapping";
import type {
  ContractRepository,
  CreateResearchContractDraftInput,
  CreateResearchProjectInput,
  CreateResearchRunInput,
  ProjectRepository,
  ResearchCatalogRepository,
  ResearchProjectPage,
  ResearchThreadPage,
  ResearchThreadRepository,
  RunEventRecovery,
  RunRepository,
  SubmitResearchTurnInput,
  UpdateResearchProjectInput,
  UpdateResearchContractDraftInput,
  RunDecisionInput,
} from "./ports";

const EVENT_PAGE_LIMIT = 100;
const PROJECT_PAGE_LIMIT = 20;

interface ResearchRepositories {
  readonly projects: ProjectRepository;
  readonly researchCatalog: ResearchCatalogRepository;
  readonly contracts: ContractRepository;
  readonly runs: RunRepository;
  readonly researchThread: ResearchThreadRepository;
}

export function createResearchRepositories(
  http: HttpClient,
): ResearchRepositories {
  const projects: ProjectRepository = {
    async getById(id) {
      const payload = await http.get<unknown>(`/api/projects/${seg(id)}`);
      return payload
        ? validateAndMap("ResearchProject", payload, mapResearchProject)
        : null;
    },
    async list(cursor = null): Promise<ResearchProjectPage> {
      const params: string[] = [`limit=${String(PROJECT_PAGE_LIMIT)}`];
      if (cursor) params.push(`cursor=${encodeURIComponent(cursor)}`);
      const env = await http.getPage<unknown>(
        `/api/projects?${params.join("&")}`,
      );
      return {
        items: env.data.map((p) =>
          validateAndMap("ResearchProject", p, mapResearchProject),
        ),
        nextCursor: env.page?.has_more ? (env.page?.next_cursor ?? null) : null,
      };
    },
    async create(input: CreateResearchProjectInput) {
      const body: CreateResearchProjectRequest = {
        name: input.name,
        description: input.description ?? "",
        case_key: input.caseKey,
      };
      const payload = await http.post<unknown>("/api/projects", body, {
        "Idempotency-Key": input.idempotencyKey,
      });
      return validateAndMap("ResearchProject", payload, mapResearchProject);
    },
    async update(id, input: UpdateResearchProjectInput, expectedRevision) {
      const body: UpdateResearchProjectRequest = { name: input.name };
      const payload = await http.patch<unknown>(
        `/api/projects/${seg(id)}`,
        body,
        { "If-Match": String(expectedRevision) },
      );
      return validateAndMap("ResearchProject", payload, mapResearchProject);
    },
    async delete(id, expectedRevision) {
      await http.delete(`/api/projects/${seg(id)}`, {
        "If-Match": String(expectedRevision),
      });
    },
  };

  const researchCatalog: ResearchCatalogRepository = {
    async getForProject(projectId) {
      const payload = await http.getRequired<unknown>(
        `/api/projects/${seg(projectId)}/research-catalog`,
      );
      return validateAndMap(
        "ResearchPlanningCatalog",
        payload,
        mapResearchPlanningCatalog,
      );
    },
  };

  const researchThread: ResearchThreadRepository = {
    async list(projectId, cursor = null): Promise<ResearchThreadPage> {
      const params = ["limit=100"];
      if (cursor) params.push(`cursor=${encodeURIComponent(cursor)}`);
      const env = await http.getPage<unknown>(
        `/api/projects/${seg(projectId)}/research-turns?${params.join("&")}`,
      );
      return {
        items: env.data.map((entry) =>
          validateAndMap("ResearchThreadEntry", entry, mapResearchThreadEntry),
        ),
        nextCursor: env.page?.has_more ? (env.page?.next_cursor ?? null) : null,
      };
    },
    async submit(
      projectId,
      input: SubmitResearchTurnInput,
    ): Promise<ResearchTurn> {
      const body: ResearchTurnRequest = {
        message: input.message,
        answer_to_question_id: input.answerToQuestionId,
      };
      const payload = await http.post<unknown>(
        `/api/projects/${seg(projectId)}/research-turns`,
        body,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return validateAndMap("ResearchTurnResult", payload, mapResearchTurn);
    },
  };

  const contracts: ContractRepository = {
    async createDraft(
      projectId,
      input: CreateResearchContractDraftInput,
    ): Promise<ResearchContractDraft> {
      const body: CreateResearchContractDraftRequest = {
        intent: input.intent,
        contract: mapDomainContractInputToDto(input.contract),
      };
      const payload = await http.post<unknown>(
        `/api/projects/${seg(projectId)}/contract-drafts`,
        body,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return validateAndMap(
        "ResearchContractDraft",
        payload,
        mapResearchContractDraft,
      );
    },
    async getDraftById(id) {
      const payload = await http.get<unknown>(
        `/api/contracts/drafts/${seg(id)}`,
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
        `/api/contracts/drafts/${seg(draftId)}`,
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
        `/api/projects/${seg(projectId)}/contracts`,
        body,
        { "Idempotency-Key": stableIdempotencyKey("confirm-contract", body) },
      );
      return validateAndMap("ResearchContract", payload, mapResearchContract);
    },
    async getContractById(id) {
      const payload = await http.get<unknown>(`/api/contracts/${seg(id)}`);
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
    const path = `/api/runs/${seg(runId)}/events?${params.join("&")}`;
    const env = await http.getPage<unknown>(path);
    return {
      events: env.data.map((p) => validateAndMap("RunEvent", p, mapRunEvent)),
      nextCursor: env.page?.next_cursor ?? null,
      hasMore: env.page?.has_more ?? false,
    };
  }

  const runs: RunRepository = {
    async getById(id) {
      const payload = await http.get<unknown>(`/api/runs/${seg(id)}`);
      return payload
        ? validateAndMap("ResearchRun", payload, mapResearchRun)
        : null;
    },
    async create(input: CreateResearchRunInput): Promise<ResearchRun> {
      const body: CreateRunRequest = {
        contract_id: input.contractId,
        execution_mode: input.executionMode,
      };
      const payload = await http.post<unknown>(
        `/api/projects/${seg(input.projectId)}/runs`,
        body,
        { "Idempotency-Key": input.idempotencyKey },
      );
      return validateAndMap("ResearchRun", payload, mapResearchRun);
    },
    async getCheckpoint(id): Promise<RunCheckpoint | null> {
      const payload = await http.get<RunCheckpointReadDto>(
        `/api/runs/${seg(id)}/checkpoint`,
      );
      return payload ? mapRunCheckpoint(payload) : null;
    },
    async decide(
      id,
      input: RunDecisionInput,
      expectedRevision,
      idempotencyKey,
    ): Promise<RunDecisionResult> {
      const body:
        | ResumeRunDecisionRequest
        | RetryRunDecisionRequest
        | CancelRunDecisionRequest =
        input.decision === "resume"
          ? (() => {
              const [first, ...rest] = input.inputIds;
              if (!first) {
                throw new TypeError("Resume decisions require an input id");
              }
              return {
                decision: "resume",
                input_ids: [first, ...rest],
              } satisfies ResumeRunDecisionRequest;
            })()
          : input.decision === "retry"
            ? { decision: "retry", step_key: input.stepKey }
            : { decision: "cancel" };
      const payload = await http.post<RunDecisionResultDto>(
        `/api/runs/${seg(id)}/decisions`,
        body,
        {
          "If-Match": String(expectedRevision),
          "Idempotency-Key": idempotencyKey,
        },
      );
      return mapRunDecisionResult(payload);
    },
    async listEvents(runId): Promise<readonly RunEvent[]> {
      const payloads = await http.list<unknown>(
        `/api/runs/${seg(runId)}/events`,
      );
      return payloads.map((p) => validateAndMap("RunEvent", p, mapRunEvent));
    },
    async recoverEvents(runId, fromCursor = null): Promise<RunEventRecovery> {
      // Snapshot-first: the Run's latest_event_sequence is authoritative.
      const payload = await http.get<unknown>(`/api/runs/${seg(runId)}`);
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
    async listSteps(runId): Promise<readonly RunStepSnapshot[]> {
      const payloads = await http.list<unknown>(
        `/api/runs/${seg(runId)}/steps`,
      );
      return payloads.map((payload) =>
        validateAndMap("RunStepRead", payload, mapRunStep),
      );
    },
  };

  return { projects, researchCatalog, contracts, runs, researchThread };
}
