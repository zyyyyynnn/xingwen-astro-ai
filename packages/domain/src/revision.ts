import type { ArtifactKind } from "./enums";
import type { DomainEntityId } from "./identifiers";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

export type FeedbackTargetType =
  | "artifact"
  | "artifact_version"
  | "dataset_field"
  | "dataset_row"
  | "paper"
  | "paper_summary"
  | "claim"
  | "relation"
  | "trace"
  | "graph_node"
  | "graph_edge";

export type FeedbackCategory =
  | "correction"
  | "omission"
  | "evidence"
  | "quality"
  | "interpretation"
  | "adjudication";

export type RelationAdjudicationDecision = "accepted" | "rejected";

export interface UserFeedback {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly baselineArtifactVersionId: DomainEntityId;
  readonly baselineVersionNumber: number;
  readonly baselineContentHash: ContentHash;
  readonly targetType: FeedbackTargetType;
  readonly targetId: DomainEntityId;
  readonly targetLocator: Readonly<Record<string, unknown>>;
  readonly category: FeedbackCategory;
  readonly adjudicationDecision: RelationAdjudicationDecision | null;
  readonly summary: string;
  readonly requestedChange: string;
  readonly createdAt: UtcIsoTimestamp;
}

export interface RevisionVersionDecision {
  readonly artifactVersionId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly artifactKind: ArtifactKind;
  readonly versionNumber: number;
  readonly decision: "recompute" | "reuse";
  readonly stepKey: string | null;
}

export interface RevisionConflict {
  readonly code: string;
  readonly artifactVersionId: DomainEntityId | null;
  readonly detail: string;
}

export interface RevisionPlan {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly parentRunId: DomainEntityId;
  readonly parentRunRevision: number;
  readonly contractId: DomainEntityId;
  readonly version: number;
  readonly status: "proposed" | "confirmed";
  readonly feedbackIds: readonly DomainEntityId[];
  readonly baselineArtifactVersionIds: readonly DomainEntityId[];
  readonly affectedArtifactVersionIds: readonly DomainEntityId[];
  readonly reusableArtifactVersionIds: readonly DomainEntityId[];
  readonly recomputeSteps: readonly string[];
  readonly versionDecisions: readonly RevisionVersionDecision[];
  readonly conflicts: readonly RevisionConflict[];
  readonly confirmedRunId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
}

export type RevisionFeedbackIntent =
  | {
      readonly kind: "artifact_correction";
      readonly artifactId: DomainEntityId;
      readonly artifactVersionId: DomainEntityId;
      readonly expectedVersionNumber: number;
      readonly summary: string;
      readonly requestedChange: string;
      readonly idempotencyKey: string;
    }
  | {
      readonly kind: "relation_correction";
      readonly artifactId: DomainEntityId;
      readonly artifactVersionId: DomainEntityId;
      readonly relationId: DomainEntityId;
      readonly expectedVersionNumber: number;
      readonly summary: string;
      readonly requestedChange: string;
      readonly idempotencyKey: string;
    }
  | {
      readonly kind: "trace_correction";
      readonly artifactId: DomainEntityId;
      readonly artifactVersionId: DomainEntityId;
      readonly traceId: DomainEntityId;
      readonly expectedVersionNumber: number;
      readonly summary: string;
      readonly requestedChange: string;
      readonly idempotencyKey: string;
    }
  | {
      readonly kind: "relation_adjudication";
      readonly artifactId: DomainEntityId;
      readonly artifactVersionId: DomainEntityId;
      readonly relationId: DomainEntityId;
      readonly decision: RelationAdjudicationDecision;
      readonly expectedVersionNumber: number;
      readonly summary: string;
      readonly requestedChange: string;
      readonly idempotencyKey: string;
    };
