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

function hash(seed: string): string {
  const encoded = Array.from(seed)
    .map((c) => c.codePointAt(0)!.toString(16))
    .join("");
  return `sha256:${encoded.repeat(Math.ceil(64 / encoded.length)).slice(0, 64)}`;
}

const T_CREATED = "2026-07-21T08:28:00Z";

const sourceSnapshot: SourceSnapshotDetail = {
  id: "snap_sci_01",
  source_id: "mast.tess",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: { target: "TOI-1233", mission: "TESS", fixture: true },
  query_hash: hash("q_sci_01"),
  content_hash: hash("c_sci_01"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "tess-dr5-2026",
  license_note: "Public domain NASA / MAST TESS observation archive data.",
};

const producerExecution: ProducerExecutionDetail = {
  id: "exec_sci_pipeline_01",
  run_id: "run_01JEXAMPLE",
  step_key: "scientific_inference",
  step_attempt_id: "attempt_sci_01",
  status: "completed",
  started_at: "2026-07-21T08:20:00Z",
  finished_at: T_CREATED,
  input_hash: hash("i_sci"),
  output_hash: hash("o_sci"),
  parameters: { pipeline: "autoastro_mavis_synthesis" },
  parameters_hash: hash("p_sci"),
  latency_ms: 120,
  error_code: null,
  producer: {
    type: "pipeline",
    name: "xingwen-scientific-runtime",
    version: "2.1.0",
  },
};

const skillExecution: ScientificSkillExecution = {
  execution_id: "exec_skill_01",
  skill_id: "light_curve_analysis",
  skill_revision: "1.0.0",
  status: "completed",
  input_hash: hash("i_skill"),
  output_hash: hash("o_skill"),
  duration_ms: 450,
  warnings: [],
};

// ---------------------------------------------------------------------------
// 1. Analysis Report
// ---------------------------------------------------------------------------
const analysisMetrics: ScientificMetric[] = [
  {
    metric_id: "met_snr",
    label: "凌星信噪比 (S/N)",
    value: 38.4,
    unit: null,
    evidence_ids: ["ev_sci_01"],
  },
  {
    metric_id: "met_period",
    label: "最佳轨道周期",
    value: 3.7952,
    unit: "d",
    evidence_ids: ["ev_sci_01"],
  },
  {
    metric_id: "met_depth",
    label: "凌星深度 (Transit Depth)",
    value: 684.2,
    unit: "ppm",
    evidence_ids: ["ev_sci_02"],
  },
  {
    metric_id: "met_rp_rs",
    label: "行星-恒星半径比 Rp/R*",
    value: 0.02616,
    unit: null,
    evidence_ids: ["ev_sci_02"],
  },
];

const analysisResultBlocks: [
  ScientificResultBlock,
  ...ScientificResultBlock[],
] = [
  {
    block_id: "blk_mcmc_summary",
    label: "MCMC 后验参数拟合结果",
    representation: "record",
    payload: {
      sampler: "emcee",
      n_walkers: 64,
      n_steps: 10000,
      burn_in: 2000,
      r_hat_max: 1.01,
      parameters: {
        orbital_period_days: "3.795231 +/- 0.000018",
        transit_epoch_bjd: "2458682.4128 +/- 0.0012",
        impact_parameter_b: "0.24 +/- 0.08",
        scaled_semimajor_axis: "11.42 +/- 0.35",
      },
    },
    content_hash: hash("blk_01"),
    evidence_ids: ["ev_sci_01"],
  },
];

export const analysisReportContent: AnalysisReportArtifactContent = {
  kind: "analysis_report",
  schema_version: "1.0.0",
  report_id: "rpt_toi_1233_transit",
  title: "TOI-1233 (HD 108236) 凌星拟合与动力学综合分析报告",
  summary:
    "基于 TESS Sector 10/11 光变曲线与高精度 RV 观测数据，完成 TOI-1233 系统的多行星凌星模型联合拟合。确认 TOI-1233.01 (b) 为短周期亚海王星，凌星信噪比达到 38.4，轨道周期 3.7952 天，半径 2.06 R_Earth。未发现显著 TTV 信号，但限制了外层行星的质量上限。",
  skill_executions: [skillExecution],
  result_blocks: analysisResultBlocks,
  metrics: analysisMetrics,
  findings: [
    {
      finding_id: "fnd_01",
      title: "确认 TOI-1233.01 凌星特征为高质量行星候选体",
      statement:
        "TESS 光变曲线呈现高对称性 U 型凌星轮廓，拟合半径比 Rp/R* = 0.02616，无显著食双星二次掩食特征。",
      status: "supported",
      evidence_ids: ["ev_sci_01"],
      metric_ids: ["met_snr", "met_depth"],
    },
    {
      finding_id: "fnd_02",
      title: "宿主星参数约束下的行星物理半径",
      statement:
        "结合 Gaia DR3 距离与光谱有效温度 (5720 K)，推导行星物理半径为 2.06 ± 0.08 R_Earth，位于挥发分包层过渡区。",
      status: "supported",
      evidence_ids: ["ev_sci_02"],
      metric_ids: ["met_rp_rs"],
    },
    {
      finding_id: "fnd_03",
      title: "凌星时刻变分 (TTV) 动力学分析",
      statement:
        "在 18 个连续观测周期内，凌星中心时刻残差在 2.1 分钟以内，未检测到超过 3-sigma 的周期性 TTV 扰动。",
      status: "partial",
      evidence_ids: ["ev_sci_01"],
      metric_ids: ["met_period"],
    },
  ],
  limitations: [
    "当前单波段 TESS 测光无法完全排除临近暗星污染率低于 1.2% 的背景共混可能性。",
    "需要高精度红外光谱 (如 JWST NIRSpec) 进一步约束大气水分子吸收带。",
  ],
  human_required: [
    "需人工审定 TTV 动力学反演参数与外部 HARPS 视向速度数据的置信区间匹配度。",
  ],
  related_artifact_version_ids: ["artv_lc_01", "artv_spec_01"],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01", "ev_sci_02"],
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
      label: "已确认系外行星 (Confirmed)",
      x_field: "period",
      y_field: "radius",
      mark: "point",
      color_token: "brand",
      points: [
        { x: 0.78, y: 1.12 },
        { x: 1.42, y: 1.45 },
        { x: 2.15, y: 1.88 },
        { x: 3.79, y: 2.06 },
        { x: 4.82, y: 2.35 },
        { x: 6.21, y: 2.72 },
        { x: 9.55, y: 3.12 },
        { x: 12.3, y: 3.48 },
        { x: 15.6, y: 2.18 },
        { x: 19.8, y: 2.65 },
        { x: 24.1, y: 3.89 },
        { x: 31.5, y: 4.12 },
      ],
    },
    {
      series_id: "ser_candidates",
      label: "TOI 候选体 (Candidates)",
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
      label: "半径谷演化拟合线 (Radius Valley)",
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
  title: "系外行星周期-半径分布图 (Period-Radius Diagram)",
  description:
    "展示系外行星样本在轨道周期与半径维度的分布格局，清晰揭示 Fulton 半径谷 (Fulton gap) 及亚海王星与超级地球的分界特征。",
  spec: chartSpec,
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
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
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
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
    "WWT 天文全景观测场景：以 TOI-1233 为中心的赤道坐标系星空视野，包含 TESS 观测切片图层与 Gaia DR3 临近恒星分布。",
};

export const wwtVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_wwt_toi_1233_scene",
  title: "TOI-1233 天文全景观测场景 (WorldWide Telescope Scene)",
  description:
    "交互式 WWT 虚拟天文台视口，展示目标天体天区、赤道坐标网格、星座连线及空间多波段多源星表图层叠加。",
  spec: wwtSpec,
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
  input_hash: hash("i_vis_wwt"),
  output_hash: hash("o_vis_wwt"),
};

