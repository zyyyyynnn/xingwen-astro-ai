import { mutationOptions, type QueryClient } from "@tanstack/react-query";
import type {
  CreateResearchProjectInput,
  RepositorySet,
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
} from "@xingwen/research-adapter";

import { workspaceQueryKeys } from "./query-keys";

interface WorkspaceMutationDependencies {
  readonly repositories: Pick<RepositorySet, "projects" | "contracts" | "runs">;
  readonly researchAdapter: ResearchAdapter;
  readonly queryClient: QueryClient;
  readonly createIdempotencyKey: () => string;
}

export interface CreateDraftVariables {
  readonly projectId: DomainEntityId;
  readonly intent: string;
  readonly contract: ResearchContractInput;
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
            { idempotencyKey: createIdempotencyKey() },
          );
          if (command.type !== "project.create") {
            throw new Error("Project create command mapping failed.");
          }
          return researchAdapter.toProjectViewModel(
            await repositories.projects.create(command.input),
          );
        },
        onSuccess: (project) => {
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
            { idempotencyKey: createIdempotencyKey() },
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
        onSuccess: (draft) => {
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
            { idempotencyKey: createIdempotencyKey() },
          );
          if (command.type !== "run.create") {
            throw new Error("Run create command mapping failed.");
          }
          return researchAdapter.toRunViewModel(
            await repositories.runs.create(command.input),
          );
        },
        onSuccess: (run) => {
          queryClient.setQueryData(workspaceQueryKeys.run(run.id), run);
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
