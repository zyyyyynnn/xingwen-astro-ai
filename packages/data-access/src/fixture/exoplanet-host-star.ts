/**
 * Exoplanet host-star integration fixture — the frozen main-case Demo Replay scenario.
 *
 * Provides 3 complete demo projects:
 * 1. proj_01JEXAMPLE: Exoplanet host-star integration (Dataset, Field Dict, Sources, Papers, Claims, Relations, Graph, Scientific Artifacts)
 * 2. proj_toi_transit: TOI transit characterization (Dataset, Analysis Report, Chart, Light Curve, Model Evaluation, Model Artifact)
 * 3. proj_l9859_spectroscopy: L 98-59 spectroscopy and observation scene (Spectrum, FITS, WWT Scene, Analysis Report)
 * Plus waiting and failed demo projects for navigation testing.
 */

import type {
  ArtifactVersionDto,
  EvidenceDetail as EvidenceDetailDto,
  EvidenceRead as EvidenceReadDto,
  ResearchArtifactDto,
  ResearchContractDto,
  ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
  ResearchProjectDto,
  ResearchRunDto,
  RunEventDto,
} from "@xingwen/contracts";
import type { Evidence } from "@xingwen/domain";

import { mapEvidenceDetail, mapEvidenceRead } from "../mapping";
import type { FixtureBundle } from "./bundle";
import { artifactPresentations } from "./artifact-presentations";
import {
  paperCandidateReadsFixture,
  paperCollectionArtifactVersionFixture,
  paperCollectionReadFixture,
} from "./paper-acquisition";
import {
  paperSummaryArtifactVersionFixture,
  paperSummaryReadFixture,
} from "./paper-summary";
import {
  dataArtifactReads,
  fieldDictionaryArtifactReads,
  graphArtifactReads,
  graphEdgeReads,
  graphNodeReads,
  literatureClaimReads,
  literatureRelationReads,
  sourceCollectionArtifactReads,
} from "./formal-artifacts";
import { scientificArtifactReadsFixture } from "./scientific-artifacts";

const T0 = "2026-07-21T08:00:00Z";
const T1 = "2026-07-21T08:05:00Z";
const T2 = "2026-07-21T08:10:00Z";
const T3 = "2026-07-21T08:15:00Z";
const T4 = "2026-07-21T08:16:00Z";
const T5 = "2026-07-21T08:18:00Z";
const T6 = "2026-07-21T08:21:00Z";
const T7 = "2026-07-21T08:25:00Z";
const T8 = "2026-07-21T08:28:00Z";
const T9 = "2026-07-21T08:30:00Z";

function hash(seed: string): string {
  const encoded = Array.from(seed)
    .map((c) => c.codePointAt(0)!.toString(16))
    .join("");
  return `sha256:${encoded.repeat(Math.ceil(64 / encoded.length)).slice(0, 64)}`;
}

const contractInput: ResearchContractInputDto = {
  research_goal: "Integrate exoplanet candidates and host-star parameters",
  target_objects: ["exoplanet_candidate", "host_star"],
  data_requirements: {
    unit_policy: "canonical",
    document_source_policy: "disabled",
  },
  requested_fields: ["planet.toi_id", "star.tic_id"],
  source_scope: { allowed_sources: ["nasa_exoplanet_archive"] },
  paper_search_scope: {
    keywords: ["exoplanet", "host star parameters"],
    year_from: 2018,
    year_to: 2026,
    source_ids: ["nasa_exoplanet_archive"],
    max_candidates: 5,
  },
  output_requirements: ["dataset", "graph"],
  evidence_requirements: {
    require_locator: true,
    require_source_snapshot: true,
    minimum_coverage: 1,
  },
  quality_constraints: {
    source_completeness_min: 1,
    unit_consistency_min: 1,
  },
};

