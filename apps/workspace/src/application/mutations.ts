import { mutationOptions, type QueryClient } from "@tanstack/react-query";
import type {
  CreateResearchProjectInput,
  CreateResearchInputInput,
  RepositorySet,
  ResearchInputRef,
  SubmitResearchTurnInput,
  UpdateResearchProjectInput,
  UpdateResearchContractDraftInput,
} from "@xingwen/data-access/ports";
import type {
  ConfigureModelProviderInput,
  CreateShareSnapshotRequest,
  DomainEntityId,
  ExecutionMode,
  RunCheckpointDecisionRequest,
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
    | "projects"
    | "contracts"
    | "runs"
    | "researchThread"
    | "researchInputs"
    | "revisions"
    | "modelProvider"
    | "shares"
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
  readonly actionId: string;
}

export interface UpdateDraftVariables {
  readonly projectId: DomainEntityId;
  readonly draftId: DomainEntityId;
  readonly expectedVersion: number;
  readonly input: UpdateResearchContractDraftInput;
}

export interface ConfirmContractVariables {
  readonly projectId: DomainEntityId;
  readonly draftId: DomainEntityId;
  readonly expectedDraftVersion: number;
}

export interface RunLifecycleVariables {
  readonly projectId: DomainEntityId;
  readonly runId: DomainEntityId;
}

export interface CheckpointDecisionVariables extends RunLifecycleVariables {
  readonly decision: RunCheckpointDecisionRequest;
}

export interface CreateRunVariables {
  readonly projectId: DomainEntityId;
  readonly contractId: DomainEntityId;
  readonly executionMode: ExecutionMode;
}

export interface DeleteResearchInputVariables {
  readonly inputId: DomainEntityId;
  readonly projectId?: DomainEntityId;
}

export interface BindResearchInputToDraftVariables {
  readonly inputId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly draftId: DomainEntityId;
}

export interface CreateRevisionFeedbackVariables {
  readonly projectId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly expectedVersionNumber: number;
  readonly summary: string;
  readonly requestedChange: string;
}

export interface CreateRevisionPlanVariables {
  readonly projectId: DomainEntityId;
  readonly feedbackId: DomainEntityId;
  readonly expectedParentRunRevision: number;
}

export interface ConfirmRevisionPlanVariables {
  readonly projectId: DomainEntityId;
  readonly planId: DomainEntityId;
  readonly expectedPlanVersion: number;
}

export interface ConfigureModelProviderVariables {
  readonly input: ConfigureModelProviderInput;
  readonly expectedRevision: number;
}

export interface CreateShareVariables {
  readonly projectId: DomainEntityId;
  readonly request: CreateShareSnapshotRequest;
}

function _invalidateRunState(
  queryClient: QueryClient,
  projectId: DomainEntityId,
  runId: DomainEntityId,
): void {
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.project(projectId),
    exact: true,
  });
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.run(projectId, runId),
    exact: true,
  });
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.runCheckpoint(projectId, runId),
    exact: true,
  });
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.runSteps(projectId, runId),
    exact: true,
  });
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.runEvents(projectId, runId),
  });
  void queryClient.invalidateQueries({
    queryKey: workspaceQueryKeys.thread(projectId),
    exact: true,
  });
}

