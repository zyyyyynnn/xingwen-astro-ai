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
import {
  asEntityId,
  type Evidence,
  type ResearchThreadEntry,
} from "@xingwen/domain";

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
import { TOI_1233_SHORT_PERIOD_ROW } from "./recorded-toi-1233-catalog";

const T0 = "2026-07-21T08:00:00Z";
const T1 = "2026-07-21T08:05:00Z";
const T2 = "2026-07-21T08:10:00Z";
const T3 = "2026-07-21T08:15:00Z";
const T4 = "2026-07-21T08:16:00Z";
const T5 = "2026-07-21T08:18:00Z";
const T6 = "2026-07-21T08:21:00Z";
const T7 = "2026-07-21T08:25:00Z";
const T8 = "2026-07-21T08:28:00Z";
const T5_AFTER = "2026-07-21T08:18:30Z";
const T6_AFTER = "2026-07-21T08:21:30Z";
const T7_AFTER = "2026-07-21T08:25:30Z";
const T8_AFTER = "2026-07-21T08:28:30Z";
const T9 = "2026-07-21T08:30:00Z";

function userThreadEntry(
  id: string,
  projectId: string,
  sequence: number,
  publicContent: string,
  createdAt: string,
): ResearchThreadEntry {
  return {
    id: asEntityId(id),
    projectId: asEntityId(projectId),
    sequence,
    kind: "user_message",
    actor: "user",
    publicContent,
    structuredPayload: { answerToQuestionId: null },
    modelExecutionId: null,
    createdAt,
  };
}

function assistantThreadEntry(
  id: string,
  projectId: string,
  sequence: number,
  publicContent: string,
  createdAt: string,
  draftId: string | null = null,
): ResearchThreadEntry {
  return {
    id: asEntityId(id),
    projectId: asEntityId(projectId),
    sequence,
    kind: "assistant_message",
    actor: "assistant",
    publicContent,
    structuredPayload: {
      outcome: draftId ? "draft_ready" : "partial",
      warnings: [],
      draftId: draftId ? asEntityId(draftId) : null,
      missingInformation: [],
      reason: null,
      errorCode: null,
    },
    modelExecutionId: null,
    createdAt,
  };
}

function clarificationQuestionThreadEntry(
  id: string,
  projectId: string,
  sequence: number,
  questionId: string,
  publicContent: string,
  options: readonly string[],
  createdAt: string,
): ResearchThreadEntry {
  return {
    id: asEntityId(id),
    projectId: asEntityId(projectId),
    sequence,
    kind: "clarification_question",
    actor: "assistant",
    publicContent,
    structuredPayload: {
      outcome: "clarification_required",
      warnings: [],
      draftId: null,
      missingInformation: ["观测时间范围与数据公开范围"],
      reason: "必须先明确检索边界，才能形成可确认的研究协议。",
      errorCode: null,
      questionId: asEntityId(questionId),
      options,
    },
    modelExecutionId: null,
    createdAt,
  };
}

