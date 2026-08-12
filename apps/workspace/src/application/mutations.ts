import { mutationOptions, type QueryClient } from "@tanstack/react-query";
import type {
  CreateResearchProjectInput,
  RepositorySet,
  SubmitResearchTurnInput,
  UpdateResearchProjectInput,
  UpdateResearchContractDraftInput,
} from "@xingwen/data-access/ports";
import type {
  DomainEntityId,
  ExecutionMode,
  ResearchContractInput,
} from "@xingwen/domain";
import type {
  ProjectViewModel,
  ResearchAdapter,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  ResearchTurnViewModel,
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";

interface WorkspaceMutationDependencies {
  readonly repositories: Pick<
    RepositorySet,
    "projects" | "contracts" | "runs" | "researchThread"
  >;
  readonly researchAdapter: ResearchAdapter;
  readonly queryClient: QueryClient;
  readonly createIdempotencyKey: () => string;
}

const MAX_PENDING_IDEMPOTENCY_KEYS = 64;

export function mergeResearchThreadEntries(
  current: readonly ResearchThreadEntryViewModel[] | undefined,
  incoming: readonly ResearchThreadEntryViewModel[],
): readonly ResearchThreadEntryViewModel[] {
  const byId = new Map<DomainEntityId, ResearchThreadEntryViewModel>();
  for (const entry of current ?? []) byId.set(entry.id, entry);
  for (const entry of incoming) byId.set(entry.id, entry);
  return [...byId.values()].sort(
    (left, right) => left.sequence - right.sequence,
  );
}

function stableSerialize(value: unknown): string {
  if (value === undefined) return "null";
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value) ?? "null";
  }
  if (Array.isArray(value)) {
    return `[${value.map(stableSerialize).join(",")}]`;
  }
  return `{${Object.entries(value)
    .filter(([, item]) => item !== undefined)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableSerialize(item)}`)
    .join(",")}}`;
}

function createIdempotencyLedger(createKey: () => string) {
  const pending = new Map<string, string>();
  const fingerprint = (scope: string, input: unknown) =>
    `${scope}:${stableSerialize(input)}`;

  return Object.freeze({
    keyFor(scope: string, input: unknown): string {
      const action = fingerprint(scope, input);
      const existing = pending.get(action);
      if (existing) return existing;
      const key = createKey();
      pending.set(action, key);
      if (pending.size > MAX_PENDING_IDEMPOTENCY_KEYS) {
        const oldest = pending.keys().next().value as string | undefined;
        if (oldest) pending.delete(oldest);
      }
      return key;
    },
    complete(scope: string, input: unknown): void {
      pending.delete(fingerprint(scope, input));
    },
  });
}

export interface CreateDraftVariables {
  readonly projectId: DomainEntityId;
  readonly intent: string;
  readonly contract: ResearchContractInput;
}

export interface UpdateProjectVariables {
  readonly projectId: DomainEntityId;
  readonly expectedRevision: number;
  readonly input: UpdateResearchProjectInput;
}

export interface DeleteProjectVariables {
  readonly projectId: DomainEntityId;
  readonly expectedRevision: number;
}

export interface SubmitResearchTurnVariables {
  readonly projectId: DomainEntityId;
  readonly message: string;
  readonly answerToQuestionId: DomainEntityId | null;
}

export interface UpdateDraftVariables {
  readonly draftId: DomainEntityId;
  readonly expectedVersion: number;
  readonly input: UpdateResearchContractDraftInput;
}

export interface ConfirmContractVariables {
  readonly projectId: DomainEntityId;
  readonly draftId: DomainEntityId;
  readonly expectedDraftVersion: number;
}

export interface CreateRunVariables {
  readonly projectId: DomainEntityId;
  readonly contractId: DomainEntityId;
  readonly executionMode: ExecutionMode;
}

export function createWorkspaceMutations({
  repositories,
  researchAdapter,
  queryClient,
  createIdempotencyKey,
}: WorkspaceMutationDependencies) {
  const idempotency = createIdempotencyLedger(createIdempotencyKey);
  return Object.freeze({
    projectCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "project", "create"],
        retry: false,
        mutationFn: async (
          input: Omit<CreateResearchProjectInput, "idempotencyKey">,
        ): Promise<ProjectViewModel> => {
          const command = researchAdapter.toApplicationCommand(
            { type: "project.create", input },
            { idempotencyKey: idempotency.keyFor("project.create", input) },
          );
          if (command.type !== "project.create") {
            throw new Error("Project create command mapping failed.");
          }
          return researchAdapter.toProjectViewModel(
            await repositories.projects.create(command.input),
          );
        },
        onSuccess: (project, input) => {
          idempotency.complete("project.create", input);
          queryClient.setQueryData(
            workspaceQueryKeys.projects(),
            (current: readonly ProjectViewModel[] | undefined) => [
              project,
              ...(current?.filter((item) => item.id !== project.id) ?? []),
            ],
          );
          queryClient.setQueryData(
            workspaceQueryKeys.project(project.id),
            project,
          );
        },
      }),
    projectUpdate: () =>
      mutationOptions({
        mutationKey: ["workspace", "project", "update"],
        retry: false,
        mutationFn: async (
          variables: UpdateProjectVariables,
        ): Promise<ProjectViewModel> =>
          researchAdapter.toProjectViewModel(
            await repositories.projects.update(
              variables.projectId,
              variables.input,
              variables.expectedRevision,
            ),
          ),
        onSuccess: (project) => {
          queryClient.setQueryData(
            workspaceQueryKeys.project(project.id),
            project,
          );
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.projects(),
            exact: true,
          });
        },
      }),
    projectDelete: () =>
      mutationOptions({
        mutationKey: ["workspace", "project", "delete"],
        retry: false,
        mutationFn: async ({
          projectId,
          expectedRevision,
        }: DeleteProjectVariables) =>
          repositories.projects.delete(projectId, expectedRevision),
        onSuccess: (_value, variables) => {
          queryClient.removeQueries({
            queryKey: workspaceQueryKeys.project(variables.projectId),
            exact: true,
          });
          queryClient.removeQueries({
            queryKey: workspaceQueryKeys.thread(variables.projectId),
            exact: true,
          });
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.projects(),
            exact: true,
          });
        },
      }),
    researchTurnSubmit: () =>
      mutationOptions({
        mutationKey: ["workspace", "research-turn", "submit"],
        retry: false,
        mutationFn: async (
          variables: SubmitResearchTurnVariables,
        ): Promise<ResearchTurnViewModel> =>
          researchAdapter.toResearchTurnViewModel(
            await repositories.researchThread.submit(variables.projectId, {
              message: variables.message,
              answerToQuestionId: variables.answerToQuestionId,
              idempotencyKey: idempotency.keyFor(
                "research-turn.submit",
                variables,
              ),
            } satisfies SubmitResearchTurnInput),
          ),
        onSuccess: (turn, variables) => {
          idempotency.complete("research-turn.submit", variables);
          queryClient.setQueryData(
            workspaceQueryKeys.thread(variables.projectId),
            (
              current:
                | readonly import("@xingwen/research-adapter").ResearchThreadEntryViewModel[]
                | undefined,
            ) => mergeResearchThreadEntries(current, turn.entries),
          );
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.project(variables.projectId),
            exact: true,
          });
        },
        onError: (_error, variables) => {
          // A failed planner execution is persisted as a completed failure.
          // A manual retry is a new provider attempt, not a replay of that key.
          idempotency.complete("research-turn.submit", variables);
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.thread(variables.projectId),
            exact: true,
          });
        },
      }),
    draftCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "draft", "create"],
        retry: false,
        mutationFn: async (
          variables: CreateDraftVariables,
        ): Promise<ResearchContractDraftViewModel> => {
          const command = researchAdapter.toApplicationCommand(
            {
              type: "contract.draft.create",
              projectId: variables.projectId,
              input: {
                intent: variables.intent,
                contract: variables.contract,
              },
            },
            {
              idempotencyKey: idempotency.keyFor(
                "contract.draft.create",
                variables,
              ),
            },
          );
          if (command.type !== "contract.draft.create") {
            throw new Error("Draft create command mapping failed.");
          }
          return researchAdapter.toContractDraftViewModel(
            await repositories.contracts.createDraft(
              command.projectId,
              command.input,
            ),
          );
        },
        onSuccess: (draft, variables) => {
          idempotency.complete("contract.draft.create", variables);
          queryClient.setQueryData(workspaceQueryKeys.draft(draft.id), draft);
        },
      }),
    draftUpdate: () =>
      mutationOptions({
        mutationKey: ["workspace", "draft", "update"],
        retry: false,
        mutationFn: async (
          variables: UpdateDraftVariables,
        ): Promise<ResearchContractDraftViewModel> => {
          const command = researchAdapter.toApplicationCommand(
            { type: "contract.draft.update", ...variables },
            { idempotencyKey: createIdempotencyKey() },
          );
          if (command.type !== "contract.draft.update") {
            throw new Error("Draft update command mapping failed.");
          }
          return researchAdapter.toContractDraftViewModel(
            await repositories.contracts.updateDraft(
              command.draftId,
              command.expectedVersion,
              command.input,
            ),
          );
        },
        onSuccess: (draft) => {
          queryClient.setQueryData(workspaceQueryKeys.draft(draft.id), draft);
        },
      }),
    contractConfirm: () =>
      mutationOptions({
        mutationKey: ["workspace", "contract", "confirm"],
        retry: false,
        mutationFn: async (
          variables: ConfirmContractVariables,
        ): Promise<ResearchContractViewModel> => {
          const command = researchAdapter.toApplicationCommand(
            { type: "contract.confirm", ...variables },
            { idempotencyKey: createIdempotencyKey() },
          );
          if (command.type !== "contract.confirm") {
            throw new Error("Contract confirm command mapping failed.");
          }
          return researchAdapter.toContractViewModel(
            await repositories.contracts.confirm(
              command.projectId,
              command.draftId,
              command.expectedDraftVersion,
            ),
          );
        },
        onSuccess: (contract, variables) => {
          queryClient.setQueryData(
            workspaceQueryKeys.contract(contract.id),
            contract,
          );
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.project(variables.projectId),
            exact: true,
          });
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.projects(),
            exact: true,
          });
        },
      }),
    runCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "run", "create"],
        retry: false,
        mutationFn: async (
          variables: CreateRunVariables,
        ): Promise<ResearchRunViewModel> => {
          const command = researchAdapter.toApplicationCommand(
            { type: "run.create", ...variables },
            {
              idempotencyKey: idempotency.keyFor("run.create", variables),
            },
          );
          if (command.type !== "run.create") {
            throw new Error("Run create command mapping failed.");
          }
          return researchAdapter.toRunViewModel(
            await repositories.runs.create(command.input),
          );
        },
        onSuccess: (run, variables) => {
          idempotency.complete("run.create", variables);
          queryClient.setQueryData(workspaceQueryKeys.run(run.id), run);
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.run(run.id),
            exact: true,
          });
          queryClient.setQueryData(
            workspaceQueryKeys.project(run.projectId),
            (current: ProjectViewModel | undefined) =>
              current
                ? {
                    ...current,
                    latestRunId: run.id,
                    latestRunStatus: run.status,
                    latestRunFailureSummary: run.failure?.summary ?? null,
                  }
                : current,
          );
          queryClient.setQueryData(
            workspaceQueryKeys.projects(),
            (current: readonly ProjectViewModel[] | undefined) =>
              current?.map((project) =>
                project.id === run.projectId
                  ? {
                      ...project,
                      latestRunId: run.id,
                      latestRunStatus: run.status,
                      latestRunFailureSummary: run.failure?.summary ?? null,
                    }
                  : project,
              ),
          );
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.project(run.projectId),
            exact: true,
          });
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.projects(),
            exact: true,
          });
        },
      }),
  });
}

export type WorkspaceMutations = ReturnType<typeof createWorkspaceMutations>;
