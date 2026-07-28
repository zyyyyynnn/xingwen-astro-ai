/**
 * Pure state transitions for the paper acquisition review feature (A-05).
 *
 * No React, no transport: load-state classification, candidate filtering and
 * small display helpers. Filtering never reorders candidates — the server
 * ranking (already labelled by `stableRank`) is authoritative and filters only
 * hide rows.
 */

import type {
  PaperAcquisitionReview,
  PaperCandidateReview,
} from "@xingwen/domain";

/** Exhaustive review load state; `ready` still carries partial acquisitions. */
export type PaperReviewState =
  | { readonly status: "idle" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly review: PaperAcquisitionReview }
  | { readonly status: "empty" }
  | { readonly status: "rate_limited"; readonly retryAfterMs: number | null }
  | { readonly status: "source_failed" }
  | { readonly status: "network_error" }
  | { readonly status: "invalid" };

/**
 * Classify a `getReview` failure into a review state. Error identity uses
 * `name`/shape rather than `instanceof` so the classification stays stable
 * across bundle boundaries; unknown failures degrade to `network_error`
 * because a re-read is the only safe next step.
 */
export function classifyPaperReviewError(error: unknown): PaperReviewState {
  if (!(error instanceof Error)) return { status: "network_error" };
  switch (error.name) {
    case "NotFoundError":
      return { status: "empty" };
    case "RateLimitedError": {
      const retryAfterMs = (error as { retryAfterMs?: unknown }).retryAfterMs;
      return {
        status: "rate_limited",
        retryAfterMs: typeof retryAfterMs === "number" ? retryAfterMs : null,
      };
    }
    case "UpstreamError":
      return { status: "source_failed" };
    case "ValidationError":
    case "FixtureValidationError":
      return { status: "invalid" };
    default:
      return { status: "network_error" };
  }
}

export type SelectionFilter = "all" | "selected" | "excluded";
export type GroupingFilter = "all" | "duplicates" | "conflicts";

export interface CandidateFilter {
  readonly text: string;
  readonly selection: SelectionFilter;
  readonly sourceId: string;
  readonly grouping: GroupingFilter;
}

export const EMPTY_CANDIDATE_FILTER: CandidateFilter = {
  text: "",
  selection: "all",
  sourceId: "all",
  grouping: "all",
};

/** A candidate belongs to a duplicate group with more than one member. */
export function isDuplicateCandidate(candidate: PaperCandidateReview): boolean {
  return candidate.duplicateGroup.candidateIds.length > 1;
}

/** A candidate whose duplicate group carries conflicts or uncertain matches. */
export function hasConflicts(candidate: PaperCandidateReview): boolean {
  return candidate.duplicateGroup.conflicts.length > 0;
}

/**
 * Apply the review filters while preserving the original server order. The
 * returned candidates keep their original `stableRank` labels untouched.
 */
export function filterCandidates(
  candidates: readonly PaperCandidateReview[],
  filter: CandidateFilter,
): readonly PaperCandidateReview[] {
  const text = filter.text.trim().toLowerCase();
  return candidates.filter((candidate) => {
    if (
      filter.selection === "selected" &&
      candidate.selection.kind !== "selected"
    ) {
      return false;
    }
    if (
      filter.selection === "excluded" &&
      candidate.selection.kind !== "excluded"
    ) {
      return false;
    }
    if (
      filter.sourceId !== "all" &&
      String(candidate.sourceSnapshot.sourceId) !== filter.sourceId
    ) {
      return false;
    }
    if (filter.grouping === "duplicates" && !isDuplicateCandidate(candidate)) {
      return false;
    }
    if (filter.grouping === "conflicts" && !hasConflicts(candidate)) {
      return false;
    }
    if (text.length > 0) {
      const haystack = [candidate.title, ...candidate.authors]
        .join(" ")
        .toLowerCase();
      if (!haystack.includes(text)) return false;
    }
    return true;
  });
}

/** Distinct source ids in review order, for the source filter control. */
export function sourceIdsOf(review: PaperAcquisitionReview): readonly string[] {
  return review.sourceExecutions.map((execution) => String(execution.sourceId));
}

/** Failed source executions listed in the partial/failure banners. */
export function failedSourceExecutions(review: PaperAcquisitionReview) {
  return review.sourceExecutions.filter(
    (execution) => execution.status === "failed",
  );
}

/** Human label for the review's source mode; never infers beyond the domain. */
export function sourceModeLabel(review: PaperAcquisitionReview): string {
  switch (review.sourceMode) {
    case "fixture":
      return "Fixture / Demo Replay";
    case "cached":
      return "Cached";
    case "live":
      return "Live";
  }
}
