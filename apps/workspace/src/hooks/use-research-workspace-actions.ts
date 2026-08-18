import { useMutation } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import { toast } from "@xingwen/ui";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { useResearchTurnSubmit } from "../application/use-research-turn-submit";

function safeError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

export interface UseResearchWorkspaceActionsOptions {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly currentDraft: ResearchContractDraftViewModel | null;
  readonly currentContract: ResearchContractViewModel | null;
  readonly setPendingTurn: (
    turn: { readonly actionId: string; readonly message: string } | null,
  ) => void;
  readonly setMessage: (message: string) => void;
  readonly setAnswerToQuestionId: (questionId: string | null) => void;
}

export function useResearchWorkspaceActions({
  runtime,
  projectId,
  currentDraft,
  currentContract,
  setPendingTurn,
  setMessage,
  setAnswerToQuestionId,
}: UseResearchWorkspaceActionsOptions) {
  const { submitMessage, isSubmitting } = useResearchTurnSubmit({
    runtime,
    resolveProjectId: async () => projectId,
    setPendingTurn,
    setMessage,
    setAnswerToQuestionId,
  });
  const confirmContract = useMutation(
    runtime.application.mutations.contractConfirm(),
  );
  const updateDraft = useMutation(runtime.application.mutations.draftUpdate());
  const createRun = useMutation(runtime.application.mutations.runCreate());

  /**
   * One-action Confirm -> Run flow:
   * If a draft is active, confirms the draft and takes the returned confirmed contract.id,
   * then calls createRun with { contractId: confirmed.id }.
   * Draft.id is NEVER passed to createRun.
   */
  const confirmAndRun = async () => {
    try {
      let contractId: DomainEntityId | null = currentContract?.id ?? null;
      if (currentDraft) {
        const confirmed = await confirmContract.mutateAsync({
          projectId,
          draftId: currentDraft.id,
          expectedDraftVersion: currentDraft.version,
        });
        contractId = confirmed.id;
      }
      if (!contractId) {
        throw new Error("缺少有效的已确认研究协议。");
      }
      const executionMode =
        "provenance" in runtime.repositories ? "demo_replay" : "live";
      await createRun.mutateAsync({
        projectId,
        contractId,
        executionMode,
      });
    } catch (err) {
      toast.error("确认并启动研究失败", {
        description: safeError(runtime, err),
      });
      throw err;
    }
  };

  /**
   * G.3 recovery: the Contract is already confirmed and only the Run start
   * failed; retry CreateRun alone — no re-confirm, no rollback, no new Draft.
   */
  const retryRunStart = async () => {
    const contractId = currentContract?.id ?? null;
    if (!contractId) {
      throw new Error("缺少有效的已确认研究协议。");
    }
    const executionMode =
      "provenance" in runtime.repositories ? "demo_replay" : "live";
    try {
      await createRun.mutateAsync({ projectId, contractId, executionMode });
    } catch (err) {
      toast.error("重新启动研究失败", {
        description: safeError(runtime, err),
      });
      throw err;
    }
  };

  return {
    submitMessage,
    confirmAndRun,
    retryRunStart,
    isSubmitting,
    isConfirming: confirmContract.isPending || createRun.isPending,
    updateDraft,
    confirmContract,
    createRun,
  };
}
