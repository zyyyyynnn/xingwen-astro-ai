/**
 * Evidence domain model and locator discriminated union.
 *
 * The entity shape follows [Data Model §10](../../docs/architecture/DATA_MODEL.md).
 * Evidence is a frontend domain entity without a standalone `/api` transport
 * schema; it is projected from ArtifactVersion evidence ids and source
 * snapshots. Repository adapters (including the fixture adapter) produce
 * Evidence instances directly in domain form.
 *
 * The `evidenceType` enum reuses the canonical values defined by the
 * `EvidenceType` contract so the vocabulary stays consistent across layers.
 */

import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";

export const EVIDENCE_TYPES = [
  "database_query",
  "data_transformation",
  "crossmatch_decision",
  "paper_search",
  "paper_metadata",
  "paper_text",
  "model_extraction",
  "reasoning_trace",
  "user_feedback",
  "cache_record",
  "service_response",
  "input_snapshot",
  "computation",
] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

/**
 * The kind of domain object an Evidence record locates. This is the closed
 * vocabulary emitted by persisted Artifact provenance.
 */
export const EVIDENCE_TARGET_TYPES = [
  "field",
  "canonical_field",
  "source",
  "paper",
  "paper_candidate",
  "paper_summary",
  "claim",
  "relation",
  "reasoning_trace",
  "graph_edge",
  "crossmatch",
  "result_block",
  "metric",
  "visualization",
  "evaluation",
  "model",
] as const;
export type EvidenceTargetType = (typeof EVIDENCE_TARGET_TYPES)[number];

export function isEvidenceTargetType(
  value: unknown,
): value is EvidenceTargetType {
  return (EVIDENCE_TARGET_TYPES as readonly unknown[]).includes(value);
}

export function isEvidenceType(value: unknown): value is EvidenceType {
  return (EVIDENCE_TYPES as readonly unknown[]).includes(value);
}

/** Discriminator for the {@link EvidenceLocator} union. */
export const LOCATOR_KINDS = [
  "database_cell",
  "paper_text",
  "model_extraction",
  "reasoning_trace",
  "scientific_computation",
] as const;
export type LocatorKind = (typeof LOCATOR_KINDS)[number];

export interface DatabaseCellLocator {
  readonly kind: "database_cell";
  readonly queryHash: string;
  readonly rowKey: string;
  readonly field: DomainEntityId;
}

export interface PaperTextLocator {
  readonly kind: "paper_text";
  readonly section: string;
  readonly page: number | null;
  readonly paragraph: number | null;
  readonly range: string | null;
}

export interface ModelExtractionLocator {
  readonly kind: "model_extraction";
  readonly inputEvidenceId: DomainEntityId;
  readonly promptName: string;
  readonly modelVersion: string;
}

export interface ReasoningTraceLocator {
  readonly kind: "reasoning_trace";
  readonly relationId: DomainEntityId;
  readonly stepKey: DomainEntityId;
}

export interface ScientificComputationLocator {
  readonly kind: "scientific_computation";
  readonly taskId: DomainEntityId;
  readonly skillId: DomainEntityId;
  readonly outputHash: string;
  readonly upstreamEvidenceIds: readonly DomainEntityId[];
}

export type EvidenceLocator =
  | DatabaseCellLocator
  | PaperTextLocator
  | ModelExtractionLocator
  | ReasoningTraceLocator
  | ScientificComputationLocator;

export interface Evidence {
  readonly id: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly targetType: EvidenceTargetType;
  readonly targetId: DomainEntityId;
  readonly evidenceType: EvidenceType;
  readonly sourceSnapshotId: DomainEntityId | null;
  readonly paperId: DomainEntityId | null;
  readonly locator: EvidenceLocator | null;
  readonly quoteOrValue: string | null;
  readonly extractionMethod: string;
  readonly confidence: number;
  readonly createdAt: UtcIsoTimestamp;
}
