/**
 * Scientific Artifact fixtures adhering to @xingwen/contracts transport DTOs.
 *
 * Covers all 6 scientific artifact kinds:
 * 1. analysis_report
 * 2. visualization (chart, fits_image, wwt_scene)
 * 3. spectrum
 * 4. light_curve
 * 5. model_evaluation
 * 6. model_artifact
 */

import type {
  AnalysisReportArtifactContent,
  ChartVisualizationSpec,
  FitsImageVisualizationSpec,
  LightCurveArtifactContent,
  ModelArtifactContent,
  ModelEvaluationArtifactContent,
  ProducerExecutionDetail,
  ScientificArtifactRead,
  ScientificMetric,
  ScientificResultBlock,
  ScientificSkillExecution,
  SourceSnapshotDetail,
  SpectrumArtifactContent,
  VisualizationArtifactContent,
  WwtSceneVisualizationSpec,
} from "@xingwen/contracts";

import {
  L9859_HARPS_DATASET_ID,
  L9859_HARPS_FILE_SHA256,
  L9859_HARPS_OBSERVED_AT,
  l9859HarpsRecordedPoints,
} from "./recorded-l9859-harps";
import {
  TOI_1233_CATALOG_ROWS,
  TOI_1233_RECORDED_AT,
  TOI_1233_RESPONSE_SHA256,
  TOI_1233_SHORT_PERIOD_ROW,
  TOI_1233_TAP_QUERY,
} from "./recorded-toi-1233-catalog";

function hash(seed: string): string {
  const encoded = Array.from(seed)
    .map((c) => c.codePointAt(0)!.toString(16))
    .join("");
  return `sha256:${encoded.repeat(Math.ceil(64 / encoded.length)).slice(0, 64)}`;
}

const T_CREATED = "2026-07-21T08:28:00Z";

