/**
 * Pure state transitions for the paper acquisition review feature (A-05).
 *
 * No React, no transport: load-state classification, candidate filtering and
 * small display helpers. Filtering never reorders candidates — the server
 * ranking (already labelled by `stableRank`) is authoritative and filters only
 * hide rows.
 */

import type {
  ExecutionMode,
  PaperAcquisitionReview,
  PaperCandidateConflictReview,
  PaperCandidateReview,
} from "@xingwen/domain";

/** Exhaustive review load state; `ready` still carries partial acquisitions. */
export type PaperReviewState =
  | { readonly status: "idle" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly review: PaperAcquisitionReview }
  | { readonly status: "empty" }
  | { readonly status: "unavailable" }
  | { readonly status: "rate_limited"; readonly retryAfterMs: number | null }
  | { readonly status: "source_failed" }
  | { readonly status: "network_error" }
  | { readonly status: "invalid" };

/**
 * Classify a `getReview` failure into a review state. Error identity uses
 * `name`/shape rather than `instanceof` so the classification stays stable
 * across bundle boundaries; unknown failures degrade to `network_error`
 * because a re-read is the only safe next step.
 *
 * A 404 only means "no candidates" when the contract explicitly reports
 * `PAPER_COLLECTION_EMPTY`; any other 404 (missing or inaccessible
 * ArtifactVersion) is surfaced as `unavailable`, never as an empty result.
 */
export function classifyPaperReviewError(error: unknown): PaperReviewState {
  if (!(error instanceof Error)) return { status: "network_error" };
  switch (error.name) {
    case "NotFoundError": {
      const code = (error as { code?: unknown }).code;
      return code === "PAPER_COLLECTION_EMPTY"
        ? { status: "empty" }
        : { status: "unavailable" };
    }
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

/**
 * Candidate- and group-level conflicts merged for review display, with
 * duplicates (same field/related/classification) collapsed.
 */
export function conflictsOf(
  candidate: PaperCandidateReview,
): readonly PaperCandidateConflictReview[] {
  const merged = [...candidate.conflicts];
  for (const conflict of candidate.duplicateGroup.conflicts) {
    const exists = merged.some(
      (item) =>
        item.field === conflict.field &&
        item.classification === conflict.classification &&
        String(item.relatedCandidateId) === String(conflict.relatedCandidateId),
    );
    if (!exists) merged.push(conflict);
  }
  return merged;
}

/** A candidate carrying any conflict or uncertain match. */
export function hasConflicts(candidate: PaperCandidateReview): boolean {
  return conflictsOf(candidate).length > 0;
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

/** Distinct source ids in first-appearance order, for the filter control. */
export function sourceIdsOf(review: PaperAcquisitionReview): readonly string[] {
  return [
    ...new Set(
      review.sourceExecutions.map((execution) => String(execution.sourceId)),
    ),
  ];
}

/** Failed source executions listed in the partial/failure banners. */
export function failedSourceExecutions(review: PaperAcquisitionReview) {
  return review.sourceExecutions.filter(
    (execution) => execution.status === "failed",
  );
}

/**
 * Human label for the collection's source mode. Never mixed with the run's
 * execution mode: `source_mode` and `execution_mode` are orthogonal facts.
 */
export function sourceModeLabel(review: PaperAcquisitionReview): string {
  switch (review.sourceMode) {
    case "fixture":
      return "Fixture";
    case "cached":
      return "Cached";
    case "live":
      return "Live";
  }
}

/** Human label for the owning ResearchRun's execution mode, display-only. */
export function executionModeLabel(mode: ExecutionMode | null): string {
  switch (mode) {
    case "demo_replay":
      return "Demo Replay";
    case "live":
      return "Live";
    case null:
      return "未知";
  }
}