const project: ResearchProjectDto = {
  id: "proj_01JEXAMPLE",
  session_id: "sess_01JEXAMPLE",
  name: "Exoplanet host-star integration",
  description: "Evidence-bound integration for the frozen main case",
  case_key: "exoplanet_host_star",
  active_contract_id: "rc_01JEXAMPLE",
  latest_run_id: "run_01JEXAMPLE",
  thread_summary: {
    has_thread_entries: true,
    latest_thread_actor: "assistant",
    has_unanswered_clarification: false,
  },
  created_at: T0,
  updated_at: T2,
  revision: 1,
};

const projectB: ResearchProjectDto = {
  id: "proj_toi_transit",
  session_id: "sess_toi_transit",
  name: "TOI-1233 行星凌星拟合与动力学特征分析",
  description:
    "TESS 光变曲线 MCMC 凌星拟合、周期图谱分析与深度残差分类模型评估",
  case_key: "exoplanet_host_star",
  active_contract_id: "rc_toi_transit",
  latest_run_id: "run_toi_transit",
  thread_summary: {
    has_thread_entries: true,
    latest_thread_actor: "assistant",
    has_unanswered_clarification: false,
  },
  created_at: T0,
  updated_at: T2,
  revision: 1,
};

const projectC: ResearchProjectDto = {
  id: "proj_l9859_spectroscopy",
  session_id: "sess_l9859",
  name: "L 98-59 (TOI-175) 高分辨率光谱与 WWT 空间场景",
  description:
    "HARPS 高分辨率吸收线测量、TESS 图像切片与虚拟天文台空间全景视口合成",
  case_key: "exoplanet_host_star",
  active_contract_id: "rc_l9859",
  latest_run_id: "run_l9859",
  thread_summary: {
    has_thread_entries: true,
    latest_thread_actor: "assistant",
    has_unanswered_clarification: false,
  },
  created_at: T0,
  updated_at: T2,
  revision: 1,
};

const projectWaiting: ResearchProjectDto = {
  id: "proj_waiting_demo",
  session_id: "sess_waiting",
  name: "TIC-307210830 观测协议编制中",
  description: "观测计划与文献检索策略排队准备中",
  case_key: "exoplanet_host_star",
  active_contract_id: null,
  latest_run_id: null,
  thread_summary: {
    has_thread_entries: false,
    latest_thread_actor: "user",
    has_unanswered_clarification: false,
  },
  created_at: T0,
  updated_at: T0,
  revision: 1,
};

const projectFailed: ResearchProjectDto = {
  id: "proj_failed_demo",
  session_id: "sess_failed",
  name: "TOI-9999 观测数据解析异常中断",
  description: "数据源连接超时导致解析失败",
  case_key: "exoplanet_host_star",
  active_contract_id: null,
  latest_run_id: "run_failed_demo",
  thread_summary: {
    has_thread_entries: true,
    latest_thread_actor: "assistant",
    has_unanswered_clarification: false,
  },
  created_at: T0,
  updated_at: T1,
  revision: 1,
};

const draft: ResearchContractDraftDto = {
  id: "rcd_01JEXAMPLE",
  session_id: "sess_01JEXAMPLE",
  project_id: "proj_01JEXAMPLE",
  version: 1,
  intent:
    "Integrate exoplanet candidates and host-star parameters across 40 TOI targets",
  status: "confirmed",
  contract: { ...contractInput },
  warnings: [],
  created_at: T1,
  updated_at: T2,
  expires_at: "2026-07-21T09:05:00Z",
};

const editableDraft: ResearchContractDraftDto = {
  ...draft,
  id: "rcd_01JTOUR",
  status: "draft",
  created_at: T0,
  updated_at: T0,
};

const contract: ResearchContractDto = {
  ...contractInput,
  id: "rc_01JEXAMPLE",
  project_id: "proj_01JEXAMPLE",
  version: 1,
  created_from_draft_id: "rcd_01JEXAMPLE",
  created_at: T2,
  content_hash:
    "sha256:82d51bd3fb5739b5ab1afeefa59c270de416bb20d6e780f39dca3c66c90d479a",
};

