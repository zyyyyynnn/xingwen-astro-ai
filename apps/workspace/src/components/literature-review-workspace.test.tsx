import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  asEntityId,
  type NonEmptyString,
  type PublicArtifactPresentation,
  type PublicPresentationEntry,
} from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiteratureReviewWorkspace } from "./literature-review-workspace";

function text(value: string): NonEmptyString {
  return value as NonEmptyString;
}

function relation(
  id: string,
  title: string,
  canAdjudicate: boolean | null,
): PublicPresentationEntry {
  return {
    key: text(id),
    title: text(title),
    externalUrl: null,
    status: text("candidate"),
    assessment: text("supports · positive"),
    paragraphs: [text(`${title} 的公开关系说明。`)],
    facts: [
      { label: text("可比较性"), values: [text("可比较")] },
      { label: text("条件"), values: [text("同一观测口径")] },
    ],
    evidenceIds: [asEntityId(`evidence-${id}`)],
    reasoningTrace: null,
    canAdjudicate,
    relation: {
      sourceClaim: text("观测主张 A"),
      targetClaim: text("对照主张 B"),
    },
  };
}

function presentation(
  entries: readonly PublicPresentationEntry[],
): PublicArtifactPresentation {
  return {
    kind: "literature_relations",
    summary: text("对已接纳声明之间的科学关系进行核验。"),
    facts: [],
    sections: [],
    entries,
    tables: [],
    graphNodes: [],
    graphEdges: [],
  };
}

afterEach(cleanup);

describe("LiteratureReviewWorkspace", () => {
  it("shows adjudication actions only for an explicitly adjudicable relation", () => {
    const onRequestRevision = vi.fn();
    render(
      <LiteratureReviewWorkspace
        title="关系审定"
        presentation={presentation([
          relation("relation-adjudicable", "可审定关系", true),
          relation("relation-locked", "不可审定关系", false),
          relation("relation-unknown", "审定能力未知", null),
        ])}
        onRequestRevision={onRequestRevision}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "选择可审定关系" }));
    expect(screen.getByText("观测主张 A")).toBeVisible();
    expect(screen.getByText("对照主张 B")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "接受并进入图谱" }));
    expect(onRequestRevision).toHaveBeenCalledWith({
      kind: "relation_adjudication",
      relationId: asEntityId("relation-adjudicable"),
      decision: "accepted",
    });

    fireEvent.click(screen.getByRole("button", { name: "选择不可审定关系" }));
    expect(screen.queryByRole("button", { name: "接受并进入图谱" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "选择审定能力未知" }));
    expect(
      screen.queryByRole("button", { name: "拒绝且不进入图谱" }),
    ).toBeNull();
  });
});