const sourceSnapshot: SourceSnapshotDetail = {
  id: "snap_sci_01",
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

const makeSkillExecution = (
  executionId: string,
  skillId: ScientificSkillExecution["skill_id"],
): ScientificSkillExecution => ({
  execution_id: executionId,
  skill_id: skillId,
  skill_revision: "1.0.0",
  status: "completed",
  input_hash: hash(`i_${executionId}`),
  output_hash: hash(`o_${executionId}`),
  duration_ms: 450,
  warnings: [],
});

const analysisSkillExecution = makeSkillExecution(
  "exec_skill_analysis_01",
  "light_curve_analysis",
);
const chartSkillExecution = makeSkillExecution(
  "exec_skill_chart_01",
  "chart_visualization",
);
const fitsSkillExecution = makeSkillExecution(
  "exec_skill_fits_01",
  "skyview_fits",
);
const wwtSkillExecution = makeSkillExecution("exec_skill_wwt_01", "wwt_scene");
const spectrumSkillExecution = makeSkillExecution(
  "exec_skill_spectrum_01",
  "spectrum_acquisition",
);
const lightCurveSkillExecution: ScientificSkillExecution = {
  ...makeSkillExecution("exec_skill_light_curve_01", "light_curve_analysis"),
  warnings: [
    "Demo Replay UI sequence generation only; no archived light curve was analyzed.",
  ],
};
const modelSkillExecution: ScientificSkillExecution = {
  ...makeSkillExecution("exec_skill_model_01", "time_series_classification"),
  warnings: [
    "Demo Replay metadata projection only; no model training or evaluation run occurred.",
  ],
};

// ---------------------------------------------------------------------------
// 1. Analysis Report
// ---------------------------------------------------------------------------
const analysisMetrics: ScientificMetric[] = [
  {
    metric_id: "met_period",
    label: "TOI 目录轨道周期",
    value: TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
    unit: "d",
    evidence_ids: ["ev_b_analysis_tess"],
  },
  {
    metric_id: "met_radius",
    label: "TOI 目录行星半径",
    value: TOI_1233_SHORT_PERIOD_ROW.planetRadiusEarth,
    unit: "R_Earth",
    evidence_ids: ["ev_b_analysis_catalog"],
  },
  {
    metric_id: "met_depth",
    label: "TOI 目录凌星深度",
    value: TOI_1233_SHORT_PERIOD_ROW.transitDepthPpm,
    unit: "ppm",
    evidence_ids: ["ev_b_analysis_catalog"],
  },
  {
    metric_id: "met_duration",
    label: "TOI 目录凌星持续时间",
    value: TOI_1233_SHORT_PERIOD_ROW.transitDurationHours,
    unit: "h",
    evidence_ids: ["ev_b_analysis_catalog"],
  },
];

const analysisResultBlocks: [
  ScientificResultBlock,
  ...ScientificResultBlock[],
] = [
  {
    block_id: "blk_recorded_catalog_summary",
    label: "冻结目录记录",
    representation: "record",
    payload: {
      source: "NASA Exoplanet Archive TOI table",
      toi: TOI_1233_SHORT_PERIOD_ROW.toi,
      tic_id: TOI_1233_SHORT_PERIOD_ROW.ticId,
      disposition: TOI_1233_SHORT_PERIOD_ROW.disposition,
      orbital_period_days: TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
      transit_depth_ppm: TOI_1233_SHORT_PERIOD_ROW.transitDepthPpm,
      transit_duration_hours: TOI_1233_SHORT_PERIOD_ROW.transitDurationHours,
      catalog_row_updated_at: TOI_1233_SHORT_PERIOD_ROW.rowUpdatedAt,
    },
    content_hash: TOI_1233_RESPONSE_SHA256,
    evidence_ids: ["ev_b_analysis_tess"],
  },
];

export const analysisReportContent: AnalysisReportArtifactContent = {
  kind: "analysis_report",
  schema_version: "1.0.0",
  report_id: "rpt_toi_1233_transit",
  title: "TOI-1233.04 公开目录参数核验与界面能力样例",
  summary:
    "本 Demo Replay 核对 NASA Exoplanet Archive TOI 表中 TOI-1233.04 的冻结目录参数，并用确定性样例覆盖分析报告、图表、光变和模型界面。它不包含原始 TESS 光度序列、MCMC 拟合、TTV 或视向速度结论。",
  skill_executions: [analysisSkillExecution],
  result_blocks: analysisResultBlocks,
  metrics: analysisMetrics,
  findings: [
    {
      finding_id: "fnd_01",
      title: "冻结目录记录可复核",
      statement: `TOI 表记录 ${TOI_1233_SHORT_PERIOD_ROW.toi} 关联 TIC ${TOI_1233_SHORT_PERIOD_ROW.ticId}，处置状态为 ${TOI_1233_SHORT_PERIOD_ROW.disposition}，轨道周期为 ${TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays} 天。`,
      status: "supported",
      evidence_ids: ["ev_b_analysis_tess"],
      metric_ids: ["met_period", "met_depth"],
    },
    {
      finding_id: "fnd_02",
      title: "目录参数不等同于重新拟合",
      statement: `目录给出的行星半径为 ${TOI_1233_SHORT_PERIOD_ROW.planetRadiusEarth} R_Earth；本回放未从光变或恒星参数重新推导该数值。`,
      status: "partial",
      evidence_ids: ["ev_b_analysis_catalog"],
      metric_ids: ["met_radius"],
    },
    {
      finding_id: "fnd_03",
      title: "原始观测分析尚未执行",
      statement:
        "当前 fixture 没有原始 TESS 光度序列，因此不能报告信噪比、周期图显著性、TTV、污染率或模型科学性能。",
      status: "partial",
      evidence_ids: ["ev_b_analysis_tess"],
      metric_ids: [],
    },
  ],
  limitations: [
    "光变点、周期图功率和模型指标是确定性的 UI 边界样例，不是从公开观测重新计算的科研结果。",
    "目录参数来自冻结 TAP 响应；若需要当前值，应重新执行 Live 查询并发布新版本。",
  ],
  human_required: [
    "需要在绑定真实 TESS 数据产品、质量位与算法版本后，才能发布任何光变拟合或模型性能结论。",
  ],
  related_artifact_version_ids: ["artv_b_lc_01", "artv_b_modeval_01"],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_analysis_tess", "ev_b_analysis_catalog"],
  input_hash: hash("i_rpt"),
  output_hash: hash("o_rpt"),
};

// ---------------------------------------------------------------------------
// 2. Visualization (Chart / FITS / WWT)
// ---------------------------------------------------------------------------
const chartSpec: ChartVisualizationSpec = {
  mode: "chart",
  dataset_artifact_version_id: "artv_dataset_01",
  source_snapshot_id: sourceSnapshot.id,
  x_axis: {
    field: "planet.period",
    label: "轨道周期 (Orbital Period)",
    unit: "d",
    scale: "log",
  },
  y_axis: {
    field: "planet.radius",
    label: "行星半径 (Planet Radius)",
    unit: "R_Earth",
    scale: "linear",
  },
  series: [
    {
      series_id: "ser_confirmed",
      label: "TOI-1233 冻结目录记录",
      x_field: "period",
      y_field: "radius",
      mark: "point",
      color_token: "brand",
      points: TOI_1233_CATALOG_ROWS.map((row) => ({
        x: row.orbitalPeriodDays,
        y: row.planetRadiusEarth,
      })) as [{ x: number; y: number }, ...{ x: number; y: number }[]],
    },
    {
      series_id: "ser_candidates",
      label: "容量边界样例（非目录记录）",
      x_field: "period",
      y_field: "radius",
      mark: "point",
      color_token: "warning",
      points: [
        { x: 1.15, y: 1.25 },
        { x: 2.85, y: 1.65 },
        { x: 5.42, y: 2.15 },
        { x: 7.92, y: 2.45 },
        { x: 11.2, y: 2.95 },
        { x: 14.8, y: 3.25 },
        { x: 22.4, y: 3.65 },
        { x: 28.9, y: 3.95 },
      ],
    },
    {
      series_id: "ser_trend",
      label: "视觉引导线（非科学拟合）",
      x_field: "period",
      y_field: "radius",
      mark: "line",
      color_token: "neutral",
      points: [
        { x: 0.5, y: 1.55 },
        { x: 1.0, y: 1.62 },
        { x: 3.0, y: 1.78 },
        { x: 10.0, y: 1.95 },
        { x: 30.0, y: 2.12 },
      ],
    },
  ],
};

export const chartVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_period_radius_diagram",
  title: "TOI-1233 冻结目录周期-半径图与容量边界样例",
  description:
    "品牌色点来自冻结的 NASA Exoplanet Archive TOI 目录响应；橙色点与引导线仅用于覆盖高密度图例、缩放和提示交互，不参与科研解释。",
  spec: chartSpec,
  skill_executions: [chartSkillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_chart_source"],
  input_hash: hash("i_vis_chart"),
  output_hash: hash("o_vis_chart"),
};

const fitsSpec: FitsImageVisualizationSpec = {
  mode: "fits_image",
  source_snapshot_id: sourceSnapshot.id,
  content_ref: "/api/fixture/fits/toi_1233_tpf.fits",
  content_hash: hash("fits_binary_01"),
  stretch: "sqrt",
  color_map: "viridis",
};

export const fitsVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_fits_target_pixel_file",
  title: "TOI-1233 TESS 目标像素文件 (Target Pixel File) 图像",
  description:
    "TESS 11×11 像素切片目标像素图，叠加最优测光孔径 (Optimal Photometric Aperture) 及邻近背景减除掩模。",
  spec: fitsSpec,
  skill_executions: [fitsSkillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_fits_source"],
  input_hash: hash("i_vis_fits"),
  output_hash: hash("o_vis_fits"),
};

const wwtSpec: WwtSceneVisualizationSpec = {
  mode: "wwt_scene",
  view: {
    field_of_view_degrees: 2.5,
    roll_degrees: 0,
    transition_seconds: 1.5,
    center: {
      ra_hours: 12.441,
      dec_degrees: -51.365,
    },
  },
  time: {
    mode: "system_clock",
    observed_at: "2026-07-21T08:00:00Z",
    rate: 1,
  },
  background: "digitized_sky_survey",
  coordinate_grids: [{ system: "equatorial", labels: true }],
  constellations: {
    boundaries: true,
    figures: true,
    pictures: false,
    labels: true,
  },
  fits_layers: [
    {
      layer_id: "fits_layer_tess_cutout",
      source_snapshot_id: sourceSnapshot.id,
      content_ref: "/api/fixture/fits/toi_1233_tpf.fits",
      content_hash: hash("fits_layer_01"),
      opacity: 0.85,
      stretch: "sqrt",
      color_map: "magma",
    },
  ],
  table_layers: [
    {
      layer_id: "tbl_gaia_stars",
      source_snapshot_id: sourceSnapshot.id,
      content_ref: "/api/fixture/tables/gaia_field_stars.csv",
      content_hash: hash("tbl_layer_01"),
      media_type: "text/csv",
      coordinates: {
        frame: "sky",
        longitude_field: "ra",
        latitude_field: "dec",
        longitude_unit: "degrees",
      },
      size_field: "phot_g_mean_mag",
      size_scale: 1.2,
      color_token: "brand",
      marker_scale: "screen",
      opacity: 0.9,
    },
  ],
  annotations: [
    {
      annotation_id: "ann_target_marker",
      kind: "circle",
      points: [{ ra_hours: 12.441, dec_degrees: -51.365 }],
      label: "TOI-1233 (HD 108236)",
      color_token: "warning",
      radius_degrees: 0.08,
      line_width: 2,
      fill: false,
    },
  ],
  readbacks: ["center_coordinates", "field_of_view", "current_time"],
  text_alternative:
    "WWT 天文全景交互场景：以 TOI-1233 为中心的赤道坐标系星空视野，包含明确标注为 Demo Replay 的 TESS 图层样例与 Gaia DR3 临近恒星分布。",
};

export const wwtVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_wwt_toi_1233_scene",
  title: "TOI-1233 天文全景交互场景 (WorldWide Telescope Scene)",
  description:
    "交互式 WWT 虚拟天文台视口，展示目标天体天区、赤道坐标网格、星座连线及空间多波段多源星表图层叠加。",
  spec: wwtSpec,
  skill_executions: [wwtSkillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_wwt_source"],
  input_hash: hash("i_vis_wwt"),
  output_hash: hash("o_vis_wwt"),
};

// ---------------------------------------------------------------------------
// 4. Light Curve
// ---------------------------------------------------------------------------
function generateLightCurvePoints(
  count: number,
  period = TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
  transitDepthPpm = TOI_1233_SHORT_PERIOD_ROW.transitDepthPpm,
) {
  const points = [];
  const durationDays = 27.4; // 1 TESS sector
  const step = durationDays / (count - 1);
  const t0 = 2458682.4128;
  const transitDuration = TOI_1233_SHORT_PERIOD_ROW.transitDurationHours / 24;

  for (let i = 0; i < count; i++) {
    const time = 2458680.0 + i * step;
    const phaseRaw = ((time - t0) % period) / period;
    const phase = phaseRaw < 0 ? phaseRaw + 1 : phaseRaw;
    const phaseNorm = phase - (phase > 0.5 ? 1 : 0);
    const dt = Math.abs(phaseNorm * period);

    let dip = 0;
    if (dt < transitDuration / 2) {
      // Limb-darkened transit profile approximation
      const z = dt / (transitDuration / 2);
      dip = (transitDepthPpm / 1_000_000) * Math.sqrt(Math.max(0, 1 - z * z));
    }

    const noise =
      Math.sin(i * 15.7) * 0.00008 +
      Math.cos(i * 8.3) * 0.00006 +
      Math.sin(time * 0.5) * 0.00005; // slight stellar variability
    const normalizedValue = 1.0 - dip + noise;
    const value = normalizedValue;

    points.push({
      time: Number(time.toFixed(4)),
      value: Number(value.toFixed(6)),
      normalized_value: Number(normalizedValue.toFixed(6)),
      uncertainty: 0.00009,
      quality: "good" as const,
      phase: Number(phaseNorm.toFixed(4)),
    });
  }
  return points;
}

// ---------------------------------------------------------------------------
// 3b. Project C — L 98-59 (TOI-175) dedicated scientific identity
// ---------------------------------------------------------------------------
const sourceSnapshotL9859: SourceSnapshotDetail = {
  id: "snap_l9859_tess",
  source_id: "fixture.l9859_scene",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: {
    target: "L 98-59",
    fixture: true,
    purpose: "FITS and WWT interaction state coverage",
  },
  query_hash: hash("q_l9859"),
  content_hash: hash("c_l9859"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: null,
  license_note:
    "Demo Replay scene input; it is not an archived TESS data product.",
};

const sourceSnapshotL9859Harps: SourceSnapshotDetail = {
  id: "snap_l9859_harps_20240309",
  source_id: "eso.harps",
  source_type: "spectrum",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: {
    dataset_id: L9859_HARPS_DATASET_ID,
    target: "L98-59",
    service: "ivoa.ObsCore",
    fixture: true,
  },
  query_hash:
    "sha256:f48ef1af93bd1d699550a5a48660aceba9e651a376450356792ec152d07c679f",
  content_hash: L9859_HARPS_FILE_SHA256,
  request_metadata: {
    adapter: "demo_replay",
    archive: "ESO Science Archive",
    projection:
      "512 median wavelength bins with local 90th-percentile continuum normalization",
  },
  source_version_or_etag: L9859_HARPS_DATASET_ID,
  license_note: "Public ESO Science Archive data product.",
};

const l9859FitsSpec: FitsImageVisualizationSpec = {
  mode: "fits_image",
  source_snapshot_id: sourceSnapshotL9859.id,
  content_ref: "/api/fixture/fits/l9859_tess_slice.fits",
  content_hash: hash("fits_binary_l9859"),
  stretch: "sqrt",
  color_map: "viridis",
};

export const l9859FitsVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_fits_l9859_slice",
  title: "L 98-59 FITS 图像交互界面样例",
  description:
    "确定性 Demo Replay 像素矩阵用于覆盖拉伸、色图、坐标和空值状态；它不是归档 TESS 图像，也不用于测光提取。",
  spec: l9859FitsSpec,
  skill_executions: [fitsSkillExecution],
  source_snapshot_ids: [sourceSnapshotL9859.id],
  evidence_ids: ["ev_c_fits_source"],
  input_hash: hash("i_vis_fits_l9859"),
  output_hash: hash("o_vis_fits_l9859"),
};

const l9859WwtSpec: WwtSceneVisualizationSpec = {
  mode: "wwt_scene",
  view: {
    field_of_view_degrees: 2.5,
    roll_degrees: 0,
    transition_seconds: 1.5,
    center: {
      ra_hours: 4.7902,
      dec_degrees: -17.251,
    },
  },
  time: {
    mode: "system_clock",
    observed_at: "2026-07-21T08:00:00Z",
    rate: 1,
  },
  background: "digitized_sky_survey",
  coordinate_grids: [{ system: "equatorial", labels: true }],
  constellations: {
    boundaries: true,
    figures: true,
    pictures: false,
    labels: true,
  },
  fits_layers: [
    {
      layer_id: "fits_layer_l9859_slice",
      source_snapshot_id: sourceSnapshotL9859.id,
      content_ref: "/api/fixture/fits/l9859_tess_slice.fits",
      content_hash: hash("fits_layer_l9859"),
      opacity: 0.85,
      stretch: "sqrt",
      color_map: "magma",
    },
  ],
  table_layers: [
    {
      layer_id: "tbl_gaia_l9859",
      source_snapshot_id: sourceSnapshotL9859.id,
      content_ref: "/api/fixture/tables/gaia_l9859_field.csv",
      content_hash: hash("tbl_layer_l9859"),
      media_type: "text/csv",
      coordinates: {
        frame: "sky",
        longitude_field: "ra",
        latitude_field: "dec",
        longitude_unit: "degrees",
      },
      size_field: "phot_g_mean_mag",
      size_scale: 1.2,
      color_token: "brand",
      marker_scale: "screen",
      opacity: 0.9,
    },
  ],
  annotations: [
    {
      annotation_id: "ann_l9859_marker",
      kind: "circle",
      points: [{ ra_hours: 4.7902, dec_degrees: -17.251 }],
      label: "L 98-59 (TOI-175)",
      color_token: "warning",
      radius_degrees: 0.08,
      line_width: 2,
      fill: false,
    },
  ],
  readbacks: ["center_coordinates", "field_of_view", "current_time"],
  text_alternative:
    "WWT 界面能力样例：以 L 98-59 为中心的赤道坐标系星空视野，图层用于覆盖开关、定位与 readback 交互，不代表真实 TESS 或 Gaia 联合观测。",
};

export const l9859WwtVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_wwt_l9859_scene",
  title: "L 98-59 天文全景交互场景 (WorldWide Telescope Scene)",
  description:
    "交互式 WWT Demo Replay 视口，覆盖 L 98-59 定位、赤道网格、星座连线与图层控制；场景图层不是科研观测产品。",
  spec: l9859WwtSpec,
  skill_executions: [wwtSkillExecution],
  source_snapshot_ids: [sourceSnapshotL9859.id],
  evidence_ids: ["ev_c_wwt_source"],
  input_hash: hash("i_vis_wwt_l9859"),
  output_hash: hash("o_vis_wwt_l9859"),
};

