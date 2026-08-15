/**
 * Review projections for the typed data artifacts published by the data
 * pipeline.  Transport DTOs stay in `@xingwen/contracts` and are mapped by
 * `@xingwen/data-access`; this module only contains the stable domain shape
 * consumed by the adapter and workspace renderers.
 */

import type { DomainEntityId } from "./identifiers";
import type { SourceMode } from "./enums";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

export type DataArtifactKind =
  "dataset" | "field_dictionary" | "source_collection";

export interface DataArtifactSourceSnapshot {
  readonly id: DomainEntityId;
  readonly sourceId: DomainEntityId;
  readonly sourceType: string;
  readonly retrievedAt: UtcIsoTimestamp;
  readonly queryHash: ContentHash;
  readonly contentHash: ContentHash;
  readonly sourceVersionOrEtag: string | null;
  readonly licenseNote: string;
}

export interface DataArtifactQualityProjection {
  readonly status: "pass" | "unknown";
  readonly resultId: DomainEntityId | null;
}

export interface DataArtifactReviewBase {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly schemaVersion: string;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly sourceSnapshots: readonly DataArtifactSourceSnapshot[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly quality: DataArtifactQualityProjection;
}

export interface DataArtifactFieldSourceAlias {
  readonly sourceId: DomainEntityId;
  readonly sourceTable: string;
  readonly rawField: string;
  readonly sourceUnit: string;
  readonly priority: number;
}

export interface DataArtifactFieldDefinition {
  readonly fieldId: DomainEntityId;
  readonly labelEn: string;
  readonly meaningZh: string;
  readonly description: string;
  readonly dataType: string;
  readonly canonicalUnit: string;
  readonly objectType: string;
  readonly required: boolean;
  readonly nullable: boolean;
  readonly crossmatchKey: boolean;
  readonly objectIdentityKey: boolean;
  readonly sourceAliases: readonly DataArtifactFieldSourceAlias[];
  readonly sourcePriority: readonly DomainEntityId[];
}

export type DataArtifactCellStatus = "mapped" | "declared_null" | "unresolved";

export interface DatasetCellReview {
  readonly canonicalFieldId: DomainEntityId;
  readonly status: DataArtifactCellStatus;
  readonly value: string | null;
  readonly unit: string | null;
  readonly reason: string | null;
  readonly conflictIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface DatasetRowReview {
  readonly rowId: string;
  readonly entityLevel: string;
  readonly alignmentStatus: string;
  readonly identity: string;
  readonly cells: readonly DatasetCellReview[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface DatasetArtifactReview extends DataArtifactReviewBase {
  readonly kind: "dataset";
  readonly candidateId: DomainEntityId | null;
  readonly requestedFields: readonly DomainEntityId[];
  readonly columns: readonly DataArtifactFieldDefinition[];
  readonly rows: readonly DatasetRowReview[];
  readonly rowCount: number;
  readonly fieldCount: number;
  readonly conflictCount: number;
}

export interface FieldDictionaryArtifactReview extends DataArtifactReviewBase {
  readonly kind: "field_dictionary";
  readonly candidateId: DomainEntityId | null;
  readonly requestedFields: readonly DomainEntityId[];
  readonly fieldDefinitions: readonly DataArtifactFieldDefinition[];
}

export interface SourceCollectionMemberReview {
  readonly sourceId: DomainEntityId | null;
  readonly sourceSnapshotId: DomainEntityId;
  readonly sourceSnapshotContentHash: ContentHash;
  readonly side: string;
  readonly dataLevel: string;
  readonly sourceMode: SourceMode;
  readonly rawRecordCount: number | null;
  readonly completionStatus: string;
  readonly licenseNote: string;
}

export interface SourceCollectionArtifactReview extends DataArtifactReviewBase {
  readonly kind: "source_collection";
  readonly candidateId: DomainEntityId | null;
  readonly members: readonly SourceCollectionMemberReview[];
  readonly alignedRecordCount: number;
  readonly conflictRecordCount: number;
  readonly inconclusiveRecordCount: number;
  readonly reviewRequiredRecordCount: number;
}

export type DataArtifactReview =
  | DatasetArtifactReview
  | FieldDictionaryArtifactReview
  | SourceCollectionArtifactReview;
