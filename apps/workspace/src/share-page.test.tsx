import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
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
      presentation: {
        kind: "dataset",
        summary: null,
        facts: [
          {
            label: "记录" as NonEmptyString,
            values: ["2 条" as NonEmptyString],
          },
          {
            label: "字段" as NonEmptyString,
            values: ["3 个" as NonEmptyString],
          },
        ],
        sections: [],
        entries: [
          {
            key: "hostname" as NonEmptyString,
            title: "宿主星名称" as NonEmptyString,
            externalUrl: null,
            status: null,
            assessment: null,
            paragraphs: ["目标天体的规范名称" as NonEmptyString],
            facts: [],
            evidenceIds: [],
            reasoningTrace: null,
          },
        ],
        tables: [
          {
            title: "规范化数据" as NonEmptyString,
            columns: [
              {
                key: "hostname" as NonEmptyString,
                label: "宿主星名称" as NonEmptyString,
                unit: null,
              },
            ],
            rows: [
              {
                key: "row-1" as NonEmptyString,
                identity: "TOI-700" as NonEmptyString,
                cells: [
                  {
                    columnKey: "hostname" as NonEmptyString,
                    value: "TOI-700 d",
                    status: "mapped",
                    reason: null,
                    evidenceIds: [id("evidence_01")],
                  },
                ],
              },
            ],
            totalRowCount: 1,
            totalColumnCount: 1,
          },
        ],
        graphNodes: [],
        graphEdges: [],
      },
      evidenceIds: [id("evidence_01")],
    },
  ],
  evidence: [
    {
      id: id("evidence_01"),
      artifactVersionId: id("artv_dataset"),
      sourceSnapshotId: id("snapshot_01"),
      locator: {
        kind: "paper_text" as NonEmptyString,
        page: 3,
        paragraph: null,
        section: "Results",
        textRange: null,
        field: null,
        rowKey: null,
        blockId: "paragraph-1",
        readingOrder: 1,
        tableId: null,
        cellId: null,
        bbox: { x1: 10, y1: 20, x2: 30, y2: 40 },
      },
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
    expect(
      screen.getByRole("columnheader", { name: "宿主星名称" }),
    ).toBeVisible();
    expect(screen.getByRole("cell", { name: "TOI-700 d" })).toBeVisible();
    expect(screen.queryByText("实时数据")).not.toBeInTheDocument();
    expect(document.querySelector("[data-source-mode]")).toBeNull();
    expect(screen.getByText(/冻结的公开副本/)).toBeVisible();
  });

  it("opens only the selected public evidence projection", () => {
    render(<PublicShareView snapshot={snapshot} />);

    fireEvent.click(screen.getByRole("button", { name: "查看证据 1" }));

    expect(screen.getByRole("heading", { name: "证据 1" })).toBeVisible();
    expect(
      screen.getByText("TOI-700 d is a temperate terrestrial planet."),
    ).toBeVisible();
    expect(screen.getByText(/^论文 ·/)).toBeVisible();
    expect(
      screen.queryByText("paper", { exact: true }),
    ).not.toBeInTheDocument();
    const inspector = screen.getByRole("complementary", { name: "证据 1" });
    expect(within(inspector).getByText("页码")).toBeVisible();
    expect(within(inspector).getByText("4")).toBeVisible();
    expect(within(inspector).getByText("章节")).toBeVisible();
    expect(within(inspector).getByText("Results")).toBeVisible();
    for (const machineFact of [
      "文档区块",
      "paragraph-1",
      "阅读顺序",
      "页面区域",
      "10, 20 – 30, 40",
    ]) {
      expect(
        within(inspector).queryByText(machineFact),
      ).not.toBeInTheDocument();
    }
    expect(screen.getByRole("link", { name: /打开原始来源/ })).toHaveAttribute(
      "href",
      "https://example.org/paper",
    );
  });

  it("uses the frozen snapshot ordinal for dossier evidence actions", () => {
    const [version] = snapshot.artifactVersions;
    const [firstEvidence] = snapshot.evidence;
    if (!version || !firstEvidence) {
      throw new Error("public share fixture requires an artifact and evidence");
    }
    const secondEvidence = {
      ...firstEvidence,
      id: id("evidence_02"),
      quoteOrValue: "Second frozen evidence.",
    };
    render(
      <PublicShareView
        snapshot={{
          ...snapshot,
          artifactVersions: [
            {
              ...version,
              presentation: {
                ...version.presentation,
                entries: version.presentation.entries.map((entry) => ({
                  ...entry,
                  evidenceIds: [secondEvidence.id],
                })),
              },
              evidenceIds: [firstEvidence.id, secondEvidence.id],
            },
          ],
          evidence: [firstEvidence, secondEvidence],
        }}
      />,
    );

    const dossier = screen.getByRole("list", { name: "科学结果档案" });
    fireEvent.click(
      within(dossier).getByRole("button", { name: "查看证据 2" }),
    );

    expect(screen.getByRole("heading", { name: "证据 2" })).toBeVisible();
    expect(screen.getByText("Second frozen evidence.")).toBeVisible();
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
              presentation: {
                kind: "literature_relations",
                summary: null,
                facts: [],
                sections: [],
                entries: [
                  {
                    key: "relation-1" as NonEmptyString,
                    title: "候选发现" as NonEmptyString,
                    externalUrl: null,
                    status: "accepted" as NonEmptyString,
                    assessment:
                      "compares_method · finding · positive" as NonEmptyString,
                    paragraphs: [],
                    facts: [],
                    evidenceIds: [],
                    reasoningTrace: null,
                  },
                ],
                tables: [],
                graphNodes: [],
                graphEdges: [],
              },
              evidenceIds: [],
            },
          ],
          evidence: [],
        }}
      />,
    );

    expect(screen.getByText("比较方法 · 发现 · 正向")).toBeVisible();
    expect(screen.getByText("已纳入结论")).toBeVisible();
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