// ---------------------------------------------------------------------------
// 3. Spectrum
// ---------------------------------------------------------------------------
function generateSpectrumPoints(count: number) {
  const points = [];
  const startWl = 3800;
  const endWl = 6800;
  const step = (endWl - startWl) / (count - 1);
  for (let i = 0; i < count; i++) {
    const wl = startWl + i * step;
    // Base blackbody-like curve around 5700K
    const x = (wl - 3800) / 3000;
    const continuum = 0.5 + 0.5 * Math.sin(x * Math.PI * 0.85);
    // Absorption lines
    let absorption = 0;
    // Ca II K & H (3933.7, 3968.5)
    if (Math.abs(wl - 3933.7) < 25)
      absorption += 0.45 * Math.exp(-Math.pow((wl - 3933.7) / 6, 2));
    if (Math.abs(wl - 3968.5) < 25)
      absorption += 0.38 * Math.exp(-Math.pow((wl - 3968.5) / 6, 2));
    // H-beta (4861.3)
    if (Math.abs(wl - 4861.3) < 20)
      absorption += 0.32 * Math.exp(-Math.pow((wl - 4861.3) / 5, 2));
    // Na I D (5890.0, 5896.0)
    if (Math.abs(wl - 5890.0) < 18)
      absorption += 0.42 * Math.exp(-Math.pow((wl - 5890.0) / 4, 2));
    if (Math.abs(wl - 5896.0) < 18)
      absorption += 0.35 * Math.exp(-Math.pow((wl - 5896.0) / 4, 2));
    // H-alpha (6562.8)
    if (Math.abs(wl - 6562.8) < 25)
      absorption += 0.5 * Math.exp(-Math.pow((wl - 6562.8) / 5, 2));

    const noise = Math.sin(i * 12.3) * 0.02 + Math.cos(i * 7.1) * 0.015;
    const normalizedFlux = Math.max(0.05, 1.0 - absorption + noise);
    const flux = continuum * normalizedFlux;
    points.push({
      wavelength: Number(wl.toFixed(2)),
      flux: Number(flux.toFixed(4)),
      continuum: Number(continuum.toFixed(4)),
      normalized_flux: Number(normalizedFlux.toFixed(4)),
      uncertainty: 0.008,
    });
  }
  return points;
}

