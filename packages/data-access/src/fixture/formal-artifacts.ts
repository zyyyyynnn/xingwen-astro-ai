/**
 * Formal read-contract fixtures for data, literature and graph ports.
 *
 * 1. Dataset: 40 recorded NASA catalog joins across 14 fields and 2 responses
 * 2. Field Dictionary: 14 rich domain field definitions
 * 3. Source Collection: 3 observational and catalog sources (NASA TOI, NASA PS, Gaia DR3)
 * 4. Claims: 6 distinct grounded scientific claims
 * 5. Relations: 5 distinct inter-claim relations without self-loops
 * 6. Graph: 16 nodes, 20 edges consuming accepted relations
 */

import type {
  CrossmatchArtifactAuthority,
  DatasetArtifactRead,
  DatasetRow,
  EvidenceDetail,
  FieldDefinition,
  FieldConflictRecord,
  FieldSelectionRecord,
  FieldDictionaryArtifactRead,
  GraphArtifactRead,
  GraphEdgeRead,
  GraphNodeRead,
  LiteratureArtifactVersionContext,
  LiteratureClaimRead,
  LiteratureClaimRejectionReason,
  LiteratureRelationRead,
  LiteratureRelationReviewReason,
  LiteratureRelationType,
  ProducerExecutionDetail,
  SourceCollectionArtifactRead,
  SourceSnapshotDetail,
  SourceValueCandidate,
  StructuredSourceCollectionMember,
} from "@xingwen/contracts";
import {
  HOST_STAR_PS_QUERY,
  HOST_STAR_PS_RESPONSE_SHA256,
  HOST_STAR_RECORDED_AT,
  HOST_STAR_TOI_QUERY,
  HOST_STAR_TOI_RESPONSE_SHA256,
  RECORDED_EXOPLANET_HOST_STAR_ROWS,
  type RecordedExoplanetHostStarRow,
} from "./recorded-exoplanet-host-star";
import {
  TOI_1233_RECORDED_AT,
  TOI_1233_RESPONSE_SHA256,
  TOI_1233_TAP_QUERY,
} from "./recorded-toi-1233-catalog";

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
  const encoded = Array.from(seed)
    .map((c) => c.codePointAt(0)!.toString(16))
    .join("");
  return `sha256:${encoded.repeat(Math.ceil(64 / encoded.length)).slice(0, 64)}`;
}

