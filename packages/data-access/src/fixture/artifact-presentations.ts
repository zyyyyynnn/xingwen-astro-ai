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
      { label: "录制响应", values: ["2 份"] },
    ],
  },
  artv_fdict_01: {
    kind: "field_dictionary",
    facts: [{ label: "字段定义", values: ["14 个"] }],
  },
  artv_srccol_01: {
    kind: "source_collection",
    facts: [{ label: "目录来源", values: ["3 个 (TOI, PS, Gaia DR3)"] }],
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
            text: "论文说明了修订版 TESS Input Catalog 及候选目标列表的构建目标与数据组织方式。",
            evidence_ids: ["evd_papsum_03"],
          },
        ],
      },
      {
        title: "研究方法",
        paragraphs: [
          {
            text: "恒星参数由目录输入、测光与天体测量信息及文中记录的计算关系共同生成。",
            evidence_ids: ["evd_papsum_04"],
          },
        ],
      },
      {
        title: "数据集",
        paragraphs: [
          {
            text: "当前研读对象是 2019 年发布的修订版 TESS Input Catalog 论文与其固定全文。",
            evidence_ids: ["evd_papsum_01"],
          },
        ],
      },
      {
        title: "发布信息",
        paragraphs: [
          {
            text: "论文的 DOI 为 10.3847/1538-3881/ab3467，可用于核验书目身份与固定全文。",
            evidence_ids: ["evd_papsum_02"],
          },
        ],
      },
      {
        title: "局限性",
        paragraphs: [
          {
            text: "当前摘要没有提取到可定位的局限性原文；使用目录参数时仍需回到来源字段、质量标记与版本记录核验。",
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
          "NASA Exoplanet Archive TOI 表将 TOI-1233.04 关联到 TIC-260647166，并记录轨道周期 3.79589 天、半径 1.553135 R_Earth。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TOI-1233.04", "TIC-260647166"] },
          {
            label: "目录参数",
            values: ["P = 3.79589 d", "Rp = 1.553135 R_Earth"],
          },
          {
            label: "成立条件",
            values: ["仅陈述冻结 TOI 目录字段，不外推物理解释"],
          },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_02",
        title:
          "同一冻结 TOI 响应记录 TIC-260647166 的有效温度 5723.87 K、log g 4.438、恒星半径 0.864173 R_Sun。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TIC-260647166"] },
          { label: "有效温度", values: ["5723.87 K"] },
          { label: "表面重力", values: ["log g = 4.438"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_03",
        title:
          "冻结 TOI 表记录 TOI-1233.03 的轨道周期为 6.2036219 天、行星半径为 2.056748 R_Earth。",
        status: "accepted",
        assessment: "finding · positive",
        facts: [
          { label: "研究对象", values: ["TOI-1233.03"] },
          {
            label: "目录参数",
            values: ["P = 6.2036219 d", "Rp = 2.056748 R_Earth"],
          },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_04",
        title:
          "候选审查：TOI-1233.03 与 TOI-1233.04 的目录周期可用于后续计算周期比，但当前响应不足以支持共振或 TTV 结论。",
        status: "candidate",
        assessment: "hypothesis · review_required",
        facts: [
          { label: "已知输入", values: ["6.2036219 d", "3.79589 d"] },
          { label: "审定状态", values: ["需要真实时序与动力学模型"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_05",
        title:
          "候选审查：TOI 编号与已确认行星名称的交叉映射需要独立来源，当前 TOI 目录响应不能单独完成别名认定。",
        status: "candidate",
        assessment: "finding · review_required",
        facts: [
          { label: "待核对字段", values: ["TOI 编号", "确认行星名称"] },
          { label: "所需来源", values: ["PS/PSCompPars 别名与发现表"] },
        ],
        evidence_ids: ["evd_02"],
      },
      {
        key: "claim_06",
        title:
          "已驳回：将 TOI-1233.01 的目录周期写成 3.79589 天，与同一冻结响应中的 14.1758947 天直接冲突。",
        status: "rejected",
        assessment: "contradiction · rejected",
        facts: [
          {
            label: "驳回依据",
            values: ["冻结 TOI 响应中的行号与周期字段不一致"],
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
        title: "TOI-1233.04 目录记录 ↔ TIC-260647166 恒星参数（同一目录系统）",
        status: "accepted",
        can_adjudicate: false,
        assessment: "describes_same_system",
        facts: [
          { label: "关联类型", values: ["同系统宿主-行星基准关联"] },
          { label: "目标天体", values: ["TIC-260647166"] },
        ],
        evidence_ids: ["evd_03"],
        reasoning_trace: {
          trace_id: "trace_rel_01",
          conclusion:
            "主张 1 与主张 2 在同一冻结 TOI 行中共享 TIC-260647166，可建立目录级同系统关系。",
          steps: ["比对冻结响应中的 TIC 标识与同一行恒星字段。"],
          facts: [
            {
              label: "成立条件",
              values: ["仅表达目录级关联，不扩展为新的天体物理结论。"],
            },
          ],
          evidence_ids: ["evd_03"],
        },
      },
      {
        key: "rel_02",
        title: "TOI-1233.04 ↔ TOI-1233.03（共享 TIC-260647166）",
        status: "accepted",
        can_adjudicate: false,
        assessment: "consistent_with",
        facts: [{ label: "关联类型", values: ["冻结目录中的同宿主记录"] }],
        evidence_ids: ["evd_03"],
      },
      {
        key: "rel_03",
        title: "TOI-1233.03 周期 ↔ TOI-1233.04 周期比解释（待审定）",
        status: "candidate",
        can_adjudicate: true,
        assessment: "predicts",
        facts: [
          { label: "待审原因", values: ["目录周期不足以证明共振或 TTV"] },
          {
            label: "成立条件",
            values: ["两项记录共享 TIC-260647166"],
          },
          {
            label: "限制",
            values: ["缺少真实时序、误差与动力学模型"],
          },
        ],
        evidence_ids: ["evd_03"],
        reasoning_trace: {
          trace_id: "trace_rel_03",
          conclusion:
            "冻结目录周期只能作为后续动力学分析输入；当前不得把周期比解释为已证实关系。",
          steps: ["核对目标恒星标识、TOI 编号与目录周期字段。"],
          facts: [
            {
              label: "审查边界",
              values: ["尚未将近共振预测作为已接受图谱关系"],
            },
          ],
          evidence_ids: ["evd_03"],
        },
      },
      {
        key: "rel_04",
        title: "TOI 编号 ↔ 已确认行星名称交叉映射（待审定）",
        status: "candidate",
        can_adjudicate: true,
        assessment: "refines_parameter",
        facts: [
          {
            label: "待审原因",
            values: ["当前证据只包含 TOI 表，缺少独立别名来源"],
          },
          {
            label: "成立条件",
            values: ["必须由独立 PS/PSCompPars 记录匹配同一 TIC/宿主"],
          },
          {
            label: "限制",
            values: ["不能仅凭编号顺序推断行星字母别名"],
          },
        ],
        evidence_ids: ["evd_03"],
        reasoning_trace: {
          trace_id: "trace_rel_04",
          conclusion:
            "TOI 与确认行星名称的映射属于跨表实体解析，需要独立来源快照和明确匹配规则。",
          steps: ["核对 TIC、宿主名、周期与正式行星名的一致性。"],
          facts: [
            {
              label: "审查边界",
              values: ["独立来源未绑定前不进入证据图谱"],
            },
          ],
          evidence_ids: ["evd_03"],
        },
      },
      {
        key: "rel_05",
        title: "TOI-1233.01 ↔ 3.79589 天周期（已驳回字段错配）",
        status: "rejected",
        can_adjudicate: false,
        assessment: "contradicts",
        facts: [
          {
            label: "驳回理由",
            values: ["同一冻结响应记录 TOI-1233.01 的周期为 14.1758947 天"],
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
      { label: "关系连边", values: ["19 条"] },
      { label: "关系衍生边", values: ["2 条（仅消费已接受关系）"] },
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
        label: "TOI 目录记录 1233.04",
      },
      {
        key: "node_planet_toi1233_02",
        kind: "entity",
        label: "TOI 目录记录 1233.03",
      },
      {
        key: "node_claim_01",
        kind: "claim",
        label: "主张 1：TOI-1233.04 冻结目录参数",
      },
      {
        key: "node_claim_02",
        kind: "claim",
        label: "主张 2：TIC-260647166 冻结恒星参数",
      },
      {
        key: "node_claim_03",
        kind: "claim",
        label: "主张 3：TOI-1233.03 冻结目录参数",
      },
      {
        key: "node_claim_04",
        kind: "claim",
        label: "主张 4：周期比解释待审",
      },
      {
        key: "node_claim_05",
        kind: "claim",
        label: "主张 5：跨表别名映射待审",
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
    ],
  },
  artv_b_analysis_01: {
    kind: "analysis_report",
    facts: [
      { label: "冻结记录", values: ["TOI-1233.04 · TIC 260647166"] },
      { label: "数据边界", values: ["公开目录参数；非原始光变"] },
    ],
  },
  artv_c_analysis_01: {
    kind: "analysis_report",
    facts: [
      { label: "研究对象", values: ["L 98-59 (TOI-175)"] },
      {
        label: "公开数据产品",
        values: ["ESO HARPS ADP.2024-03-10T01:01:18.295"],
      },
      { label: "结论边界", values: ["未自动执行谱线证认"] },
    ],
  },
  artv_b_chart_01: {
    kind: "visualization",
    facts: [
      { label: "类型", values: ["周期-半径散点图"] },
      { label: "真实记录", values: ["TOI-1233 冻结目录 4 行"] },
      { label: "其余点", values: ["容量边界样例"] },
    ],
  },
  artv_c_fits_01: {
    kind: "visualization",
    facts: [
      { label: "图像类型", values: ["FITS 交互界面样例"] },
      { label: "数据边界", values: ["非归档观测产品"] },
    ],
  },
  artv_c_wwt_01: {
    kind: "visualization",
    facts: [
      { label: "场景模式", values: ["WWT 天球视口场景"] },
      { label: "数据边界", values: ["图层仅用于交互覆盖"] },
    ],
  },
  artv_c_spec_01: {
    kind: "spectrum",
    facts: [
      { label: "显示投影范围", values: ["4000 - 6800 Å"] },
      { label: "归档产品 S/N", values: ["8.0"] },
    ],
  },
  artv_b_lc_01: {
    kind: "light_curve",
    facts: [
      { label: "界面样例", values: ["720 点确定性生成"] },
      { label: "目录周期", values: ["3.79589 d"] },
      { label: "观测边界", values: ["非原始 TESS 光度序列"] },
    ],
  },
  artv_b_modeval_01: {
    kind: "model_evaluation",
    facts: [
      { label: "用途", values: ["指标与基线布局样例"] },
      { label: "科研边界", values: ["未绑定训练集或真实执行"] },
    ],
  },
  artv_b_model_01: {
    kind: "model_artifact",
    facts: [
      { label: "格式", values: ["ONNX"] },
      { label: "任务", values: ["分类"] },
      { label: "交付边界", values: ["fixture 引用；不可部署"] },
    ],
  },
  artv_export_01: {
    kind: "export",
    summary:
      "冻结的数据、文献与证据图谱版本引用；当前工作区明确展示不支持预览状态。",
    facts: [
      { label: "格式", values: ["来源与证据报告"] },
      { label: "引用版本", values: ["3 个"] },
    ],
  },
} satisfies Readonly<Record<string, PublicArtifactPresentation>>;