export const spectrumContent: SpectrumArtifactContent = {
  kind: "spectrum",
  schema_version: "1.0.0",
  spectrum_id: "spec_toi_1233_harps",
  title: "TOI-1233 高分辨率恒星光谱 (HARPS Spectrograph)",
  object_name: "TOI-1233 (HD 108236)",
  wavelength_unit: "angstrom",
  flux_unit: "normalized_continuum",
  sample_count: 512,
  points: generateSpectrumPoints(
    512,
  ) as unknown as SpectrumArtifactContent["points"],
  signal_to_noise: 145.2,
  detected_lines: [
    {
      line_id: "line_ca_ii_k",
      kind: "absorption",
      observed_wavelength: 3933.68,
      normalized_flux: 0.55,
      significance_sigma: 18.4,
      equivalent_width: 1.42,
    },
    {
      line_id: "line_ca_ii_h",
      kind: "absorption",
      observed_wavelength: 3968.49,
      normalized_flux: 0.62,
      significance_sigma: 15.8,
      equivalent_width: 1.18,
    },
    {
      line_id: "line_h_beta",
      kind: "absorption",
      observed_wavelength: 4861.32,
      normalized_flux: 0.68,
      significance_sigma: 14.2,
      equivalent_width: 0.95,
    },
    {
      line_id: "line_na_i_d2",
      kind: "absorption",
      observed_wavelength: 5889.95,
      normalized_flux: 0.58,
      significance_sigma: 22.1,
      equivalent_width: 1.05,
    },
    {
      line_id: "line_h_alpha",
      kind: "absorption",
      observed_wavelength: 6562.81,
      normalized_flux: 0.5,
      significance_sigma: 26.8,
      equivalent_width: 1.65,
    },
  ],
  rest_wavelength: null,
  radial_velocity_km_s: 18.42,
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
  input_hash: hash("i_spec"),
  output_hash: hash("o_spec"),
};

// ---------------------------------------------------------------------------
// 4. Light Curve
// ---------------------------------------------------------------------------
function generateLightCurvePoints(count: number, period = 3.7952) {
  const points = [];
  const durationDays = 27.4; // 1 TESS sector
  const step = durationDays / (count - 1);
  const t0 = 2458682.4128;
  const transitDuration = 0.12; // ~2.8 hours

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
      dip = 0.000684 * Math.sqrt(Math.max(0, 1 - z * z));
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
  source_id: "mast.tess",
  source_type: "catalog",
  retrieved_at: "2026-07-21T08:20:00Z",
  query: { target: "L 98-59", mission: "TESS", fixture: true },
  query_hash: hash("q_l9859"),
  content_hash: hash("c_l9859"),
  request_metadata: { adapter: "demo_replay" },
  source_version_or_etag: "tess-dr5-2026",
  license_note: "Public domain NASA / MAST TESS observation archive data.",
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
  title: "L 98-59 TESS 图像切片 (Target Pixel Slice)",
  description:
    "TESS 像素切片目标图，叠加测光孔径与背景掩模，用于 L 98-59 凌星测光提取。",
  spec: l9859FitsSpec,
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshotL9859.id],
  evidence_ids: ["ev_sci_01"],
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
    "WWT 天文全景观测场景：以 L 98-59 为中心的赤道坐标系星空视野，包含 TESS 观测切片图层与 Gaia DR3 临近恒星分布。",
};

