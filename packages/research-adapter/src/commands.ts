import type {
  CreateResearchContractDraftInput,
  CreateResearchProjectInput,
  CreateResearchRunInput,
  UpdateResearchContractDraftInput,
} from "@xingwen/data-access";
import type {
  CreateShareSnapshotRequest,
  DomainEntityId,
  ExecutionMode,
} from "@xingwen/domain";

export interface CommandContext {
  readonly idempotencyKey: string;
}

export type ApplicationIntent =
  | {
      readonly type: "project.create";
      readonly input: Omit<CreateResearchProjectInput, "idempotencyKey">;
    }
  | {
      readonly type: "contract.draft.create";
      readonly projectId: DomainEntityId;
      readonly input: Omit<CreateResearchContractDraftInput, "idempotencyKey">;
    }
  | {
      readonly type: "contract.draft.update";
      readonly draftId: DomainEntityId;
      readonly expectedVersion: number;
      readonly input: UpdateResearchContractDraftInput;
    }
  | {
      readonly type: "contract.confirm";
      readonly projectId: DomainEntityId;
      readonly draftId: DomainEntityId;
      readonly expectedDraftVersion: number;
    }
  | {
      readonly type: "run.create";
      readonly projectId: DomainEntityId;
      readonly contractId: DomainEntityId;
      readonly executionMode: ExecutionMode;
    }
  | {
      readonly type: "share.create";
      readonly projectId: DomainEntityId;
      readonly request: CreateShareSnapshotRequest;
    }
  | {
      readonly type: "share.revoke";
      readonly projectId: DomainEntityId;
      readonly shareId: DomainEntityId;
    };

export type ApplicationCommand =
  | {
      readonly type: "project.create";
      readonly input: CreateResearchProjectInput;
    }
  | {
      readonly type: "contract.draft.create";
      readonly projectId: DomainEntityId;
      readonly input: CreateResearchContractDraftInput;
    }
  | {
      readonly type: "contract.draft.update";
      readonly draftId: DomainEntityId;
      readonly expectedVersion: number;
      readonly input: UpdateResearchContractDraftInput;
    }
  | {
      readonly type: "contract.confirm";
      readonly projectId: DomainEntityId;
      readonly draftId: DomainEntityId;
      readonly expectedDraftVersion: number;
    }
  | {
      readonly type: "run.create";
      readonly input: CreateResearchRunInput;
    }
  | {
      readonly type: "share.create";
      readonly projectId: DomainEntityId;
      readonly request: CreateShareSnapshotRequest;
    }
  | {
      readonly type: "share.revoke";
      readonly projectId: DomainEntityId;
      readonly shareId: DomainEntityId;
    };

function assertNever(value: never): never {
  throw new Error(`Unsupported application intent: ${String(value)}`);
}

export function toApplicationCommand(
  intent: ApplicationIntent,
  context: CommandContext,
): ApplicationCommand {
  switch (intent.type) {
    case "project.create":
      return {
        type: intent.type,
        input: {
          ...intent.input,
          idempotencyKey: context.idempotencyKey,
        },
      };
    case "contract.draft.create":
      return {
        type: intent.type,
        projectId: intent.projectId,
        input: {
          ...intent.input,
          idempotencyKey: context.idempotencyKey,
        },
      };
    case "contract.draft.update":
      return {
        type: intent.type,
        draftId: intent.draftId,
        expectedVersion: intent.expectedVersion,
        input: intent.input,
      };
    case "contract.confirm":
      return {
        type: intent.type,
        projectId: intent.projectId,
        draftId: intent.draftId,
        expectedDraftVersion: intent.expectedDraftVersion,
      };
    case "run.create":
      return {
        type: intent.type,
        input: {
          projectId: intent.projectId,
          contractId: intent.contractId,
          executionMode: intent.executionMode,
          idempotencyKey: context.idempotencyKey,
        },
      };
    case "share.create":
      return {
        type: intent.type,
        projectId: intent.projectId,
        request: intent.request,
      };
    case "share.revoke":
      return {
        type: intent.type,
        projectId: intent.projectId,
        shareId: intent.shareId,
      };
    default:
      return assertNever(intent);
  }
}
