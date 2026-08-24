import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type {
  ContentHash,
  DomainEntityId,
  NonEmptyString,
  PublicShareSnapshot,
  SemanticVersion,
  UtcIsoTimestamp,
} from "@xingwen/domain";
import { afterEach, describe, expect, it } from "vitest";

import { PublicShareView } from "./share-page";

afterEach(cleanup);

function id(value: string): DomainEntityId {
  return value as DomainEntityId;
}

const snapshot: PublicShareSnapshot = {
  id: id("share_01"),
  title: "系外行星候选研究" as NonEmptyString,
  redactionPolicy: "redacted_public_snapshot",
  createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
  expiresAt: "2026-09-24T08:00:00Z" as UtcIsoTimestamp,
  artifactVersions: [
    {
      id: id("artv_dataset"),
      artifactId: id("artifact_dataset"),
      kind: "dataset",
      title: "候选目标数据集" as NonEmptyString,
      versionNumber: 1,
      schemaVersion: "2.0.0" as SemanticVersion,
      contentHash: "content_hash" as ContentHash,
      sourceMode: "live",
      createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      content: {
        kind: "dataset",
        row_count: 2,
        field_count: 3,
        columns: [
          {
            field: {
              label_en: "hostname",
              meaning_zh: "宿主星名称",
              description: "目标天体的规范名称",
            },
          },
        ],
      },
      evidenceIds: [id("evidence_01")],
    },
  ],
  evidence: [
    {
      id: id("evidence_01"),
      artifactVersionId: id("artv_dataset"),
      sourceSnapshotId: id("snapshot_01"),
      locator: { page: 3, section: "Results" },
      quoteOrValue: "TOI-700 d is a temperate terrestrial planet.",
      createdAt: "2026-08-24T08:00:00Z" as UtcIsoTimestamp,
      source: {
        sourceId: "paper-source",
        sourceType: "paper",
        retrievedAt: "2026-08-23T08:00:00Z" as UtcIsoTimestamp,
        licenseNote: "公开论文元数据",
        requestMetadata: { source_url: "https://example.org/paper" },
      },
    },
  ],
};

describe("PublicShareView", () => {
  it("renders the frozen artifact through the shared renderer registry", () => {
    render(<PublicShareView snapshot={snapshot} />);

    expect(
      screen.getByRole("heading", { name: "系外行星候选研究" }),
    ).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "候选目标数据集" }),
    ).toBeVisible();
    expect(screen.getByText("2 条")).toBeVisible();
    expect(screen.getByText("宿主星名称")).toBeVisible();
    expect(screen.getByText(/冻结的公开副本/)).toBeVisible();
  });

  it("opens only the selected public evidence projection", () => {
    render(<PublicShareView snapshot={snapshot} />);

    fireEvent.click(screen.getByRole("button", { name: "查看证据 1" }));

    expect(screen.getByRole("heading", { name: "证据 1" })).toBeVisible();
    expect(
      screen.getByText("TOI-700 d is a temperate terrestrial planet."),
    ).toBeVisible();
    expect(screen.getByText("论文", { exact: true })).toBeVisible();
    expect(
      screen.queryByText("paper", { exact: true }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /打开原始来源/ })).toHaveAttribute(
      "href",
      "https://example.org/paper",
    );
  });

  it("renders literature taxonomy without exposing internal enum tokens", () => {
    const [baseVersion] = snapshot.artifactVersions;
    if (!baseVersion)
      throw new Error("public share fixture requires an artifact");
    render(
      <PublicShareView
        snapshot={{
          ...snapshot,
          artifactVersions: [
            {
              ...baseVersion,
              id: id("artv_relations"),
              artifactId: id("artifact_relations"),
              kind: "literature_relations",
              title: "文献关系" as NonEmptyString,
              content: {
                relations: [
                  { relation_type: "compares_method", status: "accepted" },
                  { text: "候选发现", claim_type: "finding" },
                  { text: "作用方向", polarity: "positive" },
                ],
              },
              evidenceIds: [],
            },
          ],
          evidence: [],
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "比较方法" })).toBeVisible();
    expect(screen.getByText("已纳入结论")).toBeVisible();
    expect(screen.getByText("发现")).toBeVisible();
    expect(screen.getByText("正向")).toBeVisible();
    for (const token of [
      "compares_method",
      "accepted",
      "finding",
      "positive",
    ]) {
      expect(
        screen.queryByText(token, { exact: true }),
      ).not.toBeInTheDocument();
    }
  });
});