export const l9859WwtVisualizationContent: VisualizationArtifactContent = {
  kind: "visualization",
  schema_version: "1.0.0",
  visualization_id: "vis_wwt_l9859_scene",
  title: "L 98-59 天文全景观测场景 (WorldWide Telescope Scene)",
  description:
    "交互式 WWT 虚拟天文台视口，展示 L 98-59 天区、赤道坐标网格、星座连线及 TESS/Gaia 多源图层叠加。",
  spec: l9859WwtSpec,
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshotL9859.id],
  evidence_ids: ["ev_sci_01"],
  input_hash: hash("i_vis_wwt_l9859"),
  output_hash: hash("o_vis_wwt_l9859"),
};

export const l9859SpectrumContent: SpectrumArtifactContent = {
  ...spectrumContent,
  spectrum_id: "spec_l9859_harps",
  title: "L 98-59 高分辨率恒星光谱 (HARPS Spectrograph)",
  object_name: "L 98-59 (TOI-175)",
  source_snapshot_ids: [sourceSnapshotL9859.id],
  input_hash: hash("i_spec_l9859"),
  output_hash: hash("o_spec_l9859"),
};

export const l9859AnalysisReportContent: AnalysisReportArtifactContent = {
  ...analysisReportContent,
  report_id: "rpt_l9859_spectroscopy",
  title: "L 98-59 (TOI-175) 光谱学与测光综合分析报告",
  summary:
    "基于 HARPS 高分辨率光谱与 TESS 测光切片，完成 L 98-59 系统的恒星参数测量与凌星候选证认。光谱吸收线分析约束有效温度与金属丰度，TESS 切片测光确认多行星凌星信号。",
  findings: [
    {
      finding_id: "fnd_l9859_01",
      title: "L 98-59 光谱吸收线证认",
      statement:
        "Hα、Na I D 与 Ca II K/H 吸收线轮廓与 M 型矮星分类一致，支持 L 98-59 为低质量宿主星。",
      status: "supported",
      evidence_ids: ["ev_sci_01"],
      metric_ids: ["met_snr"],
    },
  ],
  related_artifact_version_ids: ["artv_c_spec_01", "artv_c_fits_01"],
  source_snapshot_ids: [sourceSnapshotL9859.id],
  input_hash: hash("i_rpt_l9859"),
  output_hash: hash("o_rpt_l9859"),
};

export const lightCurveContent: LightCurveArtifactContent = {
  kind: "light_curve",
  schema_version: "1.0.0",
  light_curve_id: "lc_toi_1233_sector10",
  title: "TOI-1233 (HD 108236) TESS 测光光变曲线与相位折叠",
  object_name: "TOI-1233",
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
  best_period: 3.7952,
  best_power: 0.884,
  false_alarm_probability: 1e-12,
  period_peaks: [
    { period: 3.7952, power: 0.884 },
    { period: 6.2037, power: 0.652 },
    { period: 1.8976, power: 0.412 },
    { period: 14.175, power: 0.325 },
    { period: 19.592, power: 0.285 },
  ],
  points: generateLightCurvePoints(
    720,
    3.7952,
  ) as unknown as LightCurveArtifactContent["points"],
  skill_executions: [skillExecution],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01", "ev_sci_02"],
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
    evidence_ids: ["ev_sci_01"],
  },
  {
    metric_id: "met_f1",
    label: "F1 分数 (Macro F1)",
    value: 0.918,
    unit: null,
    evidence_ids: ["ev_sci_01"],
  },
  {
    metric_id: "met_roc_auc",
    label: "ROC-AUC",
    value: 0.965,
    unit: null,
    evidence_ids: ["ev_sci_01"],
  },
  {
    metric_id: "met_pr_auc",
    label: "PR-AUC",
    value: 0.934,
    unit: null,
    evidence_ids: ["ev_sci_01"],
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
  title: "TESS 凌星信号深度残差网络 (ResNet-Transit) 模型评估",
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
  skill_execution: skillExecution,
  model_binary: {
    content_ref: "/api/fixture/models/transit_classifier_resnet.onnx",
    content_hash: hash("onnx_model_binary_01"),
    media_type: "application/onnx",
  },
  diagnostic_visualization_ids: ["vis_period_radius_diagram"],
  limitations: [
    "模型在超短周期 (< 0.5 d) 及浅凌星 (< 100 ppm) 样本上的真阳性率有所下降。",
    "对于含有强烈脉动变光的宿主星样本需先行应用高通滤波预处理。",
  ],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
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
  title: "ResNet-1D 系外行星凌星信号分类 ONNX 模型包",
  status: "active",
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
  skill_execution: skillExecution,
  limitations: [
    "输入光变曲线必须经过统一标准化 (Median=1.0) 并按 720 维度等距重采样。",
  ],
  source_snapshot_ids: [sourceSnapshot.id],
  evidence_ids: ["ev_sci_01"],
  input_hash: hash("i_model_art"),
  output_hash: hash("o_model_art"),
};

