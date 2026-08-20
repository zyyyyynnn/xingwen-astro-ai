/**
 * Formal read-contract fixtures for the data, literature and graph ports.
 *
 * These are deliberately kept as transport-shaped values. The fixture
 * adapter passes them through the same mappers as the HTTP adapter; there is
 * no second fixture-only payload vocabulary or empty-content fallback.
 */

import type {
  DatasetArtifactRead,
  DatasetRow,
  EvidenceDetail,
  FieldDefinition,
  FieldDictionaryArtifactRead,
  GraphArtifactRead,
  GraphEdgeRead,
  GraphNodeRead,
  LiteratureArtifactVersionContext,
  LiteratureClaimRead,
  LiteratureRelationRead,
  ProducerExecutionDetail,
  SourceCollectionArtifactRead,
  SourceCollectionMember,
  SourceSnapshotDetail,
} from "@xingwen/contracts";

const PROJECT_ID = "proj_01JEXAMPLE";
const DATASET_VERSION_ID = "artv_dataset_01";
const FIELDS_VERSION_ID = "artv_fdict_01";
const SOURCES_VERSION_ID = "artv_srccol_01";
const CLAIMS_VERSION_ID = "artv_claims_01";
const RELATIONS_VERSION_ID = "artv_rels_01";
const GRAPH_VERSION_ID = "artv_graph_01";
const RUN_ID = "run_01JEXAMPLE";
const CREATED_AT = "2026-07-21T08:28:00Z";

function hash(seed: string): string {
  return `sha256:${seed.repeat(64)}`;
}

