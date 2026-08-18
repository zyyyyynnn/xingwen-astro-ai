import { useMutation } from "@tanstack/react-query";
import { parseEntityId, type DomainEntityId } from "@xingwen/domain";
import { toast } from "@xingwen/ui";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";

export interface UseResearchTurnSubmitOptions {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly resolveProjectId: () => Promise<DomainEntityId>;
  readonly setPendingTurn?: (
    turn: { readonly actionId: string; readonly message: string } | null,
  ) => void;
  readonly setMessage: (message: string) => void;
  readonly setAnswerToQuestionId?: (questionId: string | null) => void;
  readonly onProjectReady?: (projectId: DomainEntityId) => void;
}

function safeError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

/**
 * The single Workspace Composer submit seam.
 *
 * Existing Projects resolve immediately; the empty Workspace may create its
 * Project first. Message normalization, action identity, transient pending
 * state, clarification identity, failure restoration, and retry semantics stay
 * identical in both contexts.
 */
export function useResearchTurnSubmit({
  runtime,
  resolveProjectId,
  setPendingTurn,
  setMessage,
  setAnswerToQuestionId,
  onProjectReady,
}: UseResearchTurnSubmitOptions) {
  const submitTurn = useMutation(
    runtime.application.mutations.researchTurnSubmit(),
  );

  const submitMessage = async (
    nextMessage: string,
    answerToQuestionId: string | null,
  ) => {
    const outgoingMessage = nextMessage.trim();
    if (!outgoingMessage || submitTurn.isPending) return;

    const parsedAnswerId =
      answerToQuestionId === null ? null : parseEntityId(answerToQuestionId);
    if (answerToQuestionId !== null && parsedAnswerId === null) {
      throw new Error("澄清问题标识无效。");
    }

    const projectId = await resolveProjectId();
    const actionId = runtime.application.createResearchTurnActionId();
    setPendingTurn?.({ actionId, message: outgoingMessage });
    setMessage("");

    try {
      await submitTurn.mutateAsync({
        projectId,
        message: outgoingMessage,
        answerToQuestionId: parsedAnswerId,
        actionId,
      });
      setAnswerToQuestionId?.(null);
      onProjectReady?.(projectId);
    } catch (error) {
      setMessage(outgoingMessage);
      toast.error("消息发送失败", {
        description: safeError(runtime, error),
      });
      throw error;
    } finally {
      setPendingTurn?.(null);
    }
  };

  return {
    submitMessage,
    isSubmitting: submitTurn.isPending,
  };
}