// ---------------------------------------------------------------------------
// Unified Scientific Artifact Reads Array
// ---------------------------------------------------------------------------
const makeScientificRead = (
  artifactId: string,
  artifactVersionId: string,
  projectId: string,
  versionNumber: number,
  content: ScientificArtifactRead["content"],
): ScientificArtifactRead => ({
  artifact_id: artifactId,
  artifact_version_id: artifactVersionId,
  project_id: projectId,
  version_number: versionNumber,
  source_mode: "fixture",
  content_hash: hash(artifactVersionId),
  input_hash: hash(`in_${artifactVersionId}`),
  created_at: T_CREATED,
  supersedes_version_id: null,
  producer_execution: producerExecution,
  source_snapshots: [sourceSnapshot],
  evidence: [
    {
      id: `ev_${artifactVersionId}_01`,
      artifact_version_id: artifactVersionId,
      // The provenance trail of a scientific artifact points at the data
      // source snapshot it was computed from — `source` is the domain's
      // vocabulary for that target; artifact kinds are not target types.
      target_type: "source",
      target_id: sourceSnapshot.id,
      evidence_type: "database_query",
      source_snapshot_id: sourceSnapshot.id,
      extraction_method: "fixture.pipeline",
      confidence: 1,
      locator: { kind: "fixture_record", key: artifactVersionId },
      quote_or_value: "Deterministic scientific pipeline output.",
      paper_id: null,
      created_at: T_CREATED,
    },
  ],
  content,
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
    ),
    makeScientificRead(
      "art_b_chart_01",
      "artv_b_chart_01",
      "proj_toi_transit",
      1,
      chartVisualizationContent,
    ),
    makeScientificRead(
      "art_b_lc_01",
      "artv_b_lc_01",
      "proj_toi_transit",
      1,
      lightCurveContent,
    ),
    makeScientificRead(
      "art_b_modeval_01",
      "artv_b_modeval_01",
      "proj_toi_transit",
      1,
      modelEvaluationContent,
    ),
    makeScientificRead(
      "art_b_model_01",
      "artv_b_model_01",
      "proj_toi_transit",
      1,
      modelArtifactContent,
    ),

    // Project C (L 98-59 Spectroscopy & WWT Scene)
    makeScientificRead(
      "art_c_spec_01",
      "artv_c_spec_01",
      "proj_l9859_spectroscopy",
      1,
      l9859SpectrumContent,
    ),
    makeScientificRead(
      "art_c_fits_01",
      "artv_c_fits_01",
      "proj_l9859_spectroscopy",
      1,
      l9859FitsVisualizationContent,
    ),
    makeScientificRead(
      "art_c_wwt_01",
      "artv_c_wwt_01",
      "proj_l9859_spectroscopy",
      1,
      l9859WwtVisualizationContent,
    ),
    makeScientificRead(
      "art_c_analysis_01",
      "artv_c_analysis_01",
      "proj_l9859_spectroscopy",
      1,
      l9859AnalysisReportContent,
    ),
  ];
