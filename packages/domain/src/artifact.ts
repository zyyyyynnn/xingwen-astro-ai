/**
 * Research artifact identity and immutable publication metadata.
 *
 * Kind-specific content is validated by its producer and dedicated read
 * contract. The generic ArtifactVersion projection therefore preserves the
 * persisted JSON payload without introducing a second content authority in
 * the frontend domain package.
 */

import type { ArtifactKind, SourceMode } from "./enums";
import type { Evidence } from "./evidence";
import type { DomainEntityId } from "./identifiers";
import type { PublicArtifactPresentation } from "./share-snapshot";
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

/**
 * Immutable JSON payload stored in an ArtifactVersion.
 *
 * The API validates this payload at the producer/admission boundary. Generic
 * consumers must keep the JSON intact and use the owning read contract for
 * kind-specific interpretation.
 */
export type ArtifactVersionContent = Readonly<Record<string, unknown>>;

export interface ArtifactVersion {
  readonly id: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly createdByRunId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: SemanticVersion;
  readonly content: ArtifactVersionContent;
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
 * Version identity and provenance without the scientific `content` payload.
 *
 * Generic workspace reads (panel slots, Share wiring, hash display) only need
 * this projection. Rich kind-specific content must be read through its
 * dedicated repository instead of being reconstructed from generic metadata.
 */
export interface ArtifactVersionSummary {
  readonly id: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: SemanticVersion;
  readonly contentHash: ContentHash;
  readonly sourceMode: SourceMode;
  readonly supersedesVersionId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

export interface ArtifactVersionMetadata extends ArtifactVersionSummary {
  readonly projectId: DomainEntityId;
  readonly createdByRunId: DomainEntityId;
  readonly inputHash: ContentHash;
  readonly producer: ProducerReference;
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  /** Immutable Evidence embedded by the ArtifactVersion detail read. */
  readonly evidence?: readonly Evidence[];
  /** Canonical positive-contract presentation shared by private and public UI. */
  readonly presentation: PublicArtifactPresentation;
}
