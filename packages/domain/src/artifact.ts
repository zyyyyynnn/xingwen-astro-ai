/**
 * Research artifact and versioned artifact content domain models.
 *
 * Mirror `ResearchArtifact`, `ArtifactVersion`, `ProducerReference` and the
 * discriminated `ArtifactContent` union in the Pydantic `/api/v2` authoring
 * source.
 */

import type { ArtifactKind, ExportFormat, SourceMode } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type {
  ContentHash,
  NonEmptyString,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";

export interface ResearchArtifact {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly kind: ArtifactKind;
  readonly title: NonEmptyString;
  readonly logicalKey: DomainEntityId;
  readonly createdAt: UtcIsoTimestamp;
  readonly latestVersionId: DomainEntityId | null;
}

export type ProducerType = "pipeline" | "model" | "algorithm";

export interface ProducerReference {
  readonly type: ProducerType;
  readonly name: NonEmptyString;
  readonly version: NonEmptyString;
  readonly modelName: string | null;
  readonly promptName: string | null;
  readonly promptVersion: string | null;
  readonly parametersHash: ContentHash | null;
}

/** A single cell value in a dataset artifact row. */
export type DataCell = string | number | boolean | null;

export interface DatasetArtifactContent {
  readonly kind: "dataset";
  readonly fieldIds: readonly DomainEntityId[];
  readonly rows: readonly Record<string, DataCell>[];
}

export interface FieldDictionaryArtifactContent {
  readonly kind: "field_dictionary";
  readonly fieldIds: readonly DomainEntityId[];
}

export interface SourceCollectionArtifactContent {
  readonly kind: "source_collection";
  readonly sourceSnapshotIds: readonly DomainEntityId[];
}

export interface PaperCollectionArtifactContent {
  readonly kind: "paper_collection";
  readonly paperIds: readonly DomainEntityId[];
}

export interface PaperSummaryArtifactContent {
  readonly kind: "paper_summary";
  readonly paperId: DomainEntityId;
  readonly summaryId: DomainEntityId;
}

export interface LiteratureClaimsArtifactContent {
  readonly kind: "literature_claims";
  readonly claimIds: readonly DomainEntityId[];
}

export interface LiteratureRelationsArtifactContent {
  readonly kind: "literature_relations";
  readonly relationIds: readonly DomainEntityId[];
}

export interface ReasoningTracesArtifactContent {
  readonly kind: "reasoning_traces";
  readonly reasoningTraceIds: readonly DomainEntityId[];
}

export interface GraphArtifactContent {
  readonly kind: "graph";
  readonly nodeIds: readonly DomainEntityId[];
  readonly edgeIds: readonly DomainEntityId[];
}

export interface ExportArtifactContent {
  readonly kind: "export";
  readonly format: ExportFormat;
  readonly artifactVersionIds: readonly DomainEntityId[];
}

/**
 * Discriminated union of all artifact content variants. The `kind` field is
 * the discriminator and matches the `ArtifactKind` enum.
 */
export type ArtifactContent =
  | DatasetArtifactContent
  | FieldDictionaryArtifactContent
  | SourceCollectionArtifactContent
  | PaperCollectionArtifactContent
  | PaperSummaryArtifactContent
  | LiteratureClaimsArtifactContent
  | LiteratureRelationsArtifactContent
  | ReasoningTracesArtifactContent
  | GraphArtifactContent
  | ExportArtifactContent;

export interface ArtifactVersion {
  readonly id: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly createdByRunId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: SemanticVersion;
  readonly content: ArtifactContent;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly sourceMode: SourceMode;
  readonly producer: ProducerReference;
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly supersedesVersionId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

/**
 * Validate dataset content invariants: unique declared fields and no row keys
 * outside the declared set. Mirrors the `DatasetArtifactContent` validator.
 */
export function validateDatasetContentInvariants(
  content: DatasetArtifactContent,
): readonly string[] {
  const violations: string[] = [];

  if (content.fieldIds.length !== new Set(content.fieldIds).size) {
    violations.push("field_ids must not contain duplicates");
  }

  const declared = new Set(content.fieldIds);
  const unknown = new Set<string>();
  for (const row of content.rows) {
    for (const key of Object.keys(row)) {
      if (!declared.has(key as DomainEntityId)) {
        unknown.add(key);
      }
    }
  }
  if (unknown.size > 0) {
    violations.push(
      `dataset rows contain undeclared field(s): ${[...unknown].sort().join(", ")}`,
    );
  }

  return violations;
}
