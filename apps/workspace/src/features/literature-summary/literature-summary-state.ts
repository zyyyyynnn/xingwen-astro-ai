/**
 * Pure state transitions and helpers for the literature summary reading
 * feature (A-06).
 *
 * No React, no transport: load-state classification, statement grouping into
 * the five reading regions, and lookup helpers binding a statement to its
 * inline summary evidence and to the generic B-18 Evidence record that drives
 * the Provenance Observatory. Support status is never inferred here — it is
 * carried verbatim from the server-validated review.
 */

import type {
  DomainEntityId,
  Evidence,
  PaperSummaryEvidenceReview,
  PaperSummaryReview,
  PaperSummaryStatementReview,
  PaperSummarySupportStatus,
  SourceMode,
} from "@xingwen/domain";

import { classifyPaperReviewError } from "../paper-acquisition/paper-acquisition-state";

/** Exhaustive summary load state for the reading workspace. */
export type PaperSummaryReviewState =
  | { readonly status: "idle" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly review: PaperSummaryReview }
  | { readonly status: "empty" }
  | { readonly status: "unavailable" }
  | { readonly status: "network_error" }
  | { readonly status: "invalid" };

/**
 * Classify a `getSummary` failure into a summary state, reusing the exact
 * A-05 error-name mapping (`classifyPaperReviewError`) for every branch
 * except the 404 code: a 404 only means "no summary" when the contract
 * explicitly reports `PAPER_SUMMARY_EMPTY`; any other 404 (missing or
 * inaccessible ArtifactVersion) is `unavailable`, never an empty result.
 * States the summary read cannot produce (rate limiting, upstream source
 * failure) degrade to `network_error` because a re-read is the only safe
 * next step.
 */
export function classifyPaperSummaryError(
  error: unknown,
): PaperSummaryReviewState {
  if (error instanceof Error && error.name === "NotFoundError") {
    const code = (error as { code?: unknown }).code;
    return code === "PAPER_SUMMARY_EMPTY"
      ? { status: "empty" }
      : { status: "unavailable" };
  }
  const base = classifyPaperReviewError(error);
  return base.status === "invalid"
    ? { status: "invalid" }
    : { status: "network_error" };
}

/**
 * Chinese support-status label. `unsupported` and `unverifiable` are stated
 * plainly — a statement is never presented as fact without evidence.
 */
export function supportStatusLabel(status: PaperSummarySupportStatus): string {
  switch (status) {
    case "supported":
      return "有证据支持";
    case "unsupported":
      return "无证据（未证实）";
    case "unverifiable":
      return "证据不可核验";
  }
}

export type SummaryRegionKey =
  | "research_goal"
  | "method"
  | "dataset"
  | "findings"
  | "limitations_future_work";

export interface SummaryStatementRegion {
  readonly key: SummaryRegionKey;
  readonly title: string;
  readonly statements: readonly PaperSummaryStatementReview[];
}

/**
 * The five reading regions in fixed order, each carrying its statements.
 * Regions with no statements are kept (rendered as explicitly empty) so the
 * reading layout never silently drops a region.
 */
export function allStatements(
  review: PaperSummaryReview,
): readonly SummaryStatementRegion[] {
  return [
    {
      key: "research_goal",
      title: "研究目标",
      statements: review.researchGoal === null ? [] : [review.researchGoal],
    },
    {
      key: "method",
      title: "研究方法",
      statements: review.method === null ? [] : [review.method],
    },
    {
      key: "dataset",
      title: "使用数据集",
      statements: review.dataset === null ? [] : [review.dataset],
    },
    { key: "findings", title: "核心发现", statements: review.findings },
    {
      key: "limitations_future_work",
      title: "局限与未来工作",
      statements: [...review.limitations, ...review.futureWork],
    },
  ];
}

/**
 * The generic B-18 Evidence record for a statement, if any. The B-07 service
 * sets the generic evidence `target_id` to the statement id, so the stable
 * link is `targetId === statementId`. Returns null when absent — the caller
 * must state the gap and never fabricate evidence.
 */
export function genericEvidenceForStatement(
  review: PaperSummaryReview,
  statementId: DomainEntityId,
): Evidence | null {
  return (
    review.evidence.find(
      (item) => String(item.targetId) === String(statementId),
    ) ?? null
  );
}

/**
 * The statement's inline summary evidence, matched via
 * `statement.evidenceIds → summaryEvidence.evidenceId` in the statement's
 * declared order.
 */
export function summaryEvidenceForStatement(
  review: PaperSummaryReview,
  statement: PaperSummaryStatementReview,
): readonly PaperSummaryEvidenceReview[] {
  return statement.evidenceIds
    .map(
      (evidenceId) =>
        review.summaryEvidence.find(
          (item) => String(item.evidenceId) === String(evidenceId),
        ) ?? null,
    )
    .filter((item): item is PaperSummaryEvidenceReview => item !== null);
}

/**
 * Human label for the summary's source mode. Never mixed with the run's
 * execution mode: `source_mode` and `execution_mode` are orthogonal facts.
 */
export function summarySourceModeLabel(mode: SourceMode): string {
  switch (mode) {
    case "fixture":
      return "Fixture";
    case "cached":
      return "Cached";
    case "live":
      return "Live";
  }
}