const run: ResearchRunDto = {
  id: "run_01JEXAMPLE",
  project_id: "proj_01JEXAMPLE",
  contract_id: "rc_01JEXAMPLE",
  execution_mode: "demo_replay",
  status: "completed",
  progress: 100,
  parent_run_id: null,
  derivation_kind: "original",
  retry_from_step: null,
  cache_policy: "disabled",
  started_at: T4,
  finished_at: T9,
  created_at: T3,
  updated_at: T9,
  latest_event_sequence: 9,
  failure_code: null,
  failure_summary: null,
};

const runB: ResearchRunDto = {
  id: "run_toi_transit",
  project_id: "proj_toi_transit",
  contract_id: "rc_01JEXAMPLE",
  execution_mode: "demo_replay",
  status: "completed",
  progress: 100,
  parent_run_id: null,
  derivation_kind: "original",
  retry_from_step: null,
  cache_policy: "disabled",
  started_at: T4,
  finished_at: T9,
  created_at: T3,
  updated_at: T9,
  latest_event_sequence: 3,
  failure_code: null,
  failure_summary: null,
};

const runC: ResearchRunDto = {
  id: "run_l9859",
  project_id: "proj_l9859_spectroscopy",
  contract_id: "rc_01JEXAMPLE",
  execution_mode: "demo_replay",
  status: "completed",
  progress: 100,
  parent_run_id: null,
  derivation_kind: "original",
  retry_from_step: null,
  cache_policy: "disabled",
  started_at: T4,
  finished_at: T9,
  created_at: T3,
  updated_at: T9,
  latest_event_sequence: 3,
  failure_code: null,
  failure_summary: null,
};

const runEvents: readonly RunEventDto[] = [
  {
    run_id: "run_01JEXAMPLE",
    sequence: 1,
    activity_id: "run:run_01JEXAMPLE",
    activity_kind: "status",
    activity_phase: "queued",
    activity_name: "研究任务",
    step_key: null,
    progress: 0,
    content: "研究任务已进入执行队列。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T3,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 2,
    activity_id: "fixture:planning",
    activity_kind: "reasoning",
    activity_phase: "completed",
    activity_name: "分析",
    step_key: "planning",
    progress: 5,
    content: "正在根据研究协议规划多源星表检索与文献研读路径。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T4,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 3,
    activity_id: "fixture:fetching-data",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "查询天文数据",
    step_key: "fetching_data",
    progress: 15,
    content:
      "已执行 TAP 跨星表检索并交叉对齐 40 颗系外行星宿主星的 14 项关键物理观测参数。",
    details: {
      tool_kind: "data_query",
      sql: "SELECT toi, hostname, period, pl_rade, st_teff, st_met, st_logg, sy_dist FROM pscomppars WHERE st_teff > 3000;",
      row_count: 40,
    },
    artifact_version_ids: ["artv_srccol_01"],
    occurred_at: T5,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 4,
    activity_id: "fixture:cleaning-data",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "整理并校验研究数据",
    step_key: "cleaning_data",
    progress: 25,
    content:
      "已完成 14 项字段规范定义与单位标准化（Teff: K, [Fe/H]: dex, logg: cgs）。",
    details: { tool_kind: "evidence_validation" },
    artifact_version_ids: ["artv_fdict_01", "artv_dataset_01"],
    occurred_at: T6,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 5,
    activity_id: "fixture:searching-papers",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "检索研究论文",
    step_key: "searching_papers",
    progress: 40,
    content: "已通过 NASA ADS 检索命中 7 篇候选文献并精选 3 篇核心研究论文。",
    details: { tool_kind: "search" },
    artifact_version_ids: ["11111111-1111-4111-8111-111111111111"],
    occurred_at: T7,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 6,
    activity_id: "fixture:summarizing-papers",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "阅读并归纳论文",
    step_key: "summarizing_papers",
    progress: 55,
    content: "已完成核心文献全文章节研读与 5 处关键科学证据定位。",
    details: { tool_kind: "document_read" },
    artifact_version_ids: ["artv_papsum_01"],
    occurred_at: T7,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 7,
    activity_id: "fixture:reasoning-literature",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "分析并验证文献证据",
    step_key: "reasoning_literature",
    progress: 70,
    content: "已抽取 6 条科学主张与 5 条主张关系，完成可比性推导与审定分析。",
    details: {
      tool_kind: "evidence_validation",
      quote:
        "We confirm that TOI-1233.01 is a sub-Neptune orbiting a bright solar-type star with an effective temperature of 5720 K.",
      locator: "Section 4.2, Paragraph 3, Page 7",
      confidence: 0.96,
    },
    artifact_version_ids: ["artv_claims_01", "artv_rels_01"],
    occurred_at: T8,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 8,
    activity_id: "fixture:building-graph",
    activity_kind: "artifact",
    activity_phase: "completed",
    activity_name: "生成证据图谱与科学分析",
    step_key: "building_graph",
    progress: 90,
    content:
      "已综合生成 16 节点 20 边证据知识图谱，并产出光变曲线、高分辨率光谱及分析报告。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: [
      "artv_graph_01",
      "artv_analysis_01",
      "artv_vis_chart_01",
      "artv_vis_fits_01",
      "artv_vis_wwt_01",
      "artv_spec_01",
      "artv_lc_01",
      "artv_modeval_01",
      "artv_model_01",
    ],
    occurred_at: T8,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 9,
    activity_id: "run:run_01JEXAMPLE",
    activity_kind: "completion",
    activity_phase: "completed",
    activity_name: "研究任务",
    step_key: null,
    progress: 100,
    content: "研究任务已全部完成，所有科学产物已通过一致性校验。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T9,
  },
];