export const l9859SpectrumContent: SpectrumArtifactContent = {
  kind: "spectrum",
  schema_version: "1.0.0",
  spectrum_id: "spec_l9859_harps",
  title: "L 98-59 公开 HARPS 一维光谱记录",
  object_name: "L 98-59 (TOI-175)",
  wavelength_unit: "angstrom",
  flux_unit: "continuum_normalized",
  sample_count: l9859HarpsRecordedPoints.length,
  points: l9859HarpsRecordedPoints,
  signal_to_noise: 8,
  detected_lines: [],
  rest_wavelength: null,
  radial_velocity_km_s: null,
  skill_executions: [spectrumSkillExecution],
  source_snapshot_ids: [sourceSnapshotL9859Harps.id],
  evidence_ids: ["ev_c_spec_source"],
  input_hash: hash("i_spec_l9859"),
  output_hash: hash("o_spec_l9859"),
};

export const l9859AnalysisReportContent: AnalysisReportArtifactContent = {
  ...analysisReportContent,
  report_id: "rpt_l9859_spectroscopy",
  title: "L 98-59 (TOI-175) 公开观测数据核验报告",
  summary:
    "核验 ESO Science Archive 中 L 98-59 的公开 HARPS 一维光谱产品，并与 TESS 场景输入分别保留来源快照。当前 Demo Replay 仅展示记录投影，不自动给出谱线证认或恒星参数结论。",
  metrics: [
    {
      metric_id: "met_l9859_archive_snr",
      label: "归档产品 S/N",
      value: 8,
      unit: null,
      evidence_ids: ["ev_c_analysis_source"],
    },
    {
      metric_id: "met_l9859_display_samples",
      label: "显示投影采样点",
      value: l9859HarpsRecordedPoints.length,
      unit: null,
      evidence_ids: ["ev_c_analysis_source"],
    },
  ],
  findings: [
    {
      finding_id: "fnd_l9859_01",
      title: "公开光谱产品与目标坐标匹配",
      statement: `ESO 数据产品 ${L9859_HARPS_DATASET_ID} 的目标名为 L98-59，观测时间为 ${L9859_HARPS_OBSERVED_AT}；本次仅作连续谱归一化显示投影，未生成新的天体物理结论。`,
      status: "supported",
      evidence_ids: ["ev_c_analysis_source"],
      metric_ids: ["met_l9859_archive_snr"],
    },
  ],
  result_blocks: [
    {
      block_id: "blk_l9859_archive_record",
      label: "归档记录",
      representation: "record",
      payload: {
        dataset_id: L9859_HARPS_DATASET_ID,
        observed_at: L9859_HARPS_OBSERVED_AT,
        wavelength_range_angstrom: "4000-6800",
        display_sample_count: l9859HarpsRecordedPoints.length,
      },
      content_hash: L9859_HARPS_FILE_SHA256,
      evidence_ids: ["ev_c_analysis_source"],
    },
  ],
  skill_executions: [spectrumSkillExecution],
  related_artifact_version_ids: ["artv_c_spec_01", "artv_c_fits_01"],
  source_snapshot_ids: [sourceSnapshotL9859Harps.id, sourceSnapshotL9859.id],
  evidence_ids: ["ev_c_analysis_source"],
  limitations: [
    "光谱显示投影经过等宽分箱与局部连续谱归一化，不替代原始逐像元、逐阶数据分析。",
    "归档产品未提供可用的逐点 ERR 数组，因此界面不展示采样点误差条。",
  ],
  human_required: [
    "如需谱线证认、径向速度或恒星参数结论，应在绑定相应算法版本和质量门后另行发布新版本。",
  ],
  input_hash: hash("i_rpt_l9859"),
  output_hash: hash("o_rpt_l9859"),
};

