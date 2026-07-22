/**
 * Research run and run event domain models.
 *
 * Mirror `ResearchRun` and `RunEvent` in the Pydantic `/api/v2` authoring
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
  readonly parentRunId: DomainEntityId | null;
  readonly derivationKind: DerivationKind;
  readonly retryFromStep: DomainEntityId | null;
  readonly cachePolicy: CachePolicy;
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
  readonly eventType: DomainEntityId;
  readonly stepKey: DomainEntityId | null;
  readonly progress: number | null;
  readonly publicMessage: string;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly occurredAt: UtcIsoTimestamp;
}

/**
 * Validate the derivation invariants of a run.
 *
 * Mirrors the `model_validator` on `ResearchRun`: original runs must not carry
 * a parent; derived runs must; `retry_from_step` is only valid for retries;
 * completed runs must report full progress.
 */
export function validateRunDerivationInvariants(
  run: ResearchRun,
): readonly string[] {
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
