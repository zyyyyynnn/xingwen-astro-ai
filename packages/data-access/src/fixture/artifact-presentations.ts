import type { PublicArtifactPresentation } from "@xingwen/contracts";

/**
 * Frozen transport presentations produced for the Demo Replay fixture.
 * They are data, not a second projection implementation: HTTP presentations
 * continue to be authored by the API's typed artifact projector.
 */
export const artifactPresentations = {
  artv_dataset_01: {
    kind: "dataset",
    facts: [
      { label: "记录", values: ["1 条"] },
      { label: "字段", values: ["2 个"] },
    ],
  },
  artv_fdict_01: {
    kind: "field_dictionary",
    facts: [{ label: "字段", values: ["2 个"] }],
  },
  artv_srccol_01: {
    kind: "source_collection",
    facts: [{ label: "来源", values: ["2 个"] }],
  },
  "11111111-1111-4111-8111-111111111111": {
    kind: "paper_collection",
    facts: [
      { label: "候选论文", values: ["7 篇"] },
      { label: "已选论文", values: ["3 篇"] },
    ],
  },
  artv_papsum_01: {
    kind: "paper_summary",
    sections: [
      {
        title: "研究背景",
        paragraphs: [
          {
            text: "The paper delivers The Revised TESS Input Catalog and Candidate Target List to prioritize TESS targets.",
            evidence_ids: ["evd_papsum_03"],
          },
        ],
      },
      {
        title: "研究方法",
        paragraphs: [
          {
            text: "The catalog compiles stellar parameters from photometric catalogs and parallax measurements.",
            evidence_ids: ["evd_papsum_04"],
          },
        ],
      },
      {
        title: "数据集",
        paragraphs: [
          {
            text: "The catalog release analyzed here dates to 2019.",
            evidence_ids: ["evd_papsum_01"],
          },
        ],
      },
      {
        title: "实验与结果",
        paragraphs: [
          {
            text: "The published catalog is registered under DOI 10.3847/1538-3881/ab3467.",
            evidence_ids: ["evd_papsum_02"],
          },
        ],
      },
      {
        title: "局限性",
        paragraphs: [
          {
            text: "The catalog is claimed to be complete for all dwarf stars, without any cited evidence.",
          },
        ],
      },
    ],
  },
  artv_claims_01: {
    kind: "literature_claims",
    facts: [{ label: "论点", values: ["1 条"] }],
    entries: [
      {
        key: "claim_01",
        title: "The host star TIC-5678 has an effective temperature of 5800 K.",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TIC-5678"] },
          { label: "适用范围", values: ["host star"] },
          { label: "成立条件", values: ["catalog host-star parameters"] },
          {
            label: "限制",
            values: ["Evidence is bounded to the cited catalog record."],
          },
        ],
        evidence_ids: ["evd_02"],
      },
    ],
  },
  artv_rels_01: {
    kind: "literature_relations",
    facts: [{ label: "关系", values: ["1 条"] }],
    entries: [
      {
        key: "rel_01",
        title:
          "The host star TIC-5678 has an effective temperature of 5800 K. → The host star TIC-5678 has an effective temperature of 5800 K.",
        status: "accepted",
        assessment: "uses_same_dataset",
        facts: [
          { label: "成立条件", values: ["same host-star catalog"] },
          { label: "方向依据", values: ["shared host-star parameter"] },
        ],
        evidence_ids: ["evd_03"],
        reasoning_trace: {
          conclusion:
            "The claims are linked because they refer to the same host-star parameter.",
          steps: ["Compare the host-star identity in each claim."],
          facts: [
            { label: "成立条件", values: ["Both records identify TIC-5678."] },
            { label: "限制", values: ["No causal relationship is inferred."] },
          ],
          evidence_ids: ["evd_03"],
        },
      },
    ],
  },
  artv_graph_01: {
    kind: "graph",
    facts: [
      { label: "研究对象", values: ["2 个"] },
      { label: "证据关系", values: ["1 条"] },
    ],
    graph_nodes: [
      { key: "node_01", kind: "dataset", label: "Exoplanet candidate dataset" },
      { key: "node_02", kind: "claim", label: "Host-star temperature finding" },
    ],
    graph_edges: [
      {
        key: "edge_01",
        kind: "supports_finding",
        source_key: "node_01",
        target_key: "node_02",
        evidence_ids: ["evd_03"],
      },
    ],
  },
} satisfies Readonly<Record<string, PublicArtifactPresentation>>;