export const lightCurveContent: LightCurveArtifactContent = {
  kind: "light_curve",
  schema_version: "1.0.0",
  light_curve_id: "lc_toi_1233_sector10",
  title: "TOI-1233.04 目录参数驱动的光变界面样例",
  object_name: "TOI-1233.04 (TIC 260647166)",
  time_scale: "tdb",
  time_unit: "days",
  value_unit: "relative_flux",
  value_kind: "relative_flux",
  normalization: "median_division",
  sample_count: 720,
  accepted_sample_count: 712,
  rejected_sample_count: 8,
  duration: 27.4,
  median_cadence: 120 / 86_400, // 2-minute cadence, expressed in days
  best_period: TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
  best_power: 0.884,
  false_alarm_probability: null,
  period_peaks: [
    {
      period: TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
      power: 0.884,
    },
    { period: TOI_1233_CATALOG_ROWS[2]!.orbitalPeriodDays, power: 0.652 },
    { period: TOI_1233_CATALOG_ROWS[0]!.orbitalPeriodDays, power: 0.412 },
    { period: TOI_1233_CATALOG_ROWS[1]!.orbitalPeriodDays, power: 0.325 },
  ],
  points: generateLightCurvePoints(
    720,
    TOI_1233_SHORT_PERIOD_ROW.orbitalPeriodDays,
    TOI_1233_SHORT_PERIOD_ROW.transitDepthPpm,
  ) as unknown as LightCurveArtifactContent["points"],
  skill_executions: [lightCurveSkillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_lightcurve_source", "ev_b_lightcurve_period"],
  input_hash: hash("i_lc"),
  output_hash: hash("o_lc"),
};

// ---------------------------------------------------------------------------
// 5. Model Evaluation
// ---------------------------------------------------------------------------
const modelMetrics: [ScientificMetric, ...ScientificMetric[]] = [
  {
    metric_id: "met_acc",
    label: "准确率 (Accuracy)",
    value: 0.942,
    unit: null,
    evidence_ids: ["ev_b_modeval_source"],
  },
  {
    metric_id: "met_f1",
    label: "F1 分数 (Macro F1)",
    value: 0.918,
    unit: null,
    evidence_ids: ["ev_b_modeval_source"],
  },
  {
    metric_id: "met_roc_auc",
    label: "ROC-AUC",
    value: 0.965,
    unit: null,
    evidence_ids: ["ev_b_modeval_source"],
  },
  {
    metric_id: "met_pr_auc",
    label: "PR-AUC",
    value: 0.934,
    unit: null,
    evidence_ids: ["ev_b_modeval_source"],
  },
];

const baselineMetrics: ScientificMetric[] = [
  {
    metric_id: "met_acc",
    label: "基线准确率 (Random Forest)",
    value: 0.885,
    unit: null,
    evidence_ids: [],
  },
  {
    metric_id: "met_f1",
    label: "基准 F1 分数",
    value: 0.842,
    unit: null,
    evidence_ids: [],
  },
];

export const modelEvaluationContent: ModelEvaluationArtifactContent = {
  kind: "model_evaluation",
  schema_version: "1.0.0",
  evaluation_id: "modeval_transit_classifier_01",
  title: "Demo Replay 凌星分类器界面能力评估样例",
  task_kind: "classification",
  algorithm: "ResNet-1D-TransitClassifier",
  algorithm_version: "2.4.0",
  training_input: {
    kind: "dataset_artifact_version",
    ref_id: "artv_dataset_01",
  },
  feature_fields: [
    "phase_folded_flux",
    "transit_depth",
    "transit_duration",
    "snr",
    "stellar_radius",
    "effective_temperature",
  ],
  target_field: "is_planetary_transit",
  split: {
    strategy: "stratified",
    field: "target_label",
    random_seed: 42,
    train_fraction: 0.7,
    validation_fraction: 0.15,
    test_fraction: 0.15,
    cross_validation_folds: 5,
    train_cutoff: null,
  },
  metrics: modelMetrics,
  baseline_metrics: baselineMetrics,
  skill_execution: modelSkillExecution,
  model_binary: {
    content_ref: "/api/fixture/models/transit_classifier_resnet.onnx",
    content_hash: hash("onnx_model_binary_01"),
    media_type: "application/onnx",
  },
  diagnostic_visualization_ids: ["vis_period_radius_diagram"],
  limitations: [
    "全部指标用于覆盖指标卡、基线差异和诊断布局，不代表公开数据集上的科研基准结果。",
    "fixture 未绑定训练集、验证集或真实模型运行，因此不能用于算法优劣判断。",
  ],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_modeval_source"],
  input_hash: hash("i_modeval"),
  output_hash: hash("o_modeval"),
};

// ---------------------------------------------------------------------------
// 6. Model Artifact
// ---------------------------------------------------------------------------
export const modelArtifactContent: ModelArtifactContent = {
  kind: "model_artifact",
  schema_version: "1.0.0",
  model_id: "model_transit_classifier_onnx",
  title: "Demo Replay ResNet-1D ONNX 交互样例",
  status: "deprecated",
  task_kind: "classification",
  algorithm: "ResNet-1D-TransitClassifier",
  algorithm_version: "2.4.0",
  training_input: {
    kind: "dataset_artifact_version",
    ref_id: "artv_dataset_01",
  },
  evaluation_id: "modeval_transit_classifier_01",
  feature_fields: [
    "phase_folded_flux",
    "transit_depth",
    "transit_duration",
    "snr",
    "stellar_radius",
    "effective_temperature",
  ],
  target_field: "is_planetary_transit",
  model_binary: {
    content_ref: "/api/fixture/models/transit_classifier_resnet.onnx",
    content_hash: hash("onnx_model_binary_01"),
    media_type: "application/onnx",
  },
  input_name: "flux_and_stellar_features",
  output_names: ["transit_probability", "feature_embeddings"],
  input_shape: [-1, 720, 1],
  opset_imports: { "ai.onnx": 17 },
  dependency_revisions: [
    "torch==2.3.0",
    "onnxruntime==1.18.0",
    "numpy==1.26.4",
  ],
  skill_execution: modelSkillExecution,
  limitations: [
    "该二进制引用仅覆盖工件元数据与不可下载状态，不是经过训练、验证或可部署的 ONNX 模型。",
    "content_ref 不对应可执行生产文件；只有绑定真实二进制、依赖和评估记录的新版本才可部署。",
  ],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_b_model_source"],
  input_hash: hash("i_model_art"),
  output_hash: hash("o_model_art"),
};

// ---------------------------------------------------------------------------
// Unified Scientific Artifact Reads Array
// ---------------------------------------------------------------------------
interface FixtureEvidenceBinding {
  readonly id: string;
  readonly sourceSnapshotId: string;
  readonly extractionMethod: string;
  readonly quoteOrValue: string;
}

interface ScientificReadFixtureOptions {
  readonly runId: string;
  readonly sourceMode?: ScientificArtifactRead["source_mode"];
  readonly sourceSnapshots: readonly SourceSnapshotDetail[];
  readonly evidence: readonly FixtureEvidenceBinding[];
}

const makeProducerExecution = (
  artifactVersionId: string,
  runId: string,
  kind: ScientificArtifactRead["content"]["kind"],
): ProducerExecutionDetail => ({
  id: `exec_${artifactVersionId}`,
  run_id: runId,
  step_key: `publish_${kind}`,
  step_attempt_id: `attempt_${artifactVersionId}`,
  status: "completed",
  started_at: "2026-07-21T08:20:00Z",
  finished_at: T_CREATED,
  input_hash: hash(`in_${artifactVersionId}`),
  output_hash: hash(artifactVersionId),
  parameters: { execution_mode: "demo_replay", artifact_kind: kind },
  parameters_hash: hash(`params_${artifactVersionId}`),
  latency_ms: 120,
  error_code: null,
  producer: {
    type: "pipeline",
    name: "xingwen-scientific-runtime",
    version: "2.1.0",
  },
});

const makeScientificRead = (
  artifactId: string,
  artifactVersionId: string,
  projectId: string,
  versionNumber: number,
  content: ScientificArtifactRead["content"],
  options: ScientificReadFixtureOptions,
): ScientificArtifactRead => ({
  artifact_id: artifactId,
  artifact_version_id: artifactVersionId,
  project_id: projectId,
  version_number: versionNumber,
  source_mode: options.sourceMode ?? "fixture",
  content_hash: hash(artifactVersionId),
  input_hash: hash(`in_${artifactVersionId}`),
  created_at: T_CREATED,
  supersedes_version_id: null,
  producer_execution: makeProducerExecution(
    artifactVersionId,
    options.runId,
    content.kind,
  ),
  source_snapshots: [...options.sourceSnapshots],
  evidence: options.evidence.map((binding) => ({
    id: binding.id,
    artifact_version_id: artifactVersionId,
    target_type: "source",
    target_id: binding.sourceSnapshotId,
    evidence_type: "database_query",
    source_snapshot_id: binding.sourceSnapshotId,
    extraction_method: binding.extractionMethod,
    confidence: 1,
    locator: { kind: "fixture_record", key: binding.sourceSnapshotId },
    quote_or_value: binding.quoteOrValue,
    paper_id: null,
    created_at: T_CREATED,
  })),
  content,
});

const catalogReplayOptions = (
  runId: string,
  target: string,
  evidenceIds: readonly string[],
): ScientificReadFixtureOptions => ({
  runId,
  sourceSnapshots: [sourceSnapshot],
  evidence: evidenceIds.map((id) => ({
    id,
    sourceSnapshotId: sourceSnapshot.id,
    extractionMethod: "recorded.nasa_exoplanet_archive_toi",
    quoteOrValue: `Recorded NASA Exoplanet Archive TOI catalog response for ${target}; generated UI samples are not observed flux or model results.`,
  })),
});

const l9859TessReplayOptions = (
  evidenceIds: readonly string[],
): ScientificReadFixtureOptions => ({
  runId: "run_l9859",
  sourceSnapshots: [sourceSnapshotL9859],
  evidence: evidenceIds.map((id) => ({
    id,
    sourceSnapshotId: sourceSnapshotL9859.id,
    extractionMethod: "fixture.demo_replay",
    quoteOrValue:
      "Demo Replay-only scene input for L 98-59 FITS and WWT interaction coverage; not an archived observation.",
  })),
});

export const scientificArtifactReadsFixture: readonly ScientificArtifactRead[] =
  [
    // Project B (TOI Transit)
    makeScientificRead(
      "art_b_analysis_01",
      "artv_b_analysis_01",
      "proj_toi_transit",
      1,
      analysisReportContent,
      catalogReplayOptions("run_toi_transit", "TOI-1233", [
        "ev_b_analysis_tess",
        "ev_b_analysis_catalog",
      ]),
    ),
    makeScientificRead(
      "art_b_chart_01",
      "artv_b_chart_01",
      "proj_toi_transit",
      1,
      chartVisualizationContent,
      catalogReplayOptions("run_toi_transit", "TOI-1233", [
        "ev_b_chart_source",
      ]),
    ),
    makeScientificRead(
      "art_b_lc_01",
      "artv_b_lc_01",
      "proj_toi_transit",
      1,
      lightCurveContent,
      catalogReplayOptions("run_toi_transit", "TOI-1233", [
        "ev_b_lightcurve_source",
        "ev_b_lightcurve_period",
      ]),
    ),
    makeScientificRead(
      "art_b_modeval_01",
      "artv_b_modeval_01",
      "proj_toi_transit",
      1,
      modelEvaluationContent,
      catalogReplayOptions("run_toi_transit", "TOI-1233", [
        "ev_b_modeval_source",
      ]),
    ),
    makeScientificRead(
      "art_b_model_01",
      "artv_b_model_01",
      "proj_toi_transit",
      1,
      modelArtifactContent,
      catalogReplayOptions("run_toi_transit", "TOI-1233", [
        "ev_b_model_source",
      ]),
    ),

    // Project C (L 98-59 Spectroscopy & WWT Scene)
    makeScientificRead(
      "art_c_spec_01",
      "artv_c_spec_01",
      "proj_l9859_spectroscopy",
      1,
      l9859SpectrumContent,
      {
        runId: "run_l9859",
        sourceMode: "recorded",
        sourceSnapshots: [sourceSnapshotL9859Harps],
        evidence: [
          {
            id: "ev_c_spec_source",
            sourceSnapshotId: sourceSnapshotL9859Harps.id,
            extractionMethod: "recorded.eso_harps_projection",
            quoteOrValue: `Public ESO HARPS spectrum ${L9859_HARPS_DATASET_ID} observed at ${L9859_HARPS_OBSERVED_AT}.`,
          },
        ],
      },
    ),
    makeScientificRead(
      "art_c_fits_01",
      "artv_c_fits_01",
      "proj_l9859_spectroscopy",
      1,
      l9859FitsVisualizationContent,
      l9859TessReplayOptions(["ev_c_fits_source"]),
    ),
    makeScientificRead(
      "art_c_wwt_01",
      "artv_c_wwt_01",
      "proj_l9859_spectroscopy",
      1,
      l9859WwtVisualizationContent,
      l9859TessReplayOptions(["ev_c_wwt_source"]),
    ),
    makeScientificRead(
      "art_c_analysis_01",
      "artv_c_analysis_01",
      "proj_l9859_spectroscopy",
      1,
      l9859AnalysisReportContent,
      {
        runId: "run_l9859",
        sourceMode: "recorded",
        sourceSnapshots: [sourceSnapshotL9859Harps, sourceSnapshotL9859],
        evidence: [
          {
            id: "ev_c_analysis_source",
            sourceSnapshotId: sourceSnapshotL9859Harps.id,
            extractionMethod: "recorded.eso_harps_projection",
            quoteOrValue: `Public ESO HARPS spectrum ${L9859_HARPS_DATASET_ID} observed at ${L9859_HARPS_OBSERVED_AT}.`,
          },
        ],
      },
    ),
  ];
