/**
 * Literature comparison grid tests (A-06): one real fixture summary plus a
 * stubbed second summary, asserting per-column isolation — each column keeps
 * its own version/source identity and empty slots stay explicit.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import {
  assemblePaperSummaryReview,
  paperSummaryReadFixture,
} from "@xingwen/data-access";
import type { PaperSummaryReview } from "@xingwen/domain";
import { afterEach, describe, expect, it } from "vitest";

import { LiteratureComparisonGrid } from "./literature-comparison-grid";

const fixtureReview = assemblePaperSummaryReview(paperSummaryReadFixture);

/** A second summary stub: same shape, distinct identity and statements. */
function secondReview(): PaperSummaryReview {
  return {
    ...fixtureReview,
    artifactVersionId: "artv_papsum_02" as never,
    paperId: "pap_second_01" as never,
    sourceMode: "cached",
    researchGoal:
      fixtureReview.researchGoal === null
        ? null
        : {
            ...fixtureReview.researchGoal,
            statementId: "stmt.second_goal" as never,
            text: "Second paper goal statement for column isolation.",
            status: "unsupported",
          },
    method: null,
    findings: [],
  };
}

afterEach(() => {
  cleanup();
});

describe("LiteratureComparisonGrid", () => {
  it("renders one summary plus explicit empty slots for the rest", () => {
    render(<LiteratureComparisonGrid summaries={[fixtureReview]} />);

    const first = screen.getByRole("article", { name: "对比列 1" });
    expect(first).toHaveTextContent(
      `ArtifactVersion ${String(fixtureReview.artifactVersionId)}`,
    );
    expect(first).toHaveTextContent("source: Fixture");

    for (const slot of ["对比列 2（空）", "对比列 3（空）"]) {
      const empty = screen.getByRole("article", { name: slot });
      expect(empty).toHaveTextContent("空槽位：未选择文献总结。");
    }
  });

  it("keeps each column's version, source and statuses isolated", () => {
    render(
      <LiteratureComparisonGrid summaries={[fixtureReview, secondReview()]} />,
    );

    const first = within(screen.getByRole("article", { name: "对比列 1" }));
    const second = within(screen.getByRole("article", { name: "对比列 2" }));

    // Column 1 keeps the fixture identity and its supported/unverifiable mix.
    expect(
      first.getByText(`paper ${String(fixtureReview.paperId)}`),
    ).toBeInTheDocument();
    expect(first.getByText("source: Fixture")).toBeInTheDocument();
    expect(
      first.getByText(fixtureReview.researchGoal!.text),
    ).toBeInTheDocument();
    expect(first.getByText("证据不可核验")).toBeInTheDocument();

    // Column 2 keeps its own identity; nothing leaks across columns.
    expect(second.getByText("paper pap_second_01")).toBeInTheDocument();
    expect(second.getByText("source: Cached")).toBeInTheDocument();
    expect(
      second.getByText("Second paper goal statement for column isolation."),
    ).toBeInTheDocument();
    expect(second.getByText("无证据（未证实）")).toBeInTheDocument();
    // The stub has no method/findings: stated, never merged from column 1.
    expect(second.getAllByText("无陈述。")).toHaveLength(2);
    expect(
      second.queryByText(fixtureReview.researchGoal!.text),
    ).not.toBeInTheDocument();
    expect(
      first.queryByText("Second paper goal statement for column isolation."),
    ).not.toBeInTheDocument();
  });
});