export function createWorkspaceMutations({
  repositories,
  researchAdapter,
  queryClient,
  createIdempotencyKey,
}: WorkspaceMutationDependencies) {
  const idempotency = createIdempotencyLedger(createIdempotencyKey);
  return Object.freeze({
    modelProviderConfigure: () =>
      mutationOptions({
        mutationKey: ["workspace", "model-provider", "configure"],
        retry: false,
        mutationFn: ({
          input,
          expectedRevision,
        }: ConfigureModelProviderVariables) =>
          repositories.modelProvider.configure(input, expectedRevision),
        onSuccess: (configuration) => {
          queryClient.setQueryData(
            workspaceQueryKeys.modelProviderConfiguration(),
            configuration,
          );
        },
        onError: () => {
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.modelProviderConfiguration(),
            exact: true,
          });
        },
      }),
    modelProviderRemove: () =>
      mutationOptions({
        mutationKey: ["workspace", "model-provider", "remove"],
        retry: false,
        mutationFn: (expectedRevision: number) =>
          repositories.modelProvider.removeConfiguration(expectedRevision),
        onSuccess: (configuration) => {
          queryClient.setQueryData(
            workspaceQueryKeys.modelProviderConfiguration(),
            configuration,
          );
        },
        onError: () => {
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.modelProviderConfiguration(),
            exact: true,
          });
        },
      }),
    shareCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "share", "create"],
        retry: false,
        mutationFn: ({ projectId, request }: CreateShareVariables) =>
          repositories.shares.create(projectId, request),
      }),
    researchInputCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "research-input", "create"],
        retry: false,
        mutationFn: (
          input: CreateResearchInputInput,
        ): Promise<ResearchInputRef> =>
          repositories.researchInputs.create(input),
        onSuccess: (_input, variables) => {
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.researchInputs(variables.projectId),
            exact: true,
          });
        },
      }),
    researchInputDelete: () =>
      mutationOptions({
        mutationKey: ["workspace", "research-input", "delete"],
        retry: false,
        mutationFn: ({ inputId }: DeleteResearchInputVariables) =>
          repositories.researchInputs.delete(inputId),
        onSuccess: (_value, variables) => {
          if (!variables.projectId) return;
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.researchInputs(variables.projectId),
            exact: true,
          });
        },
      }),
    researchInputBindToDraft: () =>
      mutationOptions({
        mutationKey: ["workspace", "research-input", "bind-draft"],
        retry: false,
        mutationFn: ({
          inputId,
          projectId,
          draftId,
        }: BindResearchInputToDraftVariables) =>
          repositories.researchInputs.bindToDraft(inputId, projectId, draftId),
      }),
    revisionFeedbackCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "revision", "feedback"],
        retry: false,
        mutationFn: (variables: CreateRevisionFeedbackVariables) =>
          repositories.revisions.createFeedback({
            artifactId: variables.artifactId,
            artifactVersionId: variables.artifactVersionId,
            expectedVersionNumber: variables.expectedVersionNumber,
            summary: variables.summary,
            requestedChange: variables.requestedChange,
            idempotencyKey: idempotency.keyFor(
              "revision.feedback.create",
              variables,
            ),
          }),
        onSuccess: (_feedback, variables) => {
          idempotency.complete("revision.feedback.create", variables);
        },
      }),
    revisionPlanCreate: () =>
      mutationOptions({
        mutationKey: ["workspace", "revision", "plan", "create"],
        retry: false,
        mutationFn: (variables: CreateRevisionPlanVariables) =>
          repositories.revisions.createPlan({
            projectId: variables.projectId,
            feedbackId: variables.feedbackId,
            expectedParentRunRevision: variables.expectedParentRunRevision,
            idempotencyKey: idempotency.keyFor(
              "revision.plan.create",
              variables,
            ),
          }),
        onSuccess: (_plan, variables) => {
          idempotency.complete("revision.plan.create", variables);
        },
      }),
    revisionPlanConfirm: () =>
      mutationOptions({
        mutationKey: ["workspace", "revision", "plan", "confirm"],
        retry: false,
        mutationFn: async (variables: ConfirmRevisionPlanVariables) =>
          researchAdapter.toRunViewModel(
            await repositories.revisions.confirmPlan(
              variables.planId,
              variables.expectedPlanVersion,
              idempotency.keyFor("revision.plan.confirm", variables),
            ),
          ),
        onSuccess: (run, variables) => {
          idempotency.complete("revision.plan.confirm", variables);
          queryClient.setQueryData(
            workspaceQueryKeys.run(variables.projectId, run.id),
            run,
          );
          void _invalidateRunState(queryClient, variables.projectId, run.id);
        },
      }),
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
    runCancel: () =>
      mutationOptions({
        mutationKey: ["workspace", "run", "cancel"],
        retry: false,
        mutationFn: async (
          variables: RunLifecycleVariables,
        ): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await repositories.runs.cancel(variables.runId),
          ),
        onSuccess: (run, variables) => {
          void _invalidateRunState(queryClient, variables.projectId, run.id);
        },
      }),
    runRetry: () =>
      mutationOptions({
        mutationKey: ["workspace", "run", "retry"],
        retry: false,
        mutationFn: async (
          variables: RunLifecycleVariables,
        ): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await repositories.runs.retry(
              variables.runId,
              idempotency.keyFor("run.retry", variables),
            ),
          ),
        onSuccess: (run, variables) => {
          idempotency.complete("run.retry", variables);
          void _invalidateRunState(queryClient, variables.projectId, run.id);
        },
      }),
    checkpointDecisionSubmit: () =>
      mutationOptions({
        mutationKey: ["workspace", "run", "checkpoint-decision"],
        retry: false,
        mutationFn: async (
          variables: CheckpointDecisionVariables,
        ): Promise<ResearchRunViewModel> =>
          researchAdapter.toRunViewModel(
            await repositories.runs.submitCheckpointDecision(variables.runId, {
              ...variables.decision,
            }),
          ),
        onSuccess: (run, variables) => {
          void _invalidateRunState(queryClient, variables.projectId, run.id);
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
            queryKey: workspaceQueryKeys.projectScope(variables.projectId),
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
              idempotencyKey: variables.actionId,
            } satisfies SubmitResearchTurnInput),
          ),
        onSuccess: (turn, variables) => {
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
          void queryClient.invalidateQueries({
            queryKey: workspaceQueryKeys.thread(variables.projectId),
            exact: true,
          });
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
            {
              type: "contract.draft.update",
              draftId: variables.draftId,
              expectedVersion: variables.expectedVersion,
              input: variables.input,
            },
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
        onSuccess: (draft, variables) => {
          queryClient.setQueryData(
            workspaceQueryKeys.draft(variables.projectId, draft.id),
            draft,
          );
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
            workspaceQueryKeys.contract(variables.projectId, contract.id),
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
          queryClient.setQueryData(
            workspaceQueryKeys.run(variables.projectId, run.id),
            run,
          );
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
