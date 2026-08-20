/**
 * Research run and run event domain models.
 *
 * Mirror `ResearchRun` and `RunEvent` in the Pydantic `/api` authoring
 * source, including the derivation cross-field invariants.
 */

import type {
  CachePolicy,
  DerivationKind,
  ExecutionMode,
  RunStatus,
} from "./enums";
import type { DomainEntityId } from "./identifiers";
import type {
  ContentHash,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";

export interface ResearchRun {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly contractId: DomainEntityId;
  readonly executionMode: ExecutionMode;
  readonly status: RunStatus;
  readonly progress: number;
  readonly revision: number;
  readonly parentRunId: DomainEntityId | null;
  readonly derivationKind: DerivationKind;
  readonly retryFromStep: DomainEntityId | null;
  readonly cachePolicy: CachePolicy;
  readonly revisionPlanId?: DomainEntityId | null;
  readonly feedbackIds?: readonly DomainEntityId[];
  readonly recomputeSteps?: readonly DomainEntityId[];
  readonly reusedArtifactVersionIds?: readonly DomainEntityId[];
  readonly startedAt: UtcIsoTimestamp | null;
  readonly finishedAt: UtcIsoTimestamp | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
  readonly latestEventSequence: number;
  readonly failureCode: string | null;
  readonly failureSummary: string | null;
}

export interface RunEvent {
  readonly runId: DomainEntityId;
  readonly sequence: number;
  readonly activityId: string;
  readonly activityKind:
    | "reasoning"
    | "tool"
    | "observation"
    | "status"
    | "artifact"
    | "retry"
    | "error"
    | "completion";
  readonly activityPhase:
    "queued" | "streaming" | "running" | "completed" | "failed" | "retrying";
  readonly activityName: string;
  readonly stepKey: DomainEntityId | null;
  readonly progress: number | null;
  readonly content: string;
  readonly details: Readonly<Record<string, unknown>>;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly occurredAt: UtcIsoTimestamp;
}

export interface RunCheckpoint {
  readonly id: DomainEntityId;
  readonly runId: DomainEntityId;
  readonly runRevision: number;
  readonly stepKey: DomainEntityId;
  readonly question: string;
  readonly options: readonly string[];
  readonly kind: "choice" | "scientific_repair";
  readonly repairContext: RepairCheckpointContext | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly selectedOption: string | null;
  readonly freeText: string | null;
  readonly repairDecisions: readonly RepairDecisionInput[];
  readonly repairOutcome: RepairOutcome | null;
  readonly decidedAt: UtcIsoTimestamp | null;
}

export type RepairAction = "accepted" | "rejected" | "keep_unresolved";

export interface RepairEvidenceFact {
  readonly evidenceId: DomainEntityId;
  readonly leftCandidateId: DomainEntityId;
  readonly rightCandidateId: DomainEntityId;
  readonly confidence: number;
  readonly summary: string;
}

export interface RepairDefect {
  readonly defectId: DomainEntityId;
  readonly logicalMatchKey: ContentHash;
  readonly conflictCode: string;
  readonly leftCandidateIds: readonly DomainEntityId[];
  readonly rightCandidateIds: readonly DomainEntityId[];
  readonly evidence: readonly RepairEvidenceFact[];
}

export interface RepairRuleSetReference {
  readonly ruleSetId: DomainEntityId;
  readonly ruleSetVersion: SemanticVersion;
  readonly ruleSetContentHash: ContentHash;
  readonly allowedActions: readonly RepairAction[];
}

export interface RepairCheckpointContext {
  readonly ruleSet: RepairRuleSetReference;
  readonly sourceInputHash: ContentHash;
  readonly beforeOutputHash: ContentHash;
  readonly defects: readonly RepairDefect[];
}

export interface RepairDecisionInput {
  readonly defectId: DomainEntityId;
  readonly action: RepairAction;
  readonly rationale: string;
}

export interface RepairOutcome {
  readonly afterOutputHash: ContentHash;
  readonly qualityResultHash: ContentHash;
  readonly beforeEvidenceIds: readonly DomainEntityId[];
  readonly afterEvidenceIds: readonly DomainEntityId[];
  readonly resolvedDefectIds: readonly DomainEntityId[];
  readonly unresolvedDefectIds: readonly DomainEntityId[];
  readonly status: "revalidated" | "false_repair";
}

export interface CheckpointDecisionIdentity {
  readonly checkpointId: DomainEntityId;
  readonly expectedRunRevision: number;
}

export interface ChoiceCheckpointDecisionRequest extends CheckpointDecisionIdentity {
  readonly selectedOption: string;
  readonly freeText?: string | null;
}

export interface RepairCheckpointDecisionRequest extends CheckpointDecisionIdentity {
  readonly repairDecisions: readonly RepairDecisionInput[];
}

export type RunCheckpointDecisionRequest =
  ChoiceCheckpointDecisionRequest | RepairCheckpointDecisionRequest;

/**
 * Validate stable derivation and terminal-progress invariants of a run.
 */
export function validateRunInvariants(run: ResearchRun): readonly string[] {
  const violations: string[] = [];

  if (run.derivationKind === "original" && run.parentRunId !== null) {
    violations.push("original run must not have parent_run_id");
  }
  if (run.derivationKind !== "original" && run.parentRunId === null) {
    violations.push("derived run must have parent_run_id");
  }
  if (run.retryFromStep !== null && run.derivationKind !== "retry") {
    violations.push("retry_from_step is only valid for retry runs");
  }
  if (run.status === "completed" && run.progress !== 100) {
    violations.push("completed run must have progress 100");
  }

  return violations;
}
