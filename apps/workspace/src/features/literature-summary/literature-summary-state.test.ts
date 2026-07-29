/**
 * Unit tests for the A-06 literature summary pure helpers, driven by the real
 * pipeline-generated B-07 fixture assembled into the domain review.
 */

import {
  assemblePaperSummaryReview,
  NetworkError,
  NotFoundError,
  paperSummaryReadFixture,
  RateLimitedError,
  UpstreamError,
  ValidationError,
} from "@xingwen/data-access";
import { describe, expect, it } from "vitest";

import {
  allStatements,
  classifyPaperSummaryError,
  genericEvidenceForStatement,
  summaryEvidenceForStatement,
  summarySourceModeLabel,
  supportStatusLabel,
} from "./literature-summary-state";

const review = assemblePaperSummaryReview(paperSummaryReadFixture);

describe("classifyPaperSummaryError", () => {
  it("maps the explicit empty-summary 404 code to empty", () => {
    expect(
      classifyPaperSummaryError(
        new NotFoundError("empty", "PAPER_SUMMARY_EMPTY"),
      ),
    ).toEqual({ status: "empty" });
  });

  it("maps any other 404 code to unavailable, never empty", () => {
    expect(
      classifyPaperSummaryError(
        new NotFoundError("missing", "RESOURCE_NOT_FOUND"),
      ),
    ).toEqual({ status: "unavailable" });
    // The A-05 empty code belongs to a different artifact kind.
    expect(
      classifyPaperSummaryError(
        new NotFoundError("other", "PAPER_COLLECTION_EMPTY"),
      ),
    ).toEqual({ status: "unavailable" });
  });

  it("maps contract validation failures to invalid", () => {
    expect(
      classifyPaperSummaryError(
        new ValidationError("bad", "SCHEMA_VALIDATION_FAILED", []),
      ),
    ).toEqual({ status: "invalid" });
  });

  it("degrades every other failure to network_error", () => {
    expect(classifyPaperSummaryError(new NetworkError("offline"))).toEqual({
      status: "network_error",
    });
    expect(
      classifyPaperSummaryError(new RateLimitedError("slow", 1000)),
    ).toEqual({ status: "network_error" });
    expect(
      classifyPaperSummaryError(new UpstreamError("bad", "X", 502)),
    ).toEqual({ status: "network_error" });
    expect(classifyPaperSummaryError("not-an-error")).toEqual({
      status: "network_error",
    });
  });
});

describe("supportStatusLabel", () => {
  it("labels each server-validated status in plain Chinese", () => {
    expect(supportStatusLabel("supported")).toBe("有证据支持");
    expect(supportStatusLabel("unsupported")).toBe("无证据（未证实）");
    expect(supportStatusLabel("unverifiable")).toBe("证据不可核验");
  });
});

describe("allStatements", () => {
  it("returns the five regions in fixed reading order", () => {
    const regions = allStatements(review);
    expect(regions.map((region) => region.key)).toEqual([
      "research_goal",
      "method",
      "dataset",
      "findings",
      "limitations_future_work",
    ]);
    expect(regions.map((region) => region.title)).toEqual([
      "研究目标",
      "研究方法",
      "使用数据集",
      "核心发现",
      "局限与未来工作",
    ]);
  });

  it("groups the fixture statements with their real ids and statuses", () => {
    const regions = allStatements(review);
    expect(
      regions[0]?.statements.map((item) => String(item.statementId)),
    ).toEqual(["stmt.research_goal"]);
    expect(regions[1]?.statements[0]?.status).toBe("unverifiable");
    expect(regions[2]?.statements[0]?.status).toBe("supported");
    expect(
      regions[3]?.statements.map((item) => String(item.statementId)),
    ).toEqual(["stmt.finding_doi"]);
    // Limitations and future work merge into one region; the fixture has an
    // unsupported limitation and no future work.
    expect(regions[4]?.statements.map((item) => item.status)).toEqual([
      "unsupported",
    ]);
  });

  it("keeps empty regions instead of dropping them", () => {
    const bare = { ...review, researchGoal: null, findings: [] };
    const regions = allStatements(bare);
    expect(regions).toHaveLength(5);
    expect(regions[0]?.statements).toEqual([]);
    expect(regions[3]?.statements).toEqual([]);
  });
});

describe("genericEvidenceForStatement", () => {
  it("finds the generic Evidence whose targetId equals the statement id", () => {
    const goal = review.researchGoal!;
    const evidence = genericEvidenceForStatement(review, goal.statementId);
    expect(String(evidence?.id)).toBe("evd_papsum_03");
    expect(String(evidence?.targetId)).toBe("stmt.research_goal");
  });

  it("returns null when no generic Evidence targets the statement", () => {
    const limitation = review.limitations[0]!;
    expect(
      genericEvidenceForStatement(review, limitation.statementId),
    ).toBeNull();
  });
});

describe("summaryEvidenceForStatement", () => {
  it("matches statement.evidenceIds against summaryEvidence in order", () => {
    const goal = review.researchGoal!;
    const items = summaryEvidenceForStatement(review, goal);
    expect(items.map((item) => String(item.evidenceId))).toEqual([
      "ev.goal_title",
    ]);
    expect(items[0]?.quoteOrValue).toBe(
      "The Revised TESS Input Catalog and Candidate Target List",
    );
  });

  it("returns nothing for a statement without evidence ids", () => {
    const limitation = review.limitations[0]!;
    expect(summaryEvidenceForStatement(review, limitation)).toEqual([]);
  });
});

describe("summarySourceModeLabel", () => {
  it("labels each source mode without touching execution mode", () => {
    expect(summarySourceModeLabel("fixture")).toBe("Fixture");
    expect(summarySourceModeLabel("cached")).toBe("Cached");
    expect(summarySourceModeLabel("live")).toBe("Live");
  });
});
