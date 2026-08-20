/**
 * Domain enumerations.
 *
 * Each enum is exposed as a readonly tuple (for iteration / validation) and a
 * derived union type (for exhaustive switch checking). The values mirror the
 * Pydantic `/api` authoring source byte-for-byte so adapters can map wire
 * payloads without translation.
 */

export const EXECUTION_MODES = ["demo_replay", "live"] as const;
export type ExecutionMode = (typeof EXECUTION_MODES)[number];

export function isExecutionMode(value: unknown): value is ExecutionMode {
  return (
    typeof value === "string" &&
    (EXECUTION_MODES as readonly string[]).includes(value)
  );
}

export const SOURCE_MODES = ["fixture", "live", "cached"] as const;
export type SourceMode = (typeof SOURCE_MODES)[number];

export function isSourceMode(value: unknown): value is SourceMode {
  return (
    typeof value === "string" &&
    (SOURCE_MODES as readonly string[]).includes(value)
  );
}

export const DERIVATION_KINDS = [
  "original",
  "retry",
  "revision",
  "fork",
] as const;
export type DerivationKind = (typeof DERIVATION_KINDS)[number];

export const RUN_STATUSES = [
  "queued",
  "planning",
  "fetching_data",
  "cleaning_data",
  "acquiring_observations",
  "analyzing_data",
  "training_models",
  "building_visualizations",
  "searching_papers",
  "summarizing_papers",
  "reasoning_literature",
  "building_graph",
  "waiting_for_input",
  "completed",
  "failed",
  "cancelled",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

const TERMINAL_RUN_STATUSES: readonly RunStatus[] = [
  "completed",
  "failed",
  "cancelled",
];

export function isRunStatus(value: unknown): value is RunStatus {
  return (
    typeof value === "string" &&
    (RUN_STATUSES as readonly string[]).includes(value)
  );
}

export function isTerminalRunStatus(status: RunStatus): boolean {
  return (TERMINAL_RUN_STATUSES as readonly string[]).includes(status);
}

export const ARTIFACT_KINDS = [
  "dataset",
  "field_dictionary",
  "source_collection",
  "analysis_report",
  "visualization",
  "spectrum",
  "light_curve",
  "model_evaluation",
  "model_artifact",
  "paper_collection",
  "paper_summary",
  "literature_claims",
  "literature_relations",
  "graph",
  "export",
] as const;
export type ArtifactKind = (typeof ARTIFACT_KINDS)[number];

export function isArtifactKind(value: unknown): value is ArtifactKind {
  return (
    typeof value === "string" &&
    (ARTIFACT_KINDS as readonly string[]).includes(value)
  );
}

export const CONTRACT_DRAFT_STATUSES = [
  "draft",
  "confirmed",
  "expired",
] as const;
export type ContractDraftStatus = (typeof CONTRACT_DRAFT_STATUSES)[number];

export const UNIT_POLICIES = ["canonical"] as const;
export type UnitPolicy = (typeof UNIT_POLICIES)[number];

export const CACHE_POLICIES = [
  "disabled",
  "fallback_on_recoverable_failure",
] as const;
export type CachePolicy = (typeof CACHE_POLICIES)[number];

export const SESSION_STATUSES = ["active", "expired", "revoked"] as const;
export type SessionStatus = (typeof SESSION_STATUSES)[number];

export const WORKSPACE_PANEL_TYPES = ["atlas", "observatory"] as const;
export type WorkspacePanelType = (typeof WORKSPACE_PANEL_TYPES)[number];

export const SHARE_STATUSES = ["active", "expired", "revoked"] as const;
export type ShareStatus = (typeof SHARE_STATUSES)[number];

export const SHARE_REDACTION_POLICIES = ["public_metadata_only"] as const;
export type ShareRedactionPolicy = (typeof SHARE_REDACTION_POLICIES)[number];

/**
 * Export artifact format values (subset of the contract export content).
 */
export const EXPORT_FORMATS = ["csv", "json", "provenance_report"] as const;
export type ExportFormat = (typeof EXPORT_FORMATS)[number];

export const SCIENTIFIC_SKILL_IDS = [
  "catalog_crossmatch",
  "data_profile",
  "statistical_analysis",
  "correlation_analysis",
  "clustering_analysis",
  "anomaly_detection",
  "chart_visualization",
  "simbad_lookup",
  "skyview_fits",
  "ephemeris",
  "celestial_events",
  "gaia_cone_search",
  "vizier_tap",
  "fits_image_analysis",
  "spectrum_analysis",
  "spectrum_acquisition",
  "light_curve_analysis",
  "light_curve_acquisition",
  "tabular_machine_learning",
  "time_series_classification",
  "time_series_forecast",
  "image_classification",
  "model_inference",
  "wwt_scene",
] as const;
export type ScientificSkillId = (typeof SCIENTIFIC_SKILL_IDS)[number];

export function isScientificSkillId(
  value: unknown,
): value is ScientificSkillId {
  return (
    typeof value === "string" &&
    (SCIENTIFIC_SKILL_IDS as readonly string[]).includes(value)
  );
}
