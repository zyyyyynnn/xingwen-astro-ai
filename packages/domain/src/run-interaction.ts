import type { DomainEntityId } from "./identifiers";
import type { ResearchRun } from "./run";
import type { UtcIsoTimestamp } from "./value-types";

/** The input kinds the server can accept at a suspended run checkpoint. */
export type RunCheckpointInputType = "pdf" | "text";

export interface RunCheckpoint {
  readonly code: string;
  readonly id: DomainEntityId;
  readonly openedAt: UtcIsoTimestamp;
  readonly publicMessage: string;
  readonly requiredInputTypes: readonly RunCheckpointInputType[];
  readonly resolutionRunId: DomainEntityId | null;
  readonly resolvedAt: UtcIsoTimestamp | null;
  readonly runId: DomainEntityId;
  readonly status: "open" | "resolved" | "cancelled";
  readonly stepKey: string;
}

export type RunDecisionKind = "resume" | "retry" | "cancel";

export interface RunDecision {
  readonly childRunId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly decision: RunDecisionKind;
  readonly id: DomainEntityId;
  readonly inputIds: readonly DomainEntityId[];
  readonly parentRunId: DomainEntityId;
  readonly stepKey: string;
}

export interface RunDecisionResult {
  readonly decision: RunDecision;
  readonly run: ResearchRun;
}
