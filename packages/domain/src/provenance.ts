/**
 * Provenance state — the baseline source/version/coverage summary attached to
 * runs, artifact versions and fixture bundles.
 *
 * Per Issue Frontend Domain and Fixture Boundary the frontend establishes the *base* provenance state:
 * execution mode, source mode, schema version, retrieved-at and evidence
 * completeness. Cache-selection reasoning and revision derivation details are
 * deferred to Evidence Provenance and are intentionally absent here.
 */

import type { ExecutionMode, SourceMode } from "./enums";
import type { SemanticVersion, UtcIsoTimestamp } from "./value-types";

export interface EvidenceCompleteness {
  /** Number of located Evidence records for the target scope. */
  readonly covered: number;
  /** Total Evidence records expected for full coverage. */
  readonly total: number;
}

/** Ratio of covered/total in `[0, 1]`; full coverage when total is zero. */
export function evidenceCompletenessRatio(
  completeness: EvidenceCompleteness,
): number {
  return completeness.total === 0
    ? 1
    : completeness.covered / completeness.total;
}

export interface ProvenanceState {
  readonly executionMode: ExecutionMode;
  readonly sourceMode: SourceMode;
  readonly schemaVersion: SemanticVersion;
  readonly retrievedAt: UtcIsoTimestamp;
  readonly evidenceCompleteness: EvidenceCompleteness;
  /**
   * Human-readable provenance note. For fixtures this carries the scenario
   * identifier and Demo Replay disclaimer; for live data it may be null.
   */
  readonly note: string | null;
}