const threadEntries: readonly ResearchThreadEntry[] = [
  userThreadEntry(
    "thread_a_user_01",
    "proj_01JEXAMPLE",
    1,
    "整合系外行星候选体与宿主星参数，并为数据、文献主张和关系保留可核验证据。",
    T0,
  ),
  assistantThreadEntry(
    "thread_a_assistant_01",
    "proj_01JEXAMPLE",
    2,
    "我已整理研究目标与来源范围。请先核对研究协议，确认后将按冻结口径生成数据集、文献报告与证据图谱。",
    T1,
    "rcd_01JEXAMPLE",
  ),
  assistantThreadEntry(
    "thread_a_assistant_data",
    "proj_01JEXAMPLE",
    3,
    "目录对齐已完成：40 条候选体与宿主星记录来自两份冻结的 NASA Exoplanet Archive API 响应，14 项字段均保留行级定位证据。下一步进入文献检索与全文研读。",
    T6_AFTER,
  ),
  assistantThreadEntry(
    "thread_a_assistant_literature",
    "proj_01JEXAMPLE",
    4,
    "文献检索得到 7 条候选记录，已选 3 篇进入研读；核心报告固定到已绑定 PDF，并保留 5 个章节的页码级证据。接下来核验声明之间的科学关系。",
    T7_AFTER,
  ),
  assistantThreadEntry(
    "thread_a_assistant_review",
    "proj_01JEXAMPLE",
    5,
    "已形成 6 条科学声明和 5 条公开关系，其中 2 条候选关系仍需人工审定。已接受关系已进入证据图谱，候选关系不会在审定前发布。",
    T8_AFTER,
  ),
  assistantThreadEntry(
    "thread_a_assistant_02",
    "proj_01JEXAMPLE",
    6,
    "研究已完成。建议先处理 2 条候选关系，再从证据图谱回到论文原文复核关键结论。",
    T9,
  ),
  userThreadEntry(
    "thread_b_user_01",
    "proj_toi_transit",
    1,
    "核对 TOI-1233 的公开目录参数，并用明确标注的 Demo Replay 样例检查光变、图表和模型结果界面。",
    T0,
  ),
  assistantThreadEntry(
    "thread_b_assistant_01",
    "proj_toi_transit",
    2,
    "研究协议已准备：目录参数来自冻结的 NASA Exoplanet Archive TAP 响应；光变与模型数值仅用于界面状态覆盖，不会冒充观测或科研基准。",
    T1,
    "rcd_toi_transit",
  ),
  assistantThreadEntry(
    "thread_b_assistant_light_curve",
    "proj_toi_transit",
    3,
    `已读取 TOI-${TOI_1233_SHORT_PERIOD_ROW.toi} 的冻结目录周期、深度与持续时间，并生成 720 点确定性界面样例；这些点不是原始 TESS 光度序列。`,
    T5_AFTER,
  ),
  assistantThreadEntry(
    "thread_b_assistant_analysis",
    "proj_toi_transit",
    4,
    "目录核验报告与周期-半径图已生成；品牌色点可回溯到冻结目录，额外容量样例不参与科研解释。",
    T6_AFTER,
  ),
  assistantThreadEntry(
    "thread_b_assistant_evaluation",
    "proj_toi_transit",
    5,
    "模型评估界面样例已覆盖指标、基线差异和诊断状态；fixture 未绑定训练集或真实运行，指标不能作为算法性能结论。",
    T7_AFTER,
  ),
  assistantThreadEntry(
    "thread_b_assistant_model",
    "proj_toi_transit",
    6,
    "ONNX 结果页已覆盖不可下载状态、依赖和输入输出元数据；fixture 引用不是可部署生产模型。",
    T8_AFTER,
  ),
  assistantThreadEntry(
    "thread_b_assistant_02",
    "proj_toi_transit",
    7,
    "TOI-1233 目录核验与界面能力回放已完成；任何观测拟合或模型科研结论仍需绑定真实数据与执行记录后另行发布。",
    T9,
  ),
  userThreadEntry(
    "thread_c_user_01",
    "proj_l9859_spectroscopy",
    1,
    "核验 L 98-59 的公开 HARPS 光谱记录，并用独立的 Demo Replay 图层检查 FITS 与天球场景交互。",
    T0,
  ),
  assistantThreadEntry(
    "thread_c_assistant_01",
    "proj_l9859_spectroscopy",
    2,
    "研究协议已准备：HARPS 光谱绑定公开归档产品；FITS 与天球图层仅用于界面能力回放，并与真实光谱来源明确分离。",
    T1,
    "rcd_l9859",
  ),
  assistantThreadEntry(
    "thread_c_assistant_spectrum",
    "proj_l9859_spectroscopy",
    3,
    "L 98-59 的公开 HARPS 一维光谱已形成 512 点固定显示投影；本次回放未自动给出谱线证认，来源产品与转换方法均可复核。",
    T5_AFTER,
  ),
  assistantThreadEntry(
    "thread_c_assistant_fits",
    "proj_l9859_spectroscopy",
    4,
    "TESS 图像切片已作为独立来源快照组织，可在观测工作区中核对图像状态；它不会与 HARPS 光谱合并冒充同一观测来源。",
    T6_AFTER,
  ),
  assistantThreadEntry(
    "thread_c_assistant_scene",
    "proj_l9859_spectroscopy",
    5,
    "天球场景已固定到 L 98-59 的目标坐标与图层配置；交互控制会把实际 readback 显示在观测状态中。",
    T7_AFTER,
  ),
  assistantThreadEntry(
    "thread_c_assistant_02",
    "proj_l9859_spectroscopy",
    6,
    "L 98-59 观测研究已完成，可在统一观测工作区中依次复核光谱、FITS 与天球场景。",
    T9,
  ),
  userThreadEntry(
    "thread_waiting_user_01",
    "proj_waiting_demo",
    1,
    "为 TIC-307210830 编制后续观测协议，并优先使用可公开核验的数据来源。",
    T0,
  ),
  clarificationQuestionThreadEntry(
    "thread_waiting_question_01",
    "proj_waiting_demo",
    2,
    "question_waiting_scope",
    "为了确定观测协议边界，需要先确认希望覆盖的时间范围与数据公开范围。",
    ["近三年公开数据", "全部公开历史数据", "仅指定观测季"],
    T1,
  ),
  assistantThreadEntry(
    "thread_failed_assistant_01",
    "proj_failed_demo",
    1,
    "本次运行没有发布新的科研结果；研究输入与协议仍保留，可在来源恢复后继续。",
    T1,
  ),
];

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
  name: "TOI-1233 目录核验与科研界面能力回放",
  description:
    "冻结公开目录参数，并以明确标注的 Demo Replay 样例覆盖光变、图表和模型界面",
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
    "公开 HARPS 光谱记录投影，以及独立标注的 FITS 与 WWT 交互界面样例",
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
  name: "TIC-307210830 观测协议待确认",
  description: "等待确认观测时间范围与公开数据边界",
  case_key: "exoplanet_host_star",
  active_contract_id: null,
  latest_run_id: null,
  thread_summary: {
    has_thread_entries: true,
    latest_thread_actor: "assistant",
    has_unanswered_clarification: true,
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
  active_contract_id: "rc_failed_demo",
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

const contractInputB: ResearchContractInputDto = {
  research_goal:
    "核验 TOI-1233 冻结公开目录参数，并覆盖光变、图表与模型结果界面的完整状态",
  target_objects: ["transiting_exoplanet", "host_star"],
  data_requirements: {
    unit_policy: "canonical",
    document_source_policy: "disabled",
  },
  requested_fields: ["time.bjd", "flux.normalized", "planet.period"],
  source_scope: { allowed_sources: ["nasa_exoplanet_archive.toi"] },
  paper_search_scope: {
    keywords: ["TOI-1233", "transit photometry"],
    year_from: 2019,
    year_to: 2026,
    source_ids: ["nasa_exoplanet_archive.toi"],
    max_candidates: 3,
  },
  output_requirements: [
    "analysis_report",
    "visualization",
    "light_curve",
    "model_evaluation",
    "model_artifact",
  ],
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

const contractInputC: ResearchContractInputDto = {
  research_goal:
    "核验 L 98-59 公开 HARPS 光谱记录，并覆盖 FITS 与 WWT 界面的完整交互状态",
  target_objects: ["dwarf_star", "tess_field"],
  data_requirements: {
    unit_policy: "canonical",
    document_source_policy: "disabled",
  },
  requested_fields: ["spectrum.wavelength", "spectrum.flux", "target.ra_dec"],
  source_scope: { allowed_sources: ["fixture.l9859_scene", "eso.harps"] },
  paper_search_scope: {
    keywords: ["L 98-59", "TOI-175", "high-resolution spectroscopy"],
    year_from: 2019,
    year_to: 2026,
    source_ids: ["fixture.l9859_scene"],
    max_candidates: 3,
  },
  output_requirements: ["analysis_report", "spectrum", "visualization"],
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

const contractInputFailed: ResearchContractInputDto = {
  research_goal:
    "核对 TOI-9999 的 TESS 时序数据可用性，并在来源失败时保留可恢复上下文",
  target_objects: ["transiting_exoplanet"],
  data_requirements: {
    unit_policy: "canonical",
    document_source_policy: "disabled",
  },
  requested_fields: ["time.bjd", "flux.normalized"],
  source_scope: { allowed_sources: ["mast.tess"] },
  paper_search_scope: {
    keywords: ["TOI-9999", "TESS"],
    year_from: 2019,
    year_to: 2026,
    source_ids: ["mast.tess"],
    max_candidates: 3,
  },
  output_requirements: ["light_curve", "analysis_report"],
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

const draftB: ResearchContractDraftDto = {
  id: "rcd_toi_transit",
  session_id: "sess_toi_transit",
  project_id: "proj_toi_transit",
  version: 1,
  intent:
    "Verify the recorded TOI-1233 catalog response and exercise result UI states without presenting generated samples as observations",
  status: "confirmed",
  contract: { ...contractInputB },
  warnings: [],
  created_at: T1,
  updated_at: T2,
  expires_at: "2026-07-21T09:05:00Z",
};

const draftC: ResearchContractDraftDto = {
  id: "rcd_l9859",
  session_id: "sess_l9859",
  project_id: "proj_l9859_spectroscopy",
  version: 1,
  intent:
    "Verify the recorded L 98-59 HARPS product and exercise FITS and WWT UI states with separately identified fixture layers",
  status: "confirmed",
  contract: { ...contractInputC },
  warnings: [],
  created_at: T1,
  updated_at: T2,
  expires_at: "2026-07-21T09:05:00Z",
};

const draftFailed: ResearchContractDraftDto = {
  id: "rcd_failed_demo",
  session_id: "sess_failed",
  project_id: "proj_failed_demo",
  version: 1,
  intent:
    "Verify TOI-9999 TESS source availability with a recoverable failure path",
  status: "confirmed",
  contract: { ...contractInputFailed },
  warnings: [],
  created_at: T0,
  updated_at: T0,
  expires_at: "2026-07-21T09:05:00Z",
};

const contractB: ResearchContractDto = {
  ...contractInputB,
  id: "rc_toi_transit",
  project_id: "proj_toi_transit",
  version: 1,
  created_from_draft_id: "rcd_toi_transit",
  created_at: T2,
  content_hash: hash("rc_toi_transit"),
};

const contractC: ResearchContractDto = {
  ...contractInputC,
  id: "rc_l9859",
  project_id: "proj_l9859_spectroscopy",
  version: 1,
  created_from_draft_id: "rcd_l9859",
  created_at: T2,
  content_hash: hash("rc_l9859"),
};

const contractFailed: ResearchContractDto = {
  ...contractInputFailed,
  id: "rc_failed_demo",
  project_id: "proj_failed_demo",
  version: 1,
  created_from_draft_id: "rcd_failed_demo",
  created_at: T0,
  content_hash: hash("rc_failed_demo"),
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
  contract_id: "rc_toi_transit",
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
  latest_event_sequence: 6,
  failure_code: null,
  failure_summary: null,
};

const runC: ResearchRunDto = {
  id: "run_l9859",
  project_id: "proj_l9859_spectroscopy",
  contract_id: "rc_l9859",
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
  latest_event_sequence: 5,
  failure_code: null,
  failure_summary: null,
};

const runFailed: ResearchRunDto = {
  id: "run_failed_demo",
  project_id: "proj_failed_demo",
  contract_id: "rc_failed_demo",
  execution_mode: "demo_replay",
  status: "failed",
  progress: 35,
  parent_run_id: null,
  derivation_kind: "original",
  retry_from_step: null,
  cache_policy: "disabled",
  started_at: T0,
  finished_at: T1,
  created_at: T0,
  updated_at: T1,
  latest_event_sequence: 1,
  failure_code: "source_timeout",
  failure_summary: "数据源连接超时，请检查来源可用性后重试。",
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
    content: "已抽取 6 条科学主张与 5 条科学关系，完成可比性推导与审定分析。",
    details: {
      tool_kind: "evidence_validation",
      quote:
        "Recorded TOI table rows 1233.01-1233.04 share TIC 260647166 and retain distinct orbital periods.",
      locator: "NASA Exoplanet Archive TAP · toi rows 1233.01-1233.04",
      confidence: 1,
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
      "已综合生成 16 节点 19 边证据知识图谱；仅已接受关系进入图谱，并冻结数据、文献与来源清单版本。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_graph_01", "artv_export_01"],
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
  {
    run_id: "run_toi_transit",
    sequence: 1,
    activity_id: "run:run_toi_transit",
    activity_kind: "status",
    activity_phase: "queued",
    activity_name: "研究任务",
    step_key: null,
    progress: 0,
    content: "研究任务已进入执行队列。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T4,
  },
  {
    run_id: "run_toi_transit",
    sequence: 2,
    activity_id: "fixture:transit-light-curve",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "生成光变界面样例",
    step_key: "light_curve_analysis",
    progress: 30,
    content:
      "已按冻结 TOI 目录周期与深度生成确定性界面样例；未读取或筛选原始 TESS 光度序列。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_b_lc_01"],
    occurred_at: T5,
  },
  {
    run_id: "run_toi_transit",
    sequence: 3,
    activity_id: "fixture:transit-analysis",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "核验目录并组织图表",
    step_key: "transit_analysis",
    progress: 55,
    content:
      "已核对冻结目录参数，并将真实目录点与明确标注的容量边界样例分层呈现。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_b_analysis_01", "artv_b_chart_01"],
    occurred_at: T6,
  },
  {
    run_id: "run_toi_transit",
    sequence: 4,
    activity_id: "fixture:transit-model-evaluation",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "演示模型评估界面",
    step_key: "model_evaluation",
    progress: 78,
    content: "已覆盖模型指标、基线差异与限制说明；未绑定真实训练集或模型执行。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_b_modeval_01"],
    occurred_at: T7,
  },
  {
    run_id: "run_toi_transit",
    sequence: 5,
    activity_id: "fixture:transit-model-publication",
    activity_kind: "artifact",
    activity_phase: "completed",
    activity_name: "组织模型元数据样例",
    step_key: "model_publication",
    progress: 92,
    content:
      "已覆盖 ONNX 元数据、依赖与不可下载状态；fixture 引用不是可部署模型文件。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_b_model_01"],
    occurred_at: T8,
  },
  {
    run_id: "run_toi_transit",
    sequence: 6,
    activity_id: "run:run_toi_transit",
    activity_kind: "completion",
    activity_phase: "completed",
    activity_name: "研究任务",
    step_key: null,
    progress: 100,
    content: "公开目录核验与科研界面能力回放已完成。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T9,
  },
  {
    run_id: "run_l9859",
    sequence: 1,
    activity_id: "run:run_l9859",
    activity_kind: "status",
    activity_phase: "queued",
    activity_name: "研究任务",
    step_key: null,
    progress: 0,
    content: "研究任务已进入执行队列。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T4,
  },
  {
    run_id: "run_l9859",
    sequence: 2,
    activity_id: "fixture:l9859-spectrum",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "投影公开 HARPS 光谱",
    step_key: "spectrum_acquisition",
    progress: 38,
    content:
      "已完成 L 98-59 公开 HARPS 一维光谱的连续谱归一化显示投影；未运行谱线证认。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_c_analysis_01", "artv_c_spec_01"],
    occurred_at: T5,
  },
  {
    run_id: "run_l9859",
    sequence: 3,
    activity_id: "fixture:l9859-fits",
    activity_kind: "tool",
    activity_phase: "completed",
    activity_name: "校准 FITS 图像",
    step_key: "fits_calibration",
    progress: 66,
    content: "已完成 FITS 图像切片、坐标标定与来源固定。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_c_fits_01"],
    occurred_at: T6,
  },
  {
    run_id: "run_l9859",
    sequence: 4,
    activity_id: "fixture:l9859-wwt",
    activity_kind: "artifact",
    activity_phase: "completed",
    activity_name: "合成天球观测场景",
    step_key: "wwt_scene",
    progress: 90,
    content: "已固定目标坐标、图层与 WWT 场景控制状态。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_c_wwt_01"],
    occurred_at: T7,
  },
  {
    run_id: "run_l9859",
    sequence: 5,
    activity_id: "run:run_l9859",
    activity_kind: "completion",
    activity_phase: "completed",
    activity_name: "研究任务",
    step_key: null,
    progress: 100,
    content: "观测研究任务已完成。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T9,
  },
  {
    run_id: "run_failed_demo",
    sequence: 1,
    activity_id: "fixture:failed-source-acquisition",
    activity_kind: "tool",
    activity_phase: "failed",
    activity_name: "读取 TESS 时序来源",
    step_key: "light_curve_acquisition",
    progress: 35,
    content:
      "来源请求在取得可验证记录前超时，未发布光变或分析结果；可从该步骤重试。",
    details: {
      tool_kind: "data_query",
      failure_code: "source_timeout",
      recoverable: true,
    },
    artifact_version_ids: [],
    occurred_at: T1,
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
    "目录数据来源集合",
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
    "科学关系与公开推导",
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
    "art_export_01",
    "proj_01JEXAMPLE",
    "export",
    "研究来源与证据导出包",
    "export.provenance",
    "artv_export_01",
  ),

  // Project B
  makeArtifact(
    "art_b_analysis_01",
    "proj_toi_transit",
    "analysis_report",
    "TOI-1233.04 公开目录参数核验与界面能力样例",
    "analysis_report.b",
    "artv_b_analysis_01",
  ),
  makeArtifact(
    "art_b_chart_01",
    "proj_toi_transit",
    "visualization",
    "TOI-1233 冻结目录周期-半径图",
    "visualization.b_chart",
    "artv_b_chart_01",
  ),
  makeArtifact(
    "art_b_lc_01",
    "proj_toi_transit",
    "light_curve",
    "TOI-1233.04 目录参数驱动的光变界面样例",
    "light_curve.b",
    "artv_b_lc_01",
  ),
  makeArtifact(
    "art_b_modeval_01",
    "proj_toi_transit",
    "model_evaluation",
    "凌星分类器评估",
    "model_evaluation.b",
    "artv_b_modeval_01",
  ),
  makeArtifact(
    "art_b_model_01",
    "proj_toi_transit",
    "model_artifact",
    "ResNet-1D ONNX 模型",
    "model_artifact.b",
    "artv_b_model_01",
  ),

  // Project C
  makeArtifact(
    "art_c_spec_01",
    "proj_l9859_spectroscopy",
    "spectrum",
    "L 98-59 公开 HARPS 一维光谱",
    "spectrum.c",
    "artv_c_spec_01",
  ),
  makeArtifact(
    "art_c_fits_01",
    "proj_l9859_spectroscopy",
    "visualization",
    "L 98-59 FITS 图像",
    "visualization.c_fits",
    "artv_c_fits_01",
  ),
  makeArtifact(
    "art_c_wwt_01",
    "proj_l9859_spectroscopy",
    "visualization",
    "L 98-59 WWT 天球场景",
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
  sourceSnapshotIds: readonly string[] = ["snap_01"],
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
  source_snapshot_ids: [...sourceSnapshotIds],
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
    ["snap_toi_1233_recorded"],
  ),
  makeVersion(
    "artv_rels_01",
    "art_rels_01",
    "proj_01JEXAMPLE",
    "literature_relations",
    ["evd_03"],
    "run_01JEXAMPLE",
    ["snap_toi_1233_recorded"],
  ),
  makeVersion(
    "artv_graph_01",
    "art_graph_01",
    "proj_01JEXAMPLE",
    "graph",
    ["evd_03"],
    "run_01JEXAMPLE",
    ["snap_01", "snap_toi_1233_recorded"],
  ),
  {
    id: "artv_export_01",
    artifact_id: "art_export_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: {
      kind: "export",
      schema_version: "2.0.0",
      format: "provenance_report",
      artifact_version_ids: [
        "artv_dataset_01",
        "artv_papsum_01",
        "artv_graph_01",
      ],
    },
    content_hash: hash("artv_export_01"),
    input_hash: hash("in_artv_export_01"),
    source_mode: "fixture",
    producer: versionProducer,
    source_snapshot_ids: [],
    evidence_ids: [],
    supersedes_version_id: null,
    created_at: T8,
  },

  // Project B versions
  makeVersion(
    "artv_b_analysis_01",
    "art_b_analysis_01",
    "proj_toi_transit",
    "analysis_report",
    ["ev_b_analysis_tess", "ev_b_analysis_catalog"],
    "run_toi_transit",
    ["snap_sci_01"],
  ),
  makeVersion(
    "artv_b_chart_01",
    "art_b_chart_01",
    "proj_toi_transit",
    "visualization",
    ["ev_b_chart_source"],
    "run_toi_transit",
    ["snap_sci_01"],
  ),
  makeVersion(
    "artv_b_lc_01",
    "art_b_lc_01",
    "proj_toi_transit",
    "light_curve",
    ["ev_b_lightcurve_source", "ev_b_lightcurve_period"],
    "run_toi_transit",
    ["snap_sci_01"],
  ),
  makeVersion(
    "artv_b_modeval_01",
    "art_b_modeval_01",
    "proj_toi_transit",
    "model_evaluation",
    ["ev_b_modeval_source"],
    "run_toi_transit",
    ["snap_sci_01"],
  ),
  makeVersion(
    "artv_b_model_01",
    "art_b_model_01",
    "proj_toi_transit",
    "model_artifact",
    ["ev_b_model_source"],
    "run_toi_transit",
    ["snap_sci_01"],
  ),

  // Project C versions
  makeVersion(
    "artv_c_spec_01",
    "art_c_spec_01",
    "proj_l9859_spectroscopy",
    "spectrum",
    ["ev_c_spec_source"],
    "run_l9859",
    ["snap_l9859_harps_20240309"],
  ),
  makeVersion(
    "artv_c_fits_01",
    "art_c_fits_01",
    "proj_l9859_spectroscopy",
    "visualization",
    ["ev_c_fits_source"],
    "run_l9859",
    ["snap_l9859_tess"],
  ),
  makeVersion(
    "artv_c_wwt_01",
    "art_c_wwt_01",
    "proj_l9859_spectroscopy",
    "visualization",
    ["ev_c_wwt_source"],
    "run_l9859",
    ["snap_l9859_tess"],
  ),
  makeVersion(
    "artv_c_analysis_01",
    "art_c_analysis_01",
    "proj_l9859_spectroscopy",
    "analysis_report",
    ["ev_c_analysis_source"],
    "run_l9859",
    ["snap_l9859_harps_20240309", "snap_l9859_tess"],
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
    targetType: "source",
    targetId: "snap_toi_1233_recorded",
    evidenceType: "database_query",
    sourceSnapshotId: "snap_toi_1233_recorded",
    paperId: null,
    locator: {
      kind: "database_query",
      table: "toi",
      rowRange: "1233.01-1233.04",
    },
    quoteOrValue:
      "TOI-1233.04: TIC 260647166, P=3.79589 d, Rp=1.553135 R_Earth; TOI-1233.01: P=14.1758947 d.",
    extractionMethod: "recorded.nasa_exoplanet_archive_toi",
    confidence: 1,
    createdAt: T7,
  },
  {
    id: "evd_03",
    artifactVersionId: "artv_rels_01",
    targetType: "relation",
    targetId: "rel_01",
    evidenceType: "reasoning_trace",
    sourceSnapshotId: "snap_toi_1233_recorded",
    paperId: null,
    locator: {
      kind: "reasoning_trace",
      relationId: "rel_01",
      stepKey: "step_01",
    },
    quoteOrValue:
      "Accepted relations only reuse shared TIC and exact frozen catalog fields; candidate cross-table or dynamical interpretations remain unaccepted.",
    extractionMethod: "reasoning.catalog_identity_relation",
    confidence: 1,
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
    threadEntries,
    contractDrafts: [draft, editableDraft, draftB, draftC, draftFailed],
    contracts: [contract, contractB, contractC, contractFailed],
    runs: [run, runB, runC, runFailed],
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
