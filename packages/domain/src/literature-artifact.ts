/**
 * Review projections for the public literature artifacts.  These types keep
 * the admitted claim/relation/trace semantics while leaving transport DTOs
 * and raw model output behind the data-access boundary.
 */

import type { DataArtifactSourceSnapshot } from "./data-artifact";
import type { DomainEntityId } from "./identifiers";
import type { SourceMode } from "./enums";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

export interface LiteratureArtifactVersionReview {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: string;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly outputHash: ContentHash | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly sourceSnapshots: readonly DataArtifactSourceSnapshot[];
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface LiteratureClaimReferenceReview {
  readonly claimId: DomainEntityId;
  readonly text: string;
  readonly normalizedText: string;
  readonly status: string;
  readonly claimType: string;
  readonly polarity: string;
  readonly paperId: DomainEntityId | null;
}

export interface LiteratureClaimReview extends LiteratureClaimReferenceReview {
  readonly objects: readonly string[];
  readonly scope: readonly string[];
  readonly conditions: readonly string[];
  readonly qualifiers: readonly string[];
  readonly limitations: readonly string[];
  readonly metric: string | null;
  readonly unit: string | null;
  readonly uncertainty: string | null;
  readonly comparisonBasis: string | null;
  readonly sourceStatementId: DomainEntityId | null;
  readonly sourceSummaryId: DomainEntityId | null;
  readonly sourcePaperSummaryArtifactVersionId: DomainEntityId | null;
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly failureStage: string | null;
  readonly rejectionReason: string | null;
}

export interface LiteratureClaimsArtifactReview extends LiteratureArtifactVersionReview {
  readonly kind: "literature_claims";
  readonly claims: readonly LiteratureClaimReview[];
}

export interface LiteratureRelationComparabilityReview {
  readonly metricBasis: string;
  readonly metricStatus: string;
  readonly objectBasis: string;
  readonly objectStatus: string;
  readonly unitBasis: string;
  readonly unitStatus: string;
}

export interface LiteratureRelationDirectionReview {
  readonly basis: string;
  readonly sourceClaimId: DomainEntityId | null;
  readonly targetClaimId: DomainEntityId | null;
}

export interface LiteratureRelationConfidenceReview {
  readonly score: number | null;
  readonly status: string;
  readonly decision: string;
  readonly acceptanceThreshold: number;
}

export interface LiteratureReasoningTraceStepReview {
  readonly order: number;
  readonly operation: string;
  readonly statement: string;
  readonly claimIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface LiteratureReasoningTraceReview {
  readonly traceId: DomainEntityId;
  readonly relationId: DomainEntityId | null;
  readonly relationStatus: string;
  readonly conclusion: string;
  readonly premiseClaimIds: readonly DomainEntityId[];
  readonly conditions: readonly string[];
  readonly conflicts: readonly string[];
  readonly limitations: readonly string[];
  readonly steps: readonly LiteratureReasoningTraceStepReview[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly protocolVersion: string;
}

export interface LiteratureRelationReview {
  readonly relationId: DomainEntityId;
  readonly pairId: string;
  readonly relationType: string;
  readonly status: string;
  readonly sourceClaimId: DomainEntityId | null;
  readonly targetClaimId: DomainEntityId | null;
  readonly reasoningTraceId: DomainEntityId | null;
  readonly graphEligible: boolean;
  readonly direction: LiteratureRelationDirectionReview;
  readonly comparability: LiteratureRelationComparabilityReview;
  readonly conditions: readonly string[];
  readonly conditionConflicts: readonly string[];
  readonly conditionUncertainties: readonly string[];
  readonly confidence: LiteratureRelationConfidenceReview | null;
  readonly evidenceIds: readonly DomainEntityId[];
  readonly sourceSnapshotIds: readonly DomainEntityId[];
  readonly sourceClaim: LiteratureClaimReferenceReview | null;
  readonly targetClaim: LiteratureClaimReferenceReview | null;
  readonly reasoningTrace: LiteratureReasoningTraceReview | null;
  readonly failureStage: string | null;
  readonly rejectionReason: string | null;
}

export interface LiteratureRelationsArtifactReview extends LiteratureArtifactVersionReview {
  readonly kind: "literature_relations";
  readonly relations: readonly LiteratureRelationReview[];
}

export interface ReasoningTracesArtifactReview extends LiteratureArtifactVersionReview {
  readonly kind: "reasoning_traces";
  readonly traces: readonly LiteratureReasoningTraceReview[];
}

export type LiteratureArtifactReview =
  | LiteratureClaimsArtifactReview
  | LiteratureRelationsArtifactReview
  | ReasoningTracesArtifactReview;
