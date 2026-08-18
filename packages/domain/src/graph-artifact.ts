/** Public review projection for the governed Evidence Graph artifact. */

import type { LiteratureRelationReview } from "./literature-artifact";
import type { DomainEntityId } from "./identifiers";
import type { SourceMode } from "./enums";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

export interface GraphVersionReferenceReview {
  readonly artifactId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly kind: string;
  readonly role: string;
  readonly versionNumber: number;
  readonly schemaVersion: string;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
}

export interface GraphNodeReview {
  readonly nodeId: DomainEntityId;
  readonly nodeType: string;
  readonly label: string;
  readonly logicalReference: readonly {
    readonly name: string;
    readonly value: string;
  }[];
  readonly versionBindings: readonly {
    readonly artifactVersionId: DomainEntityId;
    readonly domainObjectId: DomainEntityId;
  }[];
}

export interface GraphDataAggregationReview {
  readonly conflictCount: number;
  readonly declaredNullOutcomeCount: number;
  readonly mappedOutcomeCount: number;
  readonly projectedRowCount: number;
  readonly retainedCandidateCount: number;
  readonly selectedCandidateCount: number;
  readonly unresolvedOutcomeCount: number;
  readonly unselectedCandidateCount: number;
  readonly upstreamEvidenceCount: number;
}

export interface GraphRelationTraceBindingReview {
  readonly relationId: DomainEntityId;
  readonly relationArtifactVersionId: DomainEntityId;
  readonly reasoningTraceId: DomainEntityId;
  readonly relationType: string;
  readonly relationStatus: string | null;
  readonly sourceClaimId: DomainEntityId;
  readonly targetClaimId: DomainEntityId;
  readonly premiseClaimIds: readonly DomainEntityId[];
  readonly traceEvidenceIds: readonly DomainEntityId[];
}

export interface GraphEdgeReview {
  readonly edgeId: DomainEntityId;
  readonly edgeType: string;
  readonly sourceNodeId: DomainEntityId | null;
  readonly targetNodeId: DomainEntityId | null;
  readonly evidenceUseIds: readonly DomainEntityId[];
  readonly dataAggregation: GraphDataAggregationReview | null;
  readonly relationTrace: GraphRelationTraceBindingReview | null;
  readonly relation: LiteratureRelationReview | null;
}

export interface GraphIntegrityReview {
  readonly status: string;
  readonly counts: {
    readonly edgeCount: number;
    readonly evidenceUseCount: number;
    readonly inputVersionCount: number;
    readonly nodeCount: number;
    readonly relationEdgeCount: number;
    readonly sourceSnapshotCount: number;
  };
  readonly findings: readonly {
    readonly stage: string;
    readonly reason: string;
    readonly priority: number;
    readonly path: string;
    readonly message: string;
  }[];
}

export interface GraphArtifactReview {
  readonly kind: "graph";
  readonly graphId: DomainEntityId | null;
  readonly artifactId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly versionNumber: number;
  readonly schemaVersion: string;
  readonly sourceMode: SourceMode;
  readonly contentHash: ContentHash;
  readonly inputHash: ContentHash;
  readonly createdAt: UtcIsoTimestamp;
  readonly nodeCount: number;
  readonly edgeCount: number;
  readonly evidenceUseCount: number;
  readonly inputVersions: readonly GraphVersionReferenceReview[];
  readonly integrity: GraphIntegrityReview;
  readonly layoutStrategy: string;
  readonly scopeSummary: readonly string[];
  readonly taxonomyNodeTypes: readonly string[];
  readonly taxonomyEdgeTypes: readonly string[];
  readonly progressive: {
    readonly chunkCount: number;
    readonly complete: boolean;
  };
  readonly nodes: readonly GraphNodeReview[];
  readonly edges: readonly GraphEdgeReview[];
}