const makeArtifact = (
  id: string,
  projectId: string,
  kind: ResearchArtifactDto["kind"],
  title: string,
  logicalKey: string,
  latestVersionId: string,
): ResearchArtifactDto => ({
  id,
  project_id: projectId,
  kind,
  title,
  logical_key: logicalKey,
  created_at: T6,
  latest_version_id: latestVersionId,
});

const artifacts: readonly ResearchArtifactDto[] = [
  // Project A
  makeArtifact(
    "art_dataset_01",
    "proj_01JEXAMPLE",
    "dataset",
    "系外行星宿主星数据集 (40 颗)",
    "dataset.primary",
    "artv_dataset_01",
  ),
  makeArtifact(
    "art_fdict_01",
    "proj_01JEXAMPLE",
    "field_dictionary",
    "天文物理特征字典",
    "field_dictionary.canonical",
    "artv_fdict_01",
  ),
  makeArtifact(
    "art_srccol_01",
    "proj_01JEXAMPLE",
    "source_collection",
    "观测星表来源集合",
    "source_collection.primary",
    "artv_srccol_01",
  ),
  makeArtifact(
    "art_papcol_01",
    "proj_01JEXAMPLE",
    "paper_collection",
    "检索文献集合 (7 篇)",
    "paper_collection.primary",
    "11111111-1111-4111-8111-111111111111",
  ),
  makeArtifact(
    "art_papsum_01",
    "proj_01JEXAMPLE",
    "paper_summary",
    "核心文献研读报告",
    "paper_summary.primary",
    "artv_papsum_01",
  ),
  makeArtifact(
    "art_claims_01",
    "proj_01JEXAMPLE",
    "literature_claims",
    "科学主张集合",
    "literature_claims.primary",
    "artv_claims_01",
  ),
  makeArtifact(
    "art_rels_01",
    "proj_01JEXAMPLE",
    "literature_relations",
    "科学主张关系与推导",
    "literature_relations.primary",
    "artv_rels_01",
  ),
  makeArtifact(
    "art_graph_01",
    "proj_01JEXAMPLE",
    "graph",
    "天文知识与证据图谱",
    "graph.primary",
    "artv_graph_01",
  ),
  makeArtifact(
    "art_analysis_01",
    "proj_01JEXAMPLE",
    "analysis_report",
    "TOI-1233 凌星拟合与动力学综合分析报告",
    "analysis_report.primary",
    "artv_analysis_01",
  ),
  makeArtifact(
    "art_vis_chart_01",
    "proj_01JEXAMPLE",
    "visualization",
    "系外行星周期-半径分布图",
    "visualization.chart",
    "artv_vis_chart_01",
  ),
  makeArtifact(
    "art_vis_fits_01",
    "proj_01JEXAMPLE",
    "visualization",
    "TOI-1233 TESS 目标像素图像",
    "visualization.fits",
    "artv_vis_fits_01",
  ),
  makeArtifact(
    "art_vis_wwt_01",
    "proj_01JEXAMPLE",
    "visualization",
    "TOI-1233 天文全景视口场景",
    "visualization.wwt",
    "artv_vis_wwt_01",
  ),
  makeArtifact(
    "art_spec_01",
    "proj_01JEXAMPLE",
    "spectrum",
    "TOI-1233 高分辨率恒星光谱",
    "spectrum.primary",
    "artv_spec_01",
  ),
  makeArtifact(
    "art_lc_01",
    "proj_01JEXAMPLE",
    "light_curve",
    "TOI-1233 TESS 测光光变曲线与相位折叠",
    "light_curve.primary",
    "artv_lc_01",
  ),
  makeArtifact(
    "art_modeval_01",
    "proj_01JEXAMPLE",
    "model_evaluation",
    "ResNet-1D 凌星分类模型评估",
    "model_evaluation.primary",
    "artv_modeval_01",
  ),
  makeArtifact(
    "art_model_01",
    "proj_01JEXAMPLE",
    "model_artifact",
    "ResNet-1D 凌星分类 ONNX 模型包",
    "model_artifact.primary",
    "artv_model_01",
  ),

  // Project B
  makeArtifact(
    "art_b_dataset_01",
    "proj_toi_transit",
    "dataset",
    "TOI 凌星光变分析数据集",
    "dataset.b",
    "artv_dataset_01",
  ),
  makeArtifact(
    "art_b_analysis_01",
    "proj_toi_transit",
    "analysis_report",
    "TOI-1233 凌星分析报告",
    "analysis_report.b",
    "artv_b_analysis_01",
  ),
  makeArtifact(
    "art_b_chart_01",
    "proj_toi_transit",
    "visualization",
    "周期-半径散点图",
    "visualization.b_chart",
    "artv_b_chart_01",
  ),
  makeArtifact(
    "art_b_lc_01",
    "proj_toi_transit",
    "light_curve",
    "TOI-1233 TESS 光变曲线",
    "light_curve.b",
    "artv_b_lc_01",
  ),
  makeArtifact(
    "art_b_modeval_01",
    "proj_toi_transit",
    "model_evaluation",
    "ResNet-1D 凌星模型评估",
    "model_evaluation.b",
    "artv_b_modeval_01",
  ),
  makeArtifact(
    "art_b_model_01",
    "proj_toi_transit",
    "model_artifact",
    "ResNet-1D ONNX 模型包",
    "model_artifact.b",
    "artv_b_model_01",
  ),

  // Project C
  makeArtifact(
    "art_c_spec_01",
    "proj_l9859_spectroscopy",
    "spectrum",
    "L 98-59 高分辨率光谱",
    "spectrum.c",
    "artv_c_spec_01",
  ),
  makeArtifact(
    "art_c_fits_01",
    "proj_l9859_spectroscopy",
    "visualization",
    "L 98-59 FITS 图像切片",
    "visualization.c_fits",
    "artv_c_fits_01",
  ),
  makeArtifact(
    "art_c_wwt_01",
    "proj_l9859_spectroscopy",
    "visualization",
    "L 98-59 WWT 天球视口场景",
    "visualization.c_wwt",
    "artv_c_wwt_01",
  ),
  makeArtifact(
    "art_c_analysis_01",
    "proj_l9859_spectroscopy",
    "analysis_report",
    "L 98-59 光谱学分析报告",
    "analysis_report.c",
    "artv_c_analysis_01",
  ),
];

