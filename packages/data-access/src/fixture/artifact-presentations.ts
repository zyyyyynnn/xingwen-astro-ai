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
      { label: "记录", values: ["40 条"] },
      { label: "字段", values: ["14 个"] },
      { label: "数据源", values: ["3 个"] },
    ],
  },
  artv_fdict_01: {
    kind: "field_dictionary",
    facts: [{ label: "字段定义", values: ["14 个"] }],
  },
  artv_srccol_01: {
    kind: "source_collection",
    facts: [{ label: "观测来源", values: ["3 个 (TOI, PS, Gaia DR3)"] }],
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
            text: "The TESS Faint Star Search presents 1,617 new transiting planet candidates identified in TESS full-frame images from the Primary Mission.",
            evidence_ids: ["evd_papsum_03"],
          },
        ],
      },
      {
        title: "研究方法",
        paragraphs: [
          {
            text: "An independent vetting pipeline applies automated vetting tests and manual inspection to QLP transit search results around fainter stars.",
            evidence_ids: ["evd_papsum_04"],
          },
        ],
      },
      {
        title: "数据集",
        paragraphs: [
          {
            text: "The search extracts FFIs for all stars brighter than TESS magnitude T = 13.5 mag in each sector.",
            evidence_ids: ["evd_papsum_01"],
          },
        ],
      },
      {
        title: "实验与结果",
        paragraphs: [
          {
            text: "The paper reports 686,242 transit candidates identified after AstroNet vetting of QLP threshold crossing events.",
            evidence_ids: ["evd_papsum_02"],
          },
        ],
      },
      {
        title: "局限性",
        paragraphs: [
          {
            text: "QLP heavily relies on manual inspection for the identification of planet candidates, leaving millions of potential transit signals un-vetted.",
          },
        ],
      },
    ],
  },
  artv_claims_01: {
    kind: "literature_claims",
    facts: [
      { label: "主张条目", values: ["6 条 (3 已接受 · 2 候选 · 1 驳回)"] },
    ],
    entries: [
      {
        key: "claim_01",
        title:
          "TOI-1233.01 (HD 108236 b) 是一颗短周期亚海王星，轨道周期为 3.795 天，围绕亮 G 型恒星 TIC-260647166 运行。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TOI-1233.01", "TIC-260647166"] },
          { label: "物理参数", values: ["P = 3.795 d", "Rp = 2.06 R_Earth"] },
          {
            label: "成立条件",
            values: ["TESS 凌星模型与 Gaia DR3 等时线拟合"],
          },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_02",
        title:
          "宿主恒星 TIC-260647166 (HD 108236) 的有效表面温度为 5720 ± 60 K，金属丰度 [Fe/H] 为 -0.05 dex。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TIC-260647166"] },
          { label: "有效温度", values: ["5720 ± 60 K"] },
          { label: "金属丰度", values: ["-0.05 dex"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_03",
        title:
          "TOI-1233.02 (HD 108236 c) 的拟合物理半径为 2.06 R_Earth，与富含挥发分气态包层的行星内部结构模型一致。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TOI-1233.02"] },
          { label: "行星半径", values: ["2.06 R_Earth"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_04",
        title:
          "TOI-1233.01 与外层伴星 TOI-1233.02 的凌星时刻变分 (TTV) 反演预示两者处于接近 5:3 的近平均运动共振区域。",
        status: "candidate",
        assessment: "hypothesis · review_required",
        facts: [
          { label: "动力学特征", values: ["5:3 近平动共振 (MMR)"] },
          { label: "审定状态", values: ["待审定动力学稳定性"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_05",
        title:
          "HARPS 高精度视向速度测量为 TOI-1233.01 的动力学质量确定了 4.8 ± 0.9 M_Earth 的强约束上限。",
        status: "candidate",
        assessment: "finding · review_required",
        facts: [
          { label: "质量上限", values: ["4.8 ± 0.9 M_Earth"] },
          { label: "测量仪器", values: ["HARPS 光谱仪"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_06",
        title:
          "TIC-260647166 为极年轻的金牛座 T Tauri 型恒星，具有强烈的色球活动与耀斑爆发特征。",
        status: "rejected",
        assessment: "contradiction · rejected",
        facts: [
          {
            label: "驳回依据",
            values: ["与 Gaia DR3 演化等时线及 HARPS 光谱特征直接冲突"],
          },
        ],
        evidence_ids: ["evd_02"],
      },
    ],
  },
  artv_rels_01: {
    kind: "literature_relations",
    facts: [
      {
        label: "主张关系",
        values: ["5 条 (2 已接受 · 2 候选待审 · 1 已驳回)"],
      },
    ],
    entries: [
      {
        key: "rel_01",
        title: "TOI-1233.01 亚海王星 ↔ 宿主星有效温度 5720 K (描述同一系统)",
        status: "accepted",
        assessment: "describes_same_system",
        facts: [
          { label: "关联类型", values: ["同系统宿主-行星基准关联"] },
          { label: "目标天体", values: ["TIC-260647166"] },
        ],
        evidence_ids: ["evd_03"],
        reasoning_trace: {
          trace_id: "trace_rel_01",
          conclusion:
            "主张 1 的候选行星与主张 2 的宿主恒星具有相同的 TIC 标识 (TIC-260647166)，构成系统物理基准。",
          steps: ["比对行星母星标识与恒星光谱参数的一致性。"],
          facts: [
            {
              label: "成立条件",
              values: ["两项主张均基于对同一恒星系统 TIC-260647166 的观测。"],
            },
          ],
          evidence_ids: ["evd_03"],
        },
      },
      {
        key: "rel_02",
        title: "TOI-1233.01 (b) ↔ TOI-1233.02 (c) (多行星系统架构一致)",
        status: "accepted",
        assessment: "consistent_with",
        facts: [{ label: "关联类型", values: ["多行星轨道排列一致性"] }],
        evidence_ids: ["evd_03"],
      },
      {
        key: "rel_03",
        title: "TOI-1233.01 周期 ↔ TTV 近共振动力学预测 (待审定)",
        status: "candidate",
        assessment: "predicts",
        facts: [
          { label: "待审原因", values: ["需人工审定近共振区动力学稳定性质询"] },
        ],
        evidence_ids: ["evd_03"],
      },
      {
        key: "rel_04",
        title: "TOI-1233.01 凌星 ↔ HARPS 视向速度质量约束 (待审定)",
        status: "candidate",
        assessment: "refines_parameter",
        facts: [
          {
            label: "待审原因",
            values: ["需人工审定 HARPS 径向速度仪器的系统误差先验"],
          },
        ],
        evidence_ids: ["evd_03"],
      },
      {
        key: "rel_05",
        title: "主序 G 型有效温度 ↔ T Tauri 年轻恒星假设 (已驳回冲突)",
        status: "rejected",
        assessment: "contradicts",
        facts: [
          {
            label: "驳回理由",
            values: ["主序有效温度与年轻 T Tauri 假设直接冲突"],
          },
        ],
        evidence_ids: ["evd_03"],
      },
    ],
  },
  artv_graph_01: {
    kind: "graph",
    facts: [
      { label: "拓扑节点", values: ["16 个"] },
      { label: "关系连边", values: ["20 条"] },
      { label: "关系衍生边", values: ["3 条 (消费已接受关系)"] },
    ],
    graph_nodes: [
      {
        key: "node_goal_01",
        kind: "research_goal",
        label: "系外行星宿主星证据链综合研究目标",
      },
      {
        key: "node_dataset_01",
        kind: "dataset",
        label: "TOI 宿主星交叉证认数据集 (40 颗)",
      },
      {
        key: "node_src_toi",
        kind: "source",
        label: "NASA Exoplanet Archive (TOI)",
      },
      {
        key: "node_src_ps",
        kind: "source",
        label: "NASA Exoplanet Archive (PS)",
      },
      { key: "node_src_gaia", kind: "source", label: "Gaia DR3 巡天星表" },
      {
        key: "node_paper_01",
        kind: "paper",
        label: "Daylan et al. (2021) HD 108236",
      },
      {
        key: "node_paper_02",
        kind: "paper",
        label: "Bonfanti et al. (2021) CHEOPS",
      },
      {
        key: "node_star_tic2606",
        kind: "entity",
        label: "恒星 TIC-260647166 (HD 108236)",
      },
      {
        key: "node_planet_toi1233_01",
        kind: "entity",
        label: "行星 TOI-1233.01 (b)",
      },
      {
        key: "node_planet_toi1233_02",
        kind: "entity",
        label: "行星 TOI-1233.02 (c)",
      },
      {
        key: "node_claim_01",
        kind: "claim",
        label: "主张 1: TOI-1233.01 短周期亚海王星",
      },
      {
        key: "node_claim_02",
        kind: "claim",
        label: "主张 2: 宿主星有效温度 5720 K",
      },
      {
        key: "node_claim_03",
        kind: "claim",
        label: "主张 3: TOI-1233.02 挥发分气态包层",
      },
      {
        key: "node_claim_04",
        kind: "claim",
        label: "主张 4: 近共振动力学 TTV 预期",
      },
      {
        key: "node_claim_05",
        kind: "claim",
        label: "主张 5: HARPS 视向速度质量上限",
      },
      {
        key: "node_fdict_01",
        kind: "field",
        label: "天文特征字典 (14 个字段)",
      },
    ],
    graph_edges: [
      {
        key: "edge_01",
        kind: "uses_dataset",
        source_key: "node_goal_01",
        target_key: "node_dataset_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_02",
        kind: "provides_field",
        source_key: "node_fdict_01",
        target_key: "node_dataset_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_03",
        kind: "derived_from",
        source_key: "node_dataset_01",
        target_key: "node_src_toi",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_04",
        kind: "derived_from",
        source_key: "node_dataset_01",
        target_key: "node_src_ps",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_05",
        kind: "derived_from",
        source_key: "node_dataset_01",
        target_key: "node_src_gaia",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_06",
        kind: "supports",
        source_key: "node_paper_01",
        target_key: "node_planet_toi1233_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_07",
        kind: "supports",
        source_key: "node_paper_01",
        target_key: "node_star_tic2606",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_08",
        kind: "supports",
        source_key: "node_paper_02",
        target_key: "node_planet_toi1233_02",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_09",
        kind: "hosts",
        source_key: "node_star_tic2606",
        target_key: "node_planet_toi1233_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_10",
        kind: "hosts",
        source_key: "node_star_tic2606",
        target_key: "node_planet_toi1233_02",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_11",
        kind: "supports_finding",
        source_key: "node_paper_01",
        target_key: "node_claim_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_12",
        kind: "supports_finding",
        source_key: "node_src_ps",
        target_key: "node_claim_02",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_13",
        kind: "supports_finding",
        source_key: "node_paper_02",
        target_key: "node_claim_03",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_14",
        kind: "supports_finding",
        source_key: "node_paper_01",
        target_key: "node_claim_04",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_15",
        kind: "supports_finding",
        source_key: "node_paper_02",
        target_key: "node_claim_05",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_16",
        kind: "observes",
        source_key: "node_dataset_01",
        target_key: "node_star_tic2606",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_17",
        kind: "observes",
        source_key: "node_dataset_01",
        target_key: "node_planet_toi1233_01",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_18_rel_01",
        kind: "describes_same_system",
        source_key: "node_claim_01",
        target_key: "node_claim_02",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_19_rel_02",
        kind: "consistent_with",
        source_key: "node_claim_01",
        target_key: "node_claim_03",
        evidence_ids: ["evd_03"],
      },
      {
        key: "edge_20_rel_03",
        kind: "predicts",
        source_key: "node_claim_01",
        target_key: "node_claim_04",
        evidence_ids: ["evd_03"],
      },
    ],
  },
  artv_b_analysis_01: {
    kind: "analysis_report",
    facts: [
      { label: "研究对象", values: ["TOI-1233"] },
      { label: "信噪比", values: ["38.4"] },
    ],
  },
  artv_c_analysis_01: {
    kind: "analysis_report",
    facts: [
      { label: "研究对象", values: ["L 98-59 (TOI-175)"] },
      { label: "高精度光谱分析", values: ["HARPS/ESPRESSO 联合分析"] },
    ],
  },
  artv_b_chart_01: {
    kind: "visualization",
    facts: [{ label: "类型", values: ["散点分布图"] }],
  },
  artv_c_fits_01: {
    kind: "visualization",
    facts: [{ label: "图像类型", values: ["FITS 图像切片"] }],
  },
  artv_c_wwt_01: {
    kind: "visualization",
    facts: [{ label: "场景模式", values: ["WWT 天球视口场景"] }],
  },
  artv_c_spec_01: {
    kind: "spectrum",
    facts: [
      { label: "光谱范围", values: ["3800 - 6800 Å"] },
      { label: "信噪比", values: ["145.2"] },
    ],
  },
  artv_b_lc_01: {
    kind: "light_curve",
    facts: [
      { label: "采样点", values: ["720 点"] },
      { label: "周期", values: ["3.7952 d"] },
    ],
  },
  artv_b_modeval_01: {
    kind: "model_evaluation",
    facts: [
      { label: "模型", values: ["ResNet-1D 凌星分类器"] },
      { label: "F1 分数", values: ["0.918"] },
    ],
  },
  artv_b_model_01: {
    kind: "model_artifact",
    facts: [
      { label: "格式", values: ["ONNX"] },
      { label: "任务", values: ["分类"] },
    ],
  },
} satisfies Readonly<Record<string, PublicArtifactPresentation>>;
