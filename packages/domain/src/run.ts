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
import type { UtcIsoTimestamp } from "./value-types";

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
  readonly stepKey: DomainEntityId;
  readonly question: string;
  readonly options: readonly string[];
  readonly createdAt: UtcIsoTimestamp;
  readonly selectedOption: string | null;
  readonly freeText: string | null;
  readonly decidedAt: UtcIsoTimestamp | null;
}

export interface RunCheckpointDecisionRequest {
  readonly selectedOption: string;
  readonly freeText?: string | null;
}

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