const versionProducer = {
  name: "fixture-data-pipeline",
  type: "algorithm" as const,
  version: "1.0.0",
};

const makeVersion = (
  id: string,
  artifactId: string,
  projectId: string,
  kind: ArtifactVersionDto["content"]["kind"],
  evidenceIds: readonly string[] = [],
  runId: string = "run_01JEXAMPLE",
): ArtifactVersionDto => ({
  id,
  artifact_id: artifactId,
  project_id: projectId,
  created_by_run_id: runId,
  version_number: 1,
  schema_version: "2.0.0",
  content: {
    kind,
    field_ids: ["planet.toi_id", "star.tic_id"],
  } as ArtifactVersionDto["content"],
  content_hash: hash(id),
  input_hash: hash(`in_${id}`),
  source_mode: "fixture",
  producer: versionProducer,
  source_snapshot_ids: ["snap_01"],
  evidence_ids: [...evidenceIds],
  supersedes_version_id: null,
  created_at: T8,
});

const artifactVersions: readonly ArtifactVersionDto[] = [
  makeVersion(
    "artv_dataset_01",
    "art_dataset_01",
    "proj_01JEXAMPLE",
    "dataset",
    ["evd_01"],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_fdict_01",
    "art_fdict_01",
    "proj_01JEXAMPLE",
    "field_dictionary",
    [],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_srccol_01",
    "art_srccol_01",
    "proj_01JEXAMPLE",
    "source_collection",
    [],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_claims_01",
    "art_claims_01",
    "proj_01JEXAMPLE",
    "literature_claims",
    ["evd_02"],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_rels_01",
    "art_rels_01",
    "proj_01JEXAMPLE",
    "literature_relations",
    ["evd_03"],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_graph_01",
    "art_graph_01",
    "proj_01JEXAMPLE",
    "graph",
    ["evd_03"],
    "run_01JEXAMPLE",
  ),
  makeVersion(
    "artv_analysis_01",
    "art_analysis_01",
    "proj_01JEXAMPLE",
    "analysis_report",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_vis_chart_01",
    "art_vis_chart_01",
    "proj_01JEXAMPLE",
    "visualization",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_vis_fits_01",
    "art_vis_fits_01",
    "proj_01JEXAMPLE",
    "visualization",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_vis_wwt_01",
    "art_vis_wwt_01",
    "proj_01JEXAMPLE",
    "visualization",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_spec_01",
    "art_spec_01",
    "proj_01JEXAMPLE",
    "spectrum",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_lc_01",
    "art_lc_01",
    "proj_01JEXAMPLE",
    "light_curve",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_modeval_01",
    "art_modeval_01",
    "proj_01JEXAMPLE",
    "model_evaluation",
    [],
    "run_01JEXAMPLE_sci",
  ),
  makeVersion(
    "artv_model_01",
    "art_model_01",
    "proj_01JEXAMPLE",
    "model_artifact",
    [],
    "run_01JEXAMPLE_sci",
  ),

  // Project B versions
  makeVersion(
    "artv_b_analysis_01",
    "art_b_analysis_01",
    "proj_toi_transit",
    "analysis_report",
    [],
    "run_toi_transit",
  ),
  makeVersion(
    "artv_b_chart_01",
    "art_b_chart_01",
    "proj_toi_transit",
    "visualization",
    [],
    "run_toi_transit",
  ),
  makeVersion(
    "artv_b_lc_01",
    "art_b_lc_01",
    "proj_toi_transit",
    "light_curve",
    [],
    "run_toi_transit",
  ),
  makeVersion(
    "artv_b_modeval_01",
    "art_b_modeval_01",
    "proj_toi_transit",
    "model_evaluation",
    [],
    "run_toi_transit",
  ),
  makeVersion(
    "artv_b_model_01",
    "art_b_model_01",
    "proj_toi_transit",
    "model_artifact",
    [],
    "run_toi_transit",
  ),

  // Project C versions
  makeVersion(
    "artv_c_spec_01",
    "art_c_spec_01",
    "proj_l9859_spectroscopy",
    "spectrum",
    [],
    "run_l9859",
  ),
  makeVersion(
    "artv_c_fits_01",
    "art_c_fits_01",
    "proj_l9859_spectroscopy",
    "visualization",
    [],
    "run_l9859",
  ),
  makeVersion(
    "artv_c_wwt_01",
    "art_c_wwt_01",
    "proj_l9859_spectroscopy",
    "visualization",
    [],
    "run_l9859",
  ),
  makeVersion(
    "artv_c_analysis_01",
    "art_c_analysis_01",
    "proj_l9859_spectroscopy",
    "analysis_report",
    [],
    "run_l9859",
  ),
];

