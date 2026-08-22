/**
 * Exoplanet host-star integration fixture — the frozen main-case Demo Replay
 * scenario.
 *
 * Every payload is a snake_case `/api` transport DTO that the fixture
 * adapter validates against the Core Domain and Transport Contract JSON Schemas before mapping into the
 * domain model. Timestamps, hashes and IDs are deterministic so Guided Tour
 * replays are reproducible.
 *
 * All artifact versions carry `source_mode: "fixture"` and the run carries
 * `execution_mode: "demo_replay"` — fixture data is never labelled live or
 * cached.
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

function hash(char: string): string {
  return `sha256:${char.repeat(64)}`;
}

const contractInput: ResearchContractInputDto = {
  research_goal: "Integrate exoplanet candidates and host-star parameters",
  target_objects: ["exoplanet_candidate", "host_star"],
  data_requirements: { unit_policy: "canonical" },
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

const draft: ResearchContractDraftDto = {
  id: "rcd_01JEXAMPLE",
  session_id: "sess_01JEXAMPLE",
  project_id: "proj_01JEXAMPLE",
  version: 1,
  intent: "Integrate exoplanet candidates and host-star parameters",
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
    "sha256:7b810e492de26672a8f2cc4c70179a754e4a82ed3bd72461bcc9e9c2abbd983f",
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
    content: "正在根据研究协议规划数据与文献采集路径。",
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
    content: "已执行 TAP 查询并对齐 1,248 颗系外行星宿主星观测参数。",
    details: {
      tool_kind: "data_query",
      sql: "SELECT TOP 50 pl_name, hostname, sy_snum, sy_pnum, st_teff, st_met, st_logg FROM pscomppars WHERE st_met > 0.15;",
      row_count: 50,
      preview_rows: [
        {
          pl_name: "Kepler-10 b",
          hostname: "Kepler-10",
          st_teff: "5627 K",
          st_met: "+0.18",
        },
        {
          pl_name: "Kepler-22 b",
          hostname: "Kepler-22",
          st_teff: "5518 K",
          st_met: "-0.29",
        },
        {
          pl_name: "WASP-12 b",
          hostname: "WASP-12",
          st_teff: "6300 K",
          st_met: "+0.30",
        },
      ],
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
    content: "已完成字段整理与单位标准化（Teff: K, [Fe/H]: dex, logg: cgs）。",
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
    content: "已通过 NASA ADS 检索命中 3 篇系外行星宿主星核心论文。",
    details: {
      tool_kind: "search",
      papers: [
        {
          title:
            "Host Star Metallicity and Exoplanet Populations in the Kepler Field",
          authors: "Buchhave et al.",
          year: 2018,
          arxiv_id: "1805.01234",
        },
        {
          title:
            "Precise Stellar Parameters for 1000 Kepler Planet-hosting Stars",
          authors: "Petigura et al.",
          year: 2022,
          arxiv_id: "2203.05678",
        },
        {
          title:
            "Atmospheric Characterization of Kepler Terrestrial Exoplanets",
          authors: "Madhusudhan et al.",
          year: 2024,
          arxiv_id: "2401.09999",
        },
      ],
    },
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
    content: "已完成候选文献论点归纳与证据定位。",
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
    content: "已提取论点、宿主星物理参数关系与证据链。",
    details: {
      tool_kind: "evidence_validation",
      quote:
        "We find a statistically significant correlation between giant planet occurrence rate and host star iron abundance [Fe/H] (p < 1e-4).",
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
    activity_name: "生成证据图谱",
    step_key: "building_graph",
    progress: 90,
    content: "证据图谱已生成。",
    details: { tool_kind: "artifact_generation" },
    artifact_version_ids: ["artv_graph_01"],
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
    content: "研究任务已完成。",
    details: {},
    artifact_version_ids: [],
    occurred_at: T9,
  },
];

const producer = {
  type: "pipeline",
  name: "data",
  version: "1.0.0",
  requested_model: null,
  prompt_name: null,
  prompt_version: null,
  parameters_hash: null,
} as const;

const artifacts: readonly ResearchArtifactDto[] = [
  {
    id: "art_dataset_01",
    project_id: "proj_01JEXAMPLE",
    kind: "dataset",
    title: "Exoplanet host-star dataset",
    logical_key: "dataset.primary",
    created_at: T6,
    latest_version_id: "artv_dataset_01",
  },
  {
    id: "art_fdict_01",
    project_id: "proj_01JEXAMPLE",
    kind: "field_dictionary",
    title: "Canonical field dictionary",
    logical_key: "field_dictionary.canonical",
    created_at: T6,
    latest_version_id: "artv_fdict_01",
  },
  {
    id: "art_srccol_01",
    project_id: "proj_01JEXAMPLE",
    kind: "source_collection",
    title: "Source snapshots",
    logical_key: "source_collection.primary",
    created_at: T5,
    latest_version_id: "artv_srccol_01",
  },
  {
    id: "art_papcol_01",
    project_id: "proj_01JEXAMPLE",
    kind: "paper_collection",
    title: "Retrieved papers",
    logical_key: "paper_collection.primary",
    created_at: T7,
    latest_version_id: "11111111-1111-4111-8111-111111111111",
  },
  {
    id: "art_papsum_01",
    project_id: "proj_01JEXAMPLE",
    kind: "paper_summary",
    title: "Paper summary",
    logical_key: "paper_summary.primary",
    created_at: T7,
    latest_version_id: "artv_papsum_01",
  },
  {
    id: "art_claims_01",
    project_id: "proj_01JEXAMPLE",
    kind: "literature_claims",
    title: "Literature claims",
    logical_key: "literature_claims.primary",
    created_at: T8,
    latest_version_id: "artv_claims_01",
  },
  {
    id: "art_rels_01",
    project_id: "proj_01JEXAMPLE",
    kind: "literature_relations",
    title: "Literature relations",
    logical_key: "literature_relations.primary",
    created_at: T8,
    latest_version_id: "artv_rels_01",
  },
  {
    id: "art_graph_01",
    project_id: "proj_01JEXAMPLE",
    kind: "graph",
    title: "Evidence graph",
    logical_key: "graph.primary",
    created_at: T8,
    latest_version_id: "artv_graph_01",
  },
];

const artifactVersions: readonly ArtifactVersionDto[] = [
  {
    id: "artv_dataset_01",
    artifact_id: "art_dataset_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "1.0.0",
    content: {
      kind: "dataset",
      field_ids: ["planet.toi_id", "star.tic_id"],
      rows: [{ "planet.toi_id": "TOI-1234", "star.tic_id": "TIC-5678" }],
    },
    content_hash: hash("b"),
    input_hash: hash("c"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: ["snap_01"],
    evidence_ids: ["evd_01"],
    supersedes_version_id: null,
    created_at: T6,
  },
  {
    id: "artv_fdict_01",
    artifact_id: "art_fdict_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: {
      kind: "field_dictionary",
      field_ids: ["planet.toi_id", "star.tic_id"],
    },
    content_hash: hash("d"),
    input_hash: hash("e"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: [],
    supersedes_version_id: null,
    created_at: T6,
  },
  {
    id: "artv_srccol_01",
    artifact_id: "art_srccol_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: { kind: "source_collection", source_snapshot_ids: ["snap_01"] },
    content_hash: hash("f"),
    input_hash: hash("0"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: ["snap_01"],
    evidence_ids: [],
    supersedes_version_id: null,
    created_at: T5,
  },
  {
    id: "artv_claims_01",
    artifact_id: "art_claims_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: { kind: "literature_claims", claim_ids: ["claim_01", "claim_02"] },
    content_hash: hash("5"),
    input_hash: hash("6"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: ["evd_02"],
    supersedes_version_id: null,
    created_at: T8,
  },
  {
    id: "artv_rels_01",
    artifact_id: "art_rels_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: { kind: "literature_relations", relation_ids: ["rel_01"] },
    content_hash: hash("7"),
    input_hash: hash("8"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: ["evd_03"],
    supersedes_version_id: null,
    created_at: T8,
  },
  {
    id: "artv_graph_01",
    artifact_id: "art_graph_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: {
      kind: "graph",
      node_ids: ["node_01", "node_02"],
      edge_ids: ["edge_01"],
    },
    content_hash: hash("b"),
    input_hash: hash("c"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: ["evd_01", "evd_02", "evd_03"],
    supersedes_version_id: null,
    created_at: T8,
  },
];

/**
 * Single-source transport projection for the dataset evidence `evd_01`.
 *
 * The HTTP adapter serves this exact `EvidenceRead` payload from
 * `/api/evidence/evd_01` (see `test/http-helpers`), and the fixture adapter
 * maps the same DTO through the shared `mapEvidenceRead`, so both adapters
 * project identical domain entities — including the nested source snapshot.
 */
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
    row_key: "TOI-1234",
    field: "planet.toi_id",
  },
  quote_or_value: "TOI-1234",
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
  // Projected from the shared `EvidenceRead` transport DTO so the nested
  // source snapshot stays identical to the HTTP evidence read.
  mapEvidenceRead(datasetEvidenceRead),
  {
    id: "evd_02",
    // Homed on the claims version, which lists it in `evidence_ids`; the
    // rich `artv_papsum_01` carries its own `evd_papsum_*` records instead.
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
      "The host star TIC-5678 has an effective temperature of 5800 K.",
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
      "Claim_01 and Claim_02 are related via shared host-star parameter.",
    extractionMethod: "reasoning.infer_relation",
    confidence: 0.85,
    createdAt: T8,
  },
  // Paper summary evidence — same ids as the PaperSummary API read fixture so the summary
  // review, generic Evidence store, pinning and Share stay wired, mapped
  // through the shared `mapEvidenceDetail` DTO→domain projection.
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
    "Demo Replay fixture for the exoplanet host-star integration main case. Data is deterministic and not sourced from live APIs.",
  generatedAt: T0,
  data: {
    projects: [project],
    contractDrafts: [draft, editableDraft],
    contracts: [contract],
    runs: [run],
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
    evidence,
  },
};
