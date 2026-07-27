/**
 * Exoplanet host-star integration fixture — the frozen main-case Demo Replay
 * scenario.
 *
 * Every payload is a snake_case `/api/v2` transport DTO that the fixture
 * adapter validates against the B-15 JSON Schemas before mapping into the
 * domain model. Timestamps, hashes and IDs are deterministic so Guided Tour
 * replays are reproducible.
 *
 * All artifact versions carry `source_mode: "fixture"` and the run carries
 * `execution_mode: "demo_replay"` — fixture data is never labelled live or
 * cached.
 */

import type {
  ArtifactVersionDto,
  ResearchArtifactDto,
  ResearchContractDto,
  ResearchContractDraftDto,
  ResearchContractInput as ResearchContractInputDto,
  ResearchProjectDto,
  ResearchRunDto,
  RunEventDto,
} from "@xingwen/contracts";
import type { Evidence } from "@xingwen/domain";

import type { FixtureBundle } from "./bundle";

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
  created_at: T0,
  updated_at: T2,
  revision: 1,
};

const draft: ResearchContractDraftDto = {
  id: "rcd_01JEXAMPLE",
  session_id: "sess_01JEXAMPLE",
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
    "sha256:a900a9fac201c6be7002237c16f1e52670733a5e4c8721d2bd9e6546e62dcaca",
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
  cache_policy: "fallback_on_recoverable_failure",
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
    event_type: "run.queued",
    step_key: null,
    progress: 0,
    public_message: "Run queued for Demo Replay",
    artifact_version_ids: [],
    occurred_at: T3,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 2,
    event_type: "run.planning",
    step_key: "planning",
    progress: 5,
    public_message: "Planning data and paper acquisition",
    artifact_version_ids: [],
    occurred_at: T4,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 3,
    event_type: "run.fetching_data",
    step_key: "fetching_data",
    progress: 15,
    public_message: "Fetching exoplanet and host-star data",
    artifact_version_ids: ["artv_srccol_01"],
    occurred_at: T5,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 4,
    event_type: "run.cleaning_data",
    step_key: "cleaning_data",
    progress: 25,
    public_message: "Cleaning and unit-normalising data",
    artifact_version_ids: ["artv_fdict_01", "artv_dataset_01"],
    occurred_at: T6,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 5,
    event_type: "run.searching_papers",
    step_key: "searching_papers",
    progress: 40,
    public_message: "Searching literature for exoplanet host-star studies",
    artifact_version_ids: ["artv_papcol_01"],
    occurred_at: T7,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 6,
    event_type: "run.summarizing_papers",
    step_key: "summarizing_papers",
    progress: 55,
    public_message: "Summarising retrieved papers",
    artifact_version_ids: ["artv_papsum_01"],
    occurred_at: T7,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 7,
    event_type: "run.reasoning_literature",
    step_key: "reasoning_literature",
    progress: 70,
    public_message: "Extracting claims, relations and reasoning traces",
    artifact_version_ids: ["artv_claims_01", "artv_rels_01", "artv_traces_01"],
    occurred_at: T8,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 8,
    event_type: "run.building_graph",
    step_key: "building_graph",
    progress: 90,
    public_message: "Building evidence graph",
    artifact_version_ids: ["artv_graph_01"],
    occurred_at: T8,
  },
  {
    run_id: "run_01JEXAMPLE",
    sequence: 9,
    event_type: "run.completed",
    step_key: null,
    progress: 100,
    public_message: "Demo Replay run completed",
    artifact_version_ids: [],
    occurred_at: T9,
  },
];

const producer = {
  type: "pipeline",
  name: "data",
  version: "1.0.0",
  model_name: null,
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
    latest_version_id: "artv_papcol_01",
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
    id: "art_traces_01",
    project_id: "proj_01JEXAMPLE",
    kind: "reasoning_traces",
    title: "Reasoning traces",
    logical_key: "reasoning_traces.primary",
    created_at: T8,
    latest_version_id: "artv_traces_01",
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
    schema_version: "2.0.0",
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
    id: "artv_papcol_01",
    artifact_id: "art_papcol_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: { kind: "paper_collection", paper_ids: ["paper_01", "paper_02"] },
    content_hash: hash("1"),
    input_hash: hash("2"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: [],
    supersedes_version_id: null,
    created_at: T7,
  },
  {
    id: "artv_papsum_01",
    artifact_id: "art_papsum_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: {
      kind: "paper_summary",
      paper_id: "paper_01",
      summary_id: "psum_01",
    },
    content_hash: hash("3"),
    input_hash: hash("4"),
    source_mode: "fixture",
    producer: { ...producer },
    source_snapshot_ids: [],
    evidence_ids: ["evd_02"],
    supersedes_version_id: null,
    created_at: T7,
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
    id: "artv_traces_01",
    artifact_id: "art_traces_01",
    project_id: "proj_01JEXAMPLE",
    created_by_run_id: "run_01JEXAMPLE",
    version_number: 1,
    schema_version: "2.0.0",
    content: { kind: "reasoning_traces", reasoning_trace_ids: ["trace_01"] },
    content_hash: hash("9"),
    input_hash: hash("a"),
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

const evidence = [
  {
    id: "evd_01",
    artifactVersionId: "artv_dataset_01",
    targetType: "field",
    targetId: "planet.toi_id",
    evidenceType: "database_query",
    sourceSnapshotId: "snap_01",
    paperId: null,
    locator: {
      kind: "database_cell",
      queryHash: "qhash_01",
      rowKey: "TOI-1234",
      field: "planet.toi_id",
    },
    quoteOrValue: "TOI-1234",
    extractionMethod: "nasa_exoplanet_archive.api_lookup",
    confidence: 1,
    createdAt: T6,
  },
  {
    id: "evd_02",
    artifactVersionId: "artv_papsum_01",
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
    evidence,
  },
};