export const datasetEvidenceRead: EvidenceReadDto = {
  id: "evd_01",
  artifact_version_id: "artv_dataset_01",
  target_type: "field",
  target_id: "planet.toi_id",
  evidence_type: "database_query",
  source_snapshot_id: "snap_01",
  paper_id: null,
  locator: {
    kind: "database_cell",
    query_hash: "qhash_01",
    row_key: "TOI-1233.01",
    field: "planet.toi_id",
  },
  quote_or_value: "TOI-1233.01",
  extraction_method: "nasa_exoplanet_archive.api_lookup",
  confidence: 1,
  created_at: T6,
  source_snapshot: {
    id: "snap_01",
    source_id: "nasa_exoplanet_archive",
    source_type: "database",
    retrieved_at: T4,
    query: { table: "toi" },
    query_hash: hash("a"),
    source_version_or_etag: null,
    content_hash: hash("b"),
    license_note: "NASA Exoplanet Archive terms",
    cache_version: null,
    request_metadata: {},
  },
};

const evidence = [
  mapEvidenceRead(datasetEvidenceRead),
  {
    id: "evd_02",
    artifactVersionId: "artv_claims_01",
    targetType: "paper_summary",
    targetId: "psum_01",
    evidenceType: "paper_text",
    sourceSnapshotId: null,
    paperId: "paper_01",
    locator: {
      kind: "paper_text",
      section: "Results",
      page: 5,
      paragraph: 2,
      range: null,
    },
    quoteOrValue:
      "The host star TIC-260647166 has an effective temperature of 5720 ± 60 K.",
    extractionMethod: "paper_summary.extract_quote",
    confidence: 0.92,
    createdAt: T7,
  },
  {
    id: "evd_03",
    artifactVersionId: "artv_rels_01",
    targetType: "relation",
    targetId: "rel_01",
    evidenceType: "reasoning_trace",
    sourceSnapshotId: null,
    paperId: null,
    locator: {
      kind: "reasoning_trace",
      relationId: "rel_01",
      stepKey: "step_01",
    },
    quoteOrValue:
      "Claim 1 and Claim 2 are related via shared host-star TIC-260647166 parameters.",
    extractionMethod: "reasoning.infer_relation",
    confidence: 0.85,
    createdAt: T8,
  },
  ...paperSummaryReadFixture.evidence.map((item) =>
    mapEvidenceDetail(item as unknown as EvidenceDetailDto),
  ),
] as unknown as readonly Evidence[];

