/**
 * Pure state tests for the paper acquisition review feature.
 *
 * Stable ranking must never change under filtering; selection reasons must
 * not be conflated; duplicate/conflict filters must match the real pipeline
 * output; error classification must be exhaustive (incl. the non-empty 404
 * path); execution/source mode labels are orthogonal; unsafe external URLs
 * must never become links.
 */

import { describe, expect, it } from "vitest";
import {
  createFixtureRepositories,
  exoplanetHostStarFixture,
  NetworkError,
  NotFoundError,
  RateLimitedError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
} from "@xingwen/data-access";
import { safeExternalUrl } from "@xingwen/domain";
import type { PaperAcquisitionReview } from "@xingwen/domain";

import {
  classifyPaperReviewError,
  EMPTY_CANDIDATE_FILTER,
  executionModeLabel,
  filterCandidates,
  hasConflicts,
  isDuplicateCandidate,
  sourceIdsOf,
  sourceModeLabel,
} from "./paper-acquisition-state";

const VERSION_ID = "artv_papcol_01" as never;

async function loadReview(): Promise<PaperAcquisitionReview> {
  const repos = createFixtureRepositories(exoplanetHostStarFixture);
  return repos.paperAcquisition.getReview(VERSION_ID);
}

describe("filterCandidates — stable ranking", () => {
  it("keeps the original stableRank labels for every filtered subset", async () => {
    const review = await loadReview();
    const excludedOnly = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      selection: "excluded",
    });
    // Ranks come from the review itself so the assertion cannot silently
    // renumber: the excluded subset must keep its server ranks verbatim.
    const expectedExcludedRanks = review.candidates
      .filter((item) => item.selection.kind === "excluded")
      .map((item) => item.stableRank);
    expect(excludedOnly.map((item) => item.stableRank)).toEqual(
      expectedExcludedRanks,
    );
    expect(expectedExcludedRanks).toEqual([2, 5, 6, 7]);

    const textOnly = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      text: "revised tess input catalog",
    });
    expect(textOnly.map((item) => item.stableRank)).toEqual([3]);
  });

  it("never reorders candidates relative to the server ranking", async () => {
    const review = await loadReview();
    const all = filterCandidates(review.candidates, EMPTY_CANDIDATE_FILTER);
    expect(all.map((item) => String(item.candidateId))).toEqual(
      review.candidates.map((item) => String(item.candidateId)),
    );
  });
});

describe("filterCandidates — selection, source, duplicates, conflicts", () => {
  it("separates selection and exclusion reasons without conflation", async () => {
    const review = await loadReview();
    const selected = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      selection: "selected",
    });
    expect(selected).toHaveLength(3);
    for (const candidate of selected) {
      expect(candidate.selection.kind).toBe("selected");
      expect(candidate.selection.reason).toBe(
        "highest ranked representative within selection limit",
      );
    }
    const excluded = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      selection: "excluded",
    });
    expect(excluded).toHaveLength(4);
    for (const candidate of excluded) {
      expect(candidate.selection.kind).toBe("excluded");
      expect(candidate.selection.reason).toMatch(
        /^duplicate of higher-ranked candidate |^selection limit reached/u,
      );
    }
  });

  it("filters by source id with distinct first-appearance ids", async () => {
    const review = await loadReview();
    expect(sourceIdsOf(review)).toEqual(["crossref"]);
    const crossrefOnly = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      sourceId: "crossref",
    });
    expect(crossrefOnly).toHaveLength(7);
    const none = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      sourceId: "arxiv",
    });
    expect(none).toHaveLength(0);
  });

  it("filters duplicate groups and conflicts correctly", async () => {
    const review = await loadReview();
    const duplicates = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      grouping: "duplicates",
    });
    // The same-DOI pair is the only multi-member duplicate group.
    expect(duplicates.map((item) => item.stableRank)).toEqual([1, 2]);
    for (const candidate of duplicates) {
      expect(isDuplicateCandidate(candidate)).toBe(true);
    }
    const conflicts = filterCandidates(review.candidates, {
      ...EMPTY_CANDIDATE_FILTER,
      grouping: "conflicts",
    });
    // Title conflict inside the DOI pair + the uncertain title/year match.
    expect(conflicts.map((item) => item.stableRank)).toEqual([1, 2, 5, 6]);
    for (const candidate of conflicts) {
      expect(hasConflicts(candidate)).toBe(true);
    }
  });
});

describe("classifyPaperReviewError — exhaustive branches", () => {
  it("classifies every typed repository failure", () => {
    expect(
      classifyPaperReviewError(
        new NotFoundError("empty", "PAPER_COLLECTION_EMPTY"),
      ),
    ).toEqual({ status: "empty" });
    // A non-empty 404 (missing/inaccessible version) is never an empty state.
    expect(
      classifyPaperReviewError(
        new NotFoundError("missing", "RESOURCE_NOT_FOUND"),
      ),
    ).toEqual({ status: "unavailable" });
    expect(
      classifyPaperReviewError(new RateLimitedError("slow down", 30_000)),
    ).toEqual({ status: "rate_limited", retryAfterMs: 30_000 });
    expect(
      classifyPaperReviewError(
        new UpstreamError("bad upstream", "PAPER_SOURCE_FAILED", 502),
      ),
    ).toEqual({ status: "source_failed" });
    expect(
      classifyPaperReviewError(
        new ValidationError("bad payload", "SCHEMA_VALIDATION_FAILED", []),
      ),
    ).toEqual({ status: "invalid" });
    expect(classifyPaperReviewError(new NetworkError("offline"))).toEqual({
      status: "network_error",
    });
    // Unknown failures degrade to a retryable network error.
    expect(
      classifyPaperReviewError(new UnexpectedHttpError("odd", 500, null)),
    ).toEqual({ status: "network_error" });
    expect(classifyPaperReviewError("not-an-error")).toEqual({
      status: "network_error",
    });
  });
});

describe("execution/source mode labels stay orthogonal", () => {
  it("labels execution mode independently of source mode", async () => {
    const review = await loadReview();
    expect(sourceModeLabel(review)).toBe("Fixture");
    expect(executionModeLabel("demo_replay")).toBe("Demo Replay");
    expect(executionModeLabel("live")).toBe("Live");
    expect(executionModeLabel(null)).toBe("未知");
    // No label ever contains the other axis.
    expect(sourceModeLabel(review)).not.toContain("Demo Replay");
    expect(executionModeLabel("demo_replay")).not.toContain("Fixture");
  });
});

describe("safeExternalUrl", () => {
  it("accepts only http(s) URLs and rejects everything else", () => {
    expect(safeExternalUrl("https://arxiv.org/abs/2405.01234")).toBe(
      "https://arxiv.org/abs/2405.01234",
    );
    expect(safeExternalUrl("http://example.org/x")).toBe(
      "http://example.org/x",
    );
    expect(safeExternalUrl("ftp://mirror.example.org/flares.pdf")).toBeNull();
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("data:text/html,hi")).toBeNull();
    expect(safeExternalUrl("https://bad url with spaces")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
  });
});