const sourceSnapshot: SourceSnapshotDetail = {
  id: "snap_01",
  source_id: "nasa_exoplanet_archive",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: { table: "exoplanet_candidates", fixture: true },
  query_hash: hash("q"),
  content_hash: hash("s"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "fixture-2026-07-21",
  license_note:
    "Fixture projection of the public NASA Exoplanet Archive schema.",
};

const producerExecution: ProducerExecutionDetail = {
  id: "exec_fixture_artifacts_01",
  run_id: RUN_ID,
  step_key: "artifact_projection",
  step_attempt_id: "attempt_fixture_artifacts_01",
  status: "completed",
  started_at: "2026-07-21T08:20:00Z",
  finished_at: CREATED_AT,
  input_hash: hash("i"),
  output_hash: hash("o"),
  parameters: { scenario: "exoplanet-host-star" },
  parameters_hash: hash("p"),
  latency_ms: 1,
  error_code: null,
  producer: {
    type: "pipeline",
    name: "fixture-artifact-projection",
    version: "1.0.0",
  },
};

function evidence(
  artifactVersionId: string,
  targetType: string,
  targetId: string,
  quoteOrValue: string,
): EvidenceDetail {
  return {
    id: `ev_${artifactVersionId}_${targetId.replaceAll(".", "_")}`,
    artifact_version_id: artifactVersionId,
    target_type: targetType,
    target_id: targetId,
    evidence_type: "database_query",
    source_snapshot_id: sourceSnapshot.id,
    extraction_method: "fixture.read_contract",
    confidence: 1,
    locator: { kind: "fixture_record", key: targetId },
    quote_or_value: quoteOrValue,
    paper_id: null,
    created_at: CREATED_AT,
  };
}

function dataBase(artifactId: string, artifactVersionId: string, kind: string) {
  return {
    artifact_id: artifactId,
    artifact_version_id: artifactVersionId,
    project_id: PROJECT_ID,
    schema_version: "1.0.0",
    source_mode: "fixture" as const,
    content_hash: hash(artifactVersionId.slice(-1)),
    input_hash: hash("d"),
    created_at: CREATED_AT,
    producer_execution: producerExecution,
    source_snapshots: [sourceSnapshot],
    evidence: [
      evidence(artifactVersionId, kind, `${kind}.candidate`, "fixture"),
    ],
    quality_projection: {
      bundle_commitment: hash("b"),
      candidate_content_hash: hash("c"),
      candidate_id: `${kind}_candidate_01`,
      candidate_input_hash: hash("d"),
      candidate_kind: kind,
      candidate_output_hash: hash("e"),
      content_hash: hash("f"),
      evaluation_commitment: hash("g"),
      evaluation_plan_content_hash: hash("h"),
      overall_status: "pass" as const,
      quality_input_hash: hash("i"),
      quality_result_content_hash: hash("j"),
      quality_result_id: `quality_${kind}_01`,
      quality_result_input_hash: hash("k"),
      quality_result_output_hash: hash("l"),
      research_contract: {
        id: "contract_01JEXAMPLE",
        version: "1.0.0",
        content_hash: hash("m"),
      },
      rule_set: {
        id: "quality_rules_01",
        version: "1.0.0",
        content_hash: hash("n"),
      },
    },
  };
}

const field: FieldDefinition = {
  field_id: "planet.toi_id",
  label_en: "TOI identifier",
  meaning_zh: "候选行星标识",
  description:
    "Stable identifier assigned by the TESS Object of Interest catalog.",
  data_type: "string",
  canonical_unit: "dimensionless",
  object_type: "planet",
  required: true,
  nullable: false,
  crossmatch_key: true,
  object_identity_key: true,
  source_priority: ["nasa_exoplanet_archive"],
  source_aliases: [
    {
      source_id: "nasa_exoplanet_archive",
      source_table: "exoplanet_candidates",
      raw_field: "toi",
      source_unit: "dimensionless",
      priority: 1,
      conversion_rule_id: "identity",
      row_key_fields: ["toi"],
    },
  ],
  conflict_resolution_rule_version: "1.0.0",
  conflict_resolution_strategy: "prefer_source_priority_preserve_all",
  crossmatch_rule_version: "1.0.0",
  evidence_locator_rule_id: "catalog-cell",
  quality_metric_inputs: ["completeness", "evidence_coverage"],
  transformation_rule_version: "1.0.0",
  limit_policy: {
    lower_limit_supported: false,
    upper_limit_supported: false,
    rule_version: "1.0.0",
  },
  null_policy: {
    allowed_reasons: ["not_in_source"],
    reason_required_when_null: true,
  },
  uncertainty_policy: {
    mode: "not_applicable",
    preserve_asymmetric_errors: false,
    rule_version: "1.0.0",
  },
};

const fieldTemperature: FieldDefinition = {
  ...field,
  field_id: "star.effective_temperature",
  label_en: "Effective temperature",
  meaning_zh: "恒星有效温度",
  description: "Stellar effective temperature from the host-star catalog.",
  data_type: "number",
  canonical_unit: "K",
  object_type: "star",
  required: false,
  nullable: true,
  crossmatch_key: false,
  object_identity_key: false,
  source_aliases: [
    {
      ...field.source_aliases[0],
      raw_field: "st_teff",
      source_unit: "K",
      row_key_fields: ["tic_id"],
    },
  ],
  null_policy: {
    allowed_reasons: ["not_measured", "not_in_source"],
    reason_required_when_null: true,
  },
  quality_metric_inputs: ["completeness", "unit_consistency"],
};

const row: DatasetRow = {
  row_id: "row_toi_1234",
  entity_level: "planet_candidate",
  alignment_status: "accepted",
  crossmatch_logical_key: "toi:1234",
  crossmatch_record_type: "planet_candidate",
  content_hash: hash("r"),
  canonical_row_identity: {
    alignment_status: "accepted",
    entity_level: "planet_candidate",
    record_type: "paired",
    member_entities: [
      {
        entity_level: "planet_candidate",
        identity_values: [
          {
            field_id: "planet.toi_id",
            normalized_value: "TOI-1234",
            normalization_rule_version: "1.0.0",
          },
        ],
      },
    ],
  },
  fields: [
    {
      canonical_field_id: "planet.toi_id",
      canonical_unit: "dimensionless",
      canonical_value: "TOI-1234",
      candidate_source_value_ids: ["source_value_toi_1234"],
      selected_source_value_id: "source_value_toi_1234",
      selection_id: "selection_toi_1234",
      conflict_ids: [],
      transformation_evidence_ids: [],
      status: "mapped",
    },
    {
      canonical_field_id: "star.effective_temperature",
      canonical_unit: "K",
      canonical_value: "5800",
      candidate_source_value_ids: ["source_value_teff_1234"],
      selected_source_value_id: "source_value_teff_1234",
      selection_id: "selection_teff_1234",
      conflict_ids: [],
      transformation_evidence_ids: [],
      status: "mapped",
    },
  ],
  conflict_ids: [],
  projected_field_ids: ["planet.toi_id", "star.effective_temperature"],
  projection_policy_version: "1.0.0",
  source_member_ids: ["source_member_nasa"],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: [],
};

const producer = {
  producer_name: "fixture-data-pipeline",
  producer_version: "1.0.0",
  producer_type: "algorithm" as const,
  conversion_catalog_id: "conversion_catalog_01",
  conversion_catalog_version: "1.0.0",
  conversion_catalog_content_hash: hash("v"),
  mapping_rule_set_id: "mapping_rules_01",
  mapping_rule_set_version: "1.0.0",
  mapping_rule_set_content_hash: hash("w"),
};

const manifestPins = {
  case_manifest_id: "case_manifest_01",
  case_manifest_version: "1.0.0",
  case_manifest_content_hash: hash("x"),
  field_manifest_id: "field_manifest_01",
  field_manifest_version: "1.0.0",
  field_manifest_content_hash: hash("y"),
};

const datasetCandidate = {
  candidate_id: "dataset_candidate_01",
  kind: "dataset" as const,
  schema_version: "1.0.0" as const,
  requested_fields: [field.field_id, fieldTemperature.field_id],
  columns: [{ field }, { field: fieldTemperature }],
  rows: [row],
  row_count: 1,
  field_count: 2,
  conflicts: [],
  evidence_ids: [],
  source_snapshot_ids: [sourceSnapshot.id],
  input_hash: hash("d"),
  output_hash: hash("e"),
  canonical_content_hash: hash("c"),
  lineage_hash: hash("l"),
  crossmatch_result_id: "crossmatch_01",
  crossmatch_input_hash: hash("a"),
  crossmatch_output_hash: hash("b"),
  crossmatch_content_hash: hash("c"),
  crossmatch_source_snapshot_ids: [sourceSnapshot.id],
  crossmatch_evidence_ids: [],
  crossmatch_evidence: [],
  producer,
  manifest_pins: manifestPins,
  conversion_catalog_id: producer.conversion_catalog_id,
  conversion_catalog_version: producer.conversion_catalog_version,
  conversion_catalog_content_hash: producer.conversion_catalog_content_hash,
  mapping_rule_set_id: producer.mapping_rule_set_id,
  mapping_rule_set_version: producer.mapping_rule_set_version,
  mapping_rule_set_content_hash: producer.mapping_rule_set_content_hash,
  quality_metric_input_declarations: ["completeness", "evidence_coverage"],
  selections: [],
  source_values: [],
  transformation_evidence: [],
};

const fieldDictionaryCandidate = {
  candidate_id: "field_dictionary_candidate_01",
  kind: "field_dictionary" as const,
  schema_version: "1.0.0" as const,
  requested_fields: [field.field_id, fieldTemperature.field_id],
  field_definitions: [field, fieldTemperature],
  evidence_ids: [],
  source_snapshot_ids: [sourceSnapshot.id],
  input_hash: hash("d"),
  output_hash: hash("e"),
  producer,
  manifest_pins: manifestPins,
  conversion_catalog_id: producer.conversion_catalog_id,
  conversion_catalog_version: producer.conversion_catalog_version,
  conversion_catalog_content_hash: producer.conversion_catalog_content_hash,
  mapping_rule_set_id: producer.mapping_rule_set_id,
  mapping_rule_set_version: producer.mapping_rule_set_version,
  mapping_rule_set_content_hash: producer.mapping_rule_set_content_hash,
};

const sourceMember: SourceCollectionMember = {
  source_id: "nasa_exoplanet_archive",
  source_snapshot_id: sourceSnapshot.id,
  source_snapshot_content_hash: sourceSnapshot.content_hash,
  source_snapshot: {
    snapshot_id: sourceSnapshot.id,
    source_id: sourceSnapshot.source_id,
    source_type: sourceSnapshot.source_type,
    retrieved_at: sourceSnapshot.retrieved_at,
    query: JSON.stringify(sourceSnapshot.query),
    query_hash: sourceSnapshot.query_hash,
    content_hash: sourceSnapshot.content_hash,
    license_note: sourceSnapshot.license_note,
    request_metadata: sourceSnapshot.request_metadata,
    source_version_or_etag: sourceSnapshot.source_version_or_etag,
  },
  side: "left",
  data_level: "fixture",
  source_mode: "fixture",
  raw_record_count: 1,
  raw_record_reference_registry_hash: hash("z"),
  raw_record_references: [
    {
      source_id: sourceSnapshot.source_id,
      source_snapshot_id: sourceSnapshot.id,
      source_snapshot_content_hash: sourceSnapshot.content_hash,
      query_hash: sourceSnapshot.query_hash,
      raw_record_content_hash: hash("r"),
      row_key: [["toi", "TOI-1234"]],
    },
  ],
  query_hash: sourceSnapshot.query_hash,
  completion: { status: "complete", continuation_cursor: null },
  license_note: sourceSnapshot.license_note,
};

const sourceCollectionCandidate = {
  candidate_id: "source_collection_candidate_01",
  kind: "source_collection" as const,
  schema_version: "1.0.0" as const,
  members: [sourceMember],
  source_snapshot_ids: [sourceSnapshot.id],
  source_value_ids: [],
  alignment_record_keys: ["toi:1234"],
  conflict_record_keys: [],
  inconclusive_record_keys: [],
  review_required_record_keys: [],
  evidence_ids: [],
  input_hash: hash("d"),
  output_hash: hash("e"),
  producer,
  manifest_pins: manifestPins,
  conversion_catalog_id: producer.conversion_catalog_id,
  conversion_catalog_version: producer.conversion_catalog_version,
  conversion_catalog_content_hash: producer.conversion_catalog_content_hash,
  mapping_rule_set_id: producer.mapping_rule_set_id,
  mapping_rule_set_version: producer.mapping_rule_set_version,
  mapping_rule_set_content_hash: producer.mapping_rule_set_content_hash,
  crossmatch_result_id: "crossmatch_01",
  crossmatch_content_hash: hash("c"),
};

export const dataArtifactReads: readonly DatasetArtifactRead[] = [
  {
    ...dataBase("art_dataset_01", DATASET_VERSION_ID, "dataset"),
    dataset: datasetCandidate,
  } as unknown as DatasetArtifactRead,
];

export const fieldDictionaryArtifactReads: readonly FieldDictionaryArtifactRead[] =
  [
    {
      ...dataBase("art_fdict_01", FIELDS_VERSION_ID, "field_dictionary"),
      field_dictionary: fieldDictionaryCandidate,
    } as unknown as FieldDictionaryArtifactRead,
  ];

export const sourceCollectionArtifactReads: readonly SourceCollectionArtifactRead[] =
  [
    {
      ...dataBase("art_srccol_01", SOURCES_VERSION_ID, "source_collection"),
      source_collection: sourceCollectionCandidate,
    } as unknown as SourceCollectionArtifactRead,
  ];

function literatureVersion(
  artifactId: string,
  artifactVersionId: string,
): LiteratureArtifactVersionContext {
  return {
    artifact_id: artifactId,
    artifact_version_id: artifactVersionId,
    project_id: PROJECT_ID,
    schema_version: "2.0.0",
    source_mode: "fixture",
    version_number: 1,
    content_hash: hash(artifactVersionId.slice(-1)),
    input_hash: hash("i"),
    output_hash: hash("o"),
    created_at: CREATED_AT,
    supersedes_version_id: null,
    producer_execution: producerExecution,
  };
}

const claimRead: LiteratureClaimRead = {
  version: literatureVersion("art_claims_01", CLAIMS_VERSION_ID),
  source_snapshots: [sourceSnapshot],
  evidence: [
    evidence(
      CLAIMS_VERSION_ID,
      "claim",
      "claim_01",
      "Host-star temperature is 5800 K.",
    ),
  ],
  paper_summary: {
    artifact_version_id: "artv_papsum_01",
    content_hash: hash("u"),
    output_hash: hash("v"),
    paper_id: "paper_01",
    schema_version: "2.0.0",
    summary_id: "psum_01",
  },
  claim: {
    claim_id: "claim_01",
    claim_type: "finding",
    text: "The host star TIC-5678 has an effective temperature of 5800 K.",
    normalized_text: "host star TIC-5678 effective temperature 5800 K",
    fingerprint: hash("claim"),
    status: "accepted",
    polarity: "positive",
    paper_id: "paper_01",
    producer_execution_id: producerExecution.id,
    model_response_hash: hash("m"),
    normalization_version: "1.0.0",
    input_hash: hash("i"),
    objects: ["TIC-5678"],
    scope: ["host star"],
    conditions: ["catalog host-star parameters"],
    qualifiers: [],
    limitations: ["Fixture evidence is bounded to the cited catalog record."],
    metric: "effective_temperature",
    unit: "K",
    uncertainty: null,
    comparison_basis: null,
    source_statement_id: "statement_01",
    source_summary_id: "psum_01",
    source_paper_summary_artifact_version_id: "artv_papsum_01",
    source_snapshot_ids: [sourceSnapshot.id],
    evidence_ids: [],
    failure_stage: null,
    rejection_reason: null,
  },
};

const relationRead: LiteratureRelationRead = {
  version: literatureVersion("art_rels_01", RELATIONS_VERSION_ID),
  source_snapshots: [sourceSnapshot],
  evidence: [
    evidence(
      RELATIONS_VERSION_ID,
      "relation",
      "rel_01",
      "Both claims use the same host-star parameter.",
    ),
  ],
  graph_eligible: true,
  source_claim: claimRead,
  target_claim: claimRead,
  relation: {
    relation_id: "rel_01",
    pair_id: "claim_01:claim_01",
    relation_type: "uses_same_dataset",
    status: "accepted",
    source_claim_id: "claim_01",
    target_claim_id: "claim_01",
    source_claim_artifact_version_id: CLAIMS_VERSION_ID,
    target_claim_artifact_version_id: CLAIMS_VERSION_ID,
    source_paper_summary_artifact_version_id: "artv_papsum_01",
    target_paper_summary_artifact_version_id: "artv_papsum_01",
    source_snapshot_ids: [sourceSnapshot.id],
    evidence_ids: [],
    conditions: ["same host-star catalog"],
    condition_conflicts: [],
    condition_uncertainties: [],
    comparability: {
      metric_basis: "effective temperature",
      metric_status: "comparable",
      object_basis: "TIC-5678",
      object_status: "comparable",
      unit_basis: "K",
      unit_status: "comparable",
    },
    direction: {
      basis: "shared host-star parameter",
      source_claim_id: "claim_01",
      target_claim_id: "claim_01",
    },
    confidence: null,
    reasoning_trace_id: "trace_01",
    fingerprint: hash("rel"),
    input_hash: hash("i"),
    model_response_hash: hash("m"),
    producer_execution_id: producerExecution.id,
    failure_stage: null,
    rejection_reason: null,
    review_reason: null,
  },
  reasoning_trace: {
    trace_id: "trace_01",
    relation_id: "rel_01",
    relation_status: "accepted",
    conclusion:
      "The claims are linked because they refer to the same host-star parameter.",
    premise_claim_ids: ["claim_01", "claim_01"],
    conditions: ["Both records identify TIC-5678."],
    conflicts: [],
    limitations: ["No causal relationship is inferred."],
    evidence_ids: ["ev_artv_rels_01_relation_rel_01"],
    input_hash: hash("i"),
    model_response_hash: hash("m"),
    producer_execution_id: producerExecution.id,
    trace_protocol_version: "1.0.0",
    steps: [
      {
        order: 1,
        operation: "compare_objects",
        statement: "Compare the host-star identity in each claim.",
        claim_ids: ["claim_01", "claim_01"],
        evidence_ids: ["ev_artv_rels_01_relation_rel_01"],
      },
    ],
  },
};

export const literatureClaimReads: readonly LiteratureClaimRead[] = [claimRead];
export const literatureRelationReads: readonly LiteratureRelationRead[] = [
  relationRead,
];

const graphVersion = {
  artifact_id: "art_graph_01",
  artifact_version_id: GRAPH_VERSION_ID,
  project_id: PROJECT_ID,
  schema_version: "2.0.0",
  source_mode: "fixture" as const,
  version_number: 1,
  content_hash: hash("g"),
  input_hash: hash("i"),
  output_hash: hash("o"),
  layout_hash: hash("l"),
  report_hash: hash("r"),
  scientific_hash: hash("s"),
  created_at: CREATED_AT,
  supersedes_version_id: null,
  producer_execution: producerExecution,
};

const graphInputVersion = {
  artifact_id: "art_dataset_01",
  artifact_version_id: DATASET_VERSION_ID,
  project_id: PROJECT_ID,
  kind: "dataset" as const,
  role: "dataset" as const,
  version_number: 1,
  schema_version: "1.0.0",
  source_mode: "fixture" as const,
  content_hash: hash("d"),
  input_hash: hash("i"),
  output_hash: hash("o"),
  parameters_hash: hash("p"),
  producer_name: "fixture-data-pipeline",
  producer_type: "algorithm" as const,
  producer_version: "1.0.0",
};

export const graphArtifactReads: readonly GraphArtifactRead[] = [
  {
    graph_id: "graph_01",
    project_id: PROJECT_ID,
    node_count: 2,
    edge_count: 1,
    evidence_use_count: 1,
    version: graphVersion,
    input_versions: {
      project_id: PROJECT_ID,
      versions: [graphInputVersion],
    },
    integrity_report: {
      status: "passed",
      content_hash: hash("h"),
      policy_version: "2.0.0",
      counts: {
        node_count: 2,
        edge_count: 1,
        evidence_use_count: 1,
        input_version_count: 1,
        relation_edge_count: 0,
        source_snapshot_count: 1,
      },
      findings: [],
      first_failure_stage: null,
      first_rejection_reason: null,
    },
    layout_hint: { strategy: "group_by_node_type" },
    policies: {
      integrity_policy_version: "2.0.0",
      taxonomy_policy_version: "2.0.0",
      progressive_policy: "complete_set_order_independent",
    },
    progressive: {
      progressive_id: "graph_progressive_01",
      chunk_count: 1,
      complete: true,
      chunks: [{ chunk_index: 0, item_ids: ["node_01", "node_02", "edge_01"] }],
    },
    scope: {
      include_data: true,
      research_goal_id: "goal_01",
      literature_claim_ids: ["claim_01"],
      literature_paper_ids: ["paper_01"],
      accepted_relation_ids: [],
      excluded_item_count: 0,
      filtered_item_count: 0,
      exclusion_reasons: [],
    },
    taxonomy: {
      content_hash: hash("t"),
      node_types: ["research_goal", "dataset", "field", "paper", "claim"],
      edge_types: [
        "uses_dataset",
        "provides_field",
        "supports_finding",
        "supports",
        "extends",
        "derived_from",
        "limits",
        "contradicts",
        "uses_same_dataset",
        "compares_method",
      ],
    },
  } as unknown as GraphArtifactRead,
];

export const graphNodeReads: readonly GraphNodeRead[] = [
  {
    version: graphVersion,
    node: {
      node_id: "node_01",
      node_type: "dataset",
      label: "Exoplanet candidate dataset",
      logical_reference: [
        { name: "artifact_version", value: DATASET_VERSION_ID },
      ],
      version_bindings: [
        {
          artifact_version_id: DATASET_VERSION_ID,
          domain_object_id: "dataset_candidate_01",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_02",
      node_type: "claim",
      label: "Host-star temperature finding",
      logical_reference: [{ name: "claim_id", value: "claim_01" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_01",
        },
      ],
    },
  },
];

export const graphEdgeReads: readonly GraphEdgeRead[] = [
  {
    version: graphVersion,
    evidence: [],
    edge: {
      edge_id: "edge_01",
      edge_type: "supports_finding",
      source_node_id: "node_01",
      target_node_id: "node_02",
      evidence_use_ids: ["evidence_use_01"],
      data_aggregation: {
        conflict_count: 0,
        declared_null_outcome_count: 0,
        mapped_outcome_count: 2,
        projected_row_count: 1,
        retained_candidate_count: 1,
        selected_candidate_count: 1,
        unresolved_outcome_count: 0,
        unselected_candidate_count: 0,
        upstream_evidence_count: 1,
      },
      relation_trace: null,
    },
  },
];