export const exoplanetHostStarFixture: FixtureBundle = {
  scenario: "exoplanet-host-star",
  schemaVersion: "2.0.0",
  executionMode: "demo_replay",
  sourceMode: "fixture",
  provenanceNote:
    "Demo Replay fixture for exoplanet host-star research. Data is deterministic and structured for guided presentation.",
  generatedAt: T0,
  data: {
    projects: [project, projectB, projectC, projectWaiting, projectFailed],
    contractDrafts: [draft, editableDraft],
    contracts: [contract],
    runs: [run, runB, runC],
    runEvents,
    artifacts,
    artifactVersions,
    paperAcquisitions: [
      {
        version: paperCollectionArtifactVersionFixture,
        collection: paperCollectionReadFixture,
        candidates: paperCandidateReadsFixture,
      },
    ],
    paperSummaries: [
      {
        version: paperSummaryArtifactVersionFixture,
        summary: paperSummaryReadFixture,
      },
    ],
    dataArtifactReads,
    fieldDictionaryArtifactReads,
    sourceCollectionArtifactReads,
    literatureClaimReads,
    literatureRelationReads,
    graphArtifactReads,
    graphNodeReads,
    graphEdgeReads,
    scientificArtifactReads: scientificArtifactReadsFixture,
    artifactPresentations,
    evidence,
  },
};
