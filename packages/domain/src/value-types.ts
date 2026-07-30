/**
 * Domain value types.
 *
 * These are documentation-grade aliases over `string`. They make the domain
 * model self-describing without introducing runtime validators inside the
 * framework-free domain boundary. Repository adapters validate wire payloads
 * before producing these values.
 */

/**
 * ISO 8601 UTC timestamp string, e.g. `2026-07-21T08:00:00Z`.
 *
 * The backend requires aware UTC datetimes; the domain mirrors that contract.
 */
export type UtcIsoTimestamp = string;

/**
 * SHA-256 content hash in the canonical `sha256:<64 hex lowercase>` form.
 */
export type ContentHash = string;

/**
 * Semantic version string matching `^[1-9]\d*\.\d+\.\d+$` (e.g. `2.0.0`).
 */
export type SemanticVersion = string;

/**
 * Frozen main research case. The contract currently allows a single case key;
 * the domain models it as a literal so downstream code cannot drift.
 */
export type CaseKey = "exoplanet_host_star";

export const CASE_KEY: CaseKey = "exoplanet_host_star";

/** Contract schema version surfaced to consumers (matches `/api`). */
export const CONTRACT_VERSION: SemanticVersion = "2.0.0";

/**
 * Non-empty trimmed string. The backend enforces `min_length=1` after
 * stripping whitespace; adapters are responsible for trimming.
 */
export type NonEmptyString = string;

/**
 * Research goal string (4–500 characters after trimming).
 */
export type ResearchGoal = string;