const sourceSnapshot: SourceSnapshotDetail = {
  id: "snap_01",
  source_id: "nasa_exoplanet_archive.toi",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: { table: "toi", fixture: true },
  query_hash: hash("q_toi"),
  content_hash: hash("s_toi"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "fixture-2026-07-21-toi",
  license_note:
    "依据 NASA Exoplanet Archive 公开 TOI 字段结构构造的确定性演示投影；不是实时或录制响应。",
};

const psSourceSnapshot: SourceSnapshotDetail = {
  id: "snap_02",
  source_id: "nasa_exoplanet_archive.ps",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:01Z",
  query: { table: "ps", fixture: true },
  query_hash: hash("q_ps"),
  content_hash: hash("s_ps"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "fixture-2026-07-21-ps",
  license_note:
    "依据 NASA Exoplanet Archive 公开行星系统字段结构构造的确定性演示投影；不是实时或录制响应。",
};

const gaiaSourceSnapshot: SourceSnapshotDetail = {
  id: "snap_03",
  source_id: "gaia_dr3",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:02Z",
  query: { table: "gaia_source", fixture: true },
  query_hash: hash("q_gaia"),
  content_hash: hash("s_gaia"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "fixture-2026-07-21-gaia-dr3",
  license_note:
    "依据 Gaia DR3 公开字段结构构造的确定性演示投影；不是实时或录制响应。",
};

const recordedToiDatasetSnapshot: SourceSnapshotDetail = {
  id: "snap_host_star_toi_recorded",
  source_id: "nasa_exoplanet_archive.toi",
  source_type: "catalog",
  retrieved_at: HOST_STAR_RECORDED_AT,
  query: {
    service: "TAP",
    table: "toi",
    adql: HOST_STAR_TOI_QUERY,
    replay_scope: "recorded_catalog_response",
  },
  query_hash:
    "sha256:f643854f2df4662235beb23affab761731d5952643227c7f8076e15a07f66521",
  content_hash: HOST_STAR_TOI_RESPONSE_SHA256,
  request_metadata: {
    adapter: "demo_replay",
    endpoint: "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
  },
  source_version_or_etag: null,
  license_note: "NASA Exoplanet Archive TOI 目录录制响应。",
};

const recordedPsDatasetSnapshot: SourceSnapshotDetail = {
  id: "snap_host_star_ps_recorded",
  source_id: "nasa_exoplanet_archive.pscomppars",
  source_type: "catalog",
  retrieved_at: HOST_STAR_RECORDED_AT,
  query: {
    service: "TAP",
    table: "pscomppars",
    adql: HOST_STAR_PS_QUERY,
    replay_scope: "recorded_catalog_response",
  },
  query_hash:
    "sha256:391bbffef869378ab1b6d8a134007cefc3e9e2862ef9396179cc9647a17726ea",
  content_hash: HOST_STAR_PS_RESPONSE_SHA256,
  request_metadata: {
    adapter: "demo_replay",
    endpoint: "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
  },
  source_version_or_etag: null,
  license_note:
    "NASA Exoplanet Archive Planetary Systems Composite Parameters 录制响应。",
};

const toi1233RecordedSnapshot: SourceSnapshotDetail = {
  id: "snap_toi_1233_recorded",
  source_id: "nasa_exoplanet_archive.toi",
  source_type: "catalog",
  retrieved_at: TOI_1233_RECORDED_AT,
  query: {
    service: "TAP",
    table: "toi",
    adql: TOI_1233_TAP_QUERY,
    replay_scope: "recorded_catalog_response",
  },
  query_hash:
    "sha256:bfa32ab3a02c1f78bb1ec7f584811077c966caa9a83c634fcf4949f96546e7d7",
  content_hash: TOI_1233_RESPONSE_SHA256,
  request_metadata: {
    adapter: "demo_replay",
    endpoint: "https://exoplanetarchive.ipac.caltech.edu/TAP/sync",
  },
  source_version_or_etag: null,
  license_note: "NASA Exoplanet Archive public catalog response.",
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
  snapshot: SourceSnapshotDetail = sourceSnapshot,
  extractionMethod = "fixture.read_contract",
): EvidenceDetail {
  return {
    id: `ev_${artifactVersionId}_${targetId.replaceAll(".", "_")}`,
    artifact_version_id: artifactVersionId,
    target_type: targetType,
    target_id: targetId,
    evidence_type: "database_query",
    source_snapshot_id: snapshot.id,
    extraction_method: extractionMethod,
    confidence: 1,
    locator: { kind: "fixture_record", key: targetId },
    quote_or_value: quoteOrValue,
    paper_id: null,
    created_at: CREATED_AT,
  };
}

type DataArtifactKind = "dataset" | "field_dictionary" | "source_collection";

function dataBase(
  artifactId: string,
  artifactVersionId: string,
  kind: DataArtifactKind,
  options: {
    sourceMode?: "fixture" | "recorded";
    sourceSnapshots?: SourceSnapshotDetail[];
    evidence?: EvidenceDetail[];
  } = {},
) {
  const sourceMode = options.sourceMode ?? "fixture";
  const sourceSnapshots = options.sourceSnapshots ?? [
    sourceSnapshot,
    psSourceSnapshot,
    gaiaSourceSnapshot,
  ];
  return {
    artifact_id: artifactId,
    artifact_version_id: artifactVersionId,
    project_id: PROJECT_ID,
    schema_version: "2.0.0",
    source_mode: sourceMode,
    content_hash: hash(artifactVersionId.slice(-1)),
    input_hash: hash("d"),
    created_at: CREATED_AT,
    producer_execution: producerExecution,
    source_snapshots: sourceSnapshots,
    evidence: options.evidence ?? [
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

// ---------------------------------------------------------------------------
// Field Definitions (14 fields)
// ---------------------------------------------------------------------------
const baseFieldDef = (
  fieldId: string,
  labelEn: string,
  meaningZh: string,
  desc: string,
  dataType: "string" | "number" | "integer",
  unit: string,
  objectType: "planet" | "star" | "system",
  req: boolean,
  nullPolicyReason:
    | "not_in_source"
    | "not_measured"
    | "not_applicable"
    | "unresolved_conflict"
    | "below_detection_limit",
): FieldDefinition => ({
  field_id: fieldId,
  label_en: labelEn,
  meaning_zh: meaningZh,
  description: desc,
  data_type: dataType,
  canonical_unit: unit,
  object_type: objectType,
  required: req,
  nullable: !req,
  crossmatch_key: fieldId === "planet.toi_id" || fieldId === "star.tic_id",
  object_identity_key: fieldId === "planet.toi_id",
  source_priority: [
    "nasa_exoplanet_archive.toi",
    "nasa_exoplanet_archive.ps",
    "gaia_dr3",
  ],
  document_aliases: [],
  source_aliases: [
    {
      source_id: "nasa_exoplanet_archive.toi",
      source_table: "toi",
      raw_field: fieldId.split(".")[1] ?? fieldId,
      source_unit: unit,
      priority: 1,
      conversion_rule_id: "identity",
      row_key_fields: ["toi"],
    },
  ],
  conflict_resolution_rule_version: "1.0.0",
  conflict_resolution_strategy: "prefer_source_priority_preserve_all",
  crossmatch_rule_version: "1.0.0",
  evidence_locator_rule_id: "catalog-cell",
  quality_metric_inputs: ["completeness", "unit_consistency"],
  transformation_rule_version: "1.0.0",
  limit_policy: {
    lower_limit_supported: false,
    upper_limit_supported: false,
    rule_version: "1.0.0",
  },
  null_policy: {
    allowed_reasons: [nullPolicyReason],
    reason_required_when_null: true,
  },
  uncertainty_policy: {
    mode: "not_applicable",
    preserve_asymmetric_errors: false,
    rule_version: "1.0.0",
  },
});

export const fieldDefinitions: FieldDefinition[] = [
  baseFieldDef(
    "planet.toi_id",
    "TOI identifier",
    "TOI 候选体编号",
    "TESS 候选行星标准编号",
    "string",
    "none",
    "planet",
    true,
    "not_in_source",
  ),
  baseFieldDef(
    "planet.name",
    "Planet Name",
    "行星名称",
    "已确认系外行星或常用命名",
    "string",
    "none",
    "planet",
    false,
    "not_in_source",
  ),
  baseFieldDef(
    "planet.period",
    "Orbital Period",
    "轨道周期",
    "行星绕宿主星公转周期",
    "number",
    "day",
    "planet",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "planet.radius",
    "Planet Radius",
    "行星半径",
    "以地球半径为单位的拟合物理半径",
    "number",
    "earth_radius",
    "planet",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "planet.mass",
    "Planet Mass",
    "行星质量",
    "以地球质量为单位的视向速度/TTV 反演质量",
    "number",
    "earth_mass",
    "planet",
    false,
    "not_measured",
  ),
  baseFieldDef(
    "planet.equilibrium_temperature",
    "Equilibrium Temp",
    "平衡温度",
    "假设零反照率下的行星表面平衡温度",
    "number",
    "kelvin",
    "planet",
    false,
    "not_measured",
  ),
  baseFieldDef(
    "star.tic_id",
    "TIC identifier",
    "TIC 恒星编号",
    "TESS Input Catalog 宿主星标识",
    "string",
    "none",
    "star",
    true,
    "not_in_source",
  ),
  baseFieldDef(
    "star.effective_temperature",
    "Effective Temp",
    "恒星有效温度",
    "宿主恒星表面有效温度",
    "number",
    "kelvin",
    "star",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "star.radius",
    "Stellar Radius",
    "恒星半径",
    "以太阳半径为单位的恒星半径",
    "number",
    "solar_radius",
    "star",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "star.mass",
    "Stellar Mass",
    "恒星质量",
    "以太阳质量为单位的恒星质量",
    "number",
    "solar_mass",
    "star",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "star.metallicity",
    "Stellar Metallicity",
    "恒星金属丰度 [Fe/H]",
    "恒星相对于太阳的铁丰度",
    "number",
    "dex",
    "star",
    false,
    "not_measured",
  ),
  baseFieldDef(
    "star.log_g",
    "Surface Gravity",
    "恒星表面重力 log(g)",
    "恒星表面重力加速度对数值 (cgs)",
    "number",
    "cgs",
    "star",
    false,
    "not_measured",
  ),
  baseFieldDef(
    "star.distance",
    "Distance",
    "恒星距离",
    "NASA TOI 目录中的宿主星距离字段",
    "number",
    "pc",
    "star",
    true,
    "not_measured",
  ),
  baseFieldDef(
    "planet.discovery_year",
    "Discovery Year",
    "发现年份",
    "TESS 首次发布或文献确认年份",
    "integer",
    "yr",
    "planet",
    true,
    "not_in_source",
  ),
];

// ---------------------------------------------------------------------------
// 40 recorded API rows
// ---------------------------------------------------------------------------
type SampleExoplanetRecord = RecordedExoplanetHostStarRow;

const rawSampleData: readonly SampleExoplanetRecord[] =
  RECORDED_EXOPLANET_HOST_STAR_ROWS;

function recordedDatasetEvidenceFor(
  rec: SampleExoplanetRecord,
): readonly [EvidenceDetail, EvidenceDetail] {
  const rowId = `row_${rec.toi.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;
  return [
    {
      id: `ev_${DATASET_VERSION_ID}_${rowId}_toi`,
      artifact_version_id: DATASET_VERSION_ID,
      target_type: "dataset_row",
      target_id: rowId,
      evidence_type: "database_query",
      source_snapshot_id: recordedToiDatasetSnapshot.id,
      extraction_method: "nasa_exoplanet_archive.recorded_tap_replay",
      confidence: 1,
      locator: {
        kind: "database_cell",
        query_hash: recordedToiDatasetSnapshot.query_hash,
        row_key: rec.toi,
        field: "toi",
      },
      quote_or_value: JSON.stringify({
        toi: rec.toi,
        tid: rec.tic,
        pl_orbper: rec.period,
        pl_rade: rec.radius,
        pl_eqt: rec.teq,
        st_teff: rec.teff,
        st_rad: rec.srad,
        st_logg: rec.logg,
        st_dist: rec.dist,
        rowupdate: rec.toiRowUpdatedAt,
      }),
      paper_id: null,
      created_at: HOST_STAR_RECORDED_AT,
    },
    {
      id: `ev_${DATASET_VERSION_ID}_${rowId}_ps`,
      artifact_version_id: DATASET_VERSION_ID,
      target_type: "dataset_row",
      target_id: rowId,
      evidence_type: "database_query",
      source_snapshot_id: recordedPsDatasetSnapshot.id,
      extraction_method: "nasa_exoplanet_archive.recorded_tap_replay",
      confidence: 1,
      locator: {
        kind: "database_cell",
        query_hash: recordedPsDatasetSnapshot.query_hash,
        row_key: `${rec.tic}:${rec.period}`,
        field: "tic_id",
      },
      quote_or_value: JSON.stringify({
        pl_name: rec.name,
        tic_id: rec.tic,
        pl_bmasse: rec.mass,
        st_mass: rec.smass,
        st_met: rec.feh,
        disc_year: rec.year,
        period_match_relative_delta: rec.periodMatchRelativeDelta,
        radius_relative_delta: rec.radiusRelativeDelta,
      }),
      paper_id: null,
      created_at: HOST_STAR_RECORDED_AT,
    },
  ];
}

const recordedDatasetEvidence = rawSampleData.flatMap((rec) =>
  recordedDatasetEvidenceFor(rec),
);

function buildRow(rec: SampleExoplanetRecord, index: number): DatasetRow {
  const rowId = `row_${rec.toi.toLowerCase().replace(/[^a-z0-9]/g, "_")}`;

  const mappedField = (
    fieldId: string,
    unit: string,
    val: string,
    keySuffix: string,
  ) => ({
    canonical_field_id: fieldId,
    canonical_unit: unit,
    canonical_value: val,
    candidate_source_value_ids: [`src_${keySuffix}_${index}`],
    selected_source_value_id: `src_${keySuffix}_${index}`,
    selection_id: `sel_${keySuffix}_${index}`,
    conflict_ids: [] as string[],
    transformation_evidence_ids: [] as string[],
    status: "mapped" as const,
  });

  const nullField = (
    fieldId: string,
    reason: "not_in_source" | "not_measured" | "not_applicable",
  ) => ({
    canonical_field_id: fieldId,
    candidate_source_value_ids: [] as string[],
    reason,
    status: "declared_null" as const,
    transformation_evidence_ids: [] as string[],
  });

  const radiusSourceValueIds = [`src_rad_toi_${index}`, `src_rad_ps_${index}`];
  const radiusConflictIds =
    rec.status === "conflict" ? [`conflict_radius_${index}`] : [];
  const radiusField = {
    ...mappedField(
      "planet.radius",
      "earth_radius",
      String(rec.radius),
      "rad_toi",
    ),
    candidate_source_value_ids: radiusSourceValueIds,
    selected_source_value_id: radiusSourceValueIds[0],
    conflict_ids: radiusConflictIds,
  };

  const fields = [
    mappedField("planet.toi_id", "none", rec.toi, "toi"),
    rec.name
      ? mappedField("planet.name", "none", rec.name, "name")
      : nullField("planet.name", "not_in_source"),
    mappedField("planet.period", "day", String(rec.period), "per"),
    radiusField,
    rec.mass !== null
      ? mappedField("planet.mass", "earth_mass", String(rec.mass), "mass")
      : nullField("planet.mass", "not_measured"),
    rec.teq !== null
      ? mappedField(
          "planet.equilibrium_temperature",
          "kelvin",
          String(rec.teq),
          "teq",
        )
      : nullField("planet.equilibrium_temperature", "not_measured"),
    mappedField("star.tic_id", "none", rec.tic, "tic"),
    mappedField(
      "star.effective_temperature",
      "kelvin",
      String(rec.teff),
      "teff",
    ),
    mappedField("star.radius", "solar_radius", String(rec.srad), "srad"),
    rec.smass !== null
      ? mappedField("star.mass", "solar_mass", String(rec.smass), "smass")
      : nullField("star.mass", "not_measured"),
    rec.feh !== null
      ? mappedField("star.metallicity", "dex", String(rec.feh), "feh")
      : nullField("star.metallicity", "not_measured"),
    mappedField("star.log_g", "cgs", String(rec.logg), "logg"),
    mappedField("star.distance", "pc", String(rec.dist), "dist"),
    rec.year !== null
      ? mappedField("planet.discovery_year", "yr", String(rec.year), "yr")
      : nullField("planet.discovery_year", "not_in_source"),
  ];

  return {
    row_id: rowId,
    content_hash: hash(rowId),
    row_authority: {
      authority_kind: "crossmatch",
      alignment_status: "accepted",
      entity_level: "planet_candidate",
      logical_key: hash(rec.toi),
      record_type: "paired",
      source_member_ids: [
        recordedToiDatasetSnapshot.source_id,
        recordedPsDatasetSnapshot.source_id,
      ],
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
                normalized_value: rec.toi,
                normalization_rule_version: "1.0.0",
              },
            ],
          },
        ],
      },
    },
    fields,
    conflict_ids: radiusConflictIds,
    projected_field_ids: fields.map((f) => f.canonical_field_id),
    projection_policy_version: "1.0.0",
    source_snapshot_ids: [
      recordedToiDatasetSnapshot.id,
      recordedPsDatasetSnapshot.id,
    ],
    evidence_ids: recordedDatasetEvidenceFor(rec).map((item) => item.id),
  };
}

const datasetRows: DatasetRow[] = rawSampleData.map(buildRow);

function radiusSourceValue(
  rec: SampleExoplanetRecord,
  index: number,
  side: "toi" | "ps",
): SourceValueCandidate {
  const isToi = side === "toi";
  const snapshot = isToi
    ? recordedToiDatasetSnapshot
    : recordedPsDatasetSnapshot;
  const rawField = "pl_rade";
  const value = isToi ? rec.radius : rec.psRadius;
  const rowKey: [unknown, unknown] = isToi
    ? ["toi", rec.toi]
    : ["tic_id+pl_orbper", `${rec.tic}:${rec.period}`];
  const locator = {
    kind: "database_cell" as const,
    query_hash: snapshot.query_hash,
    raw_field: rawField,
    raw_record_content_hash: hash(`${side}:${rec.toi}:radius`),
    row_key: [rowKey] as [[unknown, unknown]],
    source_id: snapshot.source_id,
    source_role: (isToi ? "left" : "right") as "left" | "right",
    source_snapshot_content_hash: snapshot.content_hash,
    source_snapshot_id: snapshot.id,
  };
  return {
    alias_priority: 1,
    canonical_field_id: "planet.radius",
    canonical_unit: "earth_radius",
    canonical_value: String(value),
    content_hash: hash(`${side}:${rec.toi}:${value}`),
    conversion_rule_id: "identity.r_earth",
    conversion_rule_version: "1.0.0",
    evidence_locator: locator,
    limit: { status: "measured" },
    null_status: null,
    origin: {
      kind: "structured_database",
      raw_field: rawField,
      raw_record_content_hash: locator.raw_record_content_hash,
      raw_record_row_key: [rowKey],
      source_table: isToi ? "toi" : "pscomppars",
    },
    query_hash: snapshot.query_hash,
    raw_value: value,
    source_id: snapshot.source_id,
    source_priority: isToi ? 1 : 2,
    source_snapshot_content_hash: snapshot.content_hash,
    source_snapshot_id: snapshot.id,
    source_unit: "earth_radius",
    source_value_id: `src_rad_${side}_${index}`,
    transformation_rule_version: "1.0.0",
    uncertainty: { status: "missing" },
  };
}

const datasetSourceValues = rawSampleData.flatMap((rec, index) => [
  radiusSourceValue(rec, index, "toi"),
  radiusSourceValue(rec, index, "ps"),
]);

const datasetSelections: FieldSelectionRecord[] = rawSampleData.map(
  (rec, index) => ({
    candidate_source_value_ids: [`src_rad_toi_${index}`, `src_rad_ps_${index}`],
    canonical_field_id: "planet.radius",
    content_hash: hash(`selection:${rec.toi}:radius`),
    dataset_row_id: `row_${rec.toi.toLowerCase().replace(/[^a-z0-9]/g, "_")}`,
    reason: "TOI 目录值作为展示投影；两侧录制值均完整保留。",
    selected_source_value_id: `src_rad_toi_${index}`,
    selection_id: `sel_rad_toi_${index}`,
    strategy: "prefer_source_priority_preserve_all",
  }),
);

const datasetConflicts: FieldConflictRecord[] = rawSampleData.flatMap(
  (rec, index) => {
    if (rec.status !== "conflict") return [];
    return [
      {
        absolute_difference: String(Math.abs(rec.radius - rec.psRadius)),
        canonical_field_id: "planet.radius",
        comparison_policy_version: "1.0.0",
        conflict_id: `conflict_radius_${index}`,
        conflict_scope: "cross_source" as const,
        content_hash: hash(`conflict:${rec.toi}:radius`),
        dataset_row_id: `row_${rec.toi.toLowerCase().replace(/[^a-z0-9]/g, "_")}`,
        reason:
          "distinct canonical values are retained; source priority selects display only" as const,
        relative_denominator: String(Math.abs(rec.radius)),
        relative_difference: String(rec.radiusRelativeDelta),
        source_value_ids: [`src_rad_toi_${index}`, `src_rad_ps_${index}`] as [
          string,
          string,
        ],
      },
    ];
  },
);

const producer = {
  producer_name: "demo-replay-projection",
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

const datasetCrossmatchAuthority: CrossmatchArtifactAuthority = {
  authority_kind: "crossmatch",
  result_id: "crossmatch_recorded_host_star_01",
  input_hash: hash("a"),
  output_hash: hash("b"),
  content_hash: hash("c"),
  source_snapshot_ids: [
    recordedToiDatasetSnapshot.id,
    recordedPsDatasetSnapshot.id,
  ],
  evidence: [],
  evidence_ids: [],
  alignment_record_keys: datasetRows.map((row) => row.content_hash),
  conflict_record_keys: datasetConflicts.map((item) => item.content_hash),
  inconclusive_record_keys: [],
  review_required_record_keys: [],
};

const fixtureCrossmatchAuthority: CrossmatchArtifactAuthority = {
  ...datasetCrossmatchAuthority,
  result_id: "crossmatch_source_collection_01",
  source_snapshot_ids: [
    recordedToiDatasetSnapshot.id,
    recordedPsDatasetSnapshot.id,
    gaiaSourceSnapshot.id,
  ],
};

const datasetCandidate = {
  candidate_id: "dataset_candidate_01",
  kind: "dataset" as const,
  schema_version: "3.0.0" as const,
  requested_fields: fieldDefinitions.map((f) => f.field_id),
  columns: fieldDefinitions.map((field) => ({ field })),
  rows: datasetRows,
  row_count: datasetRows.length,
  field_count: fieldDefinitions.length,
  conflicts: datasetConflicts,
  evidence_ids: [],
  source_snapshot_ids: [
    recordedToiDatasetSnapshot.id,
    recordedPsDatasetSnapshot.id,
  ],
  input_hash: hash("d"),
  output_hash: hash("e"),
  canonical_content_hash: hash("c"),
  lineage_hash: hash("l"),
  authority: datasetCrossmatchAuthority,
  producer,
  manifest_pins: manifestPins,
  conversion_catalog_id: producer.conversion_catalog_id,
  conversion_catalog_version: producer.conversion_catalog_version,
  conversion_catalog_content_hash: producer.conversion_catalog_content_hash,
  mapping_rule_set_id: producer.mapping_rule_set_id,
  mapping_rule_set_version: producer.mapping_rule_set_version,
  mapping_rule_set_content_hash: producer.mapping_rule_set_content_hash,
  quality_metric_input_declarations: ["completeness", "evidence_coverage"],
  selections: datasetSelections,
  source_values: datasetSourceValues,
  transformation_evidence: [],
};

const fieldDictionaryCandidate = {
  candidate_id: "field_dictionary_candidate_01",
  kind: "field_dictionary" as const,
  schema_version: "3.0.0" as const,
  requested_fields: fieldDefinitions.map((f) => f.field_id),
  field_definitions: fieldDefinitions,
  evidence_ids: [],
  source_snapshot_ids: [
    sourceSnapshot.id,
    psSourceSnapshot.id,
    gaiaSourceSnapshot.id,
  ],
  input_hash: hash("d"),
  output_hash: hash("e"),
  authority: fixtureCrossmatchAuthority,
  producer,
  manifest_pins: manifestPins,
  conversion_catalog_id: producer.conversion_catalog_id,
  conversion_catalog_version: producer.conversion_catalog_version,
  conversion_catalog_content_hash: producer.conversion_catalog_content_hash,
  mapping_rule_set_id: producer.mapping_rule_set_id,
  mapping_rule_set_version: producer.mapping_rule_set_version,
  mapping_rule_set_content_hash: producer.mapping_rule_set_content_hash,
};

const sourceMember: StructuredSourceCollectionMember = {
  source_id: recordedToiDatasetSnapshot.source_id,
  source_snapshot_id: recordedToiDatasetSnapshot.id,
  source_snapshot_content_hash: recordedToiDatasetSnapshot.content_hash,
  source_snapshot: {
    snapshot_id: recordedToiDatasetSnapshot.id,
    source_id: recordedToiDatasetSnapshot.source_id,
    source_type: recordedToiDatasetSnapshot.source_type,
    retrieved_at: recordedToiDatasetSnapshot.retrieved_at,
    query: JSON.stringify(recordedToiDatasetSnapshot.query),
    query_hash: recordedToiDatasetSnapshot.query_hash,
    content_hash: recordedToiDatasetSnapshot.content_hash,
    license_note: recordedToiDatasetSnapshot.license_note,
    request_metadata: recordedToiDatasetSnapshot.request_metadata,
    source_version_or_etag: recordedToiDatasetSnapshot.source_version_or_etag,
  },
  side: "left",
  data_level: "recorded_response",
  source_mode: "recorded",
  raw_record_count: 40,
  raw_record_reference_registry_hash: hash("z"),
  raw_record_references: [
    {
      source_id: recordedToiDatasetSnapshot.source_id,
      source_snapshot_id: recordedToiDatasetSnapshot.id,
      source_snapshot_content_hash: recordedToiDatasetSnapshot.content_hash,
      query_hash: recordedToiDatasetSnapshot.query_hash,
      raw_record_content_hash: hash("r"),
      row_key: [["toi", "TOI-1135.01"]],
    },
  ],
  query_hash: recordedToiDatasetSnapshot.query_hash,
  completion: { status: "complete", continuation_cursor: null },
  license_note: recordedToiDatasetSnapshot.license_note,
};

const psSourceMember: StructuredSourceCollectionMember = {
  source_id: recordedPsDatasetSnapshot.source_id,
  source_snapshot_id: recordedPsDatasetSnapshot.id,
  source_snapshot_content_hash: recordedPsDatasetSnapshot.content_hash,
  source_snapshot: {
    snapshot_id: recordedPsDatasetSnapshot.id,
    source_id: recordedPsDatasetSnapshot.source_id,
    source_type: recordedPsDatasetSnapshot.source_type,
    retrieved_at: recordedPsDatasetSnapshot.retrieved_at,
    query: JSON.stringify(recordedPsDatasetSnapshot.query),
    query_hash: recordedPsDatasetSnapshot.query_hash,
    content_hash: recordedPsDatasetSnapshot.content_hash,
    license_note: recordedPsDatasetSnapshot.license_note,
    request_metadata: recordedPsDatasetSnapshot.request_metadata,
    source_version_or_etag: recordedPsDatasetSnapshot.source_version_or_etag,
  },
  side: "right",
  data_level: "recorded_response",
  source_mode: "recorded",
  raw_record_count: 48,
  raw_record_reference_registry_hash: hash("v"),
  raw_record_references: [
    {
      source_id: recordedPsDatasetSnapshot.source_id,
      source_snapshot_id: recordedPsDatasetSnapshot.id,
      source_snapshot_content_hash: recordedPsDatasetSnapshot.content_hash,
      query_hash: recordedPsDatasetSnapshot.query_hash,
      raw_record_content_hash: hash("w"),
      row_key: [["tic_id", "TIC 154872375"]],
    },
  ],
  query_hash: recordedPsDatasetSnapshot.query_hash,
  completion: { status: "complete", continuation_cursor: null },
  license_note: recordedPsDatasetSnapshot.license_note,
};

const gaiaSourceMember: StructuredSourceCollectionMember = {
  source_id: gaiaSourceSnapshot.source_id,
  source_snapshot_id: gaiaSourceSnapshot.id,
  source_snapshot_content_hash: gaiaSourceSnapshot.content_hash,
  source_snapshot: {
    snapshot_id: gaiaSourceSnapshot.id,
    source_id: gaiaSourceSnapshot.source_id,
    source_type: gaiaSourceSnapshot.source_type,
    retrieved_at: gaiaSourceSnapshot.retrieved_at,
    query: JSON.stringify(gaiaSourceSnapshot.query),
    query_hash: gaiaSourceSnapshot.query_hash,
    content_hash: gaiaSourceSnapshot.content_hash,
    license_note: gaiaSourceSnapshot.license_note,
    request_metadata: gaiaSourceSnapshot.request_metadata,
    source_version_or_etag: gaiaSourceSnapshot.source_version_or_etag,
  },
  side: "right",
  data_level: "fixture",
  source_mode: "fixture",
  raw_record_count: 40,
  raw_record_reference_registry_hash: hash("g_reg"),
  raw_record_references: [
    {
      source_id: gaiaSourceSnapshot.source_id,
      source_snapshot_id: gaiaSourceSnapshot.id,
      source_snapshot_content_hash: gaiaSourceSnapshot.content_hash,
      query_hash: gaiaSourceSnapshot.query_hash,
      raw_record_content_hash: hash("g_rec"),
      row_key: [["source_id", "5489021948102"]],
    },
  ],
  query_hash: gaiaSourceSnapshot.query_hash,
  completion: { status: "complete", continuation_cursor: null },
  license_note: gaiaSourceSnapshot.license_note,
};

const sourceCollectionCandidate = {
  candidate_id: "source_collection_candidate_01",
  kind: "source_collection" as const,
  schema_version: "3.0.0" as const,
  members: [sourceMember, psSourceMember, gaiaSourceMember],
  source_snapshot_ids: [
    recordedToiDatasetSnapshot.id,
    recordedPsDatasetSnapshot.id,
    gaiaSourceSnapshot.id,
  ],
  source_value_ids: [],
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
  authority: fixtureCrossmatchAuthority,
};

export const dataArtifactReads: readonly DatasetArtifactRead[] = [
  {
    ...dataBase("art_dataset_01", DATASET_VERSION_ID, "dataset", {
      sourceMode: "recorded",
      sourceSnapshots: [recordedToiDatasetSnapshot, recordedPsDatasetSnapshot],
      evidence: recordedDatasetEvidence,
    }),
    dataset: datasetCandidate,
  },
];

export const fieldDictionaryArtifactReads: readonly FieldDictionaryArtifactRead[] =
  [
    {
      ...dataBase("art_fdict_01", FIELDS_VERSION_ID, "field_dictionary"),
      field_dictionary: fieldDictionaryCandidate,
    },
  ];

export const sourceCollectionArtifactReads: readonly SourceCollectionArtifactRead[] =
  [
    {
      ...dataBase("art_srccol_01", SOURCES_VERSION_ID, "source_collection", {
        sourceSnapshots: [
          recordedToiDatasetSnapshot,
          recordedPsDatasetSnapshot,
          gaiaSourceSnapshot,
        ],
        evidence: [
          evidence(
            SOURCES_VERSION_ID,
            "source_collection",
            "source_collection.candidate",
            "两份录制目录响应与一份明确标注的 Gaia 字段结构演示投影。",
            recordedToiDatasetSnapshot,
            "demo_replay.mixed_source_collection",
          ),
        ],
      }),
      source_collection: sourceCollectionCandidate,
    },
  ];

// ---------------------------------------------------------------------------
// Literature Claims & Relations
// ---------------------------------------------------------------------------
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

const makeClaimRead = (
  claimId: string,
  text: string,
  objects: string[],
  status: "accepted" | "candidate" | "rejected",
  metric: string,
  unit: string,
  rejectionReason: LiteratureClaimRejectionReason | null = null,
): LiteratureClaimRead => ({
  version: literatureVersion("art_claims_01", CLAIMS_VERSION_ID),
  source_snapshots: [toi1233RecordedSnapshot],
  evidence: [
    evidence(
      CLAIMS_VERSION_ID,
      "claim",
      claimId,
      text,
      toi1233RecordedSnapshot,
      "recorded.nasa_exoplanet_archive_toi",
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
    claim_id: claimId,
    claim_type: "finding",
    text,
    normalized_text: text.toLowerCase(),
    fingerprint: hash(claimId),
    status,
    polarity: status === "rejected" ? "negative" : "positive",
    paper_id: "paper_01",
    producer_execution_id: producerExecution.id,
    model_response_hash: hash("m"),
    normalization_version: "1.0.0",
    input_hash: hash("i"),
    objects: objects as [string, ...string[]],
    scope: ["recorded NASA Exoplanet Archive TOI catalog response"],
    conditions: ["Only exact fields in the frozen TOI response are asserted."],
    qualifiers: [],
    limitations: [
      "The fixture does not infer light-curve, dynamical, atmospheric, or model-performance conclusions.",
    ],
    metric,
    unit,
    uncertainty: null,
    comparison_basis: null,
    source_statement_id: `statement_${claimId}`,
    source_summary_id: "psum_01",
    source_paper_summary_artifact_version_id: "artv_papsum_01",
    source_snapshot_ids: [toi1233RecordedSnapshot.id],
    evidence_ids: [],
    failure_stage: null,
    rejection_reason: rejectionReason,
  },
});

const claim1 = makeClaimRead(
  "claim_01",
  "NASA Exoplanet Archive TOI 表将 TOI-1233.04 关联到 TIC-260647166，并记录轨道周期 3.79589 天、半径 1.553135 R_Earth。",
  ["TOI-1233.04", "TIC-260647166"],
  "accepted",
  "orbital_period",
  "days",
);

const claim2 = makeClaimRead(
  "claim_02",
  "同一冻结 TOI 响应记录 TIC-260647166 的有效温度 5723.87 K、log g 4.438、恒星半径 0.864173 R_Sun。",
  ["TIC-260647166"],
  "accepted",
  "effective_temperature",
  "K",
);

const claim3 = makeClaimRead(
  "claim_03",
  "冻结 TOI 表记录 TOI-1233.03 的轨道周期为 6.2036219 天、行星半径为 2.056748 R_Earth。",
  ["TOI-1233.03"],
  "accepted",
  "planet_radius",
  "R_Earth",
);

const claim4 = makeClaimRead(
  "claim_04",
  "候选审查：TOI-1233.03 与 TOI-1233.04 的目录周期可用于后续计算周期比，但当前响应不足以支持共振或 TTV 结论。",
  ["TOI-1233.03", "TOI-1233.04"],
  "candidate",
  "resonance_period_ratio",
  "dimensionless",
);

const claim5 = makeClaimRead(
  "claim_05",
  "候选审查：TOI 编号与已确认行星名称的交叉映射需要独立来源，当前 TOI 目录响应不能单独完成别名认定。",
  ["TOI-1233"],
  "candidate",
  "planet_mass",
  "M_Earth",
);

const claim6 = makeClaimRead(
  "claim_06",
  "已驳回：将 TOI-1233.01 的目录周期写成 3.79589 天，与同一冻结响应中的 14.1758947 天直接冲突。",
  ["TOI-1233.01"],
  "rejected",
  "stellar_activity_index",
  "dimensionless",
  "literature_claim.normalization_unsafe",
);

export const literatureClaimReads: readonly LiteratureClaimRead[] = [
  claim1,
  claim2,
  claim3,
  claim4,
  claim5,
  claim6,
];

const makeRelationRead = (
  relationId: string,
  sourceClaim: LiteratureClaimRead,
  targetClaim: LiteratureClaimRead,
  relationType: LiteratureRelationType,
  status: "accepted" | "candidate" | "rejected",
  conclusion: string,
  reviewReason: LiteratureRelationReviewReason | null = null,
): LiteratureRelationRead => ({
  version: literatureVersion("art_rels_01", RELATIONS_VERSION_ID),
  source_snapshots: [toi1233RecordedSnapshot],
  evidence: [
    evidence(
      RELATIONS_VERSION_ID,
      "relation",
      relationId,
      conclusion,
      toi1233RecordedSnapshot,
      "reasoning.catalog_identity_relation",
    ),
  ],
  graph_eligible: status === "accepted",
  source_claim: sourceClaim,
  target_claim: targetClaim,
  relation: {
    relation_id: relationId,
    pair_id: `${sourceClaim.claim.claim_id}:${targetClaim.claim.claim_id}`,
    relation_type: relationType,
    status,
    source_claim_id: sourceClaim.claim.claim_id,
    target_claim_id: targetClaim.claim.claim_id,
    source_claim_artifact_version_id: CLAIMS_VERSION_ID,
    target_claim_artifact_version_id: CLAIMS_VERSION_ID,
    source_paper_summary_artifact_version_id: "artv_papsum_01",
    target_paper_summary_artifact_version_id: "artv_papsum_01",
    source_snapshot_ids: [toi1233RecordedSnapshot.id],
    evidence_ids: [],
    conditions: ["shared TIC identifier in the frozen catalog response"],
    condition_conflicts: [],
    condition_uncertainties: [],
    comparability: {
      metric_basis: "frozen catalog fields",
      metric_status: "comparable",
      object_basis: "TIC-260647166",
      object_status: "comparable",
      unit_basis: "canonical",
      unit_status: "comparable",
    },
    direction: {
      basis: "catalog identity and exact-field consistency",
      source_claim_id: sourceClaim.claim.claim_id,
      target_claim_id: targetClaim.claim.claim_id,
    },
    confidence: null,
    reasoning_trace_id: `trace_${relationId}`,
    fingerprint: hash(relationId),
    input_hash: hash("i"),
    model_response_hash: hash("m"),
    producer_execution_id: producerExecution.id,
    failure_stage: null,
    rejection_reason:
      status === "rejected"
        ? "literature_relation.evidence_inconsistent"
        : null,
    review_reason: reviewReason,
  },
  reasoning_trace: {
    trace_id: `trace_${relationId}`,
    relation_id: relationId,
    relation_status: status,
    conclusion,
    premise_claim_ids: [sourceClaim.claim.claim_id, targetClaim.claim.claim_id],
    conditions: ["两项主张均来自同一冻结 TOI 目录响应。"],
    conflicts: [],
    limitations: ["不得把目录级关系扩展为动力学或观测结论。"],
    evidence_ids: [`ev_${RELATIONS_VERSION_ID}_relation_${relationId}`],
    input_hash: hash("i"),
    model_response_hash: hash("m"),
    producer_execution_id: producerExecution.id,
    trace_protocol_version: "1.0.0",
    steps: [
      {
        order: 1,
        operation: "compare_objects",
        statement: "交叉比对冻结响应中的 TIC、TOI 与精确字段值。",
        claim_ids: [sourceClaim.claim.claim_id, targetClaim.claim.claim_id],
        evidence_ids: [`ev_${RELATIONS_VERSION_ID}_relation_${relationId}`],
      },
    ],
  },
});

const rel1 = makeRelationRead(
  "rel_01",
  claim1,
  claim2,
  "uses_same_dataset",
  "accepted",
  "主张 1 与主张 2 在同一冻结 TOI 行中共享 TIC-260647166，可建立目录级同系统关系。",
);

const rel2 = makeRelationRead(
  "rel_02",
  claim1,
  claim3,
  "supports",
  "accepted",
  "主张 1 与主张 3 的记录共享 TIC-260647166，可建立冻结目录中的同宿主关系。",
);

const rel3 = makeRelationRead(
  "rel_03",
  claim1,
  claim4,
  "extends",
  "candidate",
  "冻结目录周期只能作为后续动力学分析输入；当前不得把周期比解释为已证实关系。",
  "literature_relation.review.conditions_unresolved",
);

const rel4 = makeRelationRead(
  "rel_04",
  claim1,
  claim5,
  "supports",
  "candidate",
  "TOI 与确认行星名称的映射属于跨表实体解析，需要独立来源快照和明确匹配规则。",
  "literature_relation.review.conditions_unresolved",
);

const rel5 = makeRelationRead(
  "rel_05",
  claim2,
  claim6,
  "contradicts",
  "rejected",
  "主张 6 把 3.79589 天错误归给 TOI-1233.01，与冻结响应中的 14.1758947 天直接冲突。",
);

export const literatureRelationReads: readonly LiteratureRelationRead[] = [
  rel1,
  rel2,
  rel3,
  rel4,
  rel5,
];

// ---------------------------------------------------------------------------
// Knowledge Graph (16 Nodes, 20 Edges)
// ---------------------------------------------------------------------------
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

export const graphNodeReads: readonly GraphNodeRead[] = [
  {
    version: graphVersion,
    node: {
      node_id: "node_goal_01",
      node_type: "research_goal",
      label: "系外行星宿主星证据链综合研究目标",
      logical_reference: [{ name: "project_id", value: PROJECT_ID }],
      version_bindings: [
        {
          artifact_version_id: DATASET_VERSION_ID,
          domain_object_id: "goal_01",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_dataset_01",
      node_type: "dataset",
      label: "TOI 宿主星交叉证认数据集 (40 颗)",
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
      node_id: "node_src_toi",
      node_type: "dataset",
      label: "NASA Exoplanet Archive (TOI)",
      logical_reference: [
        { name: "source_id", value: sourceSnapshot.source_id },
      ],
      version_bindings: [
        {
          artifact_version_id: DATASET_VERSION_ID,
          domain_object_id: "src_toi",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_src_ps",
      node_type: "dataset",
      label: "NASA Exoplanet Archive (PS)",
      logical_reference: [
        { name: "source_id", value: psSourceSnapshot.source_id },
      ],
      version_bindings: [
        { artifact_version_id: DATASET_VERSION_ID, domain_object_id: "src_ps" },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_src_gaia",
      node_type: "dataset",
      label: "Gaia DR3 巡天星表",
      logical_reference: [
        { name: "source_id", value: gaiaSourceSnapshot.source_id },
      ],
      version_bindings: [
        {
          artifact_version_id: DATASET_VERSION_ID,
          domain_object_id: "src_gaia",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_paper_01",
      node_type: "paper",
      label: "Daylan et al. (2021) TESS Discovery of HD 108236",
      logical_reference: [{ name: "paper_id", value: "paper_01" }],
      version_bindings: [
        { artifact_version_id: "artv_papsum_01", domain_object_id: "paper_01" },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_paper_02",
      node_type: "paper",
      label: "Bonfanti et al. (2021) CHEOPS Characterization",
      logical_reference: [{ name: "paper_id", value: "paper_02" }],
      version_bindings: [
        { artifact_version_id: "artv_papsum_01", domain_object_id: "paper_02" },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_star_tic2606",
      node_type: "field",
      label: "恒星 TIC-260647166 (HD 108236)",
      logical_reference: [{ name: "tic_id", value: "260647166" }],
      version_bindings: [
        {
          artifact_version_id: FIELDS_VERSION_ID,
          domain_object_id: "tic_260647166",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_planet_toi1233_01",
      node_type: "field",
      label: "TOI 目录记录 1233.04",
      logical_reference: [{ name: "toi_id", value: "TOI-1233.04" }],
      version_bindings: [
        {
          artifact_version_id: FIELDS_VERSION_ID,
          domain_object_id: "toi_1233_04",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_planet_toi1233_02",
      node_type: "field",
      label: "TOI 目录记录 1233.03",
      logical_reference: [{ name: "toi_id", value: "TOI-1233.03" }],
      version_bindings: [
        {
          artifact_version_id: FIELDS_VERSION_ID,
          domain_object_id: "toi_1233_03",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_claim_01",
      node_type: "claim",
      label: "主张 1：TOI-1233.04 冻结目录参数",
      logical_reference: [{ name: "claim_id", value: "claim_01" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_01",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_claim_02",
      node_type: "claim",
      label: "主张 2：TIC-260647166 冻结恒星参数",
      logical_reference: [{ name: "claim_id", value: "claim_02" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_02",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_claim_03",
      node_type: "claim",
      label: "主张 3：TOI-1233.03 冻结目录参数",
      logical_reference: [{ name: "claim_id", value: "claim_03" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_03",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_claim_04",
      node_type: "claim",
      label: "主张 4：周期比解释待审",
      logical_reference: [{ name: "claim_id", value: "claim_04" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_04",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_claim_05",
      node_type: "claim",
      label: "主张 5：跨表别名映射待审",
      logical_reference: [{ name: "claim_id", value: "claim_05" }],
      version_bindings: [
        {
          artifact_version_id: CLAIMS_VERSION_ID,
          domain_object_id: "claim_05",
        },
      ],
    },
  },
  {
    version: graphVersion,
    node: {
      node_id: "node_fdict_01",
      node_type: "field",
      label: "天文特征字典 (14 个字段)",
      logical_reference: [
        { name: "artifact_version", value: FIELDS_VERSION_ID },
      ],
      version_bindings: [
        {
          artifact_version_id: FIELDS_VERSION_ID,
          domain_object_id: "field_dictionary_candidate_01",
        },
      ],
    },
  },
];

const makeEdge = (
  edgeId: string,
  edgeType:
    | "uses_dataset"
    | "provides_field"
    | "supports_finding"
    | "supports"
    | "extends"
    | "derived_from"
    | "limits"
    | "contradicts"
    | "uses_same_dataset"
    | "compares_method",
  sourceNodeId: string,
  targetNodeId: string,
  relationId: string | null = null,
): GraphEdgeRead => ({
  version: graphVersion,
  evidence: [
    {
      use: {
        evidence_type: "database_query",
        evidence_use_id: `use_${edgeId}`,
        graph_edge_id: edgeId,
        source_snapshot_id: sourceSnapshot.id,
        upstream_artifact_version_id: relationId
          ? RELATIONS_VERSION_ID
          : DATASET_VERSION_ID,
        upstream_evidence_hash: hash(`ev_${edgeId}`),
        upstream_evidence_id: `ev_up_${edgeId}`,
        upstream_is_restricted: false,
        upstream_target_id: edgeId,
        upstream_target_type: "graph_edge",
      },
      evidence: evidence(
        GRAPH_VERSION_ID,
        "graph_edge",
        edgeId,
        `Edge ${edgeType} from ${sourceNodeId} to ${targetNodeId}`,
      ),
      source_snapshot: sourceSnapshot,
    },
  ],
  edge: {
    edge_id: edgeId,
    edge_type: edgeType,
    source_node_id: sourceNodeId,
    target_node_id: targetNodeId,
    evidence_use_ids: [`use_${edgeId}`],
    data_aggregation: {
      conflict_count: 0,
      declared_null_outcome_count: 0,
      mapped_outcome_count: 14,
      projected_row_count: 40,
      retained_candidate_count: 1,
      selected_candidate_count: 1,
      unresolved_outcome_count: 0,
      unselected_candidate_count: 0,
      upstream_evidence_count: 1,
    },
    relation_trace: relationId
      ? {
          relation_id: relationId,
          relation_artifact_version_id: RELATIONS_VERSION_ID,
          relation_type: "supports",
          relation_status: "accepted",
          source_claim_id: sourceNodeId.replace("node_", ""),
          target_claim_id: targetNodeId.replace("node_", ""),
          premise_claim_ids: [
            sourceNodeId.replace("node_", ""),
            targetNodeId.replace("node_", ""),
          ],
          reasoning_trace_id: `trace_${relationId}`,
          trace_evidence_ids: [`ev_up_${edgeId}`],
        }
      : null,
  },
});

export const graphEdgeReads: readonly GraphEdgeRead[] = [
  makeEdge("edge_01", "uses_dataset", "node_goal_01", "node_dataset_01"),
  makeEdge("edge_02", "provides_field", "node_fdict_01", "node_dataset_01"),
  makeEdge("edge_03", "derived_from", "node_dataset_01", "node_src_toi"),
  makeEdge("edge_04", "derived_from", "node_dataset_01", "node_src_ps"),
  makeEdge("edge_05", "derived_from", "node_dataset_01", "node_src_gaia"),
  makeEdge("edge_06", "supports", "node_paper_01", "node_planet_toi1233_01"),
  makeEdge("edge_07", "supports", "node_paper_01", "node_star_tic2606"),
  makeEdge("edge_08", "supports", "node_paper_02", "node_planet_toi1233_02"),
  makeEdge(
    "edge_09",
    "supports",
    "node_star_tic2606",
    "node_planet_toi1233_01",
  ),
  makeEdge(
    "edge_10",
    "supports",
    "node_star_tic2606",
    "node_planet_toi1233_02",
  ),
  makeEdge("edge_11", "supports_finding", "node_paper_01", "node_claim_01"),
  makeEdge("edge_12", "supports_finding", "node_src_ps", "node_claim_02"),
  makeEdge("edge_13", "supports_finding", "node_paper_02", "node_claim_03"),
  makeEdge("edge_14", "supports_finding", "node_paper_01", "node_claim_04"),
  makeEdge("edge_15", "supports_finding", "node_paper_02", "node_claim_05"),
  makeEdge("edge_16", "uses_dataset", "node_dataset_01", "node_star_tic2606"),
  makeEdge(
    "edge_17",
    "uses_dataset",
    "node_dataset_01",
    "node_planet_toi1233_01",
  ),
  // Relation-generated edges connecting accepted relations:
  makeEdge(
    "edge_18_rel_01",
    "uses_same_dataset",
    "node_claim_01",
    "node_claim_02",
    "rel_01",
  ),
  makeEdge(
    "edge_19_rel_02",
    "supports",
    "node_claim_01",
    "node_claim_03",
    "rel_02",
  ),
];

export const graphArtifactReads: readonly GraphArtifactRead[] = [
  {
    graph_id: "graph_01",
    project_id: PROJECT_ID,
    node_count: graphNodeReads.length,
    edge_count: graphEdgeReads.length,
    evidence_use_count: graphEdgeReads.length,
    version: graphVersion,
    input_versions: {
      project_id: PROJECT_ID,
      versions: [graphInputVersion],
    },
    integrity_report: {
      status: "passed",
      content_hash: hash("h_graph_int"),
      policy_version: "2.0.0",
      counts: {
        node_count: graphNodeReads.length,
        edge_count: graphEdgeReads.length,
        evidence_use_count: graphEdgeReads.length,
        input_version_count: 1,
        relation_edge_count: 2,
        source_snapshot_count: 3,
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
      chunks: [
        {
          chunk_index: 0,
          item_ids: [
            ...graphNodeReads.map((n) => n.node.node_id),
            ...graphEdgeReads.map((e) => e.edge.edge_id),
          ],
        },
      ],
    },
    scope: {
      include_data: true,
      research_goal_id: "goal_01",
      literature_claim_ids: literatureClaimReads.map((c) => c.claim.claim_id),
      literature_paper_ids: ["paper_01", "paper_02"],
      accepted_relation_ids: ["rel_01", "rel_02"],
      excluded_item_count: 0,
      filtered_item_count: 0,
      exclusion_reasons: [],
    },
    taxonomy: {
      content_hash: hash("t_taxonomy"),
      node_types: [
        "research_goal",
        "dataset",
        "field",
        "source",
        "paper",
        "entity",
        "claim",
      ],
      edge_types: [
        "uses_dataset",
        "provides_field",
        "derived_from",
        "hosts",
        "observes",
        "supports",
        "supports_finding",
        "describes_same_system",
        "consistent_with",
        "predicts",
      ],
    },
  } as unknown as GraphArtifactRead,
];
