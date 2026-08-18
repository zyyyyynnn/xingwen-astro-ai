import { useState } from "react";

export type ResearchInspectorTab = "overview" | "results";

/**
 * Product-owned workspace UI state that has no durable owner. Sidebar and
 * Rail preferences belong to their own owners (upstream sidebar store and the
 * rail owner) and are deliberately not duplicated here.
 */
export function useResearchWorkspaceState() {
  const [dockedTab, setDockedTab] = useState<ResearchInspectorTab>("overview");
  const [reviewOpen, setReviewOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [answerToQuestionId, setAnswerToQuestionId] = useState<string | null>(
    null,
  );
  const [pendingTurn, setPendingTurn] = useState<{
    readonly actionId: string;
    readonly message: string;
  } | null>(null);

  return {
    dockedTab,
    setDockedTab,
    reviewOpen,
    setReviewOpen,
    message,
    setMessage,
    answerToQuestionId,
    setAnswerToQuestionId,
    pendingTurn,
    setPendingTurn,
  };
}
